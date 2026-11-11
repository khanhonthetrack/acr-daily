"""Start ACR Daily (python run.py, or the built ACR-Daily.exe)."""
from acr_daily import i18n

if __name__ == '__main__':
    i18n.first_start()                 # the language (Windows' own the first time), before the app's words are made
    from acr_daily.app import main
    main()
