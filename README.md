# Finance Pulse Analytics: Enterprise Financial Performance Intelligence and Profitability Optimization Analytics Platform

[![Platform: macOS | Windows | Android](https://img.shields.io/badge/Platform-macOS%20%7C%20Windows%20%7C%20Android-brightgreen.svg)]()
[![Python: 3.9+](https://img.shields.io/badge/Python-3.9%2B-blue.svg)]()
[![UI: PyWebView + Android APK](https://img.shields.io/badge/UI-Desktop%20%7C%20Web%20%7C%20Android%20APK-orange.svg)]()
[![Privacy: 100% Local](https://img.shields.io/badge/Privacy-100%25%20Local%20%7C%20No%20Cloud-success.svg)]()
[![GitHub release](https://img.shields.io/github/v/release/yudhaxibe-hue/Finance-Pulse-Analytics?include_prereleases&color=success&label=Latest%20Release)](https://github.com/yudhaxibe-hue/Finance-Pulse-Analytics/releases/latest)

A local-first enterprise financial performance intelligence and profitability optimization analytics workbench combining **3-Pillar Narrative Briefs (`01 · What it is` · `02 · What happened` · `03 · What could have happened`)**, **Switchable Offline Charts**, **Explainable IQR Outlier Surveillance**, **Linear Regression Forecasting**, **Target-Margin Optimization**, and **Role-Isolated Governance** across **macOS**, **Windows**, **Web**, and **Android**.

---

# 💾 INSTALLATION & 1-CLICK QUICK RUN

> ### 🎓 For Evaluators, Teams & Quick Testing (Zero Setup Required)
> **You do NOT need to clone this repository, use the terminal, or install Python to evaluate Finance Pulse Analytics.**
> Simply download the package for your device below, unzip (for desktop), and launch.

| Operating System | Direct 1-Click Download | How to Run |
| :--- | :--- | :--- |
| **🪟 Windows 10 / 11** | [**📥 Download for Windows (.zip)**](https://github.com/yudhaxibe-hue/Finance-Pulse-Analytics/releases/download/v1.0.0/FinancePulseAnalytics-Windows-unsigned.zip) | **1.** Extract the downloaded `.zip` folder.<br>**2.** Double-click **`FinancePulseAnalytics.exe`**.<br>*Opens natively without terminal windows or Python setup.* |
| **🍎 macOS (Apple Silicon & Intel)** | [**📥 Download for macOS (.zip)**](https://github.com/yudhaxibe-hue/Finance-Pulse-Analytics/releases/download/v1.0.0/FinancePulseAnalytics-macOS-unsigned.zip) | **1.** Extract the `.zip` archive.<br>**2.** Open **`FinancePulseAnalytics.app`**.<br>*(First launch of an unsigned build: right-click -> **Open**).* |
| **🤖 Android (8.0+ / SDK 26–34)** | [**📥 Download Android APK (.apk)**](https://github.com/yudhaxibe-hue/Finance-Pulse-Analytics/releases/download/v1.0.0/FinancePulseAnalytics-Android.apk) | **1.** Open **`FinancePulseAnalytics-Android.apk`** on Android.<br>**2.** Runs 100% offline with bundled Chart.js & sample CSV and supports automatic wireless updates. |
| **📦 GitHub Releases Hub** | [**🔗 View All Releases & SHA-256 Checksums**](https://github.com/yudhaxibe-hue/Finance-Pulse-Analytics/releases/latest) | Official release artifacts with SHA-256 checksums built automatically by GitHub Actions. |

---

### 📂 Alternative: 1-Click Run Directly From Cloned Source
If you cloned or downloaded the source code from GitHub:
- **On macOS:** Double-click **`Run_FinancePulse_Mac.command`** in Finder.
- **On Windows:** Double-click **`Run_FinancePulse_Windows.bat`** in File Explorer.

The launcher automatically initializes `.venv` on first launch, verifies dependencies from `requirements-desktop.txt`, polls `/health` readiness on loopback `127.0.0.1`, and opens a native desktop window (with clean browser fallback if native webview runtimes are unavailable).

---

## 📚 Project Documentation & Architecture Links (Visible Inside GitHub)

| Resource | Description | Link |
| :--- | :--- | :--- |
| **User & Architecture Guide** | Complete installation, formulas, portal security, Android offline engine & testing manual (readable directly in GitHub). | [**`docs/USER_AND_ARCHITECTURE_GUIDE.md`**](docs/USER_AND_ARCHITECTURE_GUIDE.md) |
| **Executive Presentation Deck** | 12-slide presentation covering pipeline design, screenshots, packaging, and CI/CD (`.pptx`). | [**`docs/Finance_Pulse_Analytics_Presentation.pptx`**](docs/Finance_Pulse_Analytics_Presentation.pptx) |
| **Product & Analytics Spec** | Core user workflows, KPI definitions, optimization solver, and admin governance spec. | [**`PRODUCT.md`**](PRODUCT.md) |
| **Design System Reference** | Apple Precision Ledger visual tokens, typography, and component standards. | [**`DESIGN.md`**](DESIGN.md) |
| **CI/CD Release Pipeline** | Multi-OS GitHub Actions workflow building macOS `.app`, Windows `.exe`, and Android `.apk`. | [**`.github/workflows/ci.yml`**](.github/workflows/ci.yml) |

---

## ⏱️ 60-Second Evaluation & Walkthrough Guide

1. **Launch:** Open `FinancePulseAnalytics.app` / `FinancePulseAnalytics.exe` (or visit `http://127.0.0.1:5000` in source mode).
2. **Explore Landing Preview:** Toggle **Monthly pulse**, **Profitability**, and **Forecast** right inside the interactive 30-month hero showcase, or click **Create account** / **Download sample CSV**.
3. **Import Dataset:** Sign in to the User Portal, open **Import & My Data**, upload the sample CSV (or any CSV/XLSX/JSON file up to 16 MB), review the **Detected column mapping** staging preview, and confirm commit.
4. **Inspect Narrative-First Intelligence:** On **Dashboard**, **Overview**, **Products / Departments / Categories / Regions**, **Potential Anomalies**, and **Forecasting**, read the 3-pillar brief (**01 · What it is** -> **02 · What happened** -> **03 · What could have happened**) positioned directly before every Chart.js toggle (`Trajectory`, `Margin %`, `Revenue vs. Profit`, `Profit share`).
5. **Solve Target Margins & Simulate Scenarios:** Under **What-if & Optimization**, enter a desired Target Margin % (e.g., `45%`), load the calculated expense-cut or revenue-lift preset into the interactive sliders, inspect ranked 4D segment profit levers, and save named scenarios.
6. **Export Reports:** Click **Export CSV** or **Export PDF** for formatted A4 ReportLab executive summaries.

---

## 1. Repository Structure

```text
Finance-Pulse-Analytics/
├── .github/workflows/ci.yml      # Automated macOS, Windows & Android CI/CD release pipeline
├── Run_FinancePulse_Mac.command  # 1-Click macOS Finder desktop launcher
├── Run_FinancePulse_Windows.bat  # 1-Click Windows Explorer desktop launcher
├── app.py                        # Flask application, RBAC portals, exports, /health & wireless sync API
├── app_launcher.py               # Loopback/LAN PyWebView shell, --admin, --public & background updates
├── updater.py                    # In-app manifest updater, SHA-256 verification & background sync queue
├── config.py                     # OS writable DATA_DIR & PyInstaller bundle path resolver
├── analytics/                    # Core engines: metrics, profitability, anomalies, forecasting, solver, narratives
├── database/                     # SQLite schema & workspace-isolated queries + audit trail
├── data/                         # CSV/XLSX/JSON auto-aliasing importer & bundled 120-row sample CSV
├── packaging/                    # Brand icon generator (.icns/.ico/mipmaps) & PyInstaller macOS/Windows specs
├── android/                      # Gradle project + WebView shell + offline JS analytics engine + JUnit tests
├── docs/                         # User/Architecture Markdown guide + 12-slide presentation deck (.pptx)
├── static/ & templates/          # Local Chart.js & Apple Precision Ledger web UI templates
└── tests/                        # Unit & end-to-end Flask + desktop launcher test suite
```

---

## 2. Advanced Developer Setup, Admin Controls & Tests

### Manual Python Setup
```bash
git clone https://github.com/yudhaxibe-hue/Finance-Pulse-Analytics.git
cd Finance-Pulse-Analytics

python3 -m venv .venv
source .venv/bin/activate        # On Windows: .venv\Scripts\activate
pip install -r requirements-desktop.txt

python app.py                    # Web server mode -> http://127.0.0.1:5000
# Or run standalone native desktop window:
python -m app_launcher
```

### Administrator Provisioning & Server Mode
Every client desktop/APK installation stores its SQLite database locally on that user's own device without telemetry. When deploying the backend on a shared server for centralized administration:

```bash
# Create/update a local administrator account cleanly via CLI
python -m app_launcher --create-admin --admin-email admin@example.com

# Or set environment variables before running app.py:
export FINANCE_PULSE_SECRET_KEY="replace-with-a-long-random-value"
export FINANCE_PULSE_ADMIN_EMAIL="admin@example.com"
export FINANCE_PULSE_ADMIN_PASSWORD="use-a-strong-password"

# Launch desktop shell connected to a remote hosted Flask server:
python -m app_launcher --admin --remote-url https://your-finance-server.example.com
```

### Automated Verification
```bash
# Python unit + end-to-end Flask, sync & updater tests
python -m pytest tests/ -v

# Android JUnit & debug APK build (JDK 17 + Android SDK 34)
cd android && ./gradlew testDebugUnitTest assembleDebug --no-daemon
```
