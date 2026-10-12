# Разработка KeyShelf

Python 3.12 на Windows. Создайте `.venv`, установите `requirements-lock.txt`. Запуск: `KeyShelf-run.cmd`.

Проверки: `.venv/Scripts/python.exe -m pytest tests`; `.venv/Scripts/python.exe -m ruff check app tests`. Qt-тесты используют синтетические базы.

Сборка: `powershell -NoProfile -File Build_Tools/build.ps1 -TemporaryDirectory <absolute-work-directory>`. Каталог временной сборки должен быть вне исходников. Скрипт использует доверенные native пути и проверяет происхождение DLL и полный Qt MSVC runtime. Готовая папка KeyShelf остаётся в корне проекта. Перед заменой старой сборки сохраните пользовательские данные отдельно.

Установщик: `powershell -NoProfile -File Build_Tools/package.ps1 -InnoCompilerPath <ISCC.exe> -PortableDirectory <absolute-portable-directory>`. Установщик сохраняется на системном рабочем столе. `-SkipPortableCopy` создаёт только установщик. Эти команды не запускают GUI.

Неинтерактивная проверка: `KeyShelf/KeyShelf.exe --runtime-smoke-test <absolute-report.json>`. Запускать с timeout и перенаправленным stdout/stderr, в отдельном рабочем каталоге. Реальные базы не нужны.

`Account.title` — KDBX Title; `Account.alias` — optional encrypted metadata alias. `field_layout` сохраняет порядок и удаление полей. Синхронизация выполняется через TLS в локальной сети с проверкой fingerprint и подтверждений. Protocol3 sends only manual Save batches; receiver accepts or rejects. JSON import fully replaces records and services with an encrypted backup. Ключи DPAPI из .local-state не включать в Git, установщик или резервную копию на сервере.
