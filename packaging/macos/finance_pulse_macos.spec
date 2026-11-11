# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller specification for macOS standalone bundle (FinancePulseAnalytics.app)."""
from pathlib import Path

block_cipher = None
ROOT_DIR = Path.cwd()
ICON_PATH = ROOT_DIR / "packaging" / "assets" / "finance_pulse.icns"

datas = [
    (str(ROOT_DIR / "templates"), "templates"),
    (str(ROOT_DIR / "static"), "static"),
    (str(ROOT_DIR / "data" / "sample_data"), "data/sample_data"),
]

hiddenimports = [
    "flask",
    "jinja2",
    "werkzeug",
    "werkzeug.serving",
    "werkzeug.security",
    "pandas",
    "numpy",
    "openpyxl",
    "reportlab",
    "reportlab.pdfgen",
    "reportlab.pdfgen.canvas",
    "reportlab.lib.pagesizes",
    "webview",
    "webview.platforms.cocoa",
    "analytics",
    "analytics.anomalies",
    "analytics.financial_metrics",
    "analytics.forecasting",
    "analytics.intelligence",
    "analytics.optimization",
    "analytics.profitability",
    "data",
    "data.importer",
    "data.sample_data",
    "database",
    "database.db",
]

excludes = [
    "tkinter",
    "matplotlib",
    "scipy",
    "sklearn",
    "statsmodels",
    "pytest",
    "IPython",
    "notebook",
]

a = Analysis(
    [str(ROOT_DIR / "app_launcher.py")],
    pathex=[str(ROOT_DIR)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="FinancePulseAnalytics",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
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
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="FinancePulseAnalytics",
)

app = BUNDLE(
    coll,
    name="FinancePulseAnalytics.app",
    icon=str(ICON_PATH) if ICON_PATH.exists() else None,
    bundle_identifier="com.financepulse.analytics",
    info_plist={
        "CFBundleName": "Finance Pulse Analytics",
        "CFBundleDisplayName": "Finance Pulse Analytics: Enterprise Financial Performance Intelligence and Profitability Optimization Analytics Platform",
        "CFBundleShortVersionString": "1.0.0",
        "CFBundleVersion": "1.0.0",
        "NSHighResolutionCapable": True,
        "LSMinimumSystemVersion": "11.0",
    },
)
