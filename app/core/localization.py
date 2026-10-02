from PySide6.QtCore import QLibraryInfo, QLocale, QTranslator


def install_russian(app):
    locale = QLocale(QLocale.Language.Russian, QLocale.Country.Russia)
    QLocale.setDefault(locale)
    translator = QTranslator(app)
    loaded = translator.load(locale, "qtbase", "_", QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath))
    if loaded:
        app.installTranslator(translator)
    app.russian_translator = translator
    return loaded
