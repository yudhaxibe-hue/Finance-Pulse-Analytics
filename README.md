# Finance Pulse Analytics: Enterprise Financial Performance Intelligence and Profitability Optimization Analytics Platform

**Finance Pulse Analytics** is a local-first enterprise financial performance intelligence and profitability optimization analytics platform spanning **macOS**, **Windows**, and **Android**. Ingestion, dimensional profitability slicing, explainable IQR anomaly detection, regression forecasting, target-margin optimization, governance logging, and PDF/CSV reporting execute locally without external cloud dependencies.

## Platform Highlights

- **3-Pillar Narrative Intelligence Briefs & Interactive Charts:** Every analytics view opens with a crisp executive narrative (`01 · What it is` · `02 · What happened` · `03 · What could have happened`) followed by multi-mode visualizations (bar/line combos, horizontal margin rankings, profit-share doughnuts, variance vs. cutoff comparisons, and regression projection plots).
- **Workspace-Isolated User Portal & Admin Governance Portal:** Separate registration/login flows, persistent session secrets (`.flask_secret` or `FINANCE_PULSE_SECRET_KEY`), PBKDF2-SHA256 password hashing, user active/suspended governance (`/admin/users`), threshold controls, and filterable Admin **Audit Logs** (`/admin/audit`).
- **Resilient CSV, XLSX & JSON Import:** Automatic header alias detection (`Sales Date`, `COGS`, `Dept`, etc.), data quality auditing, 8-row staging preview before commit, and imported dataset history.
- **Target-Margin Optimization Solver & What-If Simulator:** Break-even revenue floor calculation, solved required expense-cut or revenue-lift presets, ranked segment profit levers across Product, Department, Category, and Region, interactive sliders, and saved scenario comparisons.
- **Native Desktop Packaging (macOS & Windows):** Embedded Flask server on ephemeral loopback `127.0.0.1`, `/health` readiness check, and native PyWebView window via [`app_launcher.py`](app_launcher.py) (with browser fallback and download support).
- **Standalone Android APK (`android/`):** Purpose-built mobile interface with bottom navigation, offline JavaScript analytics engine (`Chart.js` + bundled sample CSV + CSV/JSON upload & export), and an optional Settings bridge (`FINANCE_PULSE_REMOTE_URL` / live Flask URL) to connect to a hosted server.

## 1-Click Quick Start

### Option A · Pre-Built Releases (No Python Required)
Download the latest automated build from **GitHub Releases**:
- **macOS:** `FinancePulseAnalytics-macOS-unsigned.zip` — unzip and open `FinancePulseAnalytics.app`.
- **Windows:** `FinancePulseAnalytics-Windows-unsigned.zip` — unzip and run `FinancePulseAnalytics.exe`.
- **Android:** `FinancePulseAnalytics-Android.apk` — install directly on Android 8.0+ devices (`minSdk 26`, `targetSdk 34`).

### Option B · 1-Click Source Launchers
- **macOS:** Double-click `Run_FinancePulse_Mac.command` in Finder.
- **Windows:** Double-click `Run_FinancePulse_Windows.bat` in Explorer.

### Option C · Manual Developer Setup (Web UI)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

Open `http://127.0.0.1:5000`. Download the bundled sample CSV from **Import & My Data** to exercise all analytics modules immediately. `finance_pulse.db` initializes automatically inside the writable data directory (`FINANCE_PULSE_DATA_DIR` or OS application-data folder when packaged).

## Creating an Administrator & Hosted Server Tracking

By default, every desktop or Android install stores its SQLite/local database strictly on the user's own device (no telemetry or central tracking server). If you deploy the Flask backend on a central web host for multi-user access, you can point a private Admin desktop session to that host via:

```bash
python -m app_launcher --admin --remote-url https://your-finance-server.example.com
```

For local administrator initialization before launching:

```bash
python -m app_launcher --create-admin --admin-email admin@example.com
```

Or via environment variables (`FINANCE_PULSE_SECRET_KEY`, `FINANCE_PULSE_ADMIN_EMAIL`, `FINANCE_PULSE_ADMIN_PASSWORD`) before running `python app.py`.

## Building Distributables Locally

### Desktop Bundles (PyInstaller)

```bash
pip install -r requirements-desktop.txt
python packaging/generate_icons.py --android
# macOS
pyinstaller packaging/macos/finance_pulse_macos.spec --noconfirm
# Windows
pyinstaller packaging/windows/finance_pulse_windows.spec --noconfirm
```

### Android APK (Gradle Wrapper + JDK 17)

```bash
cd android
./gradlew testDebugUnitTest assembleDebug --no-daemon
```

## Automated Tests

```bash
.venv/bin/python -m unittest discover -s tests -v
cd android && ./gradlew testDebugUnitTest --no-daemon
```
