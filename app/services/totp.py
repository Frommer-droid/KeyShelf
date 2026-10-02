"""Offline TOTP; errors never include the supplied secret."""
import time

import pyotp


def generator(secret):
    try:
        value = secret.strip()
        otp = pyotp.parse_uri(value) if value.startswith("otpauth://") else pyotp.TOTP("".join(value.split()).upper())
        if not isinstance(otp, pyotp.TOTP) or otp.interval <= 0:
            raise ValueError
        otp.at(0)
        return otp
    except Exception:
        raise ValueError("Некорректный секрет 2FA. Введите Base32 или ссылку otpauth://totp/.") from None


def current_code(secret, timestamp=None):
    otp = generator(secret)
    now = time.time() if timestamp is None else timestamp
    return otp.at(now), otp.interval - int(now) % otp.interval
