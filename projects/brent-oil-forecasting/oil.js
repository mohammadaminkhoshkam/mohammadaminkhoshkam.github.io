// Brent oil forecasting page: candlestick terminal (EIA Brent spot) + forecast result charts.
// Data: data/brent_eia.json (daily closes) and data/results.json (native-test predictions, leaderboards).
(function () {
  "use strict";
  const $ = (s, r) => (r || document).querySelector(s);
  const $$ = (s, r) => Array.from((r || document).querySelectorAll(s));
  const C = { up: "#2bc48a", down: "#ef5a48", gold: "#f2a93b", teal: "#36c9bb", ink: "#efe7d8", dim: "#a39985", grid: "rgba(255,255,255,.06)", axis: "rgba(255,255,255,.18)" };
  const MONO = '11px "JetBrains Mono", ui-monospace, Consolas, monospace';

  // ---------- tooltip ----------
  const tip = document.createElement("div");
  tip.className = "chart-tip";
  document.body.appendChild(tip);
  function showTip(html, x, y) {
    tip.innerHTML = html; tip.style.display = "block";
    const w = tip.offsetWidth, h = tip.offsetHeight;
    let left = x + 14, top = y + 14;
    if (left + w > window.innerWidth - 8) left = x - w - 14;
    if (top + h > window.innerHeight - 8) top = y - h - 14;
    tip.style.left = left + "px"; tip.style.top = top + "px";
  }
  function hideTip() { tip.style.display = "none"; }

  // ---------- canvas helper ----------
  function setup(canvas) {
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    const w = canvas.clientWidth, h = canvas.clientHeight;
    if (canvas.width !== Math.round(w * dpr) || canvas.height !== Math.round(h * dpr)) { canvas.width = Math.round(w * dpr); canvas.height = Math.round(h * dpr); }
    const ctx = canvas.getContext("2d");
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, w, h);
    return { ctx, w, h };
  }
  function niceTicks(min, max, n) {
    const span = max - min || 1, step0 = span / Math.max(n, 1), mag = Math.pow(10, Math.floor(Math.log10(step0)));
    const err = step0 / mag, step = (err >= 7.5 ? 10 : err >= 3.5 ? 5 : err >= 1.5 ? 2 : 1) * mag;
    const out = [];
    for (let v = Math.ceil(min / step) * step; v <= max + 1e-9; v += step) out.push(+v.toFixed(10));
    return out;
  }
  const fmt = (v, d) => (v == null || isNaN(v) ? "–" : Number(v).toFixed(d));
  const sgn = (v, d) => (v > 0 ? "+" : "") + fmt(v, d);
  const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  const prettyDate = (s) => { const [y, m, d] = s.split("-"); return `${+d} ${MONTHS[+m - 1]} ${y}`; };
  function onResize(fn) { let t; window.addEventListener("resize", () => { clearTimeout(t); t = setTimeout(fn, 120); }); }

  // Well-documented events marked on the real price chart (subset of the project's event table).
  const KEY_EVENTS = [
    ["1990-08-02", "Iraq invades Kuwait"], ["1991-01-17", "Operation Desert Storm begins"], ["2001-09-11", "9/11 attacks"],
    ["2003-03-20", "US-led invasion of Iraq"], ["2008-09-15", "Lehman Brothers collapse"], ["2011-02-17", "Libyan civil war begins"],
    ["2014-11-27", "OPEC declines to cut output"], ["2015-07-14", "Iran nuclear deal (JCPOA) signed"], ["2018-05-08", "US withdraws from the JCPOA"],
    ["2019-09-14", "Abqaiq–Khurais attack"], ["2020-03-08", "Saudi–Russia price war"], ["2020-04-20", "WTI settles below zero"],
    ["2022-02-24", "Russia invades Ukraine"], ["2023-10-07", "Hamas attack on Israel"], ["2024-04-13", "Iran's drone and missile attack on Israel"]
  ];

  // =====================================================================
  // 1. Candlestick terminal
  // =====================================================================
  function aggregate(days, closes, from, period) {
    // candles from daily closes: open = previous close, high/low = extremes of open and the closes in the period
    const out = [];
    let cur = null, prevClose = null;
    const key = (s) => {
      if (period === "D") return s;
      if (period === "M") return s.slice(0, 7);
      const dt = new Date(s + "T00:00:00Z"); const day = (dt.getUTCDay() + 6) % 7; dt.setUTCDate(dt.getUTCDate() - day);
      return dt.toISOString().slice(0, 10);
    };
    for (let i = 0; i < days.length; i++) {
      const c = closes[i];
      if (days[i] < from) { prevClose = c; continue; }
      const k = key(days[i]);
      if (!cur || cur.k !== k) {
        if (cur) { out.push(cur); prevClose = cur.c; }
        const o = prevClose == null ? c : prevClose;
        cur = { k, t0: days[i], t1: days[i], o, h: Math.max(o, c), l: Math.min(o, c), c };
      } else {
        cur.t1 = days[i]; cur.c = c; cur.h = Math.max(cur.h, c); cur.l = Math.min(cur.l, c);
      }
    }
    if (cur) out.push(cur);
    return out;
  }

  function initTerminal(data) {
    const canvas = $("#candles"); if (!canvas) return;
    const days = data.d, closes = data.c, last = days[days.length - 1];
    const RANGES = { "1Y": [1, "D"], "5Y": [5, "W"], "10Y": [10, "W"], "ALL": [99, "M"] };
    let range = "5Y", candles = [], hover = -1, layout = null;
    const lastC = closes[closes.length - 1], prevC = closes[closes.length - 2];
    $("#term-last").innerHTML = `$${fmt(lastC, 2)}<small class="${lastC >= prevC ? "up" : "down"}">${sgn(100 * (lastC / prevC - 1), 2)}%</small>`;
    $("#term-date").textContent = prettyDate(last);

    function build() {
      const [yrs, per] = RANGES[range];
      const y = +last.slice(0, 4) - yrs;
      const from = yrs >= 99 ? days[0] : `${y}${last.slice(4)}`;
      candles = aggregate(days, closes, from, per);
      $("#term-period").textContent = { D: "daily", W: "weekly", M: "monthly" }[per] + " candles";
      draw();
    }

    function draw() {
      const { ctx, w, h } = setup(canvas);
      const padL = 6, padR = 52, padT = 14, padB = 22;
      const n = candles.length; if (!n) return;
      let lo = Infinity, hi = -Infinity;
      candles.forEach((k) => { lo = Math.min(lo, k.l); hi = Math.max(hi, k.h); });
      const pad = (hi - lo) * 0.08; lo = Math.max(0, lo - pad); hi += pad;
      const cw = (w - padL - padR) / n;
      const X = (i) => padL + cw * (i + 0.5), Y = (v) => padT + (h - padT - padB) * (1 - (v - lo) / (hi - lo));
      layout = { padL, padR, cw, n, X, Y, w, h };
      ctx.font = MONO; ctx.textBaseline = "middle"; ctx.textAlign = "left";
      niceTicks(lo, hi, 5).forEach((v) => {
        const y = Y(v); ctx.strokeStyle = C.grid; ctx.lineWidth = 1; ctx.beginPath(); ctx.moveTo(padL, y); ctx.lineTo(w - padR, y); ctx.stroke();
        ctx.fillStyle = C.dim; ctx.fillText("$" + v, w - padR + 6, y);
      });
      ctx.textAlign = "center"; ctx.textBaseline = "top";
      let lastLabel = "", lastX = -1e9;
      const yearly = range !== "1Y";
      candles.forEach((k, i) => {
        const lab = yearly ? k.t0.slice(0, 4) : MONTHS[+k.t0.slice(5, 7) - 1] + (k.t0.slice(5, 7) === "01" ? " " + k.t0.slice(0, 4) : "");
        if (lab !== lastLabel) {
          const x = X(i);
          if (x - lastX > (yearly ? 38 : 44)) {
            ctx.fillStyle = C.dim; ctx.fillText(lab, x, h - padB + 6);
            ctx.strokeStyle = C.grid; ctx.beginPath(); ctx.moveTo(x, padT); ctx.lineTo(x, h - padB); ctx.stroke();
            lastX = x;
          }
          lastLabel = lab;
        }
      });
      const bw = Math.max(1, Math.min(cw * 0.68, 12));
      candles.forEach((k, i) => {
        const up = k.c >= k.o, col = up ? C.up : C.down, x = X(i);
        ctx.strokeStyle = col; ctx.lineWidth = 1;
        ctx.beginPath(); ctx.moveTo(Math.round(x) + 0.5, Y(k.h)); ctx.lineTo(Math.round(x) + 0.5, Y(k.l)); ctx.stroke();
        const y0 = Y(Math.max(k.o, k.c)), y1 = Y(Math.min(k.o, k.c));
        ctx.fillStyle = col; ctx.fillRect(x - bw / 2, y0, bw, Math.max(1, y1 - y0));
      });
      const evIdx = [];
      KEY_EVENTS.forEach(([d, name]) => {
        const i = candles.findIndex((k) => d >= k.t0 && d <= k.t1);
        if (i < 0) return;
        const x = X(i), y = Y(candles[i].h) - 9;
        ctx.fillStyle = C.gold; ctx.beginPath(); ctx.moveTo(x, y - 4); ctx.lineTo(x + 4, y); ctx.lineTo(x, y + 4); ctx.lineTo(x - 4, y); ctx.closePath(); ctx.fill();
        evIdx.push({ i, name, d });
      });
      layout.events = evIdx;
      const lc = candles[n - 1].c, ly = Y(lc);
      ctx.setLineDash([3, 3]); ctx.strokeStyle = C.gold; ctx.beginPath(); ctx.moveTo(padL, ly); ctx.lineTo(w - padR, ly); ctx.stroke(); ctx.setLineDash([]);
      ctx.fillStyle = C.gold; ctx.fillRect(w - padR + 2, ly - 8, padR - 4, 16);
      ctx.fillStyle = "#1c1203"; ctx.textAlign = "left"; ctx.textBaseline = "middle"; ctx.font = "bold " + MONO; ctx.fillText(fmt(lc, 2), w - padR + 5, ly);
      if (hover >= 0 && hover < n) {
        const x = X(hover); ctx.strokeStyle = "rgba(242,169,59,.5)"; ctx.beginPath(); ctx.moveTo(x, padT); ctx.lineTo(x, h - padB); ctx.stroke();
      }
    }

    function pick(ev) {
      if (!layout) return;
      const r = canvas.getBoundingClientRect(), x = ev.clientX - r.left;
      const i = Math.floor((x - layout.padL) / layout.cw);
      if (i < 0 || i >= layout.n) { hover = -1; hideTip(); draw(); return; }
      hover = i; draw();
      const k = candles[i], ch = 100 * (k.c / k.o - 1);
      const evs = layout.events.filter((e) => e.i === i).map((e) => `<br><b>◆</b> ${prettyDate(e.d)}: ${e.name}`).join("");
      const when = k.t0 === k.t1 ? prettyDate(k.t0) : `${prettyDate(k.t0)} – ${prettyDate(k.t1)}`;
      showTip(`<b>${when}</b><br>O ${fmt(k.o, 2)} &nbsp;H ${fmt(k.h, 2)}<br>L ${fmt(k.l, 2)} &nbsp;C ${fmt(k.c, 2)}<br><span class="${ch >= 0 ? "up" : "down"}">${sgn(ch, 2)}%</span>${evs}`, ev.clientX, ev.clientY);
    }
    canvas.addEventListener("mousemove", pick);
    canvas.addEventListener("mouseleave", () => { hover = -1; hideTip(); draw(); });
    $$(".term-ranges button").forEach((b) => b.addEventListener("click", () => {
      range = b.dataset.range; $$(".term-ranges button").forEach((x) => x.setAttribute("aria-pressed", String(x === b))); build();
    }));
    onResize(draw);
    build();
  }

  // =====================================================================
  // 2. Result charts
  // =====================================================================
  function initResults(R) {
    const pressed = $('[data-scn][aria-pressed="true"]'), pw = $('[data-win][aria-pressed="true"]');
    let sid = pressed ? pressed.dataset.scn : R.scenarios[0].id, win = pw ? pw.dataset.win : "250";
    const S = () => R.scenarios.find((s) => s.id === sid);

    // eligible-row samples skip ceiling periods: never draw a line across a gap of more than 10 calendar days
    const gapAt = (dates, i) => i > 0 && (Date.parse(dates[i]) - Date.parse(dates[i - 1])) > 10 * 864e5;

    function slice(s) {
      const n = s.date.length, k = win === "all" ? n : Math.min(n, +win);
      return { a: n - k, b: n };
    }

    function readouts() {
      const s = S(), m = s.metrics;
      $("#r-model").textContent = s.model;
      $("#r-mae").textContent = fmt(m.mae, 3) + " pp";
      $("#r-skill").textContent = sgn(m.skill_vs_zero_pct, 1) + "%";
      $("#r-dir").textContent = fmt(m.direction_accuracy_pct, 1) + "%";
      $("#r-cov").textContent = fmt(m.coverage90_pct, 1) + "%";
      $("#r-n").textContent = m.test_rows.toLocaleString("en-US");
      $$("[data-h]").forEach((el) => (el.textContent = s.horizon === 1 ? "next-day" : "5-day"));
    }

    function timeAxis(ctx, dates, a, b, X, y) {
      ctx.textAlign = "center"; ctx.textBaseline = "top"; ctx.fillStyle = C.dim;
      const n = b - a, monthly = n <= 300; let last = "", lx = -1e9;
      for (let i = a; i < b; i++) {
        const lab = monthly ? MONTHS[+dates[i].slice(5, 7) - 1] + " " + dates[i].slice(2, 4) : dates[i].slice(0, 4);
        if (lab !== last) { const x = X(i); if (x - lx > 56) { ctx.fillText(lab, x, y); lx = x; } last = lab; }
      }
    }

    // --- actual vs predicted return with 90% band
    const cRet = $("#chart-returns");
    let retLayout = null;
    function drawReturns() {
      const s = S(), { a, b } = slice(s), { ctx, w, h } = setup(cRet);
      const padL = 46, padR = 10, padT = 10, padB = 22, n = b - a;
      let lo = Infinity, hi = -Infinity;
      for (let i = a; i < b; i++) { lo = Math.min(lo, s.actual[i], s.pred[i] - s.half_width[i]); hi = Math.max(hi, s.actual[i], s.pred[i] + s.half_width[i]); }
      const m = Math.max(Math.abs(lo), Math.abs(hi)) * 1.05; lo = -m; hi = m;
      const X = (i) => padL + (w - padL - padR) * ((i - a) / Math.max(n - 1, 1)), Y = (v) => padT + (h - padT - padB) * (1 - (v - lo) / (hi - lo));
      retLayout = { a, b, padL, padR, w };
      ctx.font = MONO; ctx.textBaseline = "middle"; ctx.textAlign = "right";
      niceTicks(lo, hi, 6).forEach((v) => {
        const y = Y(v); ctx.strokeStyle = v === 0 ? C.axis : C.grid; ctx.beginPath(); ctx.moveTo(padL, y); ctx.lineTo(w - padR, y); ctx.stroke();
        ctx.fillStyle = C.dim; ctx.fillText(v + "%", padL - 6, y);
      });
      timeAxis(ctx, s.date, a, b, X, h - padB + 6);
      ctx.fillStyle = "rgba(54,201,187,.16)";
      let s0 = a;
      for (let i = a + 1; i <= b; i++) {
        if (i === b || gapAt(s.date, i)) {
          ctx.beginPath();
          for (let j = s0; j < i; j++) { const x = X(j), y = Y(s.pred[j] + s.half_width[j]); j === s0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y); }
          for (let j = i - 1; j >= s0; j--) ctx.lineTo(X(j), Y(s.pred[j] - s.half_width[j]));
          ctx.closePath(); ctx.fill(); s0 = i;
        }
      }
      const bw = Math.max(1, (w - padL - padR) / n * 0.7);
      for (let i = a; i < b; i++) { const v = s.actual[i]; ctx.fillStyle = v >= 0 ? "rgba(43,196,138,.75)" : "rgba(239,90,72,.75)"; const y0 = Y(0), y1 = Y(v); ctx.fillRect(X(i) - bw / 2, Math.min(y0, y1), bw, Math.max(1, Math.abs(y1 - y0))); }
      ctx.strokeStyle = C.gold; ctx.lineWidth = n > 600 ? 1 : 1.6; ctx.beginPath();
      for (let i = a; i < b; i++) { const x = X(i), y = Y(s.pred[i]); (i === a || gapAt(s.date, i)) ? ctx.moveTo(x, y) : ctx.lineTo(x, y); }
      ctx.stroke(); ctx.lineWidth = 1;
    }
    cRet.addEventListener("mousemove", (ev) => {
      if (!retLayout) return;
      const s = S(), r = cRet.getBoundingClientRect(), x = ev.clientX - r.left, { a, b, padL, padR, w } = retLayout;
      const i = Math.round(a + (x - padL) / (w - padL - padR) * (b - a - 1));
      if (i < a || i >= b) return hideTip();
      const inBand = Math.abs(s.actual[i] - s.pred[i]) <= s.half_width[i];
      showTip(`<b>${prettyDate(s.date[i])}</b><br>actual ${sgn(s.actual[i], 2)}%<br>forecast ${sgn(s.pred[i], 2)}%<br>90% band ±${fmt(s.half_width[i], 2)} ${inBand ? "✓ inside" : "✗ outside"}`, ev.clientX, ev.clientY);
    });
    cRet.addEventListener("mouseleave", hideTip);

    // --- price path: actual Brent at t+h vs model-implied price P_t (1 + ŷ/100)
    const cPx = $("#chart-price");
    let pxLayout = null;
    function drawPrice() {
      const s = S(), { a, b } = slice(s), { ctx, w, h } = setup(cPx);
      const padL = 46, padR = 10, padT = 10, padB = 22, n = b - a;
      const act = [], prd = [], origin = [];
      for (let i = a; i < b; i++) { act.push(s.price_th[i]); prd.push(s.price_t[i] * (1 + s.pred[i] / 100)); origin.push(s.price_t[i]); }
      let lo = Math.min(...act, ...prd), hi = Math.max(...act, ...prd); const p = (hi - lo) * 0.08; lo -= p; hi += p;
      const X = (j) => padL + (w - padL - padR) * (j / Math.max(n - 1, 1)), Y = (v) => padT + (h - padT - padB) * (1 - (v - lo) / (hi - lo));
      pxLayout = { a, b, padL, padR, w, act, prd, origin };
      ctx.font = MONO; ctx.textBaseline = "middle"; ctx.textAlign = "right";
      niceTicks(lo, hi, 5).forEach((v) => { const y = Y(v); ctx.strokeStyle = C.grid; ctx.beginPath(); ctx.moveTo(padL, y); ctx.lineTo(w - padR, y); ctx.stroke(); ctx.fillStyle = C.dim; ctx.fillText("$" + v, padL - 6, y); });
      timeAxis(ctx, s.date, a, b, (i) => X(i - a), h - padB + 6);
      const line = (arr, col, lw, dash) => { ctx.setLineDash(dash || []); ctx.strokeStyle = col; ctx.lineWidth = lw; ctx.beginPath(); arr.forEach((v, j) => ((j && !gapAt(s.date, a + j)) ? ctx.lineTo(X(j), Y(v)) : ctx.moveTo(X(j), Y(v)))); ctx.stroke(); ctx.setLineDash([]); ctx.lineWidth = 1; };
      line(act, C.ink, n > 600 ? 1 : 1.6);
      line(prd, C.gold, n > 600 ? 1 : 1.6, [4, 3]);
    }
    cPx.addEventListener("mousemove", (ev) => {
      if (!pxLayout) return;
      const s = S(), r = cPx.getBoundingClientRect(), x = ev.clientX - r.left, { a, b, padL, padR, w, act, prd, origin } = pxLayout;
      const j = Math.round((x - padL) / (w - padL - padR) * (b - a - 1));
      if (j < 0 || j >= b - a) return hideTip();
      showTip(`<b>origin ${prettyDate(s.date[a + j])}</b><br>Brent at origin $${fmt(origin[j], 2)}<br>actual after ${s.horizon}d $${fmt(act[j], 2)}<br>forecast $${fmt(prd[j], 2)} (${sgn(prd[j] - act[j], 2)})`, ev.clientX, ev.clientY);
    });
    cPx.addEventListener("mouseleave", hideTip);

    // --- scatter predicted vs actual
    const cSc = $("#chart-scatter");
    function drawScatter() {
      const s = S(), { ctx, w, h } = setup(cSc);
      const padL = 44, padR = 10, padT = 10, padB = 30;
      const q = (arr, p) => { const v = arr.slice().sort((x, y) => x - y); return v[Math.floor(p * (v.length - 1))]; };
      const lim = Math.max(Math.abs(q(s.actual, 0.005)), Math.abs(q(s.actual, 0.995))) * 1.1;
      const plim = Math.max(lim * 0.25, Math.max(...s.pred.map(Math.abs)) * 1.2);
      const X = (v) => padL + (w - padL - padR) * ((v + lim) / (2 * lim)), Y = (v) => padT + (h - padT - padB) * (1 - (v + plim) / (2 * plim));
      ctx.font = MONO; ctx.textBaseline = "middle"; ctx.textAlign = "right";
      niceTicks(-plim, plim, 5).forEach((v) => { const y = Y(v); ctx.strokeStyle = v === 0 ? C.axis : C.grid; ctx.beginPath(); ctx.moveTo(padL, y); ctx.lineTo(w - padR, y); ctx.stroke(); ctx.fillStyle = C.dim; ctx.fillText(v + "", padL - 6, y); });
      ctx.textAlign = "center"; ctx.textBaseline = "top";
      niceTicks(-lim, lim, 6).forEach((v) => { const x = X(v); ctx.strokeStyle = v === 0 ? C.axis : C.grid; ctx.beginPath(); ctx.moveTo(x, padT); ctx.lineTo(x, h - padB); ctx.stroke(); ctx.fillStyle = C.dim; ctx.fillText(v + "", x, h - padB + 4); });
      ctx.fillText("actual return (%)", padL + (w - padL - padR) / 2, h - 13);
      ctx.save(); ctx.translate(11, padT + (h - padT - padB) / 2); ctx.rotate(-Math.PI / 2); ctx.fillText("forecast (%)", 0, -6); ctx.restore();
      ctx.fillStyle = "rgba(43,196,138,.06)"; ctx.fillRect(X(0), padT, w - padR - X(0), Y(0) - padT); ctx.fillRect(padL, Y(0), X(0) - padL, h - padB - Y(0));
      ctx.fillStyle = "rgba(242,169,59,.55)";
      for (let i = 0; i < s.actual.length; i++) { const x = X(s.actual[i]), y = Y(s.pred[i]); if (x < padL || x > w - padR || y < padT || y > h - padB) continue; ctx.fillRect(x - 1.2, y - 1.2, 2.4, 2.4); }
      ctx.setLineDash([4, 4]); ctx.strokeStyle = C.teal; ctx.beginPath(); const e = Math.min(lim, plim); ctx.moveTo(X(-e), Y(-e)); ctx.lineTo(X(e), Y(e)); ctx.stroke(); ctx.setLineDash([]);
    }

    // --- validation leaderboard: MAE skill vs zero per family
    const cLb = $("#chart-board");
    function drawBoard() {
      const s = S(), rows = (R.leaderboard[sid] || []).slice().sort((p, q) => q.skill - p.skill);
      if (!rows.length) return;
      cLb.style.height = Math.max(240, rows.length * 22 + 30) + "px";
      const { ctx, w, h } = setup(cLb);
      const padL = Math.min(200, w * 0.44), padR = 60, padT = 6, rowH = (h - padT - 22) / rows.length;
      // axis clipped at -12% so one very poor family (the MLP) does not squash the rest; clipped bars end in an arrow
      const CLIP = -12;
      let lo = Math.max(CLIP, Math.min(0, ...rows.map((r) => r.skill))), hi = Math.max(0, ...rows.map((r) => r.skill));
      const span = hi - lo || 1; lo -= span * 0.04; hi += span * 0.04;
      const X0 = (v) => padL + (w - padL - padR) * ((v - lo) / (hi - lo));
      const X = (v) => X0(Math.max(v, lo));
      ctx.font = MONO; ctx.textBaseline = "middle";
      rows.forEach((r, i) => {
        const y = padT + rowH * i + rowH / 2, sel = r.family === s.model;
        ctx.textAlign = "right"; ctx.fillStyle = sel ? C.gold : r.baseline ? C.dim : C.ink;
        ctx.fillText(r.family.length > 27 ? r.family.slice(0, 26) + "…" : r.family, padL - 8, y);
        const x0 = X(0), x1 = X(r.skill);
        ctx.fillStyle = r.baseline ? "rgba(163,153,133,.45)" : sel ? C.gold : r.skill >= 0 ? "rgba(54,201,187,.75)" : "rgba(239,90,72,.65)";
        ctx.fillRect(Math.min(x0, x1), y - rowH * 0.32, Math.max(1, Math.abs(x1 - x0)), rowH * 0.64);
        const clipped = r.skill < lo;
        if (clipped) { ctx.beginPath(); ctx.moveTo(x1 - 6, y); ctx.lineTo(x1, y - rowH * 0.32); ctx.lineTo(x1, y + rowH * 0.32); ctx.closePath(); ctx.fill(); }
        const neg = r.skill < 0, tx = neg ? Math.min(x0, x1) + (clipped ? 4 : 0) : x1 + 5;
        ctx.textAlign = neg ? (clipped ? "left" : "right") : "left"; ctx.fillStyle = clipped ? "#1c1203" : C.dim;
        ctx.fillText(sgn(r.skill, 2) + "%", neg && !clipped ? x1 - 5 : tx, y);
      });
      ctx.strokeStyle = C.axis; ctx.beginPath(); ctx.moveTo(X(0), padT); ctx.lineTo(X(0), h - 18); ctx.stroke();
      ctx.textAlign = "center"; ctx.fillStyle = C.dim; ctx.fillText("validation MAE skill vs zero-return forecast (higher is better)", padL + (w - padL - padR) / 2, h - 8);
    }

    function all() { readouts(); drawReturns(); drawPrice(); drawScatter(); drawBoard(); }
    $$("[data-scn]").forEach((b) => b.addEventListener("click", () => {
      sid = b.dataset.scn; $$("[data-scn]").forEach((x) => x.setAttribute("aria-pressed", String(x.dataset.scn === sid))); all();
    }));
    $$("[data-win]").forEach((b) => b.addEventListener("click", () => {
      win = b.dataset.win; $$("[data-win]").forEach((x) => x.setAttribute("aria-pressed", String(x === b))); drawReturns(); drawPrice();
    }));
    onResize(all);
    all();
  }

  // =====================================================================
  // 3. Phase 4: volatility forecasts on real Brent (log scale)
  // =====================================================================
  function initVol(V) {
    const cv = $("#chart-vol"); if (!cv) return;
    let h = "5", lay = null;
    function table() {
      const H = V.horizons[h], tb = $("#vol-table tbody");
      tb.innerHTML = H.test_table.map((r) => `<tr class="${r.model === H.selected ? "hl" : ""}"><td>${r.model}${r.model === H.selected ? " · selected" : ""}</td>` +
        `<td class="num">${fmt(r.MAE, 3)}</td><td class="num">${fmt(r.R2, 3)}</td><td class="num">${sgn(r["MAE skill vs hist. mean (%)"], 1)}%</td><td class="num">${sgn(r["MAE skill vs naive (%)"], 1)}%</td></tr>`).join("");
      $("#vol-model").textContent = H.selected;
    }
    function draw() {
      const H = V.horizons[h], { ctx, w, hgt = cv.clientHeight } = setup(cv);
      const padL = 44, padR = 10, padT = 10, padB = 22, n = H.date.length;
      const lo = Math.log(0.5), hi = Math.log(Math.max(...H.actual, ...H.forecast) * 1.1);
      const X = (i) => padL + (w - padL - padR) * (i / (n - 1)), Y = (v) => padT + (hgt - padT - padB) * (1 - (Math.log(Math.max(v, 0.5)) - lo) / (hi - lo));
      lay = { padL, padR, w, n };
      ctx.font = MONO; ctx.textBaseline = "middle"; ctx.textAlign = "right";
      [0.5, 1, 2, 5, 10, 20, 50].filter((v) => Math.log(v) <= hi).forEach((v) => {
        const y = Y(v); ctx.strokeStyle = C.grid; ctx.beginPath(); ctx.moveTo(padL, y); ctx.lineTo(w - padR, y); ctx.stroke(); ctx.fillStyle = C.dim; ctx.fillText(v + "%", padL - 6, y);
      });
      ctx.textAlign = "center"; ctx.textBaseline = "top"; let last = "";
      H.date.forEach((d, i) => { const yv = d.slice(0, 4); if (yv !== last) { const x = X(i); ctx.fillStyle = C.dim; ctx.fillText(yv, x, hgt - padB + 6); ctx.strokeStyle = C.grid; ctx.beginPath(); ctx.moveTo(x, padT); ctx.lineTo(x, hgt - padB); ctx.stroke(); last = yv; } });
      const line = (arr, col, lw, dash) => { ctx.setLineDash(dash || []); ctx.strokeStyle = col; ctx.lineWidth = lw; ctx.beginPath(); arr.forEach((v, i) => (i ? ctx.lineTo(X(i), Y(v)) : ctx.moveTo(X(i), Y(v)))); ctx.stroke(); ctx.setLineDash([]); ctx.lineWidth = 1; };
      line(H.hist_mean, C.dim, 1, [5, 4]);
      line(H.actual, C.ink, 1);
      line(H.forecast, C.gold, 1.4);
    }
    cv.addEventListener("mousemove", (ev) => {
      if (!lay) return;
      const H = V.horizons[h], r = cv.getBoundingClientRect(), i = Math.round((ev.clientX - r.left - lay.padL) / (lay.w - lay.padL - lay.padR) * (lay.n - 1));
      if (i < 0 || i >= lay.n) return hideTip();
      showTip(`<b>${prettyDate(H.date[i])}</b><br>realised next ${h}d: ${fmt(H.actual[i], 2)}%/day<br>forecast: ${fmt(H.forecast[i], 2)}%<br>historical avg: ${fmt(H.hist_mean[i], 2)}%`, ev.clientX, ev.clientY);
    });
    cv.addEventListener("mouseleave", hideTip);
    $$("[data-vh]").forEach((b) => b.addEventListener("click", () => { h = b.dataset.vh; $$("[data-vh]").forEach((x) => x.setAttribute("aria-pressed", String(x === b))); table(); draw(); }));
    onResize(draw);
    table(); draw();
  }

  document.addEventListener("DOMContentLoaded", () => {
    fetch("data/volatility.json").then((r) => r.json()).then(initVol).catch((e) => console.error("volatility data", e));
    fetch("data/brent_eia.json").then((r) => r.json()).then(initTerminal).catch((e) => console.error("brent data", e));
    fetch("data/results.json").then((r) => r.json()).then(initResults).catch((e) => console.error("results data", e));
  });
})();
