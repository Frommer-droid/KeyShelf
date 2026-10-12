"""Local TLS transport. Vault operations are dispatched to the Qt owner thread."""

import base64
import ctypes
import hashlib
import ipaddress
import json
import os
import secrets
import ssl
import subprocess
import threading
import time
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

MAX_BODY = 46 * 1024 * 1024


def local_ipv4(address):
    ip = ipaddress.ip_address(address)
    return ip.version == 4 and any(
        ip in ipaddress.ip_network(net) for net in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16")
    )


def local_addresses():
    # A private subnet also belongs to Hyper-V/VPN adapters; only hardware is eligible.
    command = """$ErrorActionPreference='Stop'; [Console]::OutputEncoding=[Text.Encoding]::UTF8;
    $rows=@(Get-NetAdapter -Physical | Where-Object Status -eq 'Up' | ForEach-Object {
        $adapter=$_; Get-NetIPAddress -InterfaceIndex $adapter.InterfaceIndex -AddressFamily IPv4 |
        Where-Object { $_.AddressState -eq 'Preferred' -and -not $_.SkipAsSource } |
        ForEach-Object { [pscustomobject]@{ address=$_.IPAddress;
            wifi=($adapter.InterfaceDescription -match 'Wi-Fi|WiFi|Wireless|802.11') } }
    }); ConvertTo-Json -InputObject $rows -Compress"""
    executable = (
        Path(os.environ.get("SystemRoot", "C:/Windows"))
        / "System32/WindowsPowerShell/v1.0/powershell.exe"
    )
    try:
        result = subprocess.run(
            [str(executable), "-NoProfile", "-NonInteractive", "-Command", command],
            capture_output=True,
            timeout=10,
            check=True,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        rows = json.loads(result.stdout.decode("utf-8-sig"))
        return physical_addresses(rows)
    except (OSError, subprocess.SubprocessError, ValueError, TypeError):
        return []


def physical_addresses(rows):
    eligible = {}
    for row in rows:
        address = row.get("address", "")
        try:
            if local_ipv4(address):
                eligible[address] = eligible.get(address, False) or row.get("wifi") is True
        except ValueError:
            continue
    return sorted(
        eligible, key=lambda address: (not eligible[address], ipaddress.ip_address(address))
    )


def preferred_address(addresses, previous=None):
    return previous if previous in addresses else next(iter(addresses), None)


def sync_action(base, local, remote):
    if local == remote:
        return "same"
    if not local or local == base:
        return "pull"
    if remote == base:
        return "push"
    return "conflict"


def dpapi(raw, decrypt=False):
    if os.name != "nt":
        raise RuntimeError("Pairing persistence requires Windows DPAPI")

    class Blob(ctypes.Structure):
        _fields_ = [("size", ctypes.c_ulong), ("data", ctypes.POINTER(ctypes.c_ubyte))]

    buffer = ctypes.create_string_buffer(raw)
    source = Blob(len(raw), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    target = Blob()
    crypt = ctypes.WinDLL("crypt32", use_last_error=True)
    function = crypt.CryptUnprotectData if decrypt else crypt.CryptProtectData
    function.argtypes = [
        ctypes.POINTER(Blob),
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_ulong,
        ctypes.POINTER(Blob),
    ]
    function.restype = ctypes.c_int
    if not function(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(target)):
        raise ctypes.WinError(ctypes.get_last_error())
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    try:
        return ctypes.string_at(target.data, target.size)
    finally:
        kernel.LocalFree(target.data)


class SyncIdentity:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.path = self.directory / "pairing.dpapi"
        self.lock = threading.Lock()
        if self.path.exists():
            self.data = json.loads(dpapi(self.path.read_bytes(), decrypt=True))
        else:
            self.data = {"key_password": secrets.token_urlsafe(32), "tokens": []}
            key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
            name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "KeyShelf local sync")])
            now = datetime.now(UTC)
            cert = (
                x509.CertificateBuilder()
                .subject_name(name)
                .issuer_name(name)
                .public_key(key.public_key())
                .serial_number(x509.random_serial_number())
                .not_valid_before(now - timedelta(days=1))
                .not_valid_after(now + timedelta(days=3650))
                .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
                .sign(key, hashes.SHA256())
            )
            self.data["certificate"] = cert.public_bytes(serialization.Encoding.PEM).decode()
            self.data["private_key"] = key.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8,
                serialization.BestAvailableEncryption(self.data["key_password"].encode()),
            ).decode()
            self.save()
        cert = x509.load_pem_x509_certificate(self.data["certificate"].encode())
        self.pin = cert.fingerprint(hashes.SHA256()).hex()
        self.invite = None
        self.expires = 0

    def save(self):
        encoded = dpapi(json.dumps(self.data).encode())
        temporary = self.path.with_suffix(".tmp")
        with temporary.open("wb") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, self.path)

    def ssl_context(self):
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        # Private PEM is encrypted; the password and long-lived identity are DPAPI-protected.
        cert = self.directory / "certificate.pem"
        key = self.directory / "private.encrypted.pem"
        cert.write_text(self.data["certificate"], encoding="ascii")
        key.write_text(self.data["private_key"], encoding="ascii")
        try:
            context.load_cert_chain(cert, key, self.data["key_password"])
        finally:
            cert.unlink(missing_ok=True)
            key.unlink(missing_ok=True)
        return context

    def invitation(self, host, port):
        with self.lock:
            self.invite = secrets.token_urlsafe(32)
            self.expires = int(time.time()) + 120
            return {
                "version": 1,
                "host": host,
                "port": port,
                "pin": self.pin,
                "invite": self.invite,
                "expires": self.expires,
            }

    def pair(self, invitation):
        with self.lock:
            if (
                not isinstance(invitation, str)
                or not self.invite
                or time.time() >= self.expires
                or not secrets.compare_digest(self.invite, invitation)
            ):
                return None
            self.invite = None
            token = secrets.token_urlsafe(32)
            self.data["tokens"].append(hashlib.sha256(token.encode()).hexdigest())
            self.save()
            return token

    def authorized(self, header):
        if not header.startswith("Bearer ") or len(header) > 200:
            return False
        digest = hashlib.sha256(header[7:].encode()).hexdigest()
        with self.lock:
            return any(secrets.compare_digest(digest, token) for token in self.data["tokens"])

    def revoke(self):
        with self.lock:
            self.data["tokens"] = []
            self.invite = None
            self.save()


class SyncServer:
    def __init__(self, identity, dispatch, host, port=48732, allow_loopback=False):
        if not local_ipv4(host) and not (allow_loopback and host == "127.0.0.1"):
            raise ValueError("Only private local IPv4 is permitted")
        self.identity = identity
        self.dispatch = dispatch
        self.semaphore = threading.BoundedSemaphore(4)
        self.events = threading.Condition()
        self.revision = 0
        self.stopping = False
        self.listeners = {}
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_):
                pass

            def setup(self):
                super().setup()
                self.connection.settimeout(20)

            def do_POST(self):
                if not owner.semaphore.acquire(blocking=False):
                    self.reply(503, {})
                    return
                try:
                    self.handle_post()
                except (ValueError, KeyError, TypeError):
                    self.reply(400, {})
                except (OSError, TimeoutError):
                    pass
                except Exception:
                    self.reply(503, {})
                finally:
                    owner.semaphore.release()

            def handle_post(self):
                if not local_ipv4(self.client_address[0]) and not (
                    allow_loopback and self.client_address[0] == "127.0.0.1"
                ):
                    self.reply(403, {})
                    return
                if self.path not in ("/pair", "/sync", "/upload", "/events"):
                    self.reply(404, {})
                    return
                if self.path != "/pair" and not identity.authorized(
                    self.headers.get("Authorization", "")
                ):
                    self.reply(401, {})
                    return
                size = int(self.headers.get("Content-Length", "-1"))
                limit = MAX_BODY if self.path == "/upload" else 4096
                if size < 0 or size > limit:
                    self.reply(413, {})
                    return
                raw = self.rfile.read(size)
                if len(raw) != size:
                    self.reply(400, {})
                    return
                body = json.loads(raw)
                if not isinstance(body, dict):
                    raise ValueError
                if self.path == "/pair":
                    token = identity.pair(body.get("invite"))
                    self.reply(200 if token else 401, {"token": token} if token else {})
                elif self.path == "/events":
                    if body.get("protocol") != 3:
                        self.reply(426, {})
                        return
                    token = hashlib.sha256(
                        self.headers.get("Authorization", "").encode()
                    ).hexdigest()
                    self.send_response(200)
                    self.send_header("Content-Type", "application/x-ndjson")
                    self.send_header("Cache-Control", "no-store")
                    self.end_headers()
                    self.connection.settimeout(None)
                    with owner.events:
                        previous = owner.listeners.get(token)
                        owner.listeners[token] = self.connection
                        owner.events.notify_all()
                        if previous is not None:
                            import socket

                            try:
                                previous.shutdown(socket.SHUT_RDWR)
                            except OSError:
                                pass
                    seen = 0
                    try:
                        self.wfile.write(b'{"event":"ready"}\n')
                        self.wfile.flush()
                        while True:
                            with owner.events:
                                owner.events.wait_for(
                                    lambda seen=seen: (
                                        owner.stopping
                                        or owner.revision > seen
                                        or owner.listeners.get(token) is not self.connection
                                    )
                                )
                                if (
                                    owner.stopping
                                    or owner.listeners.get(token) is not self.connection
                                ):
                                    break
                                seen = owner.revision
                            self.wfile.write(b'{"event":"changed"}\n')
                            self.wfile.flush()
                    finally:
                        with owner.events:
                            if owner.listeners.get(token) is self.connection:
                                owner.listeners.pop(token, None)
                else:
                    status, response = owner.dispatch(self.path, body)
                    self.reply(status, response)

            def reply(self, status, body):
                raw = json.dumps(body).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(raw)

        class Server(ThreadingHTTPServer):
            daemon_threads = True
            request_queue_size = 4

            def get_request(self):
                connection, address = self.socket.accept()
                connection.settimeout(5)
                try:
                    return self.context.wrap_socket(connection, server_side=True), address
                except Exception:
                    connection.close()
                    raise

        self.http = Server((host, port), Handler)
        self.http.context = identity.ssl_context()
        self.thread = threading.Thread(target=self.http.serve_forever, daemon=True)
        self.thread.start()

    @property
    def port(self):
        return self.http.server_port

    def notify(self):
        with self.events:
            self.revision += 1
            self.events.notify_all()

    def close(self):
        with self.events:
            self.stopping = True
            self.events.notify_all()
        self.http.shutdown()
        self.http.server_close()
        self.thread.join(timeout=2)


def sync_response(raw, body):
    remote = hashlib.sha256(raw).hexdigest()
    local = body.get("hash")
    base = body.get("base")
    if not isinstance(local, str) or len(local) not in (0, 64):
        raise ValueError
    if base is not None and (not isinstance(base, str) or len(base) != 64):
        raise ValueError
    action = sync_action(base, local, remote)
    result = {"action": action, "hash": remote}
    if action in ("pull", "conflict"):
        result["blob"] = base64.b64encode(raw).decode()
    return result
