"""The builds pack every module of the app: the in-game pages are imported by name (ingameapp.PAGES), which PyInstaller
can't see; without --collect-submodules the built 0.2.0 said "This page failed" on every tab (22 Nov 2026)."""
import os
import unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class Builds(unittest.TestCase):
    def test_every_module_packed(self):
        for name in ('build.bat', 'build_folder.bat'):
            path = os.path.join(HERE, name)
            if not os.path.exists(path):
                continue
            with open(path, encoding='utf-8') as f:
                self.assertIn('--collect-submodules acr_daily', f.read(), name)

    def test_the_pages_exist(self):
        from acr_daily import ingameapp
        import importlib
        for tab, mod in ingameapp.PAGES.items():
            if mod:
                importlib.import_module('acr_daily.' + mod)


if __name__ == '__main__':
    unittest.main()
