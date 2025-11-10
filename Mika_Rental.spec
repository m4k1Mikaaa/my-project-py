# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import collect_dynamic_libs

a = Analysis(
    ['src\\main.py'],
    pathex=[],
    # --- FIX: Explicitly include pyzbar's dependent DLLs ---
    # This collects libzbar-64.dll, libiconv.dll, etc., and adds them to the build.
    binaries=collect_dynamic_libs('pyzbar'),
    datas=[
        # --- นี่คือส่วนสำคัญที่เพิ่มเข้ามา ---
        # บอกให้ PyInstaller คัดลอกโฟลเดอร์ app_images และ fonts 
        # ไปไว้ในโปรแกรมที่ build เสร็จแล้ว        
        ('src/app_image', 'app_image'),
        ('src/fonts', 'fonts')
    ],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=None,
    noarchive=False,
)
pyz = PYZ(a.pure)

# --- FIX: Explicitly set to one-folder mode ---
a.onedir = True

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='Mika_Rental',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='src\\app_image\\icon.ico',
)