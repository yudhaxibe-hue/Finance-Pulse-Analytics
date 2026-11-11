(function () {
  "use strict";

  const FONT_FAMILY =
    '-apple-system, BlinkMacSystemFont, "SF Pro Text", "Helvetica Neue", ui-sans-serif, system-ui, sans-serif';

  // Mobile sidebar drawer
  const sidebar = document.querySelector(".app-sidebar");
  const backdrop = document.querySelector(".drawer-backdrop");
  const openBtn = document.querySelector("[data-drawer-open]");
  const closeBtn = document.querySelector("[data-drawer-close]");

  function setDrawer(open) {
    if (!sidebar || !backdrop) return;
    sidebar.classList.toggle("open", open);
    backdrop.classList.toggle("open", open);
    if (openBtn) openBtn.setAttribute("aria-expanded", open ? "true" : "false");
    document.body.style.overflow = open ? "hidden" : "";
  }

  if (openBtn) openBtn.addEventListener("click", () => setDrawer(true));
  if (closeBtn) closeBtn.addEventListener("click", () => setDrawer(false));
  if (backdrop) backdrop.addEventListener("click", () => setDrawer(false));
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && sidebar && sidebar.classList.contains("open")) {
      setDrawer(false);
    }
  });

  // Password visibility toggle
  document.querySelectorAll("[data-toggle-password]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const targetId = btn.getAttribute("data-toggle-password");
      const input = document.getElementById(targetId);
      if (!input) return;
      const show = input.type === "password";
      input.type = show ? "text" : "password";
      btn.setAttribute("aria-pressed", show ? "true" : "false");
      btn.setAttribute("aria-label", show ? "Hide password" : "Show password");
      const eyeOpen = btn.querySelector("[data-eye='open']");
      const eyeOff = btn.querySelector("[data-eye='off']");
      if (eyeOpen && eyeOff) {
        eyeOpen.style.display = show ? "none" : "block";
        eyeOff.style.display = show ? "block" : "none";
      }
    });
  });

  // Upload dropzone feedback
  document.querySelectorAll("[data-dropzone]").forEach((zone) => {
    const input = zone.querySelector('input[type="file"]');
    const badge = zone.querySelector("[data-file-badge]");
    const nameOut = zone.querySelector("[data-file-name]");
    if (!input) return;

    const showFile = () => {
      const file = input.files && input.files[0];
      if (file && badge && nameOut) {
        const kb = file.size >= 1024 * 1024
          ? `${(file.size / (1024 * 1024)).toFixed(1)} MB`
          : `${Math.max(1, Math.round(file.size / 1024))} KB`;
        nameOut.textContent = `${file.name} (${kb})`;
        badge.hidden = false;
      }
    };

    input.addEventListener("change", showFile);
    zone.addEventListener("dragover", (e) => {
      e.preventDefault();
      zone.classList.add("dragover");
    });
    zone.addEventListener("dragleave", () => zone.classList.remove("dragover"));
    zone.addEventListener("drop", () => {
      zone.classList.remove("dragover");
      setTimeout(showFile, 0);
    });
  });

  // Optimization live slider preview
  const optForm = document.querySelector("[data-optimization-form]");
  if (optForm) {
    const baseRev = Number(optForm.getAttribute("data-base-revenue") || 0);
    const baseExp = Number(optForm.getAttribute("data-base-expense") || 0);
    const baseProfit = Number(optForm.getAttribute("data-base-profit") || 0);
    const currency = optForm.getAttribute("data-currency") || "";

    const revInput = optForm.querySelector('input[name="revenue_change"]');
    const expInput = optForm.querySelector('input[name="expense_change"]');
    const revRange = optForm.querySelector('[data-range-for="revenue_change"]');
    const expRange = optForm.querySelector('[data-range-for="expense_change"]');

    const outRev = document.querySelector("[data-live-rev]");
    const outExp = document.querySelector("[data-live-exp]");
    const outProfit = document.querySelector("[data-live-profit]");
    const outMargin = document.querySelector("[data-live-margin]");
    const outDelta = document.querySelector("[data-live-delta]");

    const fmtMoney = (n) =>
      `${currency} ${n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`.trim();

    const recalc = () => {
      const rg = parseFloat(revInput && revInput.value ? revInput.value : "0") || 0;
      const eg = parseFloat(expInput && expInput.value ? expInput.value : "0") || 0;
      const projRev = baseRev * (1 + rg / 100);
      const projExp = baseExp * (1 + eg / 100);
      const projProfit = projRev - projExp;
      const projMargin = projRev !== 0 ? (projProfit / projRev) * 100 : null;
      const delta = projProfit - baseProfit;

      if (outRev) outRev.textContent = fmtMoney(projRev);
      if (outExp) outExp.textContent = fmtMoney(projExp);
      if (outProfit) outProfit.textContent = fmtMoney(projProfit);
      if (outMargin) outMargin.textContent = projMargin === null ? "N/A" : `${projMargin.toFixed(2)}%`;
      if (outDelta) {
        const sign = delta >= 0 ? "+" : "-";
        outDelta.textContent = `${sign}${fmtMoney(Math.abs(delta))} vs baseline`;
        outDelta.className = delta >= 0 ? "badge positive num" : "badge negative num";
      }
    };

    const bindPair = (numEl, rangeEl) => {
      if (!numEl || !rangeEl) return;
      numEl.addEventListener("input", () => {
        const v = parseFloat(numEl.value);
        if (!Number.isNaN(v)) rangeEl.value = Math.min(100, Math.max(-50, v));
        recalc();
      });
      rangeEl.addEventListener("input", () => {
        numEl.value = rangeEl.value;
        recalc();
      });
    };

    bindPair(revInput, revRange);
    bindPair(expInput, expRange);

    const nameInput = optForm.querySelector('input[name="name"]');
    document.querySelectorAll("[data-preset-rev]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const revVal = parseFloat(btn.getAttribute("data-preset-rev") || "0") || 0;
        const expVal = parseFloat(btn.getAttribute("data-preset-exp") || "0") || 0;
        const presetName = btn.getAttribute("data-preset-name") || "";
        if (revInput) revInput.value = revVal;
        if (revRange) revRange.value = Math.min(100, Math.max(-50, revVal));
        if (expInput) expInput.value = expVal;
        if (expRange) expRange.value = Math.min(100, Math.max(-50, expVal));
        if (nameInput && presetName) nameInput.value = presetName;
        recalc();
        optForm.scrollIntoView({ behavior: "smooth", block: "nearest" });
      });
    });

    recalc();
  }

  // Landing showcase segmented control & high-DPI sample canvas
  const segmented = document.querySelector("[data-segmented]");
  if (segmented) {
    const buttons = Array.from(segmented.querySelectorAll("[role='tab']"));
    const thumb = segmented.querySelector(".segmented-thumb");
    const panels = Array.from(document.querySelectorAll("[data-showcase-panel]"));

    const moveThumb = (btn) => {
      if (!thumb || !btn) return;
      thumb.style.width = `${btn.offsetWidth}px`;
      thumb.style.transform = `translateX(${btn.offsetLeft - 3}px)`;
    };

    const activate = (btn) => {
      const target = btn.getAttribute("data-tab");
      buttons.forEach((b) => b.setAttribute("aria-selected", b === btn ? "true" : "false"));
      panels.forEach((p) => {
        p.hidden = p.getAttribute("data-showcase-panel") !== target;
      });
      moveThumb(btn);
      if (target === "pulse") drawSampleCanvas();
    };

    const active = buttons.find((b) => b.getAttribute("aria-selected") === "true") || buttons[0];
    if (active) requestAnimationFrame(() => moveThumb(active));
    window.addEventListener("resize", () => {
      const current = buttons.find((b) => b.getAttribute("aria-selected") === "true");
      if (current) moveThumb(current);
      drawSampleCanvas();
    });

    buttons.forEach((btn) => {
      btn.addEventListener("click", () => activate(btn));
    });
  }

  // Interactive Canvas chart inside landing showcase (computed from sample CSV)
  function drawSampleCanvas(hoverIdx) {
    const canvas = document.getElementById("sampleCanvas");
    if (!canvas) return;
    const parent = canvas.parentElement;
    if (!parent || parent.offsetParent === null) return;

    canvas.style.width = "";
    canvas.style.height = "";
    const styles = window.getComputedStyle(parent);
    const padX = (parseFloat(styles.paddingLeft) || 0) + (parseFloat(styles.paddingRight) || 0);
    const padY = (parseFloat(styles.paddingTop) || 0) + (parseFloat(styles.paddingBottom) || 0);
    const cssBox = parent.getBoundingClientRect();
    const w = Math.max(240, Math.floor(cssBox.width - padX));
    const h = Math.max(150, Math.floor((canvas.clientHeight || (cssBox.height - padY))));
    const dpr = Math.min(Math.max(window.devicePixelRatio || 1, 1), 3);

    canvas.style.width = `${w}px`;
    canvas.style.height = `${h}px`;
    canvas.width = Math.round(w * dpr);
    canvas.height = Math.round(h * dpr);

    const ctx = canvas.getContext("2d");
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, w, h);

    const data = [
      { period: "2025-11", rev: 525458, exp: 303376, prof: 222082 },
      { period: "2025-12", rev: 548112, exp: 323208, prof: 224904 },
      { period: "2026-01", rev: 553247, exp: 338404, prof: 214842 },
      { period: "2026-02", rev: 567111, exp: 301161, prof: 265949 },
      { period: "2026-03", rev: 595207, exp: 371976, prof: 223231 },
      { period: "2026-04", rev: 602174, exp: 345377, prof: 256797 },
      { period: "2026-05", rev: 592716, exp: 331851, prof: 260866 },
      { period: "2026-06", rev: 573864, exp: 338527, prof: 235337 },
    ];

    const pad = { top: 28, right: 34, bottom: 26, left: 52 };
    const cw = w - pad.left - pad.right;
    const ch = h - pad.top - pad.bottom;
    const maxY = 660000;
    const minY = 160000;

    const xOf = (i) => pad.left + (i / (data.length - 1)) * cw;
    const yOf = (val) => pad.top + ch - ((val - minY) / (maxY - minY)) * ch;

    // Inline top-left series key
    const legendItems = [
      { label: "Revenue", color: "#0066CC" },
      { label: "Expenses", color: "#C2590A" },
      { label: "Profit", color: "#0E6027" },
    ];
    let lx = pad.left;
    ctx.font = `500 11px ${FONT_FAMILY}`;
    ctx.textBaseline = "middle";
    ctx.textAlign = "left";
    legendItems.forEach((item) => {
      ctx.beginPath();
      ctx.arc(lx + 4, 11, 3.5, 0, Math.PI * 2);
      ctx.fillStyle = item.color;
      ctx.fill();
      ctx.fillStyle = "#515154";
      ctx.fillText(item.label, lx + 12, 11);
      lx += ctx.measureText(item.label).width + 26;
    });

    ctx.font = `500 11px ${FONT_FAMILY}`;
    ctx.fillStyle = "#636368";

    // Horizontal rules
    [200000, 350000, 500000, 650000].forEach((tick) => {
      const y = yOf(tick);
      ctx.beginPath();
      ctx.strokeStyle = "rgba(29, 29, 31, 0.07)";
      ctx.lineWidth = 1;
      ctx.moveTo(pad.left, y);
      ctx.lineTo(w - pad.right, y);
      ctx.stroke();
      ctx.textAlign = "right";
      ctx.textBaseline = "middle";
      ctx.fillText(`${Math.round(tick / 1000)}k`, pad.left - 8, y);
    });

    // X labels
    ctx.textAlign = "center";
    ctx.textBaseline = "top";
    data.forEach((d, i) => {
      if (w < 460 && i % 2 === 1) return;
      ctx.fillText(d.period, xOf(i), h - pad.bottom + 8);
    });

    // Revenue area fill
    const grad = ctx.createLinearGradient(0, pad.top, 0, pad.top + ch);
    grad.addColorStop(0, "rgba(0, 102, 204, 0.14)");
    grad.addColorStop(1, "rgba(0, 102, 204, 0.0)");
    ctx.beginPath();
    ctx.moveTo(xOf(0), yOf(data[0].rev));
    for (let i = 1; i < data.length; i++) ctx.lineTo(xOf(i), yOf(data[i].rev));
    ctx.lineTo(xOf(data.length - 1), pad.top + ch);
    ctx.lineTo(xOf(0), pad.top + ch);
    ctx.closePath();
    ctx.fillStyle = grad;
    ctx.fill();

    const drawSeries = (key, color) => {
      ctx.beginPath();
      data.forEach((d, i) => {
        const x = xOf(i);
        const y = yOf(d[key]);
        if (i === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      });
      ctx.strokeStyle = color;
      ctx.lineWidth = 2.25;
      ctx.lineJoin = "round";
      ctx.lineCap = "round";
      ctx.stroke();
    };

    drawSeries("rev", "#0066CC");
    drawSeries("exp", "#C2590A");
    drawSeries("prof", "#0E6027");

    // Hover crosshair & dots
    const activeIdx = typeof hoverIdx === "number" ? hoverIdx : data.length - 1;
    const xSel = xOf(activeIdx);
    ctx.beginPath();
    ctx.strokeStyle = "rgba(29, 29, 31, 0.18)";
    ctx.lineWidth = 1;
    ctx.setLineDash([3, 3]);
    ctx.moveTo(xSel, pad.top);
    ctx.lineTo(xSel, pad.top + ch);
    ctx.stroke();
    ctx.setLineDash([]);

    [
      { key: "rev", color: "#0066CC" },
      { key: "exp", color: "#C2590A" },
      { key: "prof", color: "#0E6027" },
    ].forEach((s) => {
      ctx.beginPath();
      ctx.arc(xSel, yOf(data[activeIdx][s.key]), 4, 0, Math.PI * 2);
      ctx.fillStyle = "#FFFFFF";
      ctx.fill();
      ctx.lineWidth = 2;
      ctx.strokeStyle = s.color;
      ctx.stroke();
    });

    const scrubber = document.querySelector("[data-sample-scrubber]");
    if (scrubber) {
      const pt = data[activeIdx];
      scrubber.textContent =
        `${pt.period} · Rev ${pt.rev.toLocaleString()} · Profit ${pt.prof.toLocaleString()}`;
    }

    if (!canvas.dataset.bound) {
      canvas.dataset.bound = "1";
      canvas.addEventListener("mousemove", (e) => {
        const box = canvas.getBoundingClientRect();
        const relX = e.clientX - box.left - pad.left;
        const idx = Math.min(data.length - 1, Math.max(0, Math.round((relX / cw) * (data.length - 1))));
        drawSampleCanvas(idx);
      });
      canvas.addEventListener("mouseleave", () => drawSampleCanvas(data.length - 1));
      if (window.ResizeObserver) {
        let rafId = 0;
        const ro = new window.ResizeObserver(() => {
          if (rafId) cancelAnimationFrame(rafId);
          rafId = requestAnimationFrame(() => drawSampleCanvas());
        });
        ro.observe(parent);
      }
    }

    parent.classList.add("is-ready");
  }

  drawSampleCanvas();

  // Shared Chart.js Apple Theme Helper
  window.FinancePulseCharts = {
    palette: {
      cobalt: "#0066CC",
      cobaltSoft: "rgba(0, 102, 204, 0.12)",
      emerald: "#0E6027",
      emeraldSoft: "rgba(14, 96, 39, 0.10)",
      amber: "#C2590A",
      graphite: "#1D1D1F",
      grid: "rgba(29, 29, 31, 0.06)",
      tick: "#636368",
    },
    defaults() {
      return {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: "index", intersect: false },
        plugins: {
          legend: {
            position: "top",
            align: "end",
            labels: {
              boxWidth: 10,
              boxHeight: 10,
              usePointStyle: true,
              pointStyle: "circle",
              color: "#515154",
              font: { family: FONT_FAMILY, size: 12, weight: "500" },
              padding: 16,
            },
          },
          tooltip: {
            backgroundColor: "#1D1D1F",
            titleColor: "#FFFFFF",
            bodyColor: "#F5F5F7",
            padding: 11,
            cornerRadius: 10,
            titleFont: { family: FONT_FAMILY, size: 12, weight: "600" },
            bodyFont: { family: FONT_FAMILY, size: 12, weight: "400" },
            displayColors: true,
            boxPadding: 4,
          },
        },
        scales: {
          x: {
            grid: { display: false },
            border: { color: "rgba(29, 29, 31, 0.12)" },
            ticks: {
              color: "#636368",
              font: { family: FONT_FAMILY, size: 12, weight: "500" },
              maxRotation: 0,
            },
          },
          y: {
            grid: { color: "rgba(29, 29, 31, 0.06)" },
            border: { display: false },
            ticks: {
              color: "#636368",
              font: { family: FONT_FAMILY, size: 12, weight: "500" },
              callback: (v) =>
                typeof v === "number"
                  ? v.toLocaleString(undefined, { maximumFractionDigits: 0 })
                  : v,
            },
          },
        },
      };
    },
  };

  // In-app Desktop Updater & 5-tap Secret Operator Sync Console
  const banner = document.getElementById("desktopUpdateBanner");
  const updateTitle = document.getElementById("desktopUpdateTitle");
  const updateDetail = document.getElementById("desktopUpdateDetail");
  const btnBannerDownload = document.getElementById("btnDesktopDownloadUpdate");
  const btnBannerOpen = document.getElementById("btnDesktopOpenUpdate");
  const btnBannerDismiss = document.getElementById("btnDesktopDismissUpdate");
  const settingsUpdateStatus = document.getElementById("settingsUpdateStatus");
  const btnSettingsCheck = document.getElementById("btnSettingsCheckUpdate");
  const btnSettingsDownload = document.getElementById("btnSettingsDownloadUpdate");

  function renderUpdateState(info) {
    if (!info || typeof info !== "object") return;
    if (settingsUpdateStatus) {
      if (info.checking) {
        settingsUpdateStatus.textContent = "Checking for updates…";
      } else if (info.download_status === "downloading") {
        settingsUpdateStatus.textContent = "Downloading and verifying update package…";
      } else if (info.download_status === "ready") {
        settingsUpdateStatus.textContent = `Downloaded verified package to ${info.download_path}.`;
      } else if (info.update_available) {
        settingsUpdateStatus.textContent = `Update ready: v${info.latest_version} (Build ${info.latest_build}) vs installed v${info.local_version} (Build ${info.local_build}).`;
      } else if (info.error) {
        settingsUpdateStatus.textContent = `Installed: v${info.local_version} (Build ${info.local_build}) · Offline (${info.error})`;
      } else if (info.checked) {
        settingsUpdateStatus.textContent = `Up to date on v${info.local_version} (Build ${info.local_build}).`;
      }
      if (btnSettingsDownload) {
        btnSettingsDownload.hidden = !info.update_available || !info.download_url;
      }
    }
    if (banner && info.update_available && !sessionStorage.getItem("fp_dismiss_update_" + info.latest_build)) {
      banner.hidden = false;
      if (updateTitle) updateTitle.textContent = `Update available: v${info.latest_version}`;
      if (updateDetail) {
        if (info.download_status === "ready") {
          updateDetail.textContent = `Verified package saved at ${info.download_path}`;
        } else if (info.download_status === "error" && info.download_error) {
          updateDetail.textContent = info.download_error;
        } else {
          updateDetail.textContent = `Build ${info.latest_build} ready for direct download`;
        }
      }
      if (btnBannerDownload) btnBannerDownload.hidden = !info.download_url || info.download_status === "ready";
      if (btnBannerOpen) btnBannerOpen.hidden = info.download_status !== "ready";
    } else if (banner && !info.update_available) {
      banner.hidden = true;
    }
  }

  async function triggerUpdateDownload(btn) {
    if (btn) btn.disabled = true;
    if (updateDetail) updateDetail.textContent = "Downloading and checking SHA-256 checksum…";
    if (settingsUpdateStatus) settingsUpdateStatus.textContent = "Downloading and checking SHA-256 checksum…";
    try {
      const res = await fetch("/api/system/download-update", { method: "POST" });
      if (res.ok) renderUpdateState(await res.json());
    } catch (_e) {
      if (updateDetail) updateDetail.textContent = "Download unavailable right now.";
    } finally {
      if (btn) btn.disabled = false;
    }
  }

  if (banner || settingsUpdateStatus) {
    fetch("/api/system/update-status")
      .then((r) => (r.ok ? r.json() : null))
      .then((data) => {
        if (data) renderUpdateState(data);
      })
      .catch(() => {});
  }

  if (btnSettingsCheck) {
    btnSettingsCheck.addEventListener("click", async () => {
      btnSettingsCheck.disabled = true;
      if (settingsUpdateStatus) settingsUpdateStatus.textContent = "Checking for updates…";
      try {
        const res = await fetch("/api/system/check-updates", { method: "POST" });
        if (res.ok) renderUpdateState(await res.json());
      } catch (_e) {
        if (settingsUpdateStatus) settingsUpdateStatus.textContent = "Unable to check updates while offline.";
      } finally {
        btnSettingsCheck.disabled = false;
      }
    });
  }

  if (btnSettingsDownload) btnSettingsDownload.addEventListener("click", () => triggerUpdateDownload(btnSettingsDownload));
  if (btnBannerDownload) btnBannerDownload.addEventListener("click", () => triggerUpdateDownload(btnBannerDownload));
  if (btnBannerOpen) {
    btnBannerOpen.addEventListener("click", async () => {
      try { await fetch("/api/system/open-download", { method: "POST" }); } catch (_e) {}
    });
  }
  if (btnBannerDismiss && banner) {
    btnBannerDismiss.addEventListener("click", () => {
      banner.hidden = true;
      fetch("/api/system/update-status")
        .then((r) => (r.ok ? r.json() : null))
        .then((d) => {
          if (d && d.latest_build) sessionStorage.setItem("fp_dismiss_update_" + d.latest_build, "1");
        })
        .catch(() => {});
    });
  }

  // Hidden 5-tap Operator Sync Console trigger
  const opDialog = document.getElementById("operatorSyncDialog");
  const opStatusBox = document.getElementById("operatorSyncStatusBox");
  const opUrlInput = document.getElementById("operatorSyncUrlInput");
  const btnCloseOp = document.getElementById("btnCloseOperatorSync");
  const btnSaveOp = document.getElementById("btnSaveOperatorSync");
  const btnFlushOp = document.getElementById("btnFlushOperatorSync");
  const btnClearOp = document.getElementById("btnClearOperatorSync");

  async function refreshOperatorSync() {
    if (!opStatusBox) return;
    try {
      const res = await fetch("/api/system/operator-sync");
      if (!res.ok) {
        opStatusBox.textContent = "Operator sync console restricted to local/admin session.";
        return;
      }
      const cfg = await res.json();
      if (opUrlInput) opUrlInput.value = cfg.override_url || "";
      const targetLabel = cfg.effective_url || "None (offline local storage only)";
      const queueLabel = cfg.queue_count ? ` · Queued items: ${cfg.queue_count}` : "";
      const errLabel = cfg.last_sync_error ? ` · Last error: ${cfg.last_sync_error}` : "";
      opStatusBox.textContent = `Mode: ${cfg.mode} · Active endpoint: ${targetLabel}${queueLabel}${errLabel}`;
    } catch (_e) {
      opStatusBox.textContent = "Unable to read local sync service.";
    }
  }

  let secretTaps = 0;
  let secretTimer = null;
  document.querySelectorAll("[data-secret-sync-trigger]").forEach((el) => {
    el.addEventListener("click", () => {
      secretTaps += 1;
      if (secretTimer) clearTimeout(secretTimer);
      secretTimer = setTimeout(() => { secretTaps = 0; }, 2500);
      if (secretTaps >= 5) {
        secretTaps = 0;
        clearTimeout(secretTimer);
        if (opDialog && typeof opDialog.showModal === "function") {
          opDialog.showModal();
          refreshOperatorSync();
        }
      }
    });
  });

  async function postOperatorAction(action, url) {
    try {
      const res = await fetch("/api/system/operator-sync", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action, url: url || "" }),
      });
      const data = await res.json();
      if (!res.ok && opStatusBox) {
        opStatusBox.textContent = data.error || "Action rejected.";
        return;
      }
      refreshOperatorSync();
    } catch (_e) {
      if (opStatusBox) opStatusBox.textContent = "Operator sync request failed.";
    }
  }

  if (btnCloseOp && opDialog) btnCloseOp.addEventListener("click", () => opDialog.close());
  if (btnSaveOp) btnSaveOp.addEventListener("click", () => postOperatorAction("save_override", opUrlInput ? opUrlInput.value : ""));
  if (btnFlushOp) btnFlushOp.addEventListener("click", () => postOperatorAction("flush_now", ""));
  if (btnClearOp) btnClearOp.addEventListener("click", () => postOperatorAction("clear_override", ""));
})();
