<p align="center"><img src="docs/app-icon.png" width="128" height="128" alt="KeyShelf"></p>
<h1 align="center">KeyShelf</h1>

<p align="center">A local encrypted vault for keys and accounts.</p>
<p align="center"><a href="README.md">Русский</a> · <a href="https://github.com/Frommer-droid/KeyShelf/releases/latest">Latest release</a></p>

A local vault for API keys, accounts and other records on Windows 10/11 x64. Services appear on the left, records on the right. Data is stored in an encrypted KDBX4 file.

The record editor has **+** and **−** buttons at the bottom left. Focus a value field: **+** inserts an unnamed field below it, while **−** removes it with its contents. With no value field selected, **+** appends a field and **−** is disabled. Type, label and comment remain fixed. Field order persists in the encrypted vault and JSON exchange; only filled values appear in cards, with a copy button.

Existing records can change type through the dropdown. Values from visible rows move in order into the new type's standard fields; remaining values become additional fields. Switching again transfers the current values, with no separate drafts per type. The label, comment and favourite state are preserved. When choosing Account, the value in its 2FA field must be a valid TOTP secret or empty.

Hovering over a favourite button shows a filled star and the selected appearance. Hovering does not change the favourite state; clicking does.

Under **Система → Масштаб интерфейса**, choose a 50–150% adjustment to automatic screen scaling. 100% means no adjustment. Fonts, controls and dialogs scale together; the preference persists across restarts.

![Synthetic data](docs/vault-cards.png)

## Getting started

Download the installer from the [latest KeyShelf release](https://github.com/Frommer-droid/KeyShelf/releases/latest), or run `KeyShelf.exe` from the portable folder. While the repository is private, downloading requires repository access. Python is not required for the packaged build. Keep the entire folder, including `_internal`.

Create a vault outside the application folder with a master password of at least 12 characters. Add a service, click **+** and choose API, Account or Other. API records contain a label, key, paid flag and comment. Accounts contain a label, login, password, optional 2FA secret and comment. Other records contain a label, three arbitrary values and a comment.

Expand a card to view populated values and copy them. Keys and passwords are visible. Comments and permanent 2FA secrets remain in the editor. API and Other records have a compact button for copying the first value without expanding; a check mark briefly confirms copying. The master password cannot be recovered. Keep independent backups.

## Search and filters

Search covers every service and matches service names, labels, logins and field names. Values and comments are not indexed. Selecting a service clears the query. Type filters combine selected types; turning all off displays every type. Type selections are remembered separately for each service across restarts. The star filters favourites. Soft blue, green and purple distinguish types; `$` marks paid APIs and green `⓪` marks free ones.

TOTP codes are calculated locally from a Base32 secret or an `otpauth://totp/` URL. Correct system time is required. Provider APIs are not contacted to validate keys.

## Mini mode

The **Мини** button at the right end of the top row switches to a compact search across the entire vault. With an empty query, only the search field appears. Results open as accordions with square copy buttons and a check mark confirming copying. Long lists scroll. Type and favourite filters from the full window do not restrict Mini search.

![Mini mode with synthetic data](docs/mini-mode.png)

The button inside the right edge of search returns to **Maxi**. The mode and each window layout's size and position are remembered separately. After restarting, open the vault first; the selected mode then returns. Queries remain in the current session only. A global keyboard shortcut is not assigned yet.

## Tray and startup

When the system tray is available, closing hides either window mode, including the locked welcome screen. Clicking the tray icon restores the same mode and session without another password, preserving the query and expanded cards. In Mini, search receives focus and the previous query is selected for replacement. **Exit** ends the application; the next launch requires the password.

The System tab controls startup at the current Windows user's sign-in and starting minimised. The welcome screen lists ten recent vaults and stores paths only. Locking is manual; there is no idle timeout.

## Import, export and backups

JSON import merges services and adds records, skipping exact duplicates while preserving existing data. Export covers the entire vault or selected service. **JSON contains plaintext passwords and keys.** See the [exchange format](docs/import-export.md). KDBX history and attachments require an encrypted backup.

Before each change, the previous encrypted version is saved beside the vault as `.kdbx.bak`. The System tab also offers saving an encrypted copy and opening a backup.

## Storage and limitations

KDBX4 uses AES-256 and Argon2id (64 MiB, three passes, two lanes). The password stays in memory during the session. Locking and exiting clear the interface and clipboard values still owned by the application; there is no clipboard timeout. Windows is asked to exclude values from history and cloud clipboard, but other clipboard managers may retain copies. Guaranteed wiping of Python and Qt memory is not provided.

Settings live beside the executable in `settings.json`, without keys or the master password. Vaults are chosen separately. Concurrent external changes are detected; network filesystems have not been independently validated.

Uninstalling removes installed application files while retaining user-created settings, logs and vaults. Keep independent vault backups regardless.

## Running the source

Use Python 3.12 on Windows:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Then open `Запустить.cmd` in the root. See [DEVELOPER.md](DEVELOPER.md) for testing and building.

## License

Version 0.3.0, [GPL-3.0](LICENSE). The project uses GPL-3.0-licensed PyKeePass; third-party licenses are retained. Application source and build scripts are included in `source`. [Third-party notices](THIRD_PARTY_NOTICES.md), [source access](SOURCE_CODE_ACCESS.md), [Qt/PySide6](QT_PYSIDE6_COMPLIANCE.md).
