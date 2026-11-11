import numpy as np
import pandas as pd
import config


def generate():
    bundled = config.SAMPLE_FOLDER / "finance_pulse_sample.csv"
    if bundled.exists():
        return bundled
    try:
        config.SAMPLE_FOLDER.mkdir(parents=True, exist_ok=True)
        target = bundled
    except OSError:
        fallback_dir = config.DATA_DIR / "data" / "sample_data"
        fallback_dir.mkdir(parents=True, exist_ok=True)
        target = fallback_dir / "finance_pulse_sample.csv"
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
