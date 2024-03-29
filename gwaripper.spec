# -*- mode: python -*-
import os
from sys import platform

block_cipher = None

data_files = [
    # praw needs praw.ini (which it looks for in 3 places appdata etc. including cwd)
    # -> pyinstaller automatically changes __file__ refs to be relative to the bundle
    # praw was looking praw.ini in ./praw/ because thats were the __file__ presumably
    # was
    ("praw.ini", "praw/"),
    # also include webgui files
    ("gwaripper_webGUI/static", "static"),
    ("gwaripper_webGUI/templates", "templates"),
    ("gwaripper/migrations/*.py", "gwaripper/migrations"),
]

if platform == "win32" and os.path.exists(os.path.join("binary_deps", "ffmpeg.exe")):
    data_files.append(("binary_deps/ffmpeg.exe", "./"))

# IMPORTANT: pyinstaller will apparently just bundle everything it finds in the current python
# env so use a venv with only the required additional packages installed
# pyinstaller needs to be installed in the venv as well and then started (on Win) using
# Scripts\pyinstaller.exe
a = Analysis(['gwaripper-runner.py'],
             pathex=['gwaripper', 'gwaripper_webGUI'],
             binaries=[],
             datas=data_files,
             hiddenimports=[],
             hookspath=[],
             runtime_hooks=[],
             excludes=[],
             win_no_prefer_redirects=False,
             win_private_assemblies=False,
             cipher=block_cipher,
             noarchive=False)
pyz = PYZ(a.pure, a.zipped_data,
             cipher=block_cipher)
exe = EXE(pyz,
          a.scripts,
          [],
          exclude_binaries=True,
          # name of exe
          name='gwaripper',
          debug=False,
          bootloader_ignore_signals=False,
          strip=False,
          upx=True,
          console=True )
coll = COLLECT(exe,
               a.binaries,
               a.zipfiles,
               a.datas,
               strip=False,
               upx=True,
               # name of folder
               name='gwaripper')
