(function () {
  "use strict";

  const STORAGE_KEY_ROWS = "fp_mobile_rows_v1";
  const STORAGE_KEY_META = "fp_mobile_meta_v1";
  const STORAGE_KEY_CFG = "fp_mobile_cfg_v1";

  const DEFAULT_CFG = { currency: "INR", marginThreshold: 15, anomalyIqr: 1.5 };

  let state = {
    rows: [],
    meta: { source: "None", loadedAt: "" },
    cfg: loadCfg(),
    activeTab: "overview",
    overviewMode: "combo",
    segmentDim: "product",
    segmentMode: "margin",
    anomalyMode: "compare",
    charts: {},
  };

  function loadCfg() {
    try {
      const raw = localStorage.getItem(STORAGE_KEY_CFG);
      return raw ? Object.assign({}, DEFAULT_CFG, JSON.parse(raw)) : Object.assign({}, DEFAULT_CFG);
    } catch (_e) {
      return Object.assign({}, DEFAULT_CFG);
    }
  }

  function saveCfg() {
    try { localStorage.setItem(STORAGE_KEY_CFG, JSON.stringify(state.cfg)); } catch (_e) {}
  }

  function saveWorkspace(rows, sourceName) {
    state.rows = rows;
    state.meta = { source: sourceName, loadedAt: new Date().toLocaleTimeString() };
    try {
      localStorage.setItem(STORAGE_KEY_ROWS, JSON.stringify(rows));
      localStorage.setItem(STORAGE_KEY_META, JSON.stringify(state.meta));
    } catch (_e) {}
  }

  function loadWorkspace() {
    try {
      const rawRows = localStorage.getItem(STORAGE_KEY_ROWS);
      const rawMeta = localStorage.getItem(STORAGE_KEY_META);
      if (rawRows) {
        const parsed = JSON.parse(rawRows);
        if (Array.isArray(parsed) && parsed.length) {
          state.rows = parsed;
          state.meta = rawMeta ? JSON.parse(rawMeta) : { source: "Saved workspace", loadedAt: "" };
          return;
        }
      }
    } catch (_e) {}
    if (window.FINANCE_PULSE_SAMPLE_CSV) {
      const rows = parseCsv(window.FINANCE_PULSE_SAMPLE_CSV);
      saveWorkspace(rows, "finance_pulse_sample.csv (auto-loaded)");
    }
  }

  function fmtNum(v, decimals) {
    if (v === null || v === undefined || Number.isNaN(v)) return "N/A";
    const d = decimals === undefined ? 0 : decimals;
    return Number(v).toLocaleString("en-US", { minimumFractionDigits: d, maximumFractionDigits: d });
  }

  function fmtCurr(v) {
    return state.cfg.currency + " " + fmtNum(v, 0);
  }

  function esc(str) {
    return String(str === null || str === undefined ? "" : str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function parseCsv(text) {
    const clean = text.replace(/^\uFEFF/, "").trim();
    if (!clean) return [];
    const lines = [];
    let row = [];
    let cell = "";
    let inQuotes = false;
    for (let i = 0; i < clean.length; i++) {
      const ch = clean[i];
      if (inQuotes) {
        if (ch === '"' && clean[i + 1] === '"') {
          cell += '"';
          i++;
        } else if (ch === '"') {
          inQuotes = false;
        } else {
          cell += ch;
        }
      } else if (ch === '"') {
        inQuotes = true;
      } else if (ch === ",") {
        row.push(cell);
        cell = "";
      } else if (ch === "\n" || ch === "\r") {
        if (ch === "\r" && clean[i + 1] === "\n") i++;
        row.push(cell);
        if (row.some((c) => c.trim() !== "")) lines.push(row);
        row = [];
        cell = "";
      } else {
        cell += ch;
      }
    }
    row.push(cell);
    if (row.some((c) => c.trim() !== "")) lines.push(row);
    if (lines.length < 2) return [];

    const headers = lines[0].map((h) => h.trim());
    const rawObjects = [];
    for (let r = 1; r < lines.length; r++) {
      const obj = {};
      for (let c = 0; c < headers.length; c++) {
        obj[headers[c]] = (lines[r][c] || "").trim();
      }
      rawObjects.push(obj);
    }
    return normalizeObjects(rawObjects);
  }

  function normalizeObjects(objects) {
    if (!Array.isArray(objects) || !objects.length) return [];
    const aliasMap = {
      date: ["date", "sales date", "transaction date", "txn date", "txn_date"],
      transaction_id: ["transaction id", "transaction_id", "id", "invoice id"],
      category: ["category", "segment"],
      product: ["product", "item"],
      department: ["department", "dept"],
      region: ["region", "location"],
      revenue: ["revenue", "sales", "income", "amount"],
      expense: ["expense", "expenses", "cost"],
      cost: ["cost", "cogs", "cost of goods sold"],
      investment: ["investment"],
    };
    const keys = Object.keys(objects[0] || {});
    const lowerLookup = {};
    keys.forEach((k) => { lowerLookup[k.trim().toLowerCase()] = k; });
    const mapped = {};
    Object.keys(aliasMap).forEach((canon) => {
      for (const alias of aliasMap[canon]) {
        if (lowerLookup[alias] !== undefined) {
          mapped[canon] = lowerLookup[alias];
          break;
        }
      }
    });

    const out = [];
    for (const raw of objects) {
      const dStr = mapped.date ? String(raw[mapped.date] || "").trim() : "";
      const parsedDate = new Date(dStr);
      if (!dStr || Number.isNaN(parsedDate.getTime())) continue;
      const rev = Number(mapped.revenue ? raw[mapped.revenue] : 0) || 0;
      const exp = Number(mapped.expense ? raw[mapped.expense] : 0) || 0;
      if (rev < 0 || exp < 0) continue;
      const month = parsedDate.toISOString().slice(0, 7);
      out.push({
        txn_date: parsedDate.toISOString().slice(0, 10),
        period: month,
        transaction_id: mapped.transaction_id ? String(raw[mapped.transaction_id] || "") : "",
        category: (mapped.category ? String(raw[mapped.category] || "").trim() : "") || "Uncategorized",
        product: (mapped.product ? String(raw[mapped.product] || "").trim() : "") || "Unspecified",
        department: (mapped.department ? String(raw[mapped.department] || "").trim() : "") || "General",
        region: (mapped.region ? String(raw[mapped.region] || "").trim() : "") || "Global",
        revenue: rev,
        expense: exp,
        cost: Number(mapped.cost ? raw[mapped.cost] : 0) || 0,
        investment: Number(mapped.investment ? raw[mapped.investment] : 0) || 0,
      });
    }
    return out;
  }

  function computeMetrics(rows) {
    let revenue = 0, expenses = 0, cost = 0, investment = 0;
    for (const r of rows) {
      revenue += r.revenue;
      expenses += r.expense;
      cost += r.cost;
      investment += r.investment;
    }
    const profit = revenue - expenses;
    const margin = revenue > 0 ? (profit / revenue) * 100 : 0;
    const expenseRatio = revenue > 0 ? (expenses / revenue) * 100 : 0;
    const roi = investment > 0 ? ((profit - investment) / investment) * 100 : 0;
    return {
      revenue: round2(revenue),
      expenses: round2(expenses),
      cost: round2(cost),
      profit: round2(profit),
      gross_profit: round2(revenue - cost),
      margin: round2(margin),
      expense_ratio: round2(expenseRatio),
      roi: round2(roi),
      transactions: rows.length,
    };
  }

  function monthlySeries(rows) {
    const map = {};
    for (const r of rows) {
      if (!map[r.period]) map[r.period] = { period: r.period, revenue: 0, expense: 0 };
      map[r.period].revenue += r.revenue;
      map[r.period].expense += r.expense;
    }
    const sorted = Object.values(map).sort((a, b) => a.period.localeCompare(b.period));
    let running = 0;
    return sorted.map((m) => {
      const profit = m.revenue - m.expense;
      running += profit;
      const margin = m.revenue > 0 ? (profit / m.revenue) * 100 : 0;
      return {
        period: m.period,
        revenue: round2(m.revenue),
        expense: round2(m.expense),
        profit: round2(profit),
        cum_profit: round2(running),
        margin: round2(margin),
      };
    });
  }

  function byDimension(rows, field) {
    const map = {};
    for (const r of rows) {
      const key = r[field] || "Unspecified";
      if (!map[key]) map[key] = { label: key, revenue: 0, expense: 0, count: 0 };
      map[key].revenue += r.revenue;
      map[key].expense += r.expense;
      map[key].count += 1;
    }
    return Object.values(map)
      .map((item) => {
        const profit = item.revenue - item.expense;
        const margin = item.revenue > 0 ? round2((profit / item.revenue) * 100) : null;
        return { label: item.label, revenue: round2(item.revenue), expense: round2(item.expense), profit: round2(profit), margin, count: item.count };
      })
      .sort((a, b) => b.profit - a.profit);
  }

  function quantile(sortedArr, q) {
    if (!sortedArr.length) return 0;
    const pos = (sortedArr.length - 1) * q;
    const base = Math.floor(pos);
    const rest = pos - base;
    if (sortedArr[base + 1] !== undefined) {
      return sortedArr[base] + rest * (sortedArr[base + 1] - sortedArr[base]);
    }
    return sortedArr[base];
  }

  function detectAnomalies(rows, multiplier) {
    const flags = [];
    ["revenue", "expense"].forEach((col) => {
      const vals = rows.map((r) => r[col]).slice().sort((a, b) => a - b);
      if (vals.length < 4) return;
      const q1 = quantile(vals, 0.25);
      const q3 = quantile(vals, 0.75);
      const iqr = q3 - q1;
      if (iqr <= 0) return;
      const cutoff = q3 + multiplier * iqr;
      rows.forEach((r) => {
        if (r[col] > cutoff) {
          flags.push({
            date: r.txn_date,
            metric: col.charAt(0).toUpperCase() + col.slice(1),
            entity: r.product || r.category || "Entry",
            value: round2(r[col]),
            threshold: round2(cutoff),
          });
        }
      });
    });
    return flags.sort((a, b) => (b.value - b.threshold) - (a.value - a.threshold));
  }

  function computeForecast(series, horizon) {
    if (series.length < 3) return null;
    const n = series.length;
    const y = series.map((s) => s.profit);
    let sumX = 0, sumY = 0, sumXY = 0, sumXX = 0;
    for (let i = 0; i < n; i++) {
      sumX += i;
      sumY += y[i];
      sumXY += i * y[i];
      sumXX += i * i;
    }
    const denom = n * sumXX - sumX * sumX;
    const slope = denom !== 0 ? (n * sumXY - sumX * sumY) / denom : 0;
    const intercept = (sumY - slope * sumX) / n;

    let absErr = 0, sqErr = 0, apeSum = 0, apeCount = 0;
    for (let i = 0; i < n; i++) {
      const pred = slope * i + intercept;
      const err = Math.abs(y[i] - pred);
      absErr += err;
      sqErr += err * err;
      if (Math.abs(y[i]) > 1e-6) {
        apeSum += err / Math.abs(y[i]);
        apeCount += 1;
      }
    }
    const mae = round2(absErr / n);
    const rmse = round2(Math.sqrt(sqErr / n));
    const mape = apeCount ? round2((apeSum / apeCount) * 100) : 0;

    const lastDate = new Date(series[n - 1].period + "-01T00:00:00");
    const future = [];
    for (let step = 1; step <= horizon; step++) {
      const d = new Date(lastDate.getFullYear(), lastDate.getMonth() + step, 1);
      const label = d.getFullYear() + "-" + String(d.getMonth() + 1).padStart(2, "0");
      future.push({ period: label, forecast: round2(slope * (n - 1 + step) + intercept) });
    }
    return {
      slope: round2(slope),
      mae,
      rmse,
      mape,
      history: series.map((s) => ({ period: s.period, actual: s.profit })),
      future,
    };
  }

  function round2(n) {
    return Math.round((Number(n) + Number.EPSILON) * 100) / 100;
  }

  function renderBrief(elId, tag, headline, p1, p2, p3) {
    const el = document.getElementById(elId);
    if (!el) return;
    el.innerHTML =
      '<div class="intel-brief-head">' +
        '<span class="intel-tag">' + esc(tag) + '</span>' +
      '</div>' +
      '<h2 class="intel-headline">' + esc(headline) + '</h2>' +
      '<div class="intel-pillars">' +
        '<div class="intel-col"><span class="intel-step">01 · What it is</span><p>' + esc(p1) + '</p></div>' +
        '<div class="intel-col"><span class="intel-step">02 · What happened</span><p>' + esc(p2) + '</p></div>' +
        '<div class="intel-col"><span class="intel-step">03 · What could have happened</span><p>' + esc(p3) + '</p></div>' +
      '</div>';
  }

  function destroyChart(key) {
    if (state.charts[key]) {
      state.charts[key].destroy();
      state.charts[key] = null;
    }
  }

  function renderOverview() {
    const m = computeMetrics(state.rows);
    const series = monthlySeries(state.rows);
    const kpiEl = document.getElementById("overviewKpis");
    kpiEl.innerHTML =
      kpiCard("Total revenue", fmtCurr(m.revenue), m.transactions + " rows") +
      kpiCard("Operating expenses", fmtCurr(m.expenses), fmtNum(m.expense_ratio, 1) + "% of revenue") +
      kpiCard("Net profit", fmtCurr(m.profit), fmtNum(m.margin, 1) + "% margin", m.profit >= 0 ? "pos" : "neg") +
      kpiCard("Return on investment", fmtNum(m.roi, 1) + "%", "Gross " + fmtCurr(m.gross_profit));

    if (!series.length) {
      renderBrief("overviewBrief", "Overview intelligence", "No valid transactions loaded yet.",
        "Tracks aggregate cashflow across your imported ledger.",
        "Import a CSV/JSON file or load the sample dataset above.",
        "Once imported, break-even and segment levers compute automatically.");
      destroyChart("overview");
      return;
    }

    const best = series.slice().sort((a, b) => b.profit - a.profit)[0];
    const worst = series.slice().sort((a, b) => a.profit - b.profit)[0];
    const first = series[0], last = series[series.length - 1];
    const avgMargin = series.reduce((a, b) => a + b.margin, 0) / series.length;
    const altProfit = round2((m.revenue * Math.max(state.cfg.marginThreshold, avgMargin)) / 100);
    const gap = round2(Math.max(0, altProfit - m.profit));

    renderBrief(
      "overviewBrief",
      "Executive intelligence brief",
      "Net margin closed at " + fmtNum(m.margin, 1) + "% across " + series.length + " months (" + fmtCurr(m.profit) + ").",
      "Evaluates monthly cashflow progression from " + first.period + " to " + last.period + " across " + fmtNum(m.transactions) + " ledger entries.",
      "Peak month reached " + best.period + " (" + fmtCurr(best.profit) + ", " + fmtNum(best.margin, 1) + "% margin) while softest performance occurred in " + worst.period + " (" + fmtCurr(worst.profit) + ").",
      gap > 0
        ? "Holding the target margin threshold across softer periods would have added " + fmtCurr(gap) + " in cumulative net profit."
        : "Margin stability exceeded the " + state.cfg.marginThreshold + "% target threshold throughout the period."
    );

    destroyChart("overview");
    const ctx = document.getElementById("overviewCanvas").getContext("2d");
    const labels = series.map((s) => s.period);
    if (state.overviewMode === "cumulative") {
      state.charts.overview = new Chart(ctx, {
        type: "line",
        data: {
          labels,
          datasets: [{ label: "Cumulative Profit", data: series.map((s) => s.cum_profit), borderColor: "#0066CC", backgroundColor: "rgba(0,102,204,0.12)", fill: true, tension: 0.25 }]
        },
        options: chartOptions(false)
      });
    } else if (state.overviewMode === "margin") {
      state.charts.overview = new Chart(ctx, {
        type: "bar",
        data: {
          labels,
          datasets: [{ label: "Monthly Margin %", data: series.map((s) => s.margin), backgroundColor: series.map((s) => s.margin >= state.cfg.marginThreshold ? "#0E6027" : "#A61B1B"), borderRadius: 4 }]
        },
        options: chartOptions(false)
      });
    } else {
      state.charts.overview = new Chart(ctx, {
        type: "bar",
        data: {
          labels,
          datasets: [
            { label: "Revenue", data: series.map((s) => s.revenue), backgroundColor: "#0066CC", borderRadius: 4, order: 2 },
            { label: "Expense", data: series.map((s) => s.expense), backgroundColor: "#C2590A", borderRadius: 4, order: 3 },
            { type: "line", label: "Net Profit", data: series.map((s) => s.profit), borderColor: "#0E6027", backgroundColor: "#0E6027", tension: 0.25, borderWidth: 2.2, order: 1 }
          ]
        },
        options: chartOptions(false)
      });
    }
  }

  function renderSegments() {
    const dim = state.segmentDim;
    const rows = byDimension(state.rows, dim);
    if (!rows.length) return;
    const leader = rows[0];
    const laggard = rows[rows.length - 1];
    const posProfit = rows.reduce((a, b) => a + Math.max(0, b.profit), 0);
    const sharePct = posProfit > 0 ? round2((Math.max(0, leader.profit) / posProfit) * 100) : 0;

    const dimLabel = dim.charAt(0).toUpperCase() + dim.slice(1);
    renderBrief(
      "segmentBrief",
      dimLabel + " intelligence",
      leader.label + " led profitability at " + fmtCurr(leader.profit) + " (" + sharePct + "% positive share).",
      "Aggregates revenue, operating costs, net margin, and transaction count by " + dim + " (" + rows.length + " segments).",
      "Top margin performer: " + leader.label + " (" + fmtNum(leader.margin, 1) + "%). Lowest ranking: " + laggard.label + " (" + fmtCurr(laggard.profit) + ").",
      laggard.margin !== null && laggard.margin < state.cfg.marginThreshold
        ? "Lifting " + laggard.label + " to the " + state.cfg.marginThreshold + "% margin floor would recover +" + fmtCurr(Math.max(0, (laggard.revenue * state.cfg.marginThreshold) / 100 - laggard.profit)) + " in profit."
        : "Expanding volume +10% in " + leader.label + " projects +" + fmtCurr(round2(leader.profit * 0.1)) + " incremental margin."
    );

    const tbl = document.getElementById("segmentTable");
    tbl.innerHTML =
      "<thead><tr><th>" + esc(dimLabel) + "</th><th class='num'>Revenue</th><th class='num'>Expense</th><th class='num'>Profit</th><th class='num'>Margin %</th></tr></thead><tbody>" +
      rows.map((r) => {
        const cls = (r.margin || 0) >= state.cfg.marginThreshold ? "ok" : "warn";
        return "<tr><td>" + esc(r.label) + "</td><td class='num'>" + fmtNum(r.revenue) + "</td><td class='num'>" + fmtNum(r.expense) + "</td><td class='num'>" + fmtNum(r.profit) + "</td><td class='num'><span class='badge " + cls + "'>" + fmtNum(r.margin, 1) + "%</span></td></tr>";
      }).join("") +
      "</tbody>";

    destroyChart("segment");
    const ctx = document.getElementById("segmentCanvas").getContext("2d");
    const labels = rows.map((r) => r.label);
    let mode = state.segmentMode;
    if (mode === "share" && rows.filter((r) => r.profit > 0).length < 2) mode = "margin";

    if (mode === "share") {
      const posRows = rows.filter((r) => r.profit > 0);
      state.charts.segment = new Chart(ctx, {
        type: "doughnut",
        data: {
          labels: posRows.map((r) => r.label),
          datasets: [{ data: posRows.map((r) => r.profit), backgroundColor: ["#1D1D1F", "#0066CC", "#0E6027", "#C2590A", "#636368", "#515154"] }]
        },
        options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { position: "bottom" } } }
      });
    } else if (mode === "revprofit") {
      state.charts.segment = new Chart(ctx, {
        type: "bar",
        data: {
          labels,
          datasets: [
            { label: "Revenue", data: rows.map((r) => r.revenue), backgroundColor: "#0066CC", borderRadius: 4 },
            { label: "Profit", data: rows.map((r) => r.profit), backgroundColor: "#0E6027", borderRadius: 4 }
          ]
        },
        options: chartOptions(false)
      });
    } else {
      state.charts.segment = new Chart(ctx, {
        type: "bar",
        data: {
          labels,
          datasets: [{ label: "Margin %", data: rows.map((r) => r.margin || 0), backgroundColor: rows.map((r) => (r.margin || 0) >= state.cfg.marginThreshold ? "#0E6027" : "#A61B1B"), borderRadius: 4 }]
        },
        options: chartOptions(true)
      });
    }
  }

  function renderAnomalies() {
    const flags = detectAnomalies(state.rows, state.cfg.anomalyIqr);
    const m = computeMetrics(state.rows);
    const totalExcess = flags.reduce((a, f) => a + Math.max(0, f.value - f.threshold), 0);

    if (!flags.length) {
      renderBrief("anomalyBrief", "Anomaly surveillance",
        "Zero outliers detected at " + state.cfg.anomalyIqr + "x IQR.",
        "Monitors transaction-level revenue and expense spikes above Q3 + " + state.cfg.anomalyIqr + " × IQR.",
        "All " + state.rows.length + " transactions remained inside normal interquartile operating bounds.",
        "Lowering the IQR multiplier under Server & Settings tightens sensitivity for minor variances.");
      destroyChart("anomaly");
      document.getElementById("anomalyTable").innerHTML = "<tbody><tr><td>No outliers flagged above threshold.</td></tr></tbody>";
      return;
    }

    const top = flags[0];
    renderBrief(
      "anomalyBrief",
      "Anomaly surveillance",
      (flags.length === 1 ? "1 anomalous entry" : flags.length + " anomalous entries") + " flagged with " + fmtCurr(totalExcess) + " above cutoff.",
      "Screens revenue & expense outliers exceeding Q3 + " + state.cfg.anomalyIqr + " × IQR across " + state.rows.length + " entries.",
      "Largest variance occurred in " + top.entity + " (" + top.date + ") where " + top.metric + " hit " + fmtCurr(top.value) + " vs. cutoff " + fmtCurr(top.threshold) + ".",
      "Preventing excess cost spikes above statistical cutoffs would have preserved +" + fmtCurr(totalExcess) + " (~" + fmtNum(m.revenue > 0 ? (totalExcess / m.revenue) * 100 : 0, 1) + " pts margin)."
    );

    const tbl = document.getElementById("anomalyTable");
    tbl.innerHTML =
      "<thead><tr><th>Date</th><th>Entity</th><th>Metric</th><th class='num'>Observed</th><th class='num'>IQR Cutoff</th></tr></thead><tbody>" +
      flags.map((f) => "<tr><td>" + esc(f.date) + "</td><td>" + esc(f.entity) + "</td><td>" + esc(f.metric) + "</td><td class='num'>" + fmtNum(f.value) + "</td><td class='num'>" + fmtNum(f.threshold) + "</td></tr>").join("") +
      "</tbody>";

    destroyChart("anomaly");
    const ctx = document.getElementById("anomalyCanvas").getContext("2d");
    const topFlags = flags.slice(0, 8);
    const labels = topFlags.map((f) => f.date + " " + f.entity);
    state.charts.anomaly = new Chart(ctx, {
      type: "bar",
      data: state.anomalyMode === "excess"
        ? { labels, datasets: [{ label: "Excess Above Cutoff", data: topFlags.map((f) => round2(f.value - f.threshold)), backgroundColor: "#A61B1B", borderRadius: 4 }] }
        : {
            labels,
            datasets: [
              { label: "Observed", data: topFlags.map((f) => f.value), backgroundColor: "#A61B1B", borderRadius: 4 },
              { label: "IQR Cutoff", data: topFlags.map((f) => f.threshold), backgroundColor: "rgba(29,29,31,0.28)", borderRadius: 4 }
            ]
          },
      options: chartOptions(true)
    });
  }

  function renderForecastAndOptimizer() {
    const series = monthlySeries(state.rows);
    const horizon = Number(document.getElementById("forecastMonths").value || 6);
    const fc = computeForecast(series, horizon);
    const m = computeMetrics(state.rows);

    if (!fc) {
      renderBrief("forecastBrief", "Forecast & solver intelligence", "At least 3 monthly periods are required.",
        "Linear OLS regression projects profit trajectories over 3–24 months.",
        "Current dataset contains fewer than 3 distinct monthly periods.",
        "Import multi-month history to unlock backtested projections.");
      destroyChart("forecast");
    } else {
      const dir = fc.slope >= 0 ? "expanding +" : "contracting ";
      const endVal = fc.future[fc.future.length - 1].forecast;
      renderBrief(
        "forecastBrief",
        "Forecast intelligence brief",
        "Trend slope is " + dir + fmtCurr(fc.slope) + "/month toward " + fmtCurr(endVal) + " in " + horizon + " months.",
        "OLS linear regression across " + series.length + " historical months (MAE " + fmtCurr(fc.mae) + ", MAPE " + fmtNum(fc.mape, 1) + "%).",
        "Historical fit tracks net monthly profit progression with RMSE of " + fmtCurr(fc.rmse) + ".",
        "Improving monthly operational capture shifts every future projected period proportionately."
      );
      document.getElementById("forecastMetricsText").textContent =
        "Linear trend regression · MAE " + fmtNum(fc.mae) + " · RMSE " + fmtNum(fc.rmse) + " · MAPE " + fmtNum(fc.mape, 1) + "%";

      destroyChart("forecast");
      const labels = fc.history.map((h) => h.period).concat(fc.future.map((f) => f.period));
      const actualData = fc.history.map((h) => h.actual).concat(fc.future.map(() => null));
      const projData = fc.history.map((h, i) => i === fc.history.length - 1 ? h.actual : null).concat(fc.future.map((f) => f.forecast));
      state.charts.forecast = new Chart(document.getElementById("forecastCanvas").getContext("2d"), {
        type: "line",
        data: {
          labels,
          datasets: [
            { label: "Actual Profit", data: actualData, borderColor: "#1D1D1F", backgroundColor: "#1D1D1F", tension: 0.25 },
            { label: "Linear Forecast", data: projData, borderColor: "#0066CC", borderDash: [6, 5], tension: 0.2 }
          ]
        },
        options: chartOptions(false)
      });
    }

    // Target-margin solver + What-if simulation
    const targetPct = Number(document.getElementById("targetMarginRange").value || 25);
    document.getElementById("targetMarginVal").textContent = targetPct + "%";
    const neededRev = targetPct < 100 ? (m.expenses / (1 - targetPct / 100)) : m.revenue;
    const reqRevLift = m.revenue > 0 ? ((neededRev - m.revenue) / m.revenue) * 100 : 0;
    const reqExpCap = m.revenue * (1 - targetPct / 100);
    const expCutPct = m.expenses > 0 ? ((reqExpCap - m.expenses) / m.expenses) * 100 : 0;

    document.getElementById("solverSummary").innerHTML =
      '<div class="kpi-label">Break-even floor &amp; ' + targetPct + '% target</div>' +
      '<div class="kpi-value num">' + fmtCurr(m.expenses) + '</div>' +
      '<div class="kpi-note num">Requires ' + (reqRevLift >= 0 ? "+" : "") + fmtNum(reqRevLift, 1) + "% rev or " + fmtNum(expCutPct, 1) + "% exp adjustment</div>";

    const simRev = Number(document.getElementById("simRevRange").value || 0);
    const simExp = Number(document.getElementById("simExpRange").value || 0);
    document.getElementById("simRevVal").textContent = (simRev >= 0 ? "+" : "") + simRev + "%";
    document.getElementById("simExpVal").textContent = (simExp >= 0 ? "+" : "") + simExp + "%";

    const projRev = m.revenue * (1 + simRev / 100);
    const projExp = m.expenses * (1 + simExp / 100);
    const projProfit = projRev - projExp;
    const projMargin = projRev > 0 ? (projProfit / projRev) * 100 : 0;
    document.getElementById("simKpis").innerHTML =
      kpiCard("Projected revenue", fmtCurr(projRev), (simRev >= 0 ? "+" : "") + simRev + "%") +
      kpiCard("Projected expenses", fmtCurr(projExp), (simExp >= 0 ? "+" : "") + simExp + "%") +
      kpiCard("Projected profit", fmtCurr(projProfit), "Delta " + fmtCurr(projProfit - m.profit), projProfit >= m.profit ? "pos" : "neg") +
      kpiCard("Projected margin", fmtNum(projMargin, 1) + "%", "Target " + targetPct + "%");
  }

  function kpiCard(label, value, note, valClass) {
    return '<div class="kpi-cell"><div class="kpi-label">' + esc(label) + '</div><div class="kpi-value num ' + (valClass || "") + '">' + esc(value) + '</div><div class="kpi-note num">' + esc(note) + '</div></div>';
  }

  function chartOptions(horizontal) {
    return {
      responsive: true,
      maintainAspectRatio: false,
      indexAxis: horizontal ? "y" : "x",
      plugins: { legend: { position: "bottom", labels: { boxWidth: 12 } } },
      scales: {
        x: { grid: { color: "rgba(0,0,0,0.05)" } },
        y: { grid: { color: "rgba(0,0,0,0.05)" } }
      }
    };
  }

  function renderAll() {
    document.getElementById("currencyBadge").textContent = state.cfg.currency;
    document.getElementById("workspaceSummary").innerHTML =
      "<strong>" + esc(state.meta.source) + "</strong> · " + state.rows.length + " local records";
    document.getElementById("cfgCurrency").value = state.cfg.currency;
    document.getElementById("cfgMargin").value = state.cfg.marginThreshold;
    document.getElementById("cfgIqr").value = state.cfg.anomalyIqr;
    if (window.AndroidBridge && window.AndroidBridge.getSavedServer) {
      document.getElementById("serverUrlInput").value = window.AndroidBridge.getSavedServer() || "";
    }

    if (state.activeTab === "overview") renderOverview();
    else if (state.activeTab === "segments") renderSegments();
    else if (state.activeTab === "anomalies") renderAnomalies();
    else if (state.activeTab === "forecast") renderForecastAndOptimizer();
  }

  function switchTab(tabName) {
    state.activeTab = tabName;
    document.querySelectorAll(".bottom-nav .nav-item").forEach((b) => b.classList.toggle("is-active", b.dataset.tab === tabName));
    document.querySelectorAll(".tab-pane").forEach((p) => p.classList.toggle("hidden", p.id !== "tab-" + tabName));
    window.scrollTo({ top: 0, behavior: "instant" });
    renderAll();
  }

  function bindEvents() {
    document.querySelectorAll(".bottom-nav .nav-item").forEach((b) => b.addEventListener("click", () => switchTab(b.dataset.tab)));

    document.querySelectorAll("#overviewModeBar .mode-btn").forEach((b) => b.addEventListener("click", () => {
      state.overviewMode = b.dataset.mode;
      b.parentNode.querySelectorAll(".mode-btn").forEach((x) => x.classList.toggle("is-active", x === b));
      renderOverview();
    }));

    document.querySelectorAll("#dimensionPicker .mode-btn").forEach((b) => b.addEventListener("click", () => {
      state.segmentDim = b.dataset.dim;
      b.parentNode.querySelectorAll(".mode-btn").forEach((x) => x.classList.toggle("is-active", x === b));
      renderSegments();
    }));

    document.querySelectorAll("#segmentModeBar .mode-btn").forEach((b) => b.addEventListener("click", () => {
      state.segmentMode = b.dataset.mode;
      b.parentNode.querySelectorAll(".mode-btn").forEach((x) => x.classList.toggle("is-active", x === b));
      renderSegments();
    }));

    document.querySelectorAll("#anomalyModeBar .mode-btn").forEach((b) => b.addEventListener("click", () => {
      state.anomalyMode = b.dataset.mode;
      b.parentNode.querySelectorAll(".mode-btn").forEach((x) => x.classList.toggle("is-active", x === b));
      renderAnomalies();
    }));

    document.getElementById("forecastMonths").addEventListener("change", renderForecastAndOptimizer);
    document.getElementById("targetMarginRange").addEventListener("input", renderForecastAndOptimizer);
    document.getElementById("simRevRange").addEventListener("input", renderForecastAndOptimizer);
    document.getElementById("simExpRange").addEventListener("input", renderForecastAndOptimizer);

    document.getElementById("btnLoadSample").addEventListener("click", () => {
      if (window.FINANCE_PULSE_SAMPLE_CSV) {
        saveWorkspace(parseCsv(window.FINANCE_PULSE_SAMPLE_CSV), "finance_pulse_sample.csv");
        renderAll();
      }
    });

    document.getElementById("fileInput").addEventListener("change", (ev) => {
      const file = ev.target.files && ev.target.files[0];
      if (!file) return;
      const reader = new FileReader();
      reader.onload = () => {
        const text = String(reader.result || "");
        let parsed = [];
        if (file.name.toLowerCase().endsWith(".json")) {
          try {
            const json = JSON.parse(text);
            const arr = Array.isArray(json) ? json : (Array.isArray(json.transactions) ? json.transactions : []);
            parsed = normalizeObjects(arr);
          } catch (_e) {}
        } else {
          parsed = parseCsv(text);
        }
        if (parsed.length) {
          saveWorkspace(parsed, file.name);
          renderAll();
        } else {
          alert("Could not detect valid Date, Revenue, and Expense columns in " + file.name);
        }
      };
      reader.readAsText(file);
    });

    document.getElementById("btnExportCsv").addEventListener("click", () => {
      if (!state.rows.length) return;
      const header = "txn_date,product,department,category,region,revenue,expense,cost,investment\n";
      const body = state.rows.map((r) => [r.txn_date, r.product, r.department, r.category, r.region, r.revenue, r.expense, r.cost, r.investment].join(",")).join("\n");
      const csv = header + body + "\n";
      if (window.AndroidBridge && window.AndroidBridge.saveCsvExport) {
        window.AndroidBridge.saveCsvExport("finance_pulse_mobile_export.csv", csv);
      } else {
        const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = "finance_pulse_mobile_export.csv";
        a.click();
        URL.revokeObjectURL(url);
      }
    });

    document.getElementById("btnApplySettings").addEventListener("click", () => {
      state.cfg.currency = document.getElementById("cfgCurrency").value;
      state.cfg.marginThreshold = Math.max(0, Math.min(100, Number(document.getElementById("cfgMargin").value) || 15));
      state.cfg.anomalyIqr = Math.max(0.5, Math.min(10, Number(document.getElementById("cfgIqr").value) || 1.5));
      saveCfg();
      renderAll();
    });

    document.getElementById("btnConnectServer").addEventListener("click", () => {
      const url = document.getElementById("serverUrlInput").value.trim();
      const status = document.getElementById("serverStatus");
      if (window.AndroidBridge && window.AndroidBridge.connectServer) {
        const ok = window.AndroidBridge.connectServer(url);
        if (!ok) status.textContent = "Enter a valid http:// or https:// URL.";
      } else if (url) {
        status.textContent = "Server bridge available when installed as Android APK (" + url + ").";
      }
    });

    document.getElementById("btnResetData").addEventListener("click", () => {
      try { localStorage.removeItem(STORAGE_KEY_ROWS); localStorage.removeItem(STORAGE_KEY_META); } catch (_e) {}
      state.rows = [];
      state.meta = { source: "Cleared", loadedAt: "" };
      renderAll();
    });
  }

  loadWorkspace();
  bindEvents();
  renderAll();
})();
