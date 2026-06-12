# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for Launchkey Mixer offline build.
#
# Run via:  python -m PyInstaller --noconfirm --clean LaunchkeyMixer.spec
#
# This produces dist\LaunchkeyMixer.exe — a single-file Windows executable
# that bundles the FastAPI server, SQLite, the React UI, and the MIDI helper.

from PyInstaller.utils.hooks import collect_submodules, collect_data_files

block_cipher = None

# Grab ALL submodules of uvicorn, starlette, anyio so dynamic imports don't fail.
uvicorn_modules = collect_submodules('uvicorn')
starlette_modules = collect_submodules('starlette')
anyio_modules = collect_submodules('anyio')

a = Analysis(
    ['server_offline.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('static', 'static'),
        ('helper', 'helper'),
    ],
    hiddenimports=[
        # Bulk-collected submodules
        *uvicorn_modules,
        *starlette_modules,
        *anyio_modules,
        'h11',
        'sniffio',
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
