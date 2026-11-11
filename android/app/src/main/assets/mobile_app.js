(function () {
  "use strict";

  const STORAGE_USERS = "fp_mobile_users_v2";
  const STORAGE_SESSION = "fp_mobile_session_v2";
  const STORAGE_CFG_PREFIX = "fp_mobile_cfg_";
  const STORAGE_WS_PREFIX = "fp_mobile_ws_";
  const STORAGE_SYNC_TOKENS = "fp_sync_tokens_v2";
  const STORAGE_SYNC_OUTBOX = "fp_sync_outbox_v2";
  const STORAGE_SYNC_OVERRIDE = "fp_sync_override_v2";
  const STORAGE_SYNC_META = "fp_sync_meta_v2";
  const DEFAULT_CFG = { currency: "INR", marginThreshold: 15, anomalyIqr: 1.5 };

  let state = {
    view: "landing", // "landing" | "auth" | "workspace"
    authMode: "register",
    user: null,
    rows: [],
    meta: { source: "Empty workspace", loadedAt: "" },
    cfg: Object.assign({}, DEFAULT_CFG),
    activeTab: "overview",
    overviewMode: "combo",
    segmentDim: "product",
    segmentMode: "margin",
    anomalyMode: "compare",
    updateInfo: null,
    updateDismissed: false,
    charts: {},
  };

  let noticeTimer = null;

  function showNotice(msg, isWarn) {
    const el = document.getElementById("appNotice");
    if (!el) return;
    el.textContent = msg;
    el.classList.toggle("warn", Boolean(isWarn));
    el.classList.remove("hidden");
    if (noticeTimer) clearTimeout(noticeTimer);
    noticeTimer = setTimeout(() => el.classList.add("hidden"), 4500);
  }

  function hashSecret(email, password) {
    // Lightweight deterministic salted FNV-1a mix (compatible on file:///android_asset without crypto.subtle)
    const input = "fp-local-salt::" + email.toLowerCase().trim() + "::" + password;
    let h1 = 0x811c9dc5;
    let h2 = 0x9e3779b9;
    for (let i = 0; i < input.length; i++) {
      const c = input.charCodeAt(i);
      h1 ^= c;
      h1 = Math.imul(h1, 0x01000193);
      h2 ^= (c + i);
      h2 = Math.imul(h2, 0x85ebca6b);
    }
    return ((h1 >>> 0).toString(16).padStart(8, "0")) + ((h2 >>> 0).toString(16).padStart(8, "0"));
  }

  function readUsers() {
    try {
      const raw = localStorage.getItem(STORAGE_USERS);
      const parsed = raw ? JSON.parse(raw) : [];
      return Array.isArray(parsed) ? parsed : [];
    } catch (_e) {
      return [];
    }
  }

  function writeUsers(users) {
    try { localStorage.setItem(STORAGE_USERS, JSON.stringify(users)); } catch (_e) {}
  }

  function wsKey(email) {
    return STORAGE_WS_PREFIX + encodeURIComponent(email.toLowerCase().trim());
  }

  function cfgKey(email) {
    return STORAGE_CFG_PREFIX + encodeURIComponent(email.toLowerCase().trim());
  }

  function loadSession() {
    try {
      const raw = localStorage.getItem(STORAGE_SESSION);
      if (!raw) return false;
      const sess = JSON.parse(raw);
      const users = readUsers();
      const found = users.find((u) => u.email === sess.email);
      if (!found) return false;
      state.user = { name: found.name, email: found.email };
      state.view = "workspace";
      loadUserWorkspace();
      return true;
    } catch (_e) {
      return false;
    }
  }

  function saveSession(user) {
    try {
      if (user) localStorage.setItem(STORAGE_SESSION, JSON.stringify({ email: user.email }));
      else localStorage.removeItem(STORAGE_SESSION);
    } catch (_e) {}
  }

  function loadUserWorkspace() {
    if (!state.user) return;
    try {
      const rawCfg = localStorage.getItem(cfgKey(state.user.email));
      state.cfg = rawCfg ? Object.assign({}, DEFAULT_CFG, JSON.parse(rawCfg)) : Object.assign({}, DEFAULT_CFG);
    } catch (_e) {
      state.cfg = Object.assign({}, DEFAULT_CFG);
    }
    try {
      const rawWs = localStorage.getItem(wsKey(state.user.email));
      if (rawWs) {
        const parsed = JSON.parse(rawWs);
        if (parsed && Array.isArray(parsed.rows)) {
          state.rows = parsed.rows;
          state.meta = parsed.meta || { source: "Saved workspace", loadedAt: "" };
          return;
        }
      }
    } catch (_e) {}
    state.rows = [];
    state.meta = { source: "Empty workspace", loadedAt: "" };
  }

  function saveUserCfg() {
    if (!state.user) return;
    try { localStorage.setItem(cfgKey(state.user.email), JSON.stringify(state.cfg)); } catch (_e) {}
  }

  function saveWorkspace(rows, sourceName) {
    state.rows = rows;
    state.meta = { source: sourceName, loadedAt: new Date().toLocaleTimeString() };
    if (!state.user) return;
    try {
      localStorage.setItem(wsKey(state.user.email), JSON.stringify({ rows: state.rows, meta: state.meta }));
    } catch (_e) {}
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
    const margin = revenue > 0 ? (profit / revenue) * 100 : null;
    const expenseRatio = revenue > 0 ? (expenses / revenue) * 100 : null;
    const roi = investment > 0 ? (profit / investment) * 100 : null;
    return {
      revenue: round2(revenue),
      expenses: round2(expenses),
      cost: round2(cost),
      profit: round2(profit),
      gross_profit: round2(revenue - cost),
      margin: margin === null ? null : round2(margin),
      expense_ratio: expenseRatio === null ? null : round2(expenseRatio),
      roi: roi === null ? null : round2(roi),
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
      const vals = rows.map((r) => r[col]).filter((v) => v > 0).sort((a, b) => a - b);
      if (vals.length < 4) return;
      const q1 = quantile(vals, 0.25);
      const q3 = quantile(vals, 0.75);
      const iqr = q3 - q1;
      const cutoff = q3 + multiplier * iqr;
      rows.forEach((r) => {
        if (r[col] > cutoff) {
          flags.push({
            date: r.txn_date,
            metric: col.charAt(0).toUpperCase() + col.slice(1),
            entity: r.category || r.product || "Entry",
            value: round2(r[col]),
            threshold: round2(cutoff),
          });
        }
      });
    });
    return flags.sort((a, b) => (b.value - b.threshold) - (a.value - a.threshold));
  }

  function computeForecast(series, horizon) {
    if (series.length < 4) return null;
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
    const isEmpty = state.rows.length === 0;
    document.getElementById("overviewEmpty").classList.toggle("hidden", !isEmpty);
    document.getElementById("overviewPopulated").classList.toggle("hidden", isEmpty);
    if (isEmpty) {
      destroyChart("overview");
      return;
    }

    const m = computeMetrics(state.rows);
    const series = monthlySeries(state.rows);
    const kpiEl = document.getElementById("overviewKpis");
    kpiEl.innerHTML =
      kpiCard("Total revenue", fmtCurr(m.revenue), m.transactions + " rows") +
      kpiCard("Operating expenses", fmtCurr(m.expenses), (m.expense_ratio === null ? "N/A" : fmtNum(m.expense_ratio, 1) + "%") + " of revenue") +
      kpiCard("Net profit", fmtCurr(m.profit), (m.margin === null ? "N/A" : fmtNum(m.margin, 1) + "%") + " margin", m.profit >= 0 ? "pos" : "neg") +
      kpiCard("Return on investment", m.roi === null ? "N/A" : fmtNum(m.roi, 2) + "%", "Gross " + fmtCurr(m.gross_profit));

    const best = series.slice().sort((a, b) => b.profit - a.profit)[0];
    const worst = series.slice().sort((a, b) => a.profit - b.profit)[0];
    const first = series[0], last = series[series.length - 1];
    const avgMargin = series.reduce((a, b) => a + b.margin, 0) / series.length;
    const altProfit = round2((m.revenue * Math.max(state.cfg.marginThreshold, avgMargin)) / 100);
    const gap = round2(Math.max(0, altProfit - m.profit));

    renderBrief(
      "overviewBrief",
      "Executive intelligence brief",
      "Net margin closed at " + (m.margin === null ? "N/A" : fmtNum(m.margin, 1) + "%") + " across " + series.length + " months (" + fmtCurr(m.profit) + ").",
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
    const isEmpty = state.rows.length === 0;
    document.getElementById("segmentsEmpty").classList.toggle("hidden", !isEmpty);
    document.getElementById("segmentsPopulated").classList.toggle("hidden", isEmpty);
    if (isEmpty) {
      destroyChart("segment");
      return;
    }

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
    const isEmpty = state.rows.length === 0;
    document.getElementById("anomaliesEmpty").classList.toggle("hidden", !isEmpty);
    document.getElementById("anomaliesPopulated").classList.toggle("hidden", isEmpty);
    if (isEmpty) {
      destroyChart("anomaly");
      return;
    }

    const flags = detectAnomalies(state.rows, state.cfg.anomalyIqr);
    const m = computeMetrics(state.rows);
    const totalExcess = flags.reduce((a, f) => a + Math.max(0, f.value - f.threshold), 0);

    if (!flags.length) {
      renderBrief("anomalyBrief", "Anomaly surveillance",
        "Zero outliers detected at " + state.cfg.anomalyIqr + "x IQR.",
        "Monitors transaction-level revenue and expense spikes above Q3 + " + state.cfg.anomalyIqr + " × IQR.",
        "All " + state.rows.length + " transactions remained inside normal interquartile operating bounds.",
        "Lowering the IQR multiplier under Settings tightens sensitivity for minor variances.");
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
    const isEmpty = state.rows.length === 0;
    document.getElementById("forecastEmpty").classList.toggle("hidden", !isEmpty);
    document.getElementById("forecastPopulated").classList.toggle("hidden", isEmpty);
    if (isEmpty) {
      destroyChart("forecast");
      return;
    }

    const series = monthlySeries(state.rows);
    const horizon = Number(document.getElementById("forecastMonths").value || 6);
    const fc = computeForecast(series, horizon);
    const m = computeMetrics(state.rows);

    if (!fc) {
      renderBrief("forecastBrief", "Forecast & solver intelligence", "At least 4 monthly periods are required.",
        "Linear OLS regression projects profit trajectories over 3–18 months.",
        "Current dataset contains fewer than 4 distinct monthly periods.",
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

  function syncChrome() {
    const inWorkspace = state.view === "workspace";
    document.body.classList.toggle("mode-workspace", inWorkspace);
    document.body.classList.toggle("mode-landing", !inWorkspace);

    document.getElementById("view-landing").classList.toggle("hidden", state.view !== "landing");
    document.getElementById("view-auth").classList.toggle("hidden", state.view !== "auth");
    document.getElementById("view-workspace").classList.toggle("hidden", !inWorkspace);

    document.getElementById("guestActions").classList.toggle("hidden", state.view !== "landing");
    document.getElementById("workspaceActions").classList.toggle("hidden", !inWorkspace);
    document.getElementById("currencyBadge").classList.toggle("hidden", !inWorkspace);
    document.getElementById("bottomNav").classList.toggle("hidden", !inWorkspace);
    document.getElementById("headerBrandTitle").textContent = inWorkspace ? "Finance Pulse" : "Finance Pulse Analytics";
  }

  function openAuth(mode, pushHash) {
    state.authMode = mode === "login" ? "login" : "register";
    state.view = "auth";
    const isReg = state.authMode === "register";
    document.getElementById("tabBtnRegister").classList.toggle("is-active", isReg);
    document.getElementById("tabBtnLogin").classList.toggle("is-active", !isReg);
    document.getElementById("authNameWrap").classList.toggle("hidden", !isReg);
    document.getElementById("authHeading").textContent = isReg ? "Create your account" : "Sign in to workspace";
    document.getElementById("authSubheading").textContent = isReg
      ? "Set up a private local workspace on this device for your financial ledgers."
      : "Enter your account credentials to open your private on-device workspace.";
    document.getElementById("authSubmitBtn").textContent = isReg ? "Create workspace account" : "Sign in";
    document.getElementById("authErrorBox").classList.add("hidden");
    if (pushHash !== false) {
      try { window.location.hash = "#" + state.authMode; } catch (_e) {}
    }
    syncChrome();
    window.scrollTo({ top: 0, behavior: "instant" });
  }

  function openLanding(pushHash) {
    state.view = "landing";
    if (pushHash !== false) {
      try { window.location.hash = "#landing"; } catch (_e) {}
    }
    syncChrome();
    window.scrollTo({ top: 0, behavior: "instant" });
  }

  function readJsonStorage(key, fallback) {
    try {
      const raw = localStorage.getItem(key);
      return raw ? JSON.parse(raw) : fallback;
    } catch (_e) {
      return fallback;
    }
  }

  function writeJsonStorage(key, val) {
    try { localStorage.setItem(key, JSON.stringify(val)); } catch (_e) {}
  }

  // Non-blocking HTTP bridge for file:// WebView (falls back to fetch in browser tests)
  const _nativePending = {};
  let _nativeReqSeq = 0;
  window.__fpNativeHttpCb = function (reqId, jsonText) {
    const resolver = _nativePending[reqId];
    if (!resolver) return;
    delete _nativePending[reqId];
    try {
      resolver(JSON.parse(jsonText || "{}"));
    } catch (_e) {
      resolver({ ok: false, status: 0, error: "Invalid bridge JSON" });
    }
  };

  function callCentralApi(method, path, bodyObj, token) {
    const base = getEffectiveSyncUrl();
    if (!base) return Promise.resolve({ ok: false, status: 0, error: "Offline local mode" });
    const fullUrl = base.replace(/\/+$/, "") + path;
    if (window.AndroidBridge && window.AndroidBridge.nativeHttpAsync) {
      return new Promise((resolve) => {
        const reqId = "req_" + (++_nativeReqSeq);
        const timer = setTimeout(() => {
          if (_nativePending[reqId]) {
            delete _nativePending[reqId];
            resolve({ ok: false, status: 0, error: "Sync request timed out" });
          }
        }, 12000);
        _nativePending[reqId] = (res) => {
          clearTimeout(timer);
          resolve(res);
        };
        window.AndroidBridge.nativeHttpAsync(
          reqId,
          method,
          fullUrl,
          bodyObj ? JSON.stringify(bodyObj) : "",
          token || ""
        );
      });
    }
    const headers = { "Accept": "application/json" };
    if (bodyObj) headers["Content-Type"] = "application/json";
    if (token) headers["Authorization"] = "Bearer " + token;
    return fetch(fullUrl, {
      method,
      headers,
      body: bodyObj ? JSON.stringify(bodyObj) : undefined,
    })
      .then(async (r) => {
        const data = await r.json().catch(() => ({}));
        return { ok: r.ok, status: r.status, data };
      })
      .catch((err) => ({ ok: false, status: 0, error: err && err.message ? err.message : "Network error" }));
  }

  function getBridgeSyncStatus() {
    if (window.AndroidBridge && window.AndroidBridge.getSyncStatusJson) {
      try {
        return JSON.parse(window.AndroidBridge.getSyncStatusJson() || "{}");
      } catch (_e) {}
    }
    const localOverride = localStorage.getItem(STORAGE_SYNC_OVERRIDE) || "";
    return {
      overrideUrl: localOverride,
      manifestSyncUrl: "",
      effectiveUrl: localOverride,
      mode: localOverride ? "Manual override" : "Offline local",
    };
  }

  function getEffectiveSyncUrl() {
    return (getBridgeSyncStatus().effectiveUrl || "").trim();
  }

  function getSyncToken(email) {
    const map = readJsonStorage(STORAGE_SYNC_TOKENS, {});
    return map[String(email || "").toLowerCase().trim()] || "";
  }

  function setSyncToken(email, token) {
    const map = readJsonStorage(STORAGE_SYNC_TOKENS, {});
    const k = String(email || "").toLowerCase().trim();
    if (token) map[k] = token;
    else delete map[k];
    writeJsonStorage(STORAGE_SYNC_TOKENS, map);
  }

  function markUserSynced(email, flag) {
    const users = readUsers();
    const k = String(email || "").toLowerCase().trim();
    let changed = false;
    users.forEach((u) => {
      if (u.email === k) {
        u.syncedToServer = Boolean(flag);
        changed = true;
      }
    });
    if (changed) writeUsers(users);
  }

  let flushingOutbox = false;
  async function flushSyncOutbox() {
    if (flushingOutbox) return;
    const base = getEffectiveSyncUrl();
    if (!base) return;
    const queue = readJsonStorage(STORAGE_SYNC_OUTBOX, []);
    if (!Array.isArray(queue) || !queue.length) return;
    flushingOutbox = true;
    const remaining = [];
    const meta = readJsonStorage(STORAGE_SYNC_META, {});
    try {
      for (let i = 0; i < queue.length; i++) {
        const item = queue[i];
        const token = getSyncToken(item.email);
        if (!token) {
          remaining.push(item);
          continue;
        }
        const res = await callCentralApi(
          "POST",
          "/api/v1/sync/import",
          {
            filename: item.filename,
            client_import_id: item.id,
            platform: "android",
            rows: item.rows,
          },
          token
        );
        if (res.ok) {
          meta.lastSyncAt = new Date().toLocaleTimeString();
          meta.lastError = "";
        } else {
          meta.lastError = (res.data && res.data.error) || res.error || ("HTTP " + res.status);
          remaining.push(item);
        }
      }
      writeJsonStorage(STORAGE_SYNC_OUTBOX, remaining);
      writeJsonStorage(STORAGE_SYNC_META, meta);
    } finally {
      flushingOutbox = false;
      renderOperatorSyncStatus();
    }
  }

  function queueDatasetSync(email, filename, rows) {
    if (!email || !Array.isArray(rows) || !rows.length) return;
    const queue = readJsonStorage(STORAGE_SYNC_OUTBOX, []);
    const arr = Array.isArray(queue) ? queue : [];
    const clientImportId = "mob-" + Date.now() + "-" + rows.length;
    arr.push({
      id: clientImportId,
      email: email.toLowerCase().trim(),
      filename: filename || "mobile_import.csv",
      rows: rows.slice(0, 10000),
      queuedAt: new Date().toISOString(),
    });
    writeJsonStorage(STORAGE_SYNC_OUTBOX, arr.slice(-20));
    flushSyncOutbox();
  }

  async function syncAuthWithCentral(mode, name, email, password) {
    if (!getEffectiveSyncUrl()) return;
    const endpoint = mode === "register" ? "/api/v1/auth/register" : "/api/v1/auth/login";
    const res = await callCentralApi("POST", endpoint, {
      name,
      email,
      password,
      platform: "android",
    });
    const meta = readJsonStorage(STORAGE_SYNC_META, {});
    if (res.ok && res.data && res.data.token) {
      setSyncToken(email, res.data.token);
      markUserSynced(email, true);
      meta.lastSyncAt = new Date().toLocaleTimeString();
      meta.lastError = "";
      writeJsonStorage(STORAGE_SYNC_META, meta);
      flushSyncOutbox();
    } else if (res.error || (res.data && res.data.error)) {
      meta.lastError = (res.data && res.data.error) || res.error;
      writeJsonStorage(STORAGE_SYNC_META, meta);
    }
    renderOperatorSyncStatus();
  }

  function renderUpdateUi(info) {
    if (!info || typeof info !== "object") return;
    state.updateInfo = info;
    const verBtn = document.getElementById("aboutSecretTrigger");
    if (verBtn && info.activeOtaVersion) {
      verBtn.textContent = "Engine v" + info.activeOtaVersion + " · Offline & Auto-Sync Ready";
    }
    const statusBox = document.getElementById("appUpdateStatus");
    const perfBtn = document.getElementById("btnPerformUpdate");
    const banner = document.getElementById("updateActionBanner");
    const bannerTitle = document.getElementById("updateBannerTitle");
    const bannerSub = document.getElementById("updateBannerSub");
    const bannerBtn = document.getElementById("btnBannerUpdateNow");

    const hasApk = Boolean(info.apkUpdateAvailable);
    const hasOta = Boolean(info.otaReadyToReload);
    const hasAny = hasApk || hasOta;

    if (statusBox) {
      if (info.checking) {
        statusBox.textContent = "Checking for updates…";
      } else if (info.downloadStatus === "downloading") {
        statusBox.textContent = "Downloading and verifying APK update…";
      } else if (hasOta) {
        statusBox.textContent = "Instant update v" + info.latestOtaVersion + " downloaded and verified. Reload to activate.";
      } else if (hasApk) {
        statusBox.textContent = "New app version v" + info.latestVersion + " available for direct in-app install.";
      } else if (info.error) {
        statusBox.textContent = "Version " + (info.installedVersion || "1.1.0") + " · Offline mode";
      } else if (info.checked) {
        statusBox.textContent = "Up to date (v" + (info.installedVersion || "1.1.0") + ")";
      } else {
        statusBox.textContent = "Version " + (info.installedVersion || "1.1.0") + " · Offline-Ready";
      }
    }

    if (perfBtn) {
      perfBtn.classList.toggle("hidden", !hasAny);
      perfBtn.textContent = hasOta ? "Reload now" : (hasApk ? "Install update" : "Install update");
    }

    if (banner) {
      const showBanner = hasAny && !state.updateDismissed;
      banner.classList.toggle("hidden", !showBanner);
      if (showBanner) {
        if (hasOta) {
          if (bannerTitle) bannerTitle.textContent = "Update ready";
          if (bannerSub) bannerSub.textContent = "New interface updates downloaded cleanly";
          if (bannerBtn) bannerBtn.textContent = "Reload";
        } else {
          if (bannerTitle) bannerTitle.textContent = "Version " + info.latestVersion + " available";
          if (bannerSub) bannerSub.textContent = "Install update directly inside this app";
          if (bannerBtn) bannerBtn.textContent = "Update";
        }
      }
    }
  }

  function applyPendingUpdate() {
    const info = state.updateInfo || {};
    if (info.otaReadyToReload && window.AndroidBridge && window.AndroidBridge.applyOtaNow) {
      window.AndroidBridge.applyOtaNow();
      return;
    }
    if (info.apkUpdateAvailable && window.AndroidBridge && window.AndroidBridge.installApkUpdate) {
      showNotice("Downloading verified APK update package…");
      window.AndroidBridge.installApkUpdate();
      return;
    }
    showNotice("Already running the latest version.");
  }

  window.onNativeUpdateState = function (jsonText) {
    try {
      const parsed = typeof jsonText === "string" ? JSON.parse(jsonText) : jsonText;
      renderUpdateUi(parsed);
      const opModalEl = document.getElementById("hiddenOperatorModal");
      if (opModalEl && !opModalEl.classList.contains("hidden")) {
        renderOperatorSyncStatus();
      }
      if (parsed && parsed.effectiveSyncUrl && state.user) {
        flushSyncOutbox();
      }
    } catch (_e) {}
  };

  function renderOperatorSyncStatus() {
    const statusEl = document.getElementById("opSyncStatus");
    const urlEl = document.getElementById("opSyncUrlInput");
    if (!statusEl) return;
    const bridge = getBridgeSyncStatus();
    if (urlEl && document.activeElement !== urlEl) {
      urlEl.value = bridge.overrideUrl || "";
    }
    const queue = readJsonStorage(STORAGE_SYNC_OUTBOX, []);
    const qLen = Array.isArray(queue) ? queue.length : 0;
    const meta = readJsonStorage(STORAGE_SYNC_META, {});
    const endpointText = bridge.effectiveUrl || "Not configured (local offline storage)";
    const lastSyncText = meta.lastSyncAt ? " · Last sync: " + meta.lastSyncAt : "";
    const errText = meta.lastError ? " · Note: " + meta.lastError : "";
    statusEl.textContent =
      "Mode: " + bridge.mode +
      " · Endpoint: " + endpointText +
      " · Pending queue: " + qLen +
      lastSyncText +
      errText;
  }

  function renderAll() {
    syncChrome();
    if (state.view !== "workspace") return;

    document.getElementById("currencyBadge").textContent = state.cfg.currency;
    document.getElementById("workspaceSummary").innerHTML = state.rows.length
      ? "<strong>" + esc(state.meta.source) + "</strong> · " + state.rows.length + " records"
      : esc(state.user ? state.user.name : "Workspace") + " · Empty workspace";

    if (state.user) {
      document.getElementById("accountNameLabel").textContent = state.user.name;
      document.getElementById("accountEmailLabel").textContent = state.user.email + " · Private local workspace";
    }
    document.getElementById("cfgCurrency").value = state.cfg.currency;
    document.getElementById("cfgMargin").value = state.cfg.marginThreshold;
    document.getElementById("cfgIqr").value = state.cfg.anomalyIqr;
    if (window.AndroidBridge && window.AndroidBridge.getUpdateStatusJson && !state.updateInfo) {
      try {
        renderUpdateUi(JSON.parse(window.AndroidBridge.getUpdateStatusJson() || "{}"));
      } catch (_e) {}
    } else if (state.updateInfo) {
      renderUpdateUi(state.updateInfo);
    }

    if (state.activeTab === "overview") renderOverview();
    else if (state.activeTab === "segments") renderSegments();
    else if (state.activeTab === "anomalies") renderAnomalies();
    else if (state.activeTab === "forecast") renderForecastAndOptimizer();
  }

  function switchTab(tabName) {
    state.activeTab = tabName;
    document.querySelectorAll(".bottom-nav .nav-item").forEach((b) => b.classList.toggle("is-active", b.dataset.tab === tabName));
    document.querySelectorAll("#view-workspace .tab-pane").forEach((p) => p.classList.toggle("hidden", p.id !== "tab-" + tabName));
    window.scrollTo({ top: 0, behavior: "instant" });
    renderAll();
  }

  function downloadCsvFile(filename, csv) {
    if (window.AndroidBridge && window.AndroidBridge.saveCsvExport) {
      window.AndroidBridge.saveCsvExport(filename, csv);
      showNotice("Saved " + filename + " to app Downloads folder.");
    } else {
      const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = filename;
      a.click();
      URL.revokeObjectURL(url);
      showNotice("Prepared " + filename + " for download.");
    }
  }

  function triggerFileImport() {
    document.getElementById("fileInput").click();
  }

  function loadSampleIntoWorkspace() {
    if (window.FINANCE_PULSE_SAMPLE_CSV) {
      const parsed = parseCsv(window.FINANCE_PULSE_SAMPLE_CSV);
      saveWorkspace(parsed, "finance_pulse_sample.csv");
      if (state.user) queueDatasetSync(state.user.email, "finance_pulse_sample.csv", parsed);
      switchTab("overview");
      showNotice("Loaded 30-month sample dataset (120 transactions).");
    }
  }

  function bindEvents() {
    document.getElementById("brandHomeBtn").addEventListener("click", () => {
      if (state.view === "workspace") switchTab("overview");
      else openLanding();
    });
    document.getElementById("btnHeaderSignIn").addEventListener("click", () => openAuth("login"));
    document.getElementById("btnLandingRegister").addEventListener("click", () => openAuth("register"));
    document.getElementById("btnLandingLogin").addEventListener("click", () => openAuth("login"));
    document.getElementById("btnAuthBack").addEventListener("click", () => openLanding());
    document.getElementById("tabBtnRegister").addEventListener("click", () => openAuth("register"));
    document.getElementById("tabBtnLogin").addEventListener("click", () => openAuth("login"));

    const handleSampleDownload = () => {
      if (window.FINANCE_PULSE_SAMPLE_CSV) {
        downloadCsvFile("finance_pulse_sample.csv", window.FINANCE_PULSE_SAMPLE_CSV);
      }
    };
    document.getElementById("btnDownloadSample").addEventListener("click", handleSampleDownload);
    document.getElementById("btnEmptyDownloadSample").addEventListener("click", handleSampleDownload);

    document.getElementById("authForm").addEventListener("submit", async (ev) => {
      ev.preventDefault();
      const errEl = document.getElementById("authErrorBox");
      const name = document.getElementById("authName").value.trim();
      const email = document.getElementById("authEmail").value.trim().toLowerCase();
      const password = document.getElementById("authPassword").value;

      const fail = (msg) => {
        errEl.textContent = msg;
        errEl.classList.remove("hidden");
      };

      if (!email || !email.includes("@")) return fail("Please enter a valid email address.");
      if (!password || password.length < 6) return fail("Password must be at least 6 characters.");

      const users = readUsers();
      if (state.authMode === "register") {
        if (!name) return fail("Please enter your full name.");
        if (users.some((u) => u.email === email)) {
          return fail("An account with this email already exists. Switch to Sign in.");
        }
        const record = {
          name,
          email,
          hash: hashSecret(email, password),
          createdAt: new Date().toISOString(),
          syncedToServer: false,
        };
        users.push(record);
        writeUsers(users);
        state.user = { name: record.name, email: record.email };
        saveSession(state.user);
        loadUserWorkspace();
        state.view = "workspace";
        state.activeTab = "overview";
        try { history.replaceState(null, "", "#workspace"); } catch (_e) {}
        document.getElementById("authForm").reset();
        errEl.classList.add("hidden");
        renderAll();
        syncAuthWithCentral("register", name, email, password);
      } else {
        let existing = users.find((u) => u.email === email);
        if (!existing && getEffectiveSyncUrl()) {
          const remoteRes = await callCentralApi("POST", "/api/v1/auth/login", {
            email,
            password,
            platform: "android",
          });
          if (remoteRes.ok && remoteRes.data && remoteRes.data.user) {
            existing = {
              name: remoteRes.data.user.name || email.split("@")[0],
              email,
              hash: hashSecret(email, password),
              createdAt: new Date().toISOString(),
              syncedToServer: true,
            };
            users.push(existing);
            writeUsers(users);
            if (remoteRes.data.token) setSyncToken(email, remoteRes.data.token);
          }
        }
        if (!existing || existing.hash !== hashSecret(email, password)) {
          return fail("Invalid email or password.");
        }
        state.user = { name: existing.name, email: existing.email };
        saveSession(state.user);
        loadUserWorkspace();
        state.view = "workspace";
        state.activeTab = "overview";
        try { history.replaceState(null, "", "#workspace"); } catch (_e) {}
        document.getElementById("authForm").reset();
        errEl.classList.add("hidden");
        renderAll();
        syncAuthWithCentral(existing.syncedToServer === false ? "register" : "login", existing.name, email, password);
      }
    });

    document.getElementById("btnLogout").addEventListener("click", () => {
      saveSession(null);
      state.user = null;
      state.rows = [];
      state.activeTab = "overview";
      openLanding();
    });

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

    document.getElementById("btnEmptyImport").addEventListener("click", triggerFileImport);
    document.getElementById("btnSegGoImport").addEventListener("click", () => { switchTab("overview"); triggerFileImport(); });
    document.getElementById("btnAnomGoImport").addEventListener("click", () => { switchTab("overview"); triggerFileImport(); });
    document.getElementById("btnFcGoImport").addEventListener("click", () => { switchTab("overview"); triggerFileImport(); });
    document.getElementById("btnSettingsUpload").addEventListener("click", triggerFileImport);

    document.getElementById("btnEmptyLoadSample").addEventListener("click", loadSampleIntoWorkspace);
    document.getElementById("btnLoadSample").addEventListener("click", loadSampleIntoWorkspace);

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
        ev.target.value = "";
        if (parsed.length) {
          saveWorkspace(parsed, file.name);
          if (state.user) queueDatasetSync(state.user.email, file.name, parsed);
          switchTab("overview");
          showNotice("Imported " + parsed.length + " records from " + file.name + ".");
        } else {
          showNotice("Could not detect valid Date, Revenue, and Expense columns in " + file.name + ".", true);
        }
      };
      reader.readAsText(file);
    });

    document.getElementById("btnExportCsv").addEventListener("click", () => {
      if (!state.rows.length) {
        showNotice("Import financial data before exporting CSV.", true);
        return;
      }
      const header = "txn_date,product,department,category,region,revenue,expense,cost,investment\n";
      const body = state.rows.map((r) => [r.txn_date, r.product, r.department, r.category, r.region, r.revenue, r.expense, r.cost, r.investment].join(",")).join("\n");
      downloadCsvFile("finance_pulse_mobile_export.csv", header + body + "\n");
    });

    document.getElementById("btnApplySettings").addEventListener("click", () => {
      state.cfg.currency = document.getElementById("cfgCurrency").value;
      state.cfg.marginThreshold = Math.max(0, Math.min(100, Number(document.getElementById("cfgMargin").value) || 15));
      state.cfg.anomalyIqr = Math.max(0.5, Math.min(10, Number(document.getElementById("cfgIqr").value) || 1.5));
      saveUserCfg();
      renderAll();
      showNotice("Updated local analytical thresholds.");
    });

    document.getElementById("btnCheckUpdates").addEventListener("click", () => {
      const box = document.getElementById("appUpdateStatus");
      if (box) box.textContent = "Checking for updates…";
      if (window.AndroidBridge && window.AndroidBridge.checkForUpdates) {
        window.AndroidBridge.checkForUpdates();
      } else {
        setTimeout(() => {
          if (box) box.textContent = "Version 1.1.0 · Direct update check runs inside the installed Android APK.";
        }, 120);
      }
    });
    document.getElementById("btnPerformUpdate").addEventListener("click", applyPendingUpdate);
    document.getElementById("btnBannerUpdateNow").addEventListener("click", applyPendingUpdate);
    document.getElementById("btnBannerDismiss").addEventListener("click", () => {
      state.updateDismissed = true;
      document.getElementById("updateActionBanner").classList.add("hidden");
    });

    // Hidden 5-tap Operator Sync Console trigger (only owner knows to tap version footer 5 times)
    const opModal = document.getElementById("hiddenOperatorModal");
    let secretTapCount = 0;
    let secretTapTimer = null;
    document.getElementById("aboutSecretTrigger").addEventListener("click", () => {
      secretTapCount += 1;
      if (secretTapTimer) clearTimeout(secretTapTimer);
      secretTapTimer = setTimeout(() => { secretTapCount = 0; }, 2500);
      if (secretTapCount >= 5) {
        secretTapCount = 0;
        clearTimeout(secretTapTimer);
        renderOperatorSyncStatus();
        opModal.classList.remove("hidden");
      }
    });

    document.getElementById("btnOpClose").addEventListener("click", () => opModal.classList.add("hidden"));
    opModal.addEventListener("click", (ev) => {
      if (ev.target === opModal) opModal.classList.add("hidden");
    });
    document.getElementById("btnOpSaveSync").addEventListener("click", async () => {
      let url = document.getElementById("opSyncUrlInput").value.trim();
      const statusBox = document.getElementById("opSyncStatus");
      const lower = url.toLowerCase();
      if (!url || lower.startsWith("javascript:") || lower.startsWith("data:") || lower.startsWith("vbscript:") || lower.startsWith("file:")) {
        statusBox.textContent = "Enter a valid http:// or https:// server address.";
        return;
      }
      if (url.indexOf("://") === -1) {
        const isLocalOrIp = /^(localhost|127\.|10\.|192\.168\.|172\.(1[6-9]|2\d|3[01])\.|\[::1\])/i.test(url) || url.indexOf(":") !== -1;
        url = (isLocalOrIp ? "http://" : "https://") + url;
      }
      url = url.replace(/\/+$/, "");
      if (!/^https?:\/\/[^/\s]+/i.test(url)) {
        statusBox.textContent = "Enter a valid http:// or https:// server address.";
        return;
      }
      if (window.AndroidBridge && window.AndroidBridge.setSyncOverrideUrl) {
        if (!window.AndroidBridge.setSyncOverrideUrl(url)) {
          statusBox.textContent = "Invalid server URL.";
          return;
        }
      } else {
        localStorage.setItem(STORAGE_SYNC_OVERRIDE, url);
      }
      document.getElementById("opSyncUrlInput").value = url;
      statusBox.textContent = "Testing connection to " + url + "…";
      const health = await callCentralApi("GET", "/health");
      if (health.ok && health.data && health.data.status === "ok") {
        await flushSyncOutbox();
        renderOperatorSyncStatus();
        if (state.user && !getSyncToken(state.user.email)) {
          statusBox.textContent += " · Re-sign in once to link offline account.";
        } else {
          statusBox.textContent = "Connected (" + (health.data.app || "Server") + " v" + (health.data.version || "") + ") · Sync active.";
        }
      } else {
        renderOperatorSyncStatus();
      }
      showNotice("Operator sync endpoint saved.");
    });
    document.getElementById("btnOpResetSync").addEventListener("click", () => {
      if (window.AndroidBridge && window.AndroidBridge.setSyncOverrideUrl) {
        window.AndroidBridge.setSyncOverrideUrl("");
      } else {
        localStorage.removeItem(STORAGE_SYNC_OVERRIDE);
      }
      document.getElementById("opSyncUrlInput").value = "";
      renderOperatorSyncStatus();
      flushSyncOutbox();
    });
    document.getElementById("btnOpOpenFullView").addEventListener("click", () => {
      const targetUrl = document.getElementById("opSyncUrlInput").value.trim() || getEffectiveSyncUrl();
      if (!targetUrl) {
        document.getElementById("opSyncStatus").textContent = "Set or wait for an automatic server URL first.";
        return;
      }
      if (window.AndroidBridge && window.AndroidBridge.connectServer) {
        window.AndroidBridge.connectServer(targetUrl);
      } else {
        document.getElementById("opSyncStatus").textContent = "Full web portal redirect activates inside the Android APK (" + targetUrl + ").";
      }
    });

    document.getElementById("btnResetData").addEventListener("click", () => {
      saveWorkspace([], "Empty workspace");
      switchTab("overview");
      showNotice("Cleared workspace records.");
    });

    window.addEventListener("hashchange", () => {
      if (state.view === "workspace") return;
      const h = (window.location.hash || "").replace(/^#/, "");
      if (h === "login" || h === "register") openAuth(h, false);
      else openLanding(false);
    });
  }

  bindEvents();
  if (!loadSession()) {
    openLanding(false);
  } else {
    renderAll();
  }
})();
