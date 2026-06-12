# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for Launchkey Mixer offline build.
#
# Run via:  python -m PyInstaller --noconfirm --clean LaunchkeyMixer.spec
#
# This produces dist\LaunchkeyMixer.exe — a single-file Windows executable
# that bundles the FastAPI server, SQLite, the React UI, and the MIDI helper.

block_cipher = None

a = Analysis(
    ['server_offline.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('static', 'static'),
        ('helper', 'helper'),
    ],
    hiddenimports=[
        'uvicorn.logging',
        'uvicorn.loops.auto',
        'uvicorn.loops.asyncio',
        'uvicorn.protocols.http.auto',
        'uvicorn.protocols.http.h11_impl',
        'uvicorn.protocols.websockets.auto',
        'uvicorn.protocols.websockets.websockets_impl',
        'uvicorn.lifespan.on',
        'uvicorn.lifespan.off',
        # Helper deps — explicitly listed because launchkey_helper is loaded
        # dynamically and PyInstaller's static analysis can't see them.
        'requests',
        'urllib3',
        'charset_normalizer',
        'idna',
        'certifi',
        'pycaw',
        'pycaw.pycaw',
        'comtypes',
        'comtypes.client',
        'pynput',
        'pynput.keyboard',
        'pynput.mouse',
        'rtmidi',
        'launchkey_helper',
        # System tray
        'pystray',
        'pystray._win32',
        'PIL',
        'PIL.Image',
        'PIL.ImageDraw',
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=[
        'tkinter',
        'matplotlib',
        'numpy',
        'pandas',
        'scipy',
        'pytest',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='LaunchkeyMixer',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,       # hidden — app runs in system tray
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
