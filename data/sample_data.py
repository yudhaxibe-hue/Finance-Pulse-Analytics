from pathlib import Path
import numpy as np
import pandas as pd
import config


def _writable_sample_target(filename: str) -> Path:
    bundled = config.SAMPLE_FOLDER / filename
    if bundled.exists():
        return bundled
    try:
        config.SAMPLE_FOLDER.mkdir(parents=True, exist_ok=True)
        probe = config.SAMPLE_FOLDER / ".write_probe"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
        return bundled
    except OSError:
        fallback_dir = config.DATA_DIR / "data" / "sample_data"
        fallback_dir.mkdir(parents=True, exist_ok=True)
        return fallback_dir / filename


def generate():
    """Return the compact 120-row 30-month quick-start CSV (deterministic)."""
    target = _writable_sample_target("finance_pulse_sample.csv")
    if target.exists():
        return target
    rng = np.random.default_rng(42)
    months = pd.date_range("2024-01-01", periods=30, freq="MS")
    products = [
        ("Core Suite", "Software", "Product"),
        ("Insight Pro", "Software", "Product"),
        ("Advisory", "Consulting", "Services"),
        ("Support Plan", "Services", "Customer Success"),
    ]
    rows = []
    n = 1
    for i, m in enumerate(months):
        for product, category, department in products:
            revenue = max(20000, 80000 + i * 2400 + rng.normal(0, 9000))
            expense = revenue * (0.58 + rng.normal(0, 0.06))
            if i == 20 and product == "Advisory":
                expense *= 2.2
            rows.append({
                "Date": (m + pd.Timedelta(days=int(rng.integers(1, 25)))).strftime("%Y-%m-%d"),
                "Transaction ID": f"FP-{n:04d}",
                "Transaction Type": "Sale",
                "Category": category,
                "Product": product,
                "Department": department,
                "Region": "North" if n % 2 else "South",
                "Revenue": round(revenue, 2),
                "Expense": round(expense, 2),
                "Cost": round(revenue * 0.25, 2),
                "Quantity": int(rng.integers(20, 100)),
                "Unit Price": round(revenue / 50, 2),
                "Investment": 5000 if n % 5 == 0 else 0,
                "Notes": "Fictional sample transaction",
            })
            n += 1
    pd.DataFrame(rows).to_csv(target, index=False)
    return target


def build_enterprise_10k_dataframe(n_rows: int = 10000, seed: int = 2026) -> pd.DataFrame:
    """Build a clean, validated 10,000-record x 26-field enterprise financial dataframe."""
    rng = np.random.default_rng(seed)

    start_date = np.datetime64("2023-01-01")
    end_days = 1400  # ~46 months spanning 2023-2026 cleanly
    day_offsets = rng.integers(0, end_days, size=n_rows)
    dates = pd.to_datetime(start_date) + pd.to_timedelta(day_offsets, unit="D")

    catalog = [
        ("Core Suite", "Software", "SaaS Licenses", "Product", "CC-101", 88000.0, 0.44),
        ("Insight Pro", "Software", "AI Analytics", "Product", "CC-102", 74000.0, 0.48),
        ("Cloud Ledger", "Software", "FinOps", "Engineering", "CC-105", 66000.0, 0.52),
        ("Advisory", "Consulting", "Risk Strategy", "Services", "CC-201", 52000.0, 0.67),
        ("Audit Assurance", "Consulting", "Compliance", "Finance", "CC-204", 49000.0, 0.61),
        ("Support Plan", "Services", "Enterprise Care", "Customer Success", "CC-301", 41000.0, 0.59),
        ("Managed Ops", "Operations", "Infrastructure", "Operations", "CC-401", 36000.0, 0.78),
        ("Growth Campaign", "Marketing", "Demand Gen", "Marketing", "CC-501", 28000.0, 0.86),
    ]
    cat_idx = rng.integers(0, len(catalog), size=n_rows)

    geo = [
        ("North", "India"),
        ("South", "India"),
        ("West", "India"),
        ("East", "Singapore"),
        ("North America", "United States"),
        ("EMEA", "United Kingdom"),
    ]
    geo_idx = rng.integers(0, len(geo), size=n_rows)

    channels = np.array(["Direct", "Enterprise", "Partner", "Online", "Marketplace"])
    payments = np.array(["Bank Transfer", "Corporate Card", "UPI / Instant", "Wire", "Invoice Net-30"])
    segments = np.array(["Enterprise", "Mid-Market", "SMB", "Government"])
    vendors = np.array([
        "Apex Cloud Systems", "Meridian Advisory", "Vertex Infra", "Vanguard Telco",
        "Direct Enterprise Account", "Horizon Logistics", "Prism Media", "Sterling Partners",
    ])
    txn_types = np.array(["Sale", "Subscription", "Service Retainer", "Operating Expense", "Renewal"])

    month_nums = dates.month.to_numpy()
    year_nums = dates.year.to_numpy()
    seasonal = 1.0 + 0.14 * np.sin((month_nums - 1) * np.pi / 6.0) + 0.05 * (year_nums - 2023)

    products = np.array([catalog[i][0] for i in cat_idx], dtype=object)
    categories = np.array([catalog[i][1] for i in cat_idx], dtype=object)
    subcategories = np.array([catalog[i][2] for i in cat_idx], dtype=object)
    departments = np.array([catalog[i][3] for i in cat_idx], dtype=object)
    cost_centers = np.array([catalog[i][4] for i in cat_idx], dtype=object)
    base_rev = np.array([catalog[i][5] for i in cat_idx], dtype=float)
    base_exp_ratio = np.array([catalog[i][6] for i in cat_idx], dtype=float)

    regions = np.array([geo[i][0] for i in geo_idx], dtype=object)
    countries = np.array([geo[i][1] for i in geo_idx], dtype=object)

    qty = rng.integers(5, 160, size=n_rows)
    revenue = np.maximum(5000.0, np.round(base_rev * seasonal * rng.normal(1.0, 0.22, size=n_rows), 2))
    expense_ratio = np.clip(base_exp_ratio + rng.normal(0.0, 0.075, size=n_rows), 0.22, 1.08)
    expense = np.round(revenue * expense_ratio, 2)

    # Inject realistic high-spend anomalies (~1.8% of ledger) for Random Forest / Isolation Forest training
    outlier_mask = rng.random(n_rows) < 0.018
    expense[outlier_mask] = np.round(expense[outlier_mask] * rng.uniform(1.85, 2.75, size=int(outlier_mask.sum())), 2)

    cost = np.round(revenue * rng.uniform(0.18, 0.34, size=n_rows), 2)
    tax_amount = np.round(revenue * 0.12, 2)
    discount_amount = np.round(np.where(rng.random(n_rows) < 0.35, revenue * rng.uniform(0.02, 0.09, size=n_rows), 0.0), 2)
    unit_price = np.round(revenue / np.maximum(1, qty), 2)
    investment = np.where((np.arange(n_rows) % 12) == 0, np.round(rng.uniform(2500.0, 9500.0, size=n_rows), 2), 0.0)

    quarters = np.array([f"Q{((m - 1) // 3) + 1}" for m in month_nums], dtype=object)
    txn_ids = [f"ENT-{i + 1:05d}" for i in range(n_rows)]

    notes = np.where(
        outlier_mask,
        "Unscheduled surge billing flagged for variance review",
        "Verified enterprise ledger transaction",
    )

    return pd.DataFrame({
        "Date": dates.strftime("%Y-%m-%d"),
        "Transaction ID": txn_ids,
        "Transaction Type": txn_types[rng.integers(0, len(txn_types), size=n_rows)],
        "Fiscal Year": year_nums.astype(int),
        "Fiscal Quarter": quarters,
        "Category": categories,
        "Subcategory": subcategories,
        "Product": products,
        "Department": departments,
        "Cost Center": cost_centers,
        "Region": regions,
        "Country": countries,
        "Channel": channels[rng.integers(0, len(channels), size=n_rows)],
        "Payment Method": payments[rng.integers(0, len(payments), size=n_rows)],
        "Currency": np.full(n_rows, "INR", dtype=object),
        "Customer Segment": segments[rng.integers(0, len(segments), size=n_rows)],
        "Vendor Name": vendors[rng.integers(0, len(vendors), size=n_rows)],
        "Revenue": revenue,
        "Expense": expense,
        "Cost": cost,
        "Tax Amount": tax_amount,
        "Discount Amount": discount_amount,
        "Quantity": qty,
        "Unit Price": unit_price,
        "Investment": investment,
        "Notes": notes,
    })


def generate_enterprise_10k(force: bool = False) -> Path:
    """Ensure the 10,000-record x 26-field benchmark CSV exists on disk cleanly."""
    target = _writable_sample_target("finance_pulse_enterprise_10k.csv")
    if target.exists() and not force:
        return target
    df = build_enterprise_10k_dataframe(n_rows=10000, seed=2026)
    df.to_csv(target, index=False)
    return target
