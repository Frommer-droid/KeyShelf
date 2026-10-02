# Сторонние компоненты

Приложение распространяется под GPL-3.0. Компоненты используются без изменения исходников.

| Компонент | Лицензия | Исходники |
| --- | --- | --- |
| Python 3.12 | PSF License | https://www.python.org/downloads/source/ |
| PySide6, Shiboken6, Qt | LGPL-3.0 / GPL, лицензии отдельных модулей | https://download.qt.io/official_releases/QtForPython/ |
| PyKeePass | GPL-3.0 | https://github.com/libkeepass/pykeepass |
| PyOTP | MIT | https://github.com/pyauth/pyotp |
| PyCryptodome | BSD / public domain | https://github.com/Legrandin/pycryptodome |
| Argon2-cffi и bindings | MIT | https://github.com/hynek/argon2-cffi |
| CFFI | MIT | https://foss.heptapod.net/pypy/cffi |
| lxml | BSD-3-Clause, bundled libxml2/libxslt notices | https://github.com/lxml/lxml |
| Construct | MIT | https://github.com/construct/construct |

Тексты лицензий установленных компонентов находятся в `third-party-licenses` готовой сборки. Перечень фактических версий находится в `RUNTIME_MANIFEST.json` и `source/requirements-lock.txt`. PyInstaller предоставляет исключение для распространения сформированных исполняемых файлов; его исходники доступны на https://github.com/pyinstaller/pyinstaller.
