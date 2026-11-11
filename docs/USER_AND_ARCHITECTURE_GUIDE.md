# Finance Pulse Analytics: User Guide & Cross-Platform Architecture

> **Canonical Title:** *Finance Pulse Analytics: Enterprise Financial Performance Intelligence and Profitability Optimization Analytics Platform*

This guide explains how to install and run **Finance Pulse Analytics** on macOS, Windows, Android, or from Python source, along with the analytical formulas powering every intelligence brief, anomaly detector, forecast, and optimization solver.

---

## 1. Quick Installation Summary

| Platform | Package / Entry | Requirements |
| :--- | :--- | :--- |
| **Windows 10/11** | `FinancePulseAnalytics-Windows-unsigned.zip` (`FinancePulseAnalytics.exe`) | None (standalone bundle) |
| **macOS (Apple Silicon & Intel)** | `FinancePulseAnalytics-macOS-unsigned.zip` (`FinancePulseAnalytics.app`) | None (standalone bundle) |
| **Android (8.0+ / SDK 26–34)** | `FinancePulseAnalytics-Android.apk` | Android 8.0 or newer |
| **Developer Source Launch** | `Run_FinancePulse_Mac.command` / `Run_FinancePulse_Windows.bat` | Python 3.9+ |

> **First-Time Unsigned App Approval:**
> - **macOS:** Right-click `FinancePulseAnalytics.app` -> **Open** (or **System Settings -> Privacy & Security -> Open Anyway**).
> - **Windows:** Click **More info -> Run anyway** on SmartScreen for unsigned community builds.

---

## 2. Analytical & Mathematical Methodology

### Core Performance Metrics (`analytics/financial_metrics.py`)
- **Net Profit:** Revenue − Expenses
- **Gross Profit:** Revenue − Cost (COGS)
- **Net Margin (%):** `(Net Profit / Revenue) × 100` (safe zero-revenue handling)
- **Return on Investment (%):** `((Net Profit − Investment) / Investment) × 100`
- **3-Pillar Narrative Briefs (`analytics/intelligence.py`):** Every analytics page renders **`01 · What it is`** (scope and definitions), **`02 · What happened`** (actual leaders, peaks, troughs, period changes), and **`03 · What could have happened`** (quantified upside vs. best-quartile or margin-floor counterfactuals) directly before visualizations.

### Explainable Anomaly Detection (`analytics/anomalies.py`)
Uses deterministic Interquartile Range (IQR) statistical bounds:
- Computes 25th percentile (`Q1`), 75th percentile (`Q3`), and `IQR = Q3 - Q1`.
- Upper bound cutoff: `Cutoff = Q3 + k × IQR` (`k = 1.5` default, configurable by Admin).
- Outputs exact date, entity, metric (`Revenue` / `Expense`), observed amount, cutoff threshold, and recoverable margin impact.

### Trend Forecasting (`analytics/forecasting.py`)
When at least 4 distinct monthly periods exist:
- Fits Ordinary Least Squares (`numpy.polyfit(..., deg=1)`) across monthly Revenue, Expense, or Net Profit.
- Evaluates historical fit transparently via **MAE**, **RMSE**, and **MAPE (%)**.
- Forecasts configurable horizons between **3 and 24 months**.

### Profitability Optimization Solver (`analytics/optimization.py`)
- **Break-Even Revenue Floor:** Minimum revenue required to cover active operating expenses.
- **Target-Margin Solver:** Given desired margin %, computes exact **required expense reduction %** holding revenue constant, or **required revenue lift %** holding expenses constant, with 1-click preset loading into What-If sliders.
- **Segment Profit Levers:** Ranks Product, Department, Category, and Region levers (+10% scale upside for leaders vs. margin-floor recovery for underperformers).

---

## 3. Portal Architecture & Privacy Boundaries

- **Workspace-Isolated User Portal (`/user/*`):** Each user account owns an isolated SQLite workspace (`workspaces` table) so uploaded CSV, XLSX, and JSON datasets and saved What-If scenarios remain strictly separated per user.
- **Admin Governance Portal (`/admin/*`):** Separate login gate (`/admin/login`) automatically clears active user cookies. Supports account status toggling (`active` / `suspended`), global threshold management, and filterable **Audit Logs** (`/admin/audit`).
- **Private Local Admin Desktop App (`dist_private/`):** Excluded from Git via [`.gitignore`](../.gitignore). Can manage a local SQLite file or point to a centrally hosted Flask server via `--remote-url` (`FINANCE_PULSE_REMOTE_URL`).
- **Offline Android Engine (`android/`):** Embeds Chart.js (`chart.umd.min.js`), sample CSV data, a deterministic JS replica of all 4 analytics engines (`mobile_app.js`), a two-layer SHA-256 verified in-app updater (instant OTA asset swaps + native APK upgrades via `ApkFileProvider`), and offline-first automatic wireless sync.

---

## 4. Related Project Documents

- [README](../README.md) — 1-Click downloads & quickstart
- [Presentation Deck (12 Slides)](Finance_Pulse_Analytics_Presentation.pptx) — Full visual overview
- [Product Specification](../PRODUCT.md) — Functional & domain requirements
- [Design System](../DESIGN.md) — Typography, color tokens & component rules
- [CI/CD Workflow](../.github/workflows/ci.yml) — Automated macOS, Windows & Android release builds
