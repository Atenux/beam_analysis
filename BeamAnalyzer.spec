# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all

datas = [('C:\\Users\\matias.thiele\\Desktop\\beam_analysis\\.venv\\Lib\\site-packages\\cadquery_ocp.libs', 'cadquery_ocp.libs')]
binaries = []
hiddenimports = ['cadquery_ocp_proxy', 'shapely', 'shapely.geometry', 'shapely.ops', 'shapely.validation', 'matplotlib.backends.backend_qtagg', 'matplotlib.backends.backend_qt']
tmp_ret = collect_all('OCP')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]


a = Analysis(
    ['C:\\Users\\matias.thiele\\Desktop\\beam_analysis\\beam_analyzer\\main.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=['C:\\Users\\matias.thiele\\Desktop\\beam_analysis\\_pyi_rthook.py'],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='BeamAnalyzer',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='BeamAnalyzer',
)
