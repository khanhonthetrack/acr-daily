"""Writes version_info.txt for PyInstaller (--version-file): the exe's Windows details (name, version, description).
An exe without them looks more suspicious to antivirus heuristics."""
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(HERE, 'acr_daily', '__init__.py'), encoding='utf-8') as f:
    version = re.search(r"__version__ = '([\d.]+)'", f.read()).group(1)
nums = tuple(int(x) for x in version.split('.')) + (0,) * (4 - len(version.split('.')))

TEMPLATE = """VSVersionInfo(
  ffi=FixedFileInfo(filevers=%(nums)s, prodvers=%(nums)s, mask=0x3f, flags=0x0, OS=0x40004, fileType=0x1,
                    subtype=0x0, date=(0, 0)),
  kids=[
    StringFileInfo([StringTable('040904B0', [
      StringStruct('CompanyName', 'ACR Daily (open source)'),
      StringStruct('FileDescription', 'ACR Daily - daily stages and leaderboard for Assetto Corsa Rally'),
      StringStruct('FileVersion', '%(v)s'),
      StringStruct('InternalName', 'ACR-Daily'),
      StringStruct('LegalCopyright', 'MIT licence - github.com/khanhonthetrack/acr-daily'),
      StringStruct('OriginalFilename', 'ACR-Daily.exe'),
      StringStruct('ProductName', 'ACR Daily'),
      StringStruct('ProductVersion', '%(v)s')])]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
"""

with open(os.path.join(HERE, 'version_info.txt'), 'w', encoding='utf-8') as f:
    f.write(TEMPLATE % {'nums': nums, 'v': version})
print('version_info.txt for', version)
