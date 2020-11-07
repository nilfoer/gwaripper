# -*- mode: python -*-

block_cipher = None


a = Analysis(['gwaripper-runner.py'],
             # tell pyinstaller where Universal CRT dlls are (needed for >py3.5 on <win10 -> see
             # https://pyinstaller.readthedocs.io/en/v3.3.1/usage.html#windows   
             pathex=['D:\\SYNC\\coding\\_sgasm-repo',
                     '..\\UniversalCRTDLLs\\x86', '..\\UniversalCRTDLLs\\x64'],
             binaries=[],
             # praw needs praw.ini (which it looks for in 3 places appdata etc. including cwd)
             # -> pyinstaller automatically changes __file__ refs to be relative to the bundle
             # praw was looking praw.ini in ./praw/ because thats were the __file__ presumably
             # was
             datas=[
                ("venv/Lib/site-packages/praw/praw.ini", "praw/"),
                 # also enclude webgui fils
                ("gwaripper_webGUI/static", "static"),
                ("gwaripper_webGUI/templates", "templates"),
                ("gwaripper/migrations/*.py", "gwaripper/migrations"),
             ],
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
          a.binaries,
          a.zipfiles,
          a.datas,
          [],
          name='gwaripper',
          debug=False,
          bootloader_ignore_signals=False,
          strip=False,
          upx=True,
          runtime_tmpdir=None,
          console=True )
