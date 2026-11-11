# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

- **Business Analysts & Finance Leads (User Portal):** Individuals or teams evaluating historical revenue, expenses, COGS, net profit, margins, ROI, anomalies, forecasts, target-margin plans, segment profit levers, and what-if scenarios within a private, workspace-isolated local environment. *(Verified from `app.py` routes and templates; workflow autonomy confirmed from user direction.)*
- **Workspace Administrators (Admin Portal):** Authorized operators at `/admin/login` managing administrator and user accounts (active/suspended governance), inspecting workspace datasets/import quality, reviewing immutable audit logs (`/admin/audit`), and configuring global thresholds (currency, margin warning threshold, IQR anomaly multiplier, forecast horizon, date format). *(Verified from `app.py` admin routes and `README.md`.)*

## Product Purpose

**Finance Pulse Analytics: Enterprise Financial Performance Intelligence and Profitability Optimization Analytics Platform** turns raw transactional CSV, Excel (XLSX), and JSON exports into clear financial performance intelligence—profitability breakdowns across products, departments, categories, and regions; explainable IQR anomaly flags; linear-trend forecasts with error backtesting; target-margin break-even solving; and persisted what-if scenario modeling—with every calculation, chart script, and export running locally on the host machine.

## Positioning

Local-first enterprise financial intelligence without cloud lock-in or black-box estimates: private per-user SQLite workspaces, transparent formula-driven analytics (exact margin/ROI definitions, IQR thresholds, MAE/RMSE/MAPE error metrics alongside linear regression, break-even and target-margin optimization plans), full admin governance and audit trail, and direct CSV and local PDF reporting.

## Operating Context

- Served locally via Flask (`127.0.0.1:5000`) backed by SQLite (`finance_pulse.db`), Pandas, NumPy, ReportLab, and bundled offline Chart.js (`static/js/chart.umd.min.js`).
- Packaging-ready path resolution via `config.py` (`BUNDLE_DIR` for frozen assets, `DATA_DIR` / `FINANCE_PULSE_DATA_DIR` for OS writable storage) and `/health` readiness checks.
- Dual-portal separation: User Portal (`/register`, `/login`, `/user/*`) vs Admin Portal (`/admin/login`, `/admin/*`), with automatic session reset when switching registration or portal entry points.
- Core workflow loop: Register/Sign in -> Upload CSV/XLSX/JSON -> Inspect detected column mapping & data quality -> Confirm import -> Monitor Dashboard KPIs & monthly trend -> Drill down into Products/Departments/Categories/Regions/Anomalies -> Forecast revenue/expense/profit -> Model What-if scenarios -> Export CSV or PDF summary.

## Capabilities and Constraints

- **Must preserve intact (fundamental core):** All routes, HTTP form contracts, database schema, workspace isolation (`workspace_id`), column auto-detection (`data/importer.py`), calculation modules (`analytics/*`), date-range filtering, empty states (`No financial data has been imported yet`, `No matching transactions`), CSV export (`/user/export.csv`), PDF report (`/user/report.pdf`), sample dataset download (`/sample`), and admin configuration bounds (`app.py` + `tests/test_financial_metrics.py`).
- **Constraints:** Supports CSV, XLSX, and JSON up to 16 MB; requires `Date`, `Revenue`, and `Expense` columns; zero fabricated customer claims, pricing tiers, or fake cloud metrics.
- **UI/UX test contract compatibility:** Keep functional markup and copy signals expected by automated verification (`Create your account`, `Administrator sign in`, `Detected column mapping`, `imported successfully`, `No matching transactions`, `Clear date filter`, `Linear trend regression`, `Saved scenarios`, `No financial data has been imported yet`, adjacent dataset/record counts in admin users table).

## Brand Commitments

- **Full Exact Title:** Finance Pulse Analytics: Enterprise Financial Performance Intelligence and Profitability Optimization Analytics Platform.
- **Compact Lockup:** Finance Pulse Analytics.
- **Binding visual standard (user-pinned):** First-in-class, Apple-inspired design aesthetic—refined neutral surfaces, restrained optical typography, deliberate spatial hierarchy, crisp interactive clarity, and tactile micro-interactions—while keeping the fundamental functional core unchanged.

## Evidence on Hand

- Live Flask application (`app.py`), analytics modules (`analytics/*.py`), and passing unit/integration test suite (`tests/test_financial_metrics.py`).
- Bundled synthetic 30-month dataset (`data/sample_data.py` -> `finance_pulse_sample.csv`) covering four products (`Core Suite`, `Insight Pro`, `Advisory`, `Support Plan`), Software & Consulting categories, North/South regions, and an intentional Advisory expense spike anomaly for demonstration.
- Absence: No external cloud integrations, third-party testimonials, customer logos, or pricing plans exist; landing demonstrations must strictly showcase real local capabilities and clearly labeled sample data.

## Product Principles

1. **Explainability over opacity:** Pair every KPI, anomaly flag, forecast, and scenario with the underlying formula, baseline comparison, or accuracy metric.
2. **Strict portal & workspace boundaries:** User financial data stays isolated per workspace; administrative controls remain clearly separated.
3. **Calm precision:** High numerical density reads effortlessly through tabular alignment, clear hierarchy, and zero visual clutter.
4. **Local trust:** Present what the local engine actually computes—no unverified claims or synthetic filler presented as live account data.

## Accessibility & Inclusion

- Meet WCAG AA contrast (≥4.5:1 body, ≥3:1 large text and interactive controls).
- Support keyboard navigation (`:focus-visible`), `prefers-reduced-motion: reduce`, `prefers-reduced-transparency: reduce`, and `prefers-contrast: more`.
- Tabular numeric alignment (`tabular-nums`) and readable minimum UI text sizes (≥11px functional labels, ≥14px body text) across desktop and mobile viewports.
