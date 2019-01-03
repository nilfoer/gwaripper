# -*- mode: python -*-

block_cipher = None

a = Analysis(['gwaripper-runner.py'],
             # tell pyinstaller where Universal CRT dlls are (needed for >py3.5 on <win10 -> see https://pyinstaller.readthedocs.io/en/v3.3.1/usage.html#windows   
             pathex=['N:\\coding\\_sgasm-repo',
                     '..\\UniversalCRTDLLs\\x86', '..\\UniversalCRTDLLs\\x64'],
             binaries=[],
             # praw needs praw.ini (which it looks for in 3 places appdata etc. including cwd)
             # -> include praw.ini in root folder
             datas=[("venv/Lib/site-packages/praw/praw.ini", ".")],
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
