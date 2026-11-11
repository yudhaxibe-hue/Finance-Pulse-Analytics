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
    filterYear: "",
    filterDepartment: "",
    activeTab: "overview",
    overviewMode: "combo",
    segmentDim: "product",
    segmentMode: "margin",
    anomalyMode: "compare",
    forecastModel: "ensemble",
    copilotLang: "auto",
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
    state.filterYear = "";
    state.filterDepartment = "";
    if (!state.user) return;
    try {
      localStorage.setItem(wsKey(state.user.email), JSON.stringify({ rows: state.rows, meta: state.meta }));
    } catch (_e) {
      // If 10,000+ rows exceed tight WebView localStorage quotas, keep live in memory for this session
    }
  }

  function getActiveRows() {
    if (!state.rows.length) return [];
    if (!state.filterYear && !state.filterDepartment) return state.rows;
    return state.rows.filter((r) => {
      if (state.filterYear && String(r.fiscal_year || (r.txn_date || "").slice(0, 4)) !== String(state.filterYear)) {
        return false;
      }
      if (state.filterDepartment && String(r.department || "General") !== state.filterDepartment) {
        return false;
      }
      return true;
    });
  }

  function renderFilterOptions() {
    const yrSel = document.getElementById("filterYear");
    const depSel = document.getElementById("filterDepartment");
    const resetBtn = document.getElementById("btnFilterReset");
    if (!yrSel || !depSel) return;

    const years = Array.from(new Set(state.rows.map((r) => String(r.fiscal_year || (r.txn_date || "").slice(0, 4))).filter((y) => /^\d{4}$/.test(y)))).sort();
    const deps = Array.from(new Set(state.rows.map((r) => String(r.department || "General")).filter(Boolean))).sort();

    yrSel.innerHTML = '<option value="">All years</option>' + years.map((y) => '<option value="' + esc(y) + '"' + (state.filterYear === y ? " selected" : "") + '>' + esc(y) + "</option>").join("");
    depSel.innerHTML = '<option value="">All units</option>' + deps.map((d) => '<option value="' + esc(d) + '"' + (state.filterDepartment === d ? " selected" : "") + '>' + esc(d) + "</option>").join("");
    if (resetBtn) {
      resetBtn.classList.toggle("hidden", !(state.filterYear || state.filterDepartment));
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

  function parseCleanNum(val) {
    if (val === null || val === undefined || val === "") return NaN;
    if (typeof val === "number") return Number.isFinite(val) ? val : NaN;
    let s = String(val).trim();
    if (!s || /^(nan|none|null|n\/a|-|--)$/i.test(s)) return NaN;
    const isNeg = s.startsWith("(") && s.endsWith(")");
    if (isNeg) s = s.slice(1, -1).trim();
    s = s.replace(/\b(?:INR|Rs\.?|USD|EUR|GBP|AUD|CAD)(?=\s|[0-9₹$€£,(]|$)/gi, "").replace(/[₹$€£,\s]/g, "");
    if (!s) return NaN;
    const n = Number(s);
    if (!Number.isFinite(n)) return NaN;
    return isNeg ? -Math.abs(n) : n;
  }

  function parseDateIso(rawStr) {
    const s = String(rawStr || "").trim();
    if (!s) return null;
    // Match YYYY-MM-DD or YYYY/MM/DD (timezone-safe)
    let m = s.match(/^(\d{4})[-/](\d{1,2})[-/](\d{1,2})(?:[T\s].*)?$/);
    if (m) {
      const y = Number(m[1]), mo = Number(m[2]), d = Number(m[3]);
      if (mo >= 1 && mo <= 12 && d >= 1 && d <= 31) {
        return String(y).padStart(4, "0") + "-" + String(mo).padStart(2, "0") + "-" + String(d).padStart(2, "0");
      }
    }
    // Match DD-MM-YYYY or DD/MM/YYYY
    m = s.match(/^(\d{1,2})[-/](\d{1,2})[-/](\d{4})$/);
    if (m) {
      const a = Number(m[1]), b = Number(m[2]), y = Number(m[3]);
      const day = b <= 12 ? a : b;
      const mo = b <= 12 ? b : a;
      if (mo >= 1 && mo <= 12 && day >= 1 && day <= 31) {
        return String(y).padStart(4, "0") + "-" + String(mo).padStart(2, "0") + "-" + String(day).padStart(2, "0");
      }
    }
    const dt = new Date(s);
    if (Number.isNaN(dt.getTime())) return null;
    return dt.getFullYear() + "-" + String(dt.getMonth() + 1).padStart(2, "0") + "-" + String(dt.getDate()).padStart(2, "0");
  }

  function classifyTxnType(rawType) {
    const clean = String(rawType || "").toLowerCase().replace(/[^a-z]+/g, " ").trim();
    if (!clean) return "unknown";
    const words = new Set(clean.split(/\s+/));
    const expWords = ["expense", "expenses", "debit", "dr", "payment", "payments", "outflow", "withdrawal", "spend", "spending", "cost", "purchase", "payout", "expenditure", "paid"];
    for (const w of expWords) { if (words.has(w)) return "expense"; }
    const incWords = ["income", "credit", "cr", "receipt", "receipts", "revenue", "sale", "sales", "deposit", "inflow", "earning", "earnings", "contribution", "grant", "fee", "fees", "interest", "received"];
    for (const w of incWords) { if (words.has(w)) return "income"; }
    return "unknown";
  }

  function normHeaderKey(k) {
    return String(k || "").trim().toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();
  }

  function normalizeObjects(objects) {
    if (!Array.isArray(objects) || !objects.length) return [];
    const aliasMap = {
      date: ["date", "sales date", "transaction date", "txn date", "txn_date", "entry date", "posting date"],
      revenue: ["revenue", "total revenue", "gross revenue", "net revenue", "sales", "total sales", "income"],
      expense: ["expense", "expenses", "total expense", "total expenses", "spend", "spending", "expenditure", "operating expense"],
      credit: ["credit", "credit amount", "cr", "cr amount", "deposit", "receipt", "inflow"],
      debit: ["debit", "debit amount", "dr", "dr amount", "withdrawal", "payment", "outflow"],
      amount: [
        "total_amount_inr", "total amount inr", "total_amount", "total amount",
        "amount", "amount inr", "amount_inr", "transaction amount", "transaction_amount",
        "txn amount", "txn_amount", "net amount", "net_amount", "gross amount", "gross_amount",
        "total", "value"
      ],
      transaction_type: ["transaction type", "transaction_type", "type", "entry type", "dr/cr", "cr/dr", "flow"],
      transaction_id: ["transaction id", "transaction_id", "entry id", "entry_id", "voucher no", "receipt no", "reference", "ref no", "invoice id", "id"],
      fiscal_year: ["fiscal year", "fiscal_year", "year", "fy"],
      category: ["category", "segment", "account head"],
      subcategory: ["subcategory", "sub category", "sub_category", "nature", "account nature"],
      product: ["product", "item description", "item_description", "item", "service", "particulars"],
      department: ["department", "dept", "unit", "business unit", "course or dept", "course_or_dept", "course"],
      region: ["region", "location", "building or location", "building_or_location", "branch", "site"],
      vendor_name: ["vendor name", "vendor_name", "vendor", "merchant", "party", "paid to or received from", "paid_to_or_received_from", "payee", "payor", "counterparty"],
      payment_method: ["payment method", "payment_method", "payment mode", "payment_mode", "mode", "payment"],
      notes: ["notes", "note", "description", "remarks", "remark", "memo", "narration"],
      cost: ["cost", "cogs", "cost of goods sold"],
      quantity: ["quantity", "qty", "units"],
      unit_price: ["unit price", "unit_price", "unit amount inr", "unit_amount_inr", "unit amount", "price", "rate"],
      investment: ["investment", "capex"],
    };
    const keys = Object.keys(objects[0] || {});
    const lowerLookup = {};
    const normLookup = {};
    keys.forEach((k) => {
      lowerLookup[k.trim().toLowerCase()] = k;
      const nk = normHeaderKey(k);
      if (nk && normLookup[nk] === undefined) normLookup[nk] = k;
    });
    const mapped = {};
    const usedCols = new Set();
    Object.keys(aliasMap).forEach((canon) => {
      for (const alias of aliasMap[canon]) {
        const col = lowerLookup[alias];
        if (col !== undefined && !usedCols.has(col)) {
          mapped[canon] = col;
          usedCols.add(col);
          return;
        }
      }
      for (const alias of aliasMap[canon]) {
        const col = normLookup[normHeaderKey(alias)];
        if (col !== undefined && !usedCols.has(col)) {
          mapped[canon] = col;
          usedCols.add(col);
          return;
        }
      }
    });

    if (!mapped.date) return [];
    const hasDual = Boolean(mapped.revenue && mapped.expense);
    const hasCrDr = Boolean(mapped.credit || mapped.debit);
    const hasAmount = Boolean(mapped.amount);
    if (!hasDual && !hasCrDr && !hasAmount) {
      // Compatibility fallback if a simple file only has Revenue + Cost
      if (!(mapped.revenue && mapped.cost)) return [];
    }

    const out = [];
    for (const raw of objects) {
      const isoDate = parseDateIso(raw[mapped.date]);
      if (!isoDate) continue;

      let rev = 0;
      let exp = 0;
      const ttype = mapped.transaction_type ? String(raw[mapped.transaction_type] || "").trim() : "";

      if (hasDual) {
        const rv = parseCleanNum(raw[mapped.revenue]);
        const ev = parseCleanNum(raw[mapped.expense]);
        rev = Number.isNaN(rv) ? 0 : rv;
        exp = Number.isNaN(ev) ? 0 : ev;
        if (rev < 0 || exp < 0) continue;
      } else if (hasCrDr) {
        const cv = mapped.credit ? parseCleanNum(raw[mapped.credit]) : 0;
        const dv = mapped.debit ? parseCleanNum(raw[mapped.debit]) : 0;
        const cNum = Number.isNaN(cv) ? 0 : cv;
        const dNum = Number.isNaN(dv) ? 0 : dv;
        rev = cNum >= 0 ? cNum : 0;
        exp = dNum < 0 ? Math.abs(dNum) : (cNum < 0 ? Math.abs(cNum) : dNum);
      } else if (hasAmount) {
        const av = parseCleanNum(raw[mapped.amount]);
        const amt = Number.isNaN(av) ? 0 : av;
        const kind = classifyTxnType(ttype);
        if (kind === "expense") {
          exp = Math.abs(amt);
        } else if (kind === "income") {
          if (amt >= 0) rev = amt;
          else exp = Math.abs(amt);
        } else {
          if (amt >= 0) rev = amt;
          else exp = Math.abs(amt);
        }
      } else {
        const rv = parseCleanNum(raw[mapped.revenue]);
        const ev = parseCleanNum(raw[mapped.cost]);
        rev = Number.isNaN(rv) ? 0 : rv;
        exp = Number.isNaN(ev) ? 0 : ev;
        if (rev < 0 || exp < 0) continue;
      }

      const costVal = mapped.cost ? parseCleanNum(raw[mapped.cost]) : 0;
      const qtyVal = mapped.quantity ? parseCleanNum(raw[mapped.quantity]) : 0;
      const upVal = mapped.unit_price ? parseCleanNum(raw[mapped.unit_price]) : 0;
      const invVal = mapped.investment ? parseCleanNum(raw[mapped.investment]) : 0;
      const fyRaw = mapped.fiscal_year ? parseCleanNum(raw[mapped.fiscal_year]) : NaN;
      const fy = Number.isFinite(fyRaw) && fyRaw > 1900 ? Math.round(fyRaw) : Number(isoDate.slice(0, 4));

      out.push({
        txn_date: isoDate,
        period: isoDate.slice(0, 7),
        fiscal_year: fy,
        transaction_id: mapped.transaction_id ? String(raw[mapped.transaction_id] || "").trim() : "",
        transaction_type: ttype,
        subcategory: mapped.subcategory ? String(raw[mapped.subcategory] || "").trim() : "",
        category: (mapped.category ? String(raw[mapped.category] || "").trim() : "") || "Uncategorized",
        product: (mapped.product ? String(raw[mapped.product] || "").trim() : "") || "Unspecified",
        department: (mapped.department ? String(raw[mapped.department] || "").trim() : "") || "General",
        region: (mapped.region ? String(raw[mapped.region] || "").trim() : "") || "Global",
        vendor_name: mapped.vendor_name ? String(raw[mapped.vendor_name] || "").trim() : "",
        payment_method: mapped.payment_method ? String(raw[mapped.payment_method] || "").trim() : "",
        notes: mapped.notes ? String(raw[mapped.notes] || "").trim() : "",
        revenue: rev,
        expense: exp,
        cost: Number.isNaN(costVal) ? 0 : Math.max(0, costVal),
        quantity: Number.isNaN(qtyVal) ? 0 : Math.max(0, qtyVal),
        unit_price: Number.isNaN(upVal) ? 0 : Math.max(0, upVal),
        investment: Number.isNaN(invVal) ? 0 : Math.max(0, invVal),
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

  function computeForecast(series, horizon, modelMode) {
    if (series.length < 4) return null;
    const mode = modelMode === "ols" ? "ols" : "ensemble";
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

    // Seasonal calendar-month residual effect when >= 12 historical months exist
    const monthRes = {};
    if (n >= 12) {
      for (let i = 0; i < n; i++) {
        const mo = Number((series[i].period || "").slice(5, 7));
        const res = y[i] - (slope * i + intercept);
        if (!monthRes[mo]) monthRes[mo] = { sum: 0, cnt: 0 };
        monthRes[mo].sum += res;
        monthRes[mo].cnt += 1;
      }
    }

    const useEnsemble = mode === "ensemble" && n >= 6;
    const recentTail = y.slice(-Math.min(6, n));
    let recentVelocity = 0;
    if (recentTail.length >= 2) {
      recentVelocity = (recentTail[recentTail.length - 1] - recentTail[0]) / (recentTail.length - 1);
    }

    let absErr = 0, sqErr = 0, apeSum = 0, apeCount = 0;
    const residuals = [];
    for (let i = 0; i < n; i++) {
      let pred = slope * i + intercept;
      if (useEnsemble) {
        const mo = Number((series[i].period || "").slice(5, 7));
        const sAdj = monthRes[mo] && monthRes[mo].cnt ? (monthRes[mo].sum / monthRes[mo].cnt) * 0.45 : 0;
        pred = pred * 0.72 + (y[Math.max(0, i - 1)] + recentVelocity * 0.65) * 0.28 + sAdj;
      }
      const err = Math.abs(y[i] - pred);
      residuals.push(y[i] - pred);
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
    const meanY = sumY / n;
    const ssTot = y.reduce((a, v) => a + (v - meanY) * (v - meanY), 0);
    const r2 = ssTot > 1e-6 ? round2(1 - sqErr / ssTot) : 0;
    const stdErr = Math.max(mae * 1.15, Math.sqrt(sqErr / Math.max(1, n - 2)));

    const lastDate = new Date(series[n - 1].period + "-01T00:00:00");
    const future = [];
    let rollingAnchor = y[n - 1];
    for (let step = 1; step <= horizon; step++) {
      const d = new Date(lastDate.getFullYear(), lastDate.getMonth() + step, 1);
      const label = d.getFullYear() + "-" + String(d.getMonth() + 1).padStart(2, "0");
      const linVal = slope * (n - 1 + step) + intercept;
      let val = linVal;
      if (useEnsemble) {
        const mo = d.getMonth() + 1;
        const sAdj = monthRes[mo] && monthRes[mo].cnt ? (monthRes[mo].sum / monthRes[mo].cnt) * 0.45 : 0;
        rollingAnchor = rollingAnchor + recentVelocity * 0.55;
        val = linVal * 0.62 + rollingAnchor * 0.38 + sAdj;
      }
      const band = 1.645 * stdErr * Math.sqrt(1 + step * 0.14);
      future.push({
        period: label,
        forecast: round2(val),
        low: round2(val - band),
        high: round2(val + band),
      });
    }
    return {
      modelLabel: useEnsemble ? "Ensemble ML Momentum + Seasonal" : "Linear trend regression",
      slope: round2(slope),
      mae,
      rmse,
      mape,
      r2,
      history: series.map((s) => ({ period: s.period, actual: s.profit })),
      future,
    };
  }

  function computeRiskProfile(rows) {
    if (!rows.length) {
      return { total: 0, high: 0, moderate: 0, low: 0, highPct: 0, avgScore: 0, highExposure: 0 };
    }
    const expPos = rows.map((r) => r.expense).filter((v) => v > 0).sort((a, b) => a - b);
    const q1 = quantile(expPos, 0.25);
    const q3 = quantile(expPos, 0.75);
    const iqr = Math.max(0, q3 - q1);
    const medExp = quantile(expPos, 0.5);
    const cutoff = expPos.length >= 4 ? q3 + state.cfg.anomalyIqr * iqr : (medExp * 2.5 || 1e9);

    let high = 0, moderate = 0, low = 0, scoreSum = 0, highExposure = 0;
    for (const r of rows) {
      const rev = r.revenue || 0;
      const exp = r.expense || 0;
      let score = 16;
      if (rev > 0 && exp > 0) {
        const ratio = exp / rev;
        score += Math.min(48, Math.max(0, (ratio - 0.52) * 85));
        if (exp > rev) score += 18;
      } else if (exp > 0 && rev === 0) {
        // Institutional expense entry: score by size relative to expense distribution
        if (exp > cutoff) score += 52;
        else if (q3 > 0 && exp >= q3) score += 26;
        else score += 10;
      }
      if (exp > cutoff && exp > 0) score += 20;
      if (!r.category || r.category === "Uncategorized") score += 6;
      const bounded = Math.max(5, Math.min(99, score));
      scoreSum += bounded;
      if (bounded >= 68) {
        high += 1;
        highExposure += exp;
      } else if (bounded >= 42) {
        moderate += 1;
      } else {
        low += 1;
      }
    }
    const total = rows.length;
    return {
      total,
      high,
      moderate,
      low,
      highPct: round2((high / total) * 100),
      avgScore: round2(scoreSum / total),
      highExposure: round2(highExposure),
    };
  }

  function computeCashflowRunway(series) {
    if (!series.length) {
      return { months: 0, recentRev: 0, recentExp: 0, recentNet: 0, savingsRate: null, cashReserve: 0, runwayMonths: null, status: "No Data" };
    }
    const tail = series.slice(-Math.min(3, series.length));
    const recentRev = round2(tail.reduce((a, s) => a + s.revenue, 0) / tail.length);
    const recentExp = round2(tail.reduce((a, s) => a + s.expense, 0) / tail.length);
    const recentNet = round2(recentRev - recentExp);
    const savingsRate = recentRev > 0 ? round2((recentNet / recentRev) * 100) : null;
    const cumReserve = round2(series[series.length - 1].cum_profit || 0);
    let runwayMonths = null;
    let status = "Surplus Generating";
    if (recentNet < 0) {
      const burn = Math.abs(recentNet);
      runwayMonths = cumReserve > 0 ? round2(cumReserve / burn) : 0;
      status = runwayMonths >= 12 ? "Watch" : "Critical";
    } else if (savingsRate !== null && savingsRate < state.cfg.marginThreshold) {
      status = "Watch";
    }
    return { months: series.length, recentRev, recentExp, recentNet, savingsRate, cashReserve: cumReserve, runwayMonths, status };
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
    const hasTotal = state.rows.length > 0;
    document.getElementById("overviewEmpty").classList.toggle("hidden", hasTotal);
    document.getElementById("overviewPopulated").classList.toggle("hidden", !hasTotal);
    if (!hasTotal) {
      destroyChart("overview");
      return;
    }

    renderFilterOptions();
    const rows = getActiveRows();
    if (!rows.length) {
      document.getElementById("overviewKpis").innerHTML = kpiCard("Filtered rows", "0", "Adjust Year/Unit filter");
      renderBrief("overviewBrief", "Executive intelligence brief", "No matching transactions in current filter.", "Reset Year or Department filters to view ledger metrics.", "0 records matched the selected filter criteria.", "Tap Reset filter above to restore all records.");
      destroyChart("overview");
      const mlKpiEl = document.getElementById("overviewMlKpis");
      if (mlKpiEl) mlKpiEl.innerHTML = "";
      return;
    }

    const m = computeMetrics(rows);
    const series = monthlySeries(rows);
    const kpiEl = document.getElementById("overviewKpis");
    kpiEl.innerHTML =
      kpiCard("Total revenue", fmtCurr(m.revenue), m.transactions + " rows") +
      kpiCard("Operating expenses", fmtCurr(m.expenses), (m.expense_ratio === null ? "N/A" : fmtNum(m.expense_ratio, 1) + "%") + " of revenue") +
      kpiCard("Net profit", fmtCurr(m.profit), (m.margin === null ? "N/A" : fmtNum(m.margin, 1) + "%") + " margin", m.profit >= 0 ? "pos" : "neg") +
      kpiCard("Return on investment", m.roi === null ? "N/A" : fmtNum(m.roi, 2) + "%", "Gross " + fmtCurr(m.gross_profit));

    const rp = computeRiskProfile(rows);
    const rw = computeCashflowRunway(series);
    const mlKpiEl = document.getElementById("overviewMlKpis");
    const mlSubEl = document.getElementById("overviewMlSub");
    if (mlKpiEl) {
      mlKpiEl.innerHTML =
        kpiCard("High-risk entries", fmtNum(rp.high) + " (" + fmtNum(rp.highPct, 1) + "%)", fmtNum(rp.moderate) + " mod · " + fmtNum(rp.low) + " low", rp.high > 0 ? "neg" : "pos") +
        kpiCard("Mean risk score", fmtNum(rp.avgScore, 1) + " / 100", "Exposure " + fmtCurr(rp.highExposure)) +
        kpiCard("Recent net pace/mo", fmtCurr(rw.recentNet), (rw.savingsRate === null ? "No inflow pace" : "Savings " + fmtNum(rw.savingsRate, 1) + "%"), rw.recentNet >= 0 ? "pos" : "neg") +
        kpiCard("Liquidity posture", rw.runwayMonths === null ? "Self-Sustaining" : fmtNum(rw.runwayMonths, 1) + " months", rw.status);
    }
    if (mlSubEl) {
      mlSubEl.textContent = "Screened " + fmtNum(rp.total) + " transactions across " + rw.months + " months on-device";
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
    const active = getActiveRows();
    const isEmpty = active.length === 0;
    document.getElementById("segmentsEmpty").classList.toggle("hidden", !isEmpty);
    document.getElementById("segmentsPopulated").classList.toggle("hidden", isEmpty);
    if (isEmpty) {
      destroyChart("segment");
      return;
    }

    const dim = state.segmentDim;
    const rows = byDimension(active, dim);
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
    const chartRows = rows.length > 12 ? rows.slice(0, 12) : rows;
    const segSubEl = document.getElementById("segmentChartSub");
    if (segSubEl) {
      segSubEl.textContent = rows.length > 12
        ? "Top 12 of " + rows.length + " segments (full ledger in table below)"
        : "Switch visualization format";
    }
    const labels = chartRows.map((r) => r.label);
    let mode = state.segmentMode;
    if (mode === "share" && rows.filter((r) => r.profit > 0).length < 2) mode = "margin";

    if (mode === "share") {
      const posRows = rows.filter((r) => r.profit > 0).slice(0, 10);
      state.charts.segment = new Chart(ctx, {
        type: "doughnut",
        data: {
          labels: posRows.map((r) => r.label),
          datasets: [{ data: posRows.map((r) => r.profit), backgroundColor: ["#1D1D1F", "#0066CC", "#0E6027", "#C2590A", "#636368", "#515154", "#3B9BFF", "#2E7D32", "#B45309", "#8E8E93"] }]
        },
        options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { position: "bottom" } } }
      });
    } else if (mode === "revprofit") {
      state.charts.segment = new Chart(ctx, {
        type: "bar",
        data: {
          labels,
          datasets: [
            { label: "Revenue", data: chartRows.map((r) => r.revenue), backgroundColor: "#0066CC", borderRadius: 4 },
            { label: "Profit", data: chartRows.map((r) => r.profit), backgroundColor: "#0E6027", borderRadius: 4 }
          ]
        },
        options: chartOptions(false)
      });
    } else {
      state.charts.segment = new Chart(ctx, {
        type: "bar",
        data: {
          labels,
          datasets: [{ label: "Margin %", data: chartRows.map((r) => r.margin || 0), backgroundColor: chartRows.map((r) => (r.margin || 0) >= state.cfg.marginThreshold ? "#0E6027" : "#A61B1B"), borderRadius: 4 }]
        },
        options: chartOptions(true)
      });
    }
  }

  function renderAnomalies() {
    const active = getActiveRows();
    const isEmpty = active.length === 0;
    document.getElementById("anomaliesEmpty").classList.toggle("hidden", !isEmpty);
    document.getElementById("anomaliesPopulated").classList.toggle("hidden", isEmpty);
    if (isEmpty) {
      destroyChart("anomaly");
      return;
    }

    const flags = detectAnomalies(active, state.cfg.anomalyIqr);
    const m = computeMetrics(active);
    const totalExcess = flags.reduce((a, f) => a + Math.max(0, f.value - f.threshold), 0);

    if (!flags.length) {
      renderBrief("anomalyBrief", "Anomaly surveillance",
        "Zero outliers detected at " + state.cfg.anomalyIqr + "x IQR.",
        "Monitors transaction-level revenue and expense spikes above Q3 + " + state.cfg.anomalyIqr + " × IQR.",
        "All " + active.length + " transactions remained inside normal interquartile operating bounds.",
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
      "Screens revenue & expense outliers exceeding Q3 + " + state.cfg.anomalyIqr + " × IQR across " + active.length + " entries.",
      "Largest variance occurred in " + top.entity + " (" + top.date + ") where " + top.metric + " hit " + fmtCurr(top.value) + " vs. cutoff " + fmtCurr(top.threshold) + ".",
      "Preventing excess cost spikes above statistical cutoffs would have preserved +" + fmtCurr(totalExcess) + " (~" + fmtNum(m.revenue > 0 ? (totalExcess / m.revenue) * 100 : 0, 1) + " pts margin)."
    );

    const tbl = document.getElementById("anomalyTable");
    const shownFlags = flags.slice(0, 120);
    tbl.innerHTML =
      "<thead><tr><th>Date</th><th>Entity</th><th>Metric</th><th class='num'>Observed</th><th class='num'>IQR Cutoff</th></tr></thead><tbody>" +
      shownFlags.map((f) => "<tr><td>" + esc(f.date) + "</td><td>" + esc(f.entity) + "</td><td>" + esc(f.metric) + "</td><td class='num'>" + fmtNum(f.value) + "</td><td class='num'>" + fmtNum(f.threshold) + "</td></tr>").join("") +
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
    const active = getActiveRows();
    const isEmpty = active.length === 0;
    document.getElementById("forecastEmpty").classList.toggle("hidden", !isEmpty);
    document.getElementById("forecastPopulated").classList.toggle("hidden", isEmpty);
    if (isEmpty) {
      destroyChart("forecast");
      return;
    }

    const series = monthlySeries(active);
    const horizon = Number(document.getElementById("forecastMonths").value || 6);
    const engineSel = document.getElementById("forecastModelMode");
    const modelMode = engineSel ? engineSel.value : state.forecastModel;
    state.forecastModel = modelMode;
    const fc = computeForecast(series, horizon, modelMode);
    const m = computeMetrics(active);

    if (!fc) {
      renderBrief("forecastBrief", "Forecast & solver intelligence", "At least 4 monthly periods are required.",
        "Ensemble ML + OLS regression projects profit trajectories over 3–18 months.",
        "Current dataset contains fewer than 4 distinct monthly periods.",
        "Import multi-month history to unlock backtested projections.");
      destroyChart("forecast");
    } else {
      const dir = fc.slope >= 0 ? "expanding +" : "contracting ";
      const endRow = fc.future[fc.future.length - 1];
      renderBrief(
        "forecastBrief",
        "Forecast intelligence brief",
        "Trend slope is " + dir + fmtCurr(fc.slope) + "/month toward " + fmtCurr(endRow.forecast) + " in " + horizon + " months.",
        fc.modelLabel + " across " + series.length + " historical months (MAE " + fmtCurr(fc.mae) + ", R² " + fmtNum(fc.r2, 2) + ").",
        "Projected range by " + endRow.period + " spans " + fmtCurr(endRow.low) + " to " + fmtCurr(endRow.high) + " (RMSE " + fmtCurr(fc.rmse) + ").",
        "Improving monthly operational capture shifts every future projected period proportionately."
      );
      document.getElementById("forecastMetricsText").textContent =
        fc.modelLabel + " · MAE " + fmtNum(fc.mae) + " · RMSE " + fmtNum(fc.rmse) + " · R² " + fmtNum(fc.r2, 2);

      destroyChart("forecast");
      const labels = fc.history.map((h) => h.period).concat(fc.future.map((f) => f.period));
      const actualData = fc.history.map((h) => h.actual).concat(fc.future.map(() => null));
      const bridgeIdx = fc.history.length - 1;
      const projData = fc.history.map((h, i) => i === bridgeIdx ? h.actual : null).concat(fc.future.map((f) => f.forecast));
      const upperData = fc.history.map((h, i) => i === bridgeIdx ? h.actual : null).concat(fc.future.map((f) => f.high));
      const lowerData = fc.history.map((h, i) => i === bridgeIdx ? h.actual : null).concat(fc.future.map((f) => f.low));
      state.charts.forecast = new Chart(document.getElementById("forecastCanvas").getContext("2d"), {
        type: "line",
        data: {
          labels,
          datasets: [
            { label: "Actual Profit", data: actualData, borderColor: "#1D1D1F", backgroundColor: "#1D1D1F", tension: 0.25 },
            { label: "Forecast", data: projData, borderColor: "#0066CC", borderDash: [6, 4], tension: 0.2 },
            { label: "Upper 90%", data: upperData, borderColor: "rgba(0,102,204,0.28)", backgroundColor: "rgba(0,102,204,0.08)", borderDash: [2, 3], pointRadius: 0, fill: "+1" },
            { label: "Lower 90%", data: lowerData, borderColor: "rgba(0,102,204,0.28)", borderDash: [2, 3], pointRadius: 0, fill: false }
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
    writeJsonStorage(STORAGE_SYNC_OUTBOX, arr.slice(-4));
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
        statusBox.textContent = "Version " + (info.installedVersion || "1.2.0") + " · Offline mode";
      } else if (info.checked) {
        statusBox.textContent = "Up to date (v" + (info.installedVersion || "1.2.0") + ")";
      } else {
        statusBox.textContent = "Version " + (info.installedVersion || "1.2.0") + " · Offline-Ready";
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
    const activeCount = getActiveRows().length;
    document.getElementById("workspaceSummary").innerHTML = state.rows.length
      ? "<strong>" + esc(state.meta.source) + "</strong> · " + fmtNum(activeCount) + (activeCount !== state.rows.length ? " of " + fmtNum(state.rows.length) : "") + " records"
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

  function generateEnterprise10kRows() {
    let seed = 20260420;
    function rand() {
      seed = (seed + 0x6D2B79F5) | 0;
      let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
      t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    }
    const years = [2022, 2023, 2024, 2025, 2026];
    const cats = ["Software", "Consulting", "Services", "Infrastructure", "Payroll"];
    const prods = ["Core Suite", "Insight Pro", "Advisory Plan", "CloudOps Shield", "Campus Support"];
    const depts = ["Engineering", "Customer Success", "Product", "Services", "Operations"];
    const regs = ["North", "South", "West", "East"];
    const modes = ["UPI", "NEFT", "Bank Transfer", "Corporate Card", "Cheque"];
    const vendors = ["Apex Cloud Ltd", "Southern Grid Corp", "Meridian Advisors", "Vertex Tech", "Coastal Logistics"];
    const rows = [];
    for (let i = 0; i < 10000; i++) {
      const y = years[i % years.length];
      const mo = (i * 7 + Math.floor(rand() * 3)) % 12 + 1;
      const day = Math.floor(rand() * 27) + 1;
      const dt = String(y) + "-" + String(mo).padStart(2, "0") + "-" + String(day).padStart(2, "0");
      const ci = i % cats.length;
      const growth = 1 + (y - 2022) * 0.14;
      const isSpike = i % 197 === 0;
      const rev = round2((12000 + rand() * 34000) * growth);
      const expBase = (6500 + rand() * 19500) * growth;
      const exp = round2(isSpike ? expBase * 2.85 : expBase);
      const cost = round2(rev * (0.22 + rand() * 0.08));
      const qty = Math.floor(rand() * 45) + 5;
      rows.push({
        txn_date: dt,
        period: dt.slice(0, 7),
        fiscal_year: y,
        transaction_id: "ENT-" + String(i + 1).padStart(5, "0"),
        transaction_type: isSpike ? "Adjustment Expense" : "Sale",
        subcategory: isSpike ? "Outlier Audit Item" : "Recurring Operations",
        category: cats[ci],
        product: prods[(i + Math.floor(rand() * 2)) % prods.length],
        department: depts[i % depts.length],
        region: regs[(i >> 2) % regs.length],
        vendor_name: vendors[i % vendors.length],
        payment_method: modes[i % modes.length],
        notes: isSpike ? "Scheduled capital spike" : "Automated enterprise ledger record",
        revenue: rev,
        expense: exp,
        cost: cost,
        quantity: qty,
        unit_price: round2(rev / qty),
        investment: i % 25 === 0 ? 5000 : 0,
      });
    }
    return rows;
  }

  function loadEnterprise10kIntoWorkspace() {
    const rows = generateEnterprise10kRows();
    saveWorkspace(rows, "enterprise_10k_ledger.csv");
    if (state.user) queueDatasetSync(state.user.email, "enterprise_10k_ledger.csv", rows.slice(0, 2000));
    switchTab("overview");
    showNotice("Generated & loaded 10,000-row enterprise dataset locally.");
  }

  function parseReceiptText(rawText) {
    const text = String(rawText || "").trim();
    const low = text.toLowerCase();
    const res = {
      txn_date: new Date().toISOString().slice(0, 10),
      flow: "expense",
      amount: "",
      vendor: "",
      category: "Operations",
    };
    const isoM = text.match(/\b(20\d{2})[-/](\d{1,2})[-/](\d{1,2})\b/);
    const dmyM = text.match(/\b(\d{1,2})[-/](\d{1,2})[-/](20\d{2})\b/);
    if (isoM) {
      res.txn_date = isoM[1] + "-" + String(isoM[2]).padStart(2, "0") + "-" + String(isoM[3]).padStart(2, "0");
    } else if (dmyM) {
      res.txn_date = dmyM[3] + "-" + String(dmyM[2]).padStart(2, "0") + "-" + String(dmyM[1]).padStart(2, "0");
    }
    if (/\b(credited|received|salary|fee receipt|income|deposit|refund)\b/i.test(low)) {
      res.flow = "income";
    }
    const textNoDate = text
      .replace(/\b20\d{2}[-/]\d{1,2}[-/]\d{1,2}\b/g, " ")
      .replace(/\b\d{1,2}[-/]\d{1,2}[-/]20\d{2}\b/g, " ");
    const amtM = textNoDate.match(/(?:INR|Rs\.?|₹|\$|USD)\s*([0-9][0-9,]*(?:\.[0-9]{1,2})?)/i)
      || textNoDate.match(/(?:total|amount|amt|paid|bill|salary|received|debited|credited)\s*[:\-]?\s*([0-9]{1,3}(?:,[0-9]{2,3})+(?:\.[0-9]{1,2})?|[0-9]+(?:\.[0-9]{1,2})?)/i)
      || textNoDate.match(/\b([0-9]{1,3}(?:,[0-9]{2,3})+(?:\.[0-9]{1,2})?|[0-9]{3,}(?:\.[0-9]{1,2})?)\b/);
    if (amtM) {
      const v = Number(amtM[1].replace(/,/g, ""));
      if (Number.isFinite(v) && v > 0) res.amount = String(round2(v));
    }
    const venM = text.match(/\b(?:to|from|at|vendor|merchant|payee)\s+([A-Za-z0-9&.\- ]{2,32}?)(?=\s+(?:on|for|via|inr|rs|₹|$)|\s*[,.;\n]|$)/i);
    if (venM) res.vendor = venM[1].trim();
    if (/salary|payroll|wage/i.test(low)) res.category = "Payroll";
    else if (/equipment|lab|software|cloud|server/i.test(low)) res.category = "Infrastructure";
    else if (/tuition|fee|grant|consulting/i.test(low)) res.category = "Services";
    else if (/travel|fuel|uber|flight|train/i.test(low)) res.category = "Travel";
    else if (/power|electricity|water|internet|rent|utility/i.test(low)) res.category = "Utilities";
    return res;
  }

  function detectMobileLanguage(question, explicitLang) {
    if (explicitLang === "en" || explicitLang === "ta" || explicitLang === "hi") return explicitLang;
    const q = String(question || "");
    if (/[\u0B80-\u0BFF]/.test(q)) return "ta";
    if (/[\u0900-\u097F]/.test(q)) return "hi";
    const low = q.toLowerCase();
    if (/\b(sambalam|selavu|varuvai|labam|semippu|ethirkala|aabathu|enna|ethanai|vendum)\b/.test(low)) return "ta";
    if (/\b(kamai|kharcha|bachat|munafa|bhavishya|kitna|kya karu|chahiye|khatra)\b/.test(low)) return "hi";
    return "en";
  }

  function parsePersonalBudgetQuery(question) {
    const q = String(question || "");
    const low = q.toLowerCase();
    const hasCue = /(salary|salaried|paycheck|earn|sambalam|सैलरी|वेतन|சம்பளம்|spend|selavu|kharcha|बचत|சேமிப்பு)/i.test(low);
    if (!hasCue) return null;
    const pat = /(?:inr|rs\.?|₹|\$)?\s*([0-9]{1,3}(?:,[0-9]{2,3})+|[0-9]+(?:\.[0-9]+)?)\s*(k|l|lac|lakh|lakhs|m|mn|cr|crore)?\b/gi;
    const hits = [];
    let m;
    while ((m = pat.exec(q)) !== null) {
      let val = Number(m[1].replace(/,/g, ""));
      const suf = (m[2] || "").toLowerCase();
      if (suf === "k") val *= 1000;
      else if (suf === "l" || suf === "lac" || suf === "lakh" || suf === "lakhs") val *= 100000;
      else if (suf === "m" || suf === "mn") val *= 1000000;
      else if (suf === "cr" || suf === "crore") val *= 10000000;
      if (!suf && ((val >= 1900 && val <= 2099) || val < 500)) continue;
      const ctx = low.slice(Math.max(0, m.index - 24), Math.min(low.length, m.index + m[0].length + 24));
      hits.push({ val, ctx });
    }
    if (hits.length < 2) return null;
    let salary = null, spend = null, save = null;
    for (const h of hits) {
      if (salary === null && /(salary|earn|income|get|sambalam|वेतन|सैलरी|சம்பளம்)/.test(h.ctx)) salary = h.val;
      else if (spend === null && /(spend|spent|expense|kharcha|selavu|खर्च|செலவு)/.test(h.ctx)) spend = h.val;
      else if (save === null && /(rest|save|saving|remaining|left|bachat|semippu|meedhi|बचत|மீதி)/.test(h.ctx)) save = h.val;
    }
    const sorted = hits.map((h) => h.val).sort((a, b) => b - a);
    if (salary === null) salary = sorted[0];
    if (spend === null) spend = sorted.find((v) => Math.abs(v - salary) > 1e-6) || 0;
    if (salary <= 0) return null;
    if (save === null) save = Math.max(0, salary - spend);
    return { salary, spend, save };
  }

  function askMobileCopilot(question, explicitLang) {
    const cleanQ = String(question || "").trim();
    const low = cleanQ.toLowerCase();
    const lang = detectMobileLanguage(cleanQ, explicitLang);
    const curr = state.cfg.currency;

    const personal = parsePersonalBudgetQuery(cleanQ);
    if (personal) {
      const { salary, spend, save } = personal;
      const net = salary - spend;
      const sr = salary > 0 ? round2((net / salary) * 100) : 0;
      const er = salary > 0 ? round2((spend / salary) * 100) : 0;
      const emer3 = spend * 3;
      const emer6 = spend * 6;
      const allocEmer = Math.round(save * 0.50);
      const allocInv = Math.round(save * 0.35);
      const allocShield = Math.max(0, Math.round(save - allocEmer - allocInv));
      const rLiq = 0.065 / 12, rSip = 0.11 / 12, halfS = save * 0.5;
      const fv3y = Math.round(halfS * ((Math.pow(1 + rLiq, 36) - 1) / rLiq) + halfS * ((Math.pow(1 + rSip, 36) - 1) / rSip));
      const riskLabel = net <= 0 ? "Critical Risk (Zero Surplus)" : (sr < 15 ? "Elevated Risk" : (sr < 25 ? "Moderate Risk" : "Managed Risk"));

      if (lang === "ta") {
        return {
          title: "தனிநபர் சம்பளம் & ஆபத்து திட்டம்",
          meta: "On-Device Copilot · தமிழ்",
          answer: "சம்பளம் " + curr + " " + fmtNum(salary) + " இல் " + curr + " " + fmtNum(spend) + " (" + er + "%) செலவு செய்து " + curr + " " + fmtNum(save) + " (" + sr + "%) சேமிப்பது நல்ல தொடக்கம் (" + riskLabel + "). 6 மாத அவசர நிதி (" + curr + " " + fmtNum(emer6) + ") சேரும் வரை மருத்துவ/வருமானத் தடை ஆபத்து உள்ளது.",
          metrics: [
            { label: "மாத சேமிப்பு", value: curr + " " + fmtNum(save) + " (" + sr + "%)" },
            { label: "Risk Status", value: riskLabel },
            { label: "6-மாத அவசர நிதி", value: curr + " " + fmtNum(emer6) },
            { label: "3-ஆண்டு மதிப்பு", value: curr + " " + fmtNum(fv3y) },
          ],
          actions: [
            "1. அவசர நிதி (50% = " + curr + " " + fmtNum(allocEmer) + "/மாதம்): " + curr + " " + fmtNum(emer3) + " சேரும் வரை Liquid Fund / Sweep FD-ல் சேமிக்கவும்.",
            "2. வளர்ச்சி SIP (35% = " + curr + " " + fmtNum(allocInv) + "/மாதம்): 3-மாத Buffer பின் Index SIP தொடங்கவும் (~" + curr + " " + fmtNum(fv3y) + ").",
            "3. காப்பீடு & பாதுகாப்பு (15% = " + curr + " " + fmtNum(allocShield) + "/மாதம்): Health/Term insurance எடுத்து +10% செலவு உயர்வைத் தவிர்க்கவும்.",
          ],
        };
      }
      if (lang === "hi") {
        return {
          title: "व्यक्तिगत वेतन और जोखिम सलाहकार",
          meta: "On-Device Copilot · हिन्दी",
          answer: curr + " " + fmtNum(salary) + " मासिक सैलरी में " + curr + " " + fmtNum(spend) + " (" + er + "%) खर्च के बाद " + curr + " " + fmtNum(save) + " (" + sr + "% बचत) एक मजबूत शुरुआत है (" + riskLabel + ")। मुख्य जोखिम: " + curr + " " + fmtNum(emer6) + " इमरजेंसी फंड (6 माह खर्च) के बिना आय रुकने का खतरा रहता है।",
          metrics: [
            { label: "मासिक बचत", value: curr + " " + fmtNum(save) + " (" + sr + "%)" },
            { label: "जोखिम स्तर", value: riskLabel },
            { label: "6-माह इमरजेंसी", value: curr + " " + fmtNum(emer6) },
            { label: "3-वर्ष अनुमान", value: curr + " " + fmtNum(fv3y) },
          ],
          actions: [
            "1. इमरजेंसी बफर (50% = " + curr + " " + fmtNum(allocEmer) + "/माह): " + curr + " " + fmtNum(emer3) + "–" + fmtNum(emer6) + " के लिए Liquid Fund / RD में डालें।",
            "2. ग्रोथ SIP (35% = " + curr + " " + fmtNum(allocInv) + "/माह): 1 माह के बफर के बाद Index SIP शुरू करें (~" + curr + " " + fmtNum(fv3y) + " संभावित)।",
            "3. रिस्क शील्ड (15% = " + curr + " " + fmtNum(allocShield) + "/माह): टर्म व हेल्थ बीमा रखें और 10% अतिरिक्त खर्च को रोकें।",
          ],
        };
      }
      return {
        title: "Personal Cash-Flow & Risk Plan",
        meta: "On-Device Copilot · English",
        answer: "Saving " + curr + " " + fmtNum(save) + " on " + curr + " " + fmtNum(salary) + " (" + sr + "% savings rate, " + er + "% expense load) clears the 20% benchmark (" + riskLabel + "). Main risk factor: zero emergency buffer covers <1 month if pay pauses, and a 10% expense jump cuts monthly surplus by " + Math.round((spend * 0.1 / Math.max(1, save)) * 100) + "%.",
        metrics: [
          { label: "Monthly Surplus", value: curr + " " + fmtNum(save) + " (" + sr + "%)" },
          { label: "Risk Factor", value: riskLabel },
          { label: "6-Month Buffer", value: curr + " " + fmtNum(emer6) },
          { label: "3-Year Wealth", value: curr + " " + fmtNum(fv3y) },
        ],
        actions: [
          "1. Emergency Runway (50% = " + curr + " " + fmtNum(allocEmer) + "/mo): Liquid Fund / Sweep FD until " + curr + " " + fmtNum(emer3) + "–" + curr + " " + fmtNum(emer6) + " is funded.",
          "2. Compounding SIP (35% = " + curr + " " + fmtNum(allocInv) + "/mo): Start index / recurring SIP (~" + curr + " " + fmtNum(fv3y) + " 3-yr total).",
          "3. Protection (15% = " + curr + " " + fmtNum(allocShield) + "/mo): Keep health & term cover so medical bills never wipe savings.",
        ],
      };
    }

    const rows = getActiveRows();
    if (!rows.length) {
      return {
        title: "Workspace Ready",
        meta: "Offline Copilot",
        answer: "Import a CSV/JSON ledger or load the 10,000-row enterprise sample — or ask a personal cashflow question like: '30k salary, 22k spend, 8k savings — what is the risk?'",
        metrics: [],
        actions: ["Tap Load 10,000-row sample or Upload financial data on Overview"],
      };
    }

    const m = computeMetrics(rows);
    const series = monthlySeries(rows);
    const rp = computeRiskProfile(rows);
    const rw = computeCashflowRunway(series);

    if (/(predict|forecast|projection|future|ethirkala|kanippu|bhavishya|कணிப்பு|கணிப்பு|भविष्य)/i.test(low)) {
      const hM = low.match(/\b(\d{1,2})\s*(?:month|months|mo|माह|மாத)\b/);
      const horizon = hM ? Math.max(3, Math.min(24, Number(hM[1]))) : 6;
      const fc = computeForecast(series, horizon, state.forecastModel);
      if (!fc) {
        return { title: "Forecast Unavailable", meta: "Offline Forecast", answer: "At least 4 distinct monthly periods are required.", metrics: [], actions: [] };
      }
      const endRow = fc.future[fc.future.length - 1];
      const cumFc = round2(fc.future.reduce((a, r) => a + r.forecast, 0));
      const ans = lang === "ta"
        ? fc.modelLabel + " அடிப்படையில் அடுத்த " + horizon + " மாத நிகர கணிப்பு: " + endRow.period + " இல் " + fmtCurr(endRow.forecast) + " (மொத்தம் " + fmtCurr(cumFc) + ", MAE " + fmtCurr(fc.mae) + ")."
        : (lang === "hi"
          ? fc.modelLabel + " के अनुसार अगले " + horizon + " माह का पूर्वानुमान " + endRow.period + " में " + fmtCurr(endRow.forecast) + " (कुल " + fmtCurr(cumFc) + ", MAE " + fmtCurr(fc.mae) + ") है।"
          : fc.modelLabel + " projects next " + horizon + " months reaching " + fmtCurr(endRow.forecast) + " by " + endRow.period + " (90% band " + fmtCurr(endRow.low) + " to " + fmtCurr(endRow.high) + "). Cumulative total: " + fmtCurr(cumFc) + ".");
      return {
        title: "Future Prediction (" + horizon + "M)",
        meta: fc.modelLabel,
        answer: ans,
        metrics: [
          { label: horizon + "M Cumulative", value: fmtCurr(cumFc) },
          { label: "End (" + endRow.period + ")", value: fmtCurr(endRow.forecast) },
          { label: "Historical MAE", value: fmtCurr(fc.mae) },
          { label: "Fit R² / MAPE", value: fmtNum(fc.r2, 2) + " · " + fmtNum(fc.mape, 1) + "%" },
        ],
        actions: ["Open Forecast tab to switch Ensemble ML vs Linear OLS and adjust horizon"],
      };
    }

    if (/(runway|burn rate|liquidity|buffer|survival|थांग|thaangum)/i.test(low)) {
      return {
        title: "Cash-Flow Runway & Burn Check",
        meta: "On-Device Runway Analyzer",
        answer: "Status is " + rw.status + " across " + rw.months + " months. Recent monthly pace averages " + fmtCurr(rw.recentRev) + " revenue vs " + fmtCurr(rw.recentExp) + " expense (net " + fmtCurr(rw.recentNet) + "/mo).",
        metrics: [
          { label: "Runway", value: rw.runwayMonths === null ? "Self-Sustaining" : fmtNum(rw.runwayMonths, 1) + " mo" },
          { label: "Recent Net/Mo", value: fmtCurr(rw.recentNet) },
          { label: "Savings Rate", value: rw.savingsRate === null ? "N/A" : fmtNum(rw.savingsRate, 1) + "%" },
          { label: "Cumulative Buffer", value: fmtCurr(rw.cashReserve) },
        ],
        actions: ["Keep operating costs capped to sustain surplus generation"],
      };
    }

    if (/(anomal|outlier|iqr|spike|அசாதாரண|असामान्य)/i.test(low)) {
      const flags = detectAnomalies(rows, state.cfg.anomalyIqr);
      if (!flags.length) {
        return { title: "Anomaly Audit Clean", meta: "IQR Detector", answer: "Zero outliers exceeded Q3 + " + state.cfg.anomalyIqr + "× IQR across " + fmtNum(rows.length) + " rows.", metrics: [], actions: [] };
      }
      const top = flags[0];
      return {
        title: "Outlier & Anomaly Audit",
        meta: "Deterministic IQR Audit",
        answer: "Flagged " + fmtNum(flags.length) + " outliers. Top spike occurred on " + top.date + " in '" + top.entity + "' (" + top.metric + " " + fmtCurr(top.value) + " vs cutoff " + fmtCurr(top.threshold) + ").",
        metrics: [
          { label: "Flagged Count", value: fmtNum(flags.length) },
          { label: "Peak Outlier", value: fmtCurr(top.value) },
          { label: "IQR Cutoff", value: fmtCurr(top.threshold) },
          { label: "Entity", value: top.entity },
        ],
        actions: ["Inspect full outlier table in Anomalies tab"],
      };
    }

    if (/(risk|aabathu|जोखिम|exposure)/i.test(low)) {
      return {
        title: "On-Device Risk Assessment",
        meta: "Transaction Risk Scorer",
        answer: "Screened " + fmtNum(rp.total) + " transactions: " + fmtNum(rp.high) + " High Risk (" + fmtNum(rp.highPct, 1) + "%), " + fmtNum(rp.moderate) + " Moderate Risk, and " + fmtNum(rp.low) + " Low Risk. Mean score: " + fmtNum(rp.avgScore, 1) + "/100.",
        metrics: [
          { label: "High Risk", value: fmtNum(rp.high) + " (" + fmtNum(rp.highPct, 1) + "%)" },
          { label: "Exposure", value: fmtCurr(rp.highExposure) },
          { label: "Mod / Low", value: fmtNum(rp.moderate) + " / " + fmtNum(rp.low) },
          { label: "Mean Score", value: fmtNum(rp.avgScore, 1) + " / 100" },
        ],
        actions: ["Audit High Risk disbursements and check IQR outlier table"],
      };
    }

    if (/(what if|what-if|simulate|agar )/i.test(low) && /[+-]?\d+\s*%/.test(low)) {
      const pm = [];
      const re = /([+-]?\d+(?:\.\d+)?)\s*%/g;
      let match;
      while ((match = re.exec(cleanQ)) !== null) {
        let v = Number(match[1]);
        const ctx = low.slice(Math.max(0, match.index - 20), match.index);
        if (v > 0 && !match[1].startsWith("+") && /(drop|cut|reduce|down|lower|trim|less|ghat)/.test(ctx)) v = -v;
        pm.push(v);
      }
      const rc = pm.length >= 1 ? pm[0] : 10;
      const ec = pm.length >= 2 ? pm[1] : -5;
      const pr = m.revenue * (1 + rc / 100);
      const pe = m.expenses * (1 + ec / 100);
      const pp = pr - pe;
      const pmgn = pr > 0 ? round2((pp / pr) * 100) : 0;
      return {
        title: "What-If (" + (rc >= 0 ? "+" : "") + rc + "% Rev, " + (ec >= 0 ? "+" : "") + ec + "% Exp)",
        meta: "Scenario Simulator",
        answer: "Projected profit shifts from " + fmtCurr(m.profit) + " to " + fmtCurr(pp) + " (delta " + fmtCurr(pp - m.profit) + ", margin " + fmtNum(pmgn, 1) + "%).",
        metrics: [
          { label: "Proj. Revenue", value: fmtCurr(pr) },
          { label: "Proj. Expense", value: fmtCurr(pe) },
          { label: "Proj. Profit", value: fmtCurr(pp) },
          { label: "Margin", value: fmtNum(pmgn, 1) + "%" },
        ],
        actions: [],
      };
    }

    if (/(target margin|break.?even|optimiz)/i.test(low)) {
      const tmM = cleanQ.match(/(\d+(?:\.\d+)?)\s*%/);
      const tm = tmM ? Number(tmM[1]) : Math.max(state.cfg.marginThreshold, 25);
      const needRev = tm < 100 ? (m.expenses / (1 - tm / 100)) : m.revenue;
      const revLift = m.revenue > 0 ? round2(((needRev - m.revenue) / m.revenue) * 100) : 0;
      const expCut = m.expenses > 0 ? round2((((m.revenue * (1 - tm / 100)) - m.expenses) / m.expenses) * 100) : 0;
      return {
        title: "Target " + tm + "% Margin Plan",
        meta: "Margin Solver",
        answer: "Current margin is " + (m.margin === null ? "N/A" : fmtNum(m.margin, 1) + "%") + ". Reaching " + tm + "% requires " + (revLift >= 0 ? "+" : "") + fmtNum(revLift, 1) + "% revenue OR " + fmtNum(expCut, 1) + "% expense adjustment.",
        metrics: [
          { label: "Target Margin", value: tm + "%" },
          { label: "Revenue Lift", value: (revLift >= 0 ? "+" : "") + fmtNum(revLift, 1) + "%" },
          { label: "Expense Cut", value: fmtNum(expCut, 1) + "%" },
          { label: "Break-Even", value: fmtCurr(m.expenses) },
        ],
        actions: [],
      };
    }

    if (/(product|department|dept|region|category|segment|branch|course|विभाग)/i.test(low)) {
      const dim = /(dept|department|course|unit|विभाग)/.test(low) ? "department" : (/(region|location|branch)/.test(low) ? "region" : (/categor/.test(low) ? "category" : "product"));
      const segs = byDimension(rows, dim);
      const top = segs[0], lowS = segs[segs.length - 1];
      return {
        title: "Top & Bottom " + dim.charAt(0).toUpperCase() + dim.slice(1) + "s",
        meta: "Segment Aggregator",
        answer: "Across " + segs.length + " segments, '" + top.label + "' led with " + fmtCurr(top.profit) + " profit (" + fmtNum(top.margin, 1) + "% margin). Lowest net: '" + lowS.label + "' (" + fmtCurr(lowS.profit) + ").",
        metrics: [
          { label: "Leader", value: top.label.slice(0, 22) },
          { label: "Leader Profit", value: fmtCurr(top.profit) },
          { label: "Lowest", value: lowS.label.slice(0, 22) },
          { label: "Lowest Profit", value: fmtCurr(lowS.profit) },
        ],
        actions: [],
      };
    }

    if (/\b(20\d{2})\b/.test(low)) {
      const yr = cleanQ.match(/\b(20\d{2})\b/)[1];
      const sub = rows.filter((r) => String(r.fiscal_year || (r.txn_date || "").slice(0, 4)) === yr);
      if (!sub.length) return { title: "Year " + yr, meta: "Year Filter", answer: "No ledger records matched " + yr + ".", metrics: [], actions: [] };
      const sm = computeMetrics(sub);
      return {
        title: "Fiscal Year " + yr,
        meta: "Local Year Filter",
        answer: "In " + yr + " (" + fmtNum(sm.transactions) + " rows), revenue reached " + fmtCurr(sm.revenue) + " vs " + fmtCurr(sm.expenses) + " expense, yielding " + fmtCurr(sm.profit) + " net profit.",
        metrics: [
          { label: yr + " Revenue", value: fmtCurr(sm.revenue) },
          { label: yr + " Expense", value: fmtCurr(sm.expenses) },
          { label: yr + " Profit", value: fmtCurr(sm.profit) },
          { label: "Rows", value: fmtNum(sm.transactions) },
        ],
        actions: [],
      };
    }

    if (/(vendor|supplier|party|payment|upi|cheque|payee)/i.test(low)) {
      const vMap = {};
      rows.forEach((r) => {
        if (r.expense > 0) {
          const k = r.vendor_name || r.category || "Unspecified";
          vMap[k] = (vMap[k] || 0) + r.expense;
        }
      });
      const sortedV = Object.entries(vMap).sort((a, b) => b[1] - a[1]);
      const topV = sortedV[0] || ["N/A", 0];
      return {
        title: "Vendor & Payment Audit",
        meta: "Local Counterparty Ranker",
        answer: "Highest expense payee is '" + topV[0] + "' at " + fmtCurr(topV[1]) + ".",
        metrics: [
          { label: "Top Payee", value: String(topV[0]).slice(0, 24) },
          { label: "Disbursed", value: fmtCurr(topV[1]) },
        ],
        actions: [],
      };
    }

    // Default Overview Summary in EN / TA / HI
    const ovAns = lang === "ta"
      ? fmtNum(m.transactions) + " பதிவுகளில் வருவாய் " + fmtCurr(m.revenue) + ", செலவு " + fmtCurr(m.expenses) + ", நிகர லாபம் " + fmtCurr(m.profit) + " (" + (m.margin === null ? "N/A" : fmtNum(m.margin, 1) + "%") + " விகிதம்)."
      : (lang === "hi"
        ? fmtNum(m.transactions) + " लेनदेन में कुल राजस्व " + fmtCurr(m.revenue) + ", खर्च " + fmtCurr(m.expenses) + " और शुद्ध लाभ " + fmtCurr(m.profit) + " (" + (m.margin === null ? "N/A" : fmtNum(m.margin, 1) + "%") + " मार्जिन) है।"
        : "Across " + fmtNum(m.transactions) + " records (" + (state.meta.source || "Ledger") + "), revenue totaled " + fmtCurr(m.revenue) + " vs " + fmtCurr(m.expenses) + " expenses, delivering " + fmtCurr(m.profit) + " net profit (" + (m.margin === null ? "N/A" : fmtNum(m.margin, 1) + "%") + " margin).");
    return {
      title: "Executive Ledger Summary",
      meta: "On-Device SQLite Engine",
      answer: ovAns,
      metrics: [
        { label: "Revenue", value: fmtCurr(m.revenue) },
        { label: "Expenses", value: fmtCurr(m.expenses) },
        { label: "Net Profit", value: fmtCurr(m.profit) },
        { label: "Runway", value: rw.runwayMonths === null ? "Self-Sustaining" : fmtNum(rw.runwayMonths, 1) + " mo" },
      ],
      actions: ["Ask 'Predict next 6 months profit' or '30k salary / 22k spend risk'"],
    };
  }

  function appendMobileCopilotMessage(role, payload) {
    const stream = document.getElementById("mobCopilotMessages");
    if (!stream) return;
    const card = document.createElement("div");
    card.className = "mob-msg " + (role === "user" ? "mob-msg-user" : "mob-msg-bot");
    if (role === "user") {
      const meta = document.createElement("div");
      meta.className = "mob-msg-meta";
      meta.textContent = "You";
      const p = document.createElement("p");
      p.textContent = String(payload || "");
      card.appendChild(meta);
      card.appendChild(p);
    } else {
      const meta = document.createElement("div");
      meta.className = "mob-msg-meta";
      meta.textContent = (payload.title || "Copilot") + (payload.meta ? " · " + payload.meta : "");
      card.appendChild(meta);
      const p = document.createElement("p");
      p.textContent = payload.answer || "";
      card.appendChild(p);
      if (Array.isArray(payload.metrics) && payload.metrics.length) {
        const grid = document.createElement("div");
        grid.className = "mob-msg-kpis";
        payload.metrics.forEach((item) => {
          const cell = document.createElement("div");
          cell.className = "mob-msg-kpi";
          const lbl = document.createElement("span");
          lbl.textContent = item.label || "";
          const val = document.createElement("strong");
          val.textContent = item.value || "";
          cell.appendChild(lbl);
          cell.appendChild(val);
          grid.appendChild(cell);
        });
        card.appendChild(grid);
      }
      if (Array.isArray(payload.actions) && payload.actions.length) {
        const ul = document.createElement("ul");
        ul.className = "mob-msg-actions";
        payload.actions.forEach((act) => {
          const li = document.createElement("li");
          li.textContent = act;
          ul.appendChild(li);
        });
        card.appendChild(ul);
      }
    }
    stream.appendChild(card);
    stream.scrollTop = stream.scrollHeight;
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
    const fcEngineEl = document.getElementById("forecastModelMode");
    if (fcEngineEl) fcEngineEl.addEventListener("change", renderForecastAndOptimizer);
    document.getElementById("targetMarginRange").addEventListener("input", renderForecastAndOptimizer);
    document.getElementById("simRevRange").addEventListener("input", renderForecastAndOptimizer);
    document.getElementById("simExpRange").addEventListener("input", renderForecastAndOptimizer);

    const yrFilterEl = document.getElementById("filterYear");
    const depFilterEl = document.getElementById("filterDepartment");
    const resetFilterEl = document.getElementById("btnFilterReset");
    if (yrFilterEl) yrFilterEl.addEventListener("change", () => { state.filterYear = yrFilterEl.value; renderAll(); });
    if (depFilterEl) depFilterEl.addEventListener("change", () => { state.filterDepartment = depFilterEl.value; renderAll(); });
    if (resetFilterEl) resetFilterEl.addEventListener("click", () => { state.filterYear = ""; state.filterDepartment = ""; renderAll(); });

    document.getElementById("btnEmptyImport").addEventListener("click", triggerFileImport);
    document.getElementById("btnSegGoImport").addEventListener("click", () => { switchTab("overview"); triggerFileImport(); });
    document.getElementById("btnAnomGoImport").addEventListener("click", () => { switchTab("overview"); triggerFileImport(); });
    document.getElementById("btnFcGoImport").addEventListener("click", () => { switchTab("overview"); triggerFileImport(); });
    document.getElementById("btnSettingsUpload").addEventListener("click", triggerFileImport);

    document.getElementById("btnEmptyLoadSample").addEventListener("click", loadSampleIntoWorkspace);
    document.getElementById("btnLoadSample").addEventListener("click", loadSampleIntoWorkspace);
    const btnEmptyEnt = document.getElementById("btnEmptyLoadEnterprise");
    const btnSetEnt = document.getElementById("btnLoadEnterprise");
    if (btnEmptyEnt) btnEmptyEnt.addEventListener("click", loadEnterprise10kIntoWorkspace);
    if (btnSetEnt) btnSetEnt.addEventListener("click", loadEnterprise10kIntoWorkspace);

    // Quick Entry & Receipt Parser modal
    const qeModal = document.getElementById("quickEntryModal");
    function openQuickEntryModal() {
      if (!qeModal) return;
      const dEl = document.getElementById("qeDate");
      if (dEl && !dEl.value) dEl.value = new Date().toISOString().slice(0, 10);
      qeModal.classList.remove("hidden");
    }
    ["btnQuickEntryOpen", "btnEmptyQuickEntry", "btnSettingsQuickEntry"].forEach((id) => {
      const btn = document.getElementById(id);
      if (btn) btn.addEventListener("click", openQuickEntryModal);
    });
    const btnQeClose = document.getElementById("btnQeClose");
    if (btnQeClose && qeModal) btnQeClose.addEventListener("click", () => qeModal.classList.add("hidden"));
    if (qeModal) qeModal.addEventListener("click", (ev) => { if (ev.target === qeModal) qeModal.classList.add("hidden"); });

    const btnQeParse = document.getElementById("btnQeParse");
    if (btnQeParse) {
      btnQeParse.addEventListener("click", () => {
        const raw = document.getElementById("qeReceiptText").value;
        if (!raw.trim()) {
          document.getElementById("qeParseNote").textContent = "Paste bill or SMS text first.";
          return;
        }
        const ext = parseReceiptText(raw);
        document.getElementById("qeDate").value = ext.txn_date;
        document.getElementById("qeType").value = ext.flow;
        if (ext.amount) document.getElementById("qeAmount").value = ext.amount;
        document.getElementById("qeCategory").value = ext.category;
        if (ext.vendor) document.getElementById("qeVendor").value = ext.vendor;
        document.getElementById("qeParseNote").textContent = ext.amount
          ? "Extracted " + ext.flow + " (" + state.cfg.currency + " " + ext.amount + ") — review & save."
          : "Date & category filled — verify amount before saving.";
      });
    }

    const qeForm = document.getElementById("quickEntryForm");
    if (qeForm) {
      qeForm.addEventListener("submit", (ev) => {
        ev.preventDefault();
        const dt = document.getElementById("qeDate").value || new Date().toISOString().slice(0, 10);
        const flow = document.getElementById("qeType").value;
        const amt = Math.max(0, Number(document.getElementById("qeAmount").value) || 0);
        if (amt <= 0) return;
        const cat = document.getElementById("qeCategory").value.trim() || "Operations";
        const dept = document.getElementById("qeDepartment").value.trim() || "General";
        const prod = document.getElementById("qeProduct").value.trim() || "Ledger Entry";
        const vend = document.getElementById("qeVendor").value.trim();
        const row = {
          txn_date: dt,
          period: dt.slice(0, 7),
          fiscal_year: Number(dt.slice(0, 4)) || 2026,
          transaction_id: "MOB-" + Date.now().toString().slice(-6),
          transaction_type: flow === "income" ? "Income" : "Expense",
          subcategory: "Manual Entry",
          category: cat,
          product: prod,
          department: dept,
          region: "Global",
          vendor_name: vend,
          payment_method: "Direct Entry",
          notes: "Added via Mobile Quick Entry",
          revenue: flow === "income" ? amt : 0,
          expense: flow === "expense" ? amt : 0,
          cost: 0,
          quantity: 1,
          unit_price: amt,
          investment: 0,
        };
        const updated = state.rows.concat([row]);
        saveWorkspace(updated, state.rows.length ? state.meta.source : "manual_ledger.csv");
        if (state.user) queueDatasetSync(state.user.email, "manual_entry.csv", [row]);
        if (qeModal) qeModal.classList.add("hidden");
        qeForm.reset();
        switchTab("overview");
        showNotice("Saved " + flow + " transaction (" + fmtCurr(amt) + ") locally.");
      });
    }

    // Mobile Offline AI Copilot Modal
    const mobCopilotModal = document.getElementById("mobileCopilotModal");
    function openMobileCopilot() {
      if (!mobCopilotModal) return;
      mobCopilotModal.classList.remove("hidden");
      const inp = document.getElementById("mobCopilotInput");
      if (inp) inp.focus();
    }
    ["btnMobileCopilot", "btnPanelCopilot"].forEach((id) => {
      const b = document.getElementById(id);
      if (b) b.addEventListener("click", openMobileCopilot);
    });
    const btnCloseCop = document.getElementById("btnMobCopilotClose");
    if (btnCloseCop && mobCopilotModal) btnCloseCop.addEventListener("click", () => mobCopilotModal.classList.add("hidden"));
    if (mobCopilotModal) mobCopilotModal.addEventListener("click", (ev) => { if (ev.target === mobCopilotModal) mobCopilotModal.classList.add("hidden"); });

    document.querySelectorAll("#mobCopilotLangBar .mode-btn").forEach((b) => b.addEventListener("click", () => {
      state.copilotLang = b.dataset.lang || "auto";
      b.parentNode.querySelectorAll(".mode-btn").forEach((x) => x.classList.toggle("is-active", x === b));
    }));

    function sendMobileCopilotPrompt(text) {
      const q = String(text || "").trim();
      if (!q) return;
      appendMobileCopilotMessage("user", q);
      const reply = askMobileCopilot(q, state.copilotLang);
      appendMobileCopilotMessage("bot", reply);
    }

    document.querySelectorAll("#mobCopilotPrompts .copilot-chip-mob").forEach((c) => {
      c.addEventListener("click", () => sendMobileCopilotPrompt(c.dataset.prompt || c.textContent));
    });
    const mobCopForm = document.getElementById("mobCopilotForm");
    if (mobCopForm) {
      mobCopForm.addEventListener("submit", (ev) => {
        ev.preventDefault();
        const inp = document.getElementById("mobCopilotInput");
        const q = inp ? inp.value : "";
        if (inp) inp.value = "";
        sendMobileCopilotPrompt(q);
      });
    }

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
          showNotice("Could not detect valid Date and Amount / Revenue / Expense columns in " + file.name + ".", true);
        }
      };
      reader.readAsText(file);
    });

    function csvCell(val) {
      const s = String(val === null || val === undefined ? "" : val);
      return /[",\r\n]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s;
    }

    document.getElementById("btnExportCsv").addEventListener("click", () => {
      if (!state.rows.length) {
        showNotice("Import financial data before exporting CSV.", true);
        return;
      }
      const header = "txn_date,transaction_id,transaction_type,category,subcategory,product,department,region,vendor_name,payment_method,revenue,expense,cost,investment,notes\n";
      const body = state.rows.map((r) => [
        r.txn_date, r.transaction_id || "", r.transaction_type || "", r.category, r.subcategory || "",
        r.product, r.department, r.region, r.vendor_name || "", r.payment_method || "",
        r.revenue, r.expense, r.cost, r.investment, r.notes || ""
      ].map(csvCell).join(",")).join("\n");
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
          if (box) box.textContent = "Version 1.2.0 · Direct update check runs inside the installed Android APK.";
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
