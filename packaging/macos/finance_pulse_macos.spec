# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller specification for macOS standalone bundle (FinancePulseAnalytics.app)."""
import json
from pathlib import Path

block_cipher = None
ROOT_DIR = Path.cwd()
ICON_PATH = ROOT_DIR / "packaging" / "assets" / "finance_pulse.icns"

BUILD_INFO_PATH = ROOT_DIR / "build_info.json"
APP_VER = "1.2.0"
if BUILD_INFO_PATH.is_file():
    try:
        APP_VER = str(json.loads(BUILD_INFO_PATH.read_text(encoding="utf-8")).get("version") or APP_VER)
    except Exception:
        pass

datas = [
    (str(ROOT_DIR / "templates"), "templates"),
    (str(ROOT_DIR / "static"), "static"),
    (str(ROOT_DIR / "data" / "sample_data"), "data/sample_data"),
]
if BUILD_INFO_PATH.is_file():
    datas.append((str(BUILD_INFO_PATH), "."))

hiddenimports = [
    "updater",
    "itsdangerous",
    "flask",
    "jinja2",
    "werkzeug",
    "werkzeug.serving",
    "werkzeug.security",
    "sqlalchemy",
    "sqlalchemy.dialects.sqlite",
    "pandas",
    "numpy",
    "scipy",
    "scipy.special",
    "scipy.sparse",
    "sklearn",
    "sklearn.ensemble",
    "sklearn.feature_extraction.text",
    "sklearn.linear_model",
    "sklearn.pipeline",
    "sklearn.metrics",
    "joblib",
    "matplotlib",
    "matplotlib.backends.backend_agg",
    "seaborn",
    "openpyxl",
    "pypdf",
    "PIL",
    "reportlab",
    "reportlab.pdfgen",
    "reportlab.pdfgen.canvas",
    "reportlab.lib.pagesizes",
    "webview",
    "webview.platforms.cocoa",
    "Vision",
    "analytics",
    "analytics.anomalies",
    "analytics.copilot",
    "analytics.financial_metrics",
    "analytics.forecasting",
    "analytics.intelligence",
    "analytics.ml_engine",
    "analytics.optimization",
    "analytics.powerbi",
    "analytics.privacy",
    "analytics.profitability",
    "analytics.receipt_ocr",
    "analytics.visuals",
    "data",
    "data.importer",
    "data.sample_data",
    "database",
    "database.db",
    "database.models",
]

excludes = [
    "tkinter",
    "pytest",
    "IPython",
    "notebook",
    "pptx",
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
        "CFBundleDisplayName": "Finance Pulse Analytics",
        "CFBundleShortVersionString": APP_VER,
        "CFBundleVersion": APP_VER,
        "NSHighResolutionCapable": True,
        "LSMinimumSystemVersion": "11.0",
    },
)
