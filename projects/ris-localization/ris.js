// RIS localization page: top-view map of the bound scenario and the error-budget explorer.
//
// Geometry is the bound scenario of crlb/create_crlb_config.m. The numbers in DATA are copied
// from crlb/crlb_results/snr_sweep_bounds.csv, prior_sensitivity.csv and crlb_results.mat
// (condition number of the equivalent FIM). The tile colours of the RIS panels are an
// illustration (the phase each tile would need to focus BS -> RIS -> UE), not a result.
(function () {
  "use strict";

  var GEO = {
    bs: [0, 0, 5],
    ue: [8, 7, 1.5],
    v: [1.2, -0.4, 0.1],
    ris: [[0, 18, 3], [20, 0, 4], [18, 18, 6]]
  };

  var DATA = {
    snr: [-10, -7.5, -5, -2.5, 0, 2.5, 5, 7.5, 10, 12.5, 15, 17.5, 20, 22.5, 25, 27.5, 30],
    peb: [5.50624, 4.20027, 3.24250, 2.55053, 2.06179, 1.72723, 1.50681, 1.36734, 1.28226, 1.23184, 1.20256, 1.18578, 1.17623, 1.17083, 1.16778, 1.16607, 1.16510],
    veb: [55.938, 41.950, 31.460, 23.595, 17.698, 13.277, 9.964, 7.482, 5.624, 4.236, 3.200, 2.431, 1.864, 1.451, 1.155, 0.950, 0.811],
    eta: [0.043341, 0.032503, 0.024376, 0.018282, 0.013714, 0.010289, 0.0077224, 0.0058001, 0.0043616, 0.0032868, 0.0024861, 0.0018924, 0.0014558, 0.0011391, 0.00091390, 0.00075847, 0.00065506],
    dc: [4.5860, 3.4990, 2.7020, 2.1265, 1.7202, 1.4423, 1.2594, 1.1437, 1.0733, 1.0315, 1.0073, 0.99337, 0.98548, 0.98101, 0.97849, 0.97706, 0.97626],
    cond: [8.338e7, 8.339e7, 8.340e7, 8.343e7, 8.347e7, 8.354e7, 8.366e7, 8.389e7, 8.428e7, 8.499e7, 8.625e7, 8.849e7, 9.249e7, 1.089e8, 1.923e8, 3.409e8, 6.052e8],
    sp: [0.02, 0.05, 0.1, 0.2, 0.5],
    sv: [0.01, 0.025, 0.05, 0.1, 0.25],
    pebP: [0.28835, 0.60630, 1.17623, 2.33392, 5.82176],
    vebP: [1.77274, 1.79309, 1.86396, 2.12394, 3.43053],
    risP: [0.034641, 0.086603, 0.173205, 0.346410, 0.866025]
  };

  // cyclic phase colour wheel (same stops as the CSS strip)
  var WHEEL = [[0, 43, 47, 140], [0.2, 61, 123, 217], [0.4, 79, 227, 208], [0.6, 243, 231, 161], [0.8, 232, 96, 138], [1, 43, 47, 140]];
  function wheel(u, a) {
    u = u - Math.floor(u);
    var k = 0;
    while (k < WHEEL.length - 2 && u > WHEEL[k + 1][0]) k++;
    var p = WHEEL[k], q = WHEEL[k + 1], t = (u - p[0]) / (q[0] - p[0]);
    return "rgba(" + Math.round(p[1] + (q[1] - p[1]) * t) + "," + Math.round(p[2] + (q[2] - p[2]) * t) + "," + Math.round(p[3] + (q[3] - p[3]) * t) + "," + (a == null ? 1 : a) + ")";
  }
  var RIS_HUE = [0.42, 0.62, 0.84];

  function dist(a, b) { var dx = a[0] - b[0], dy = a[1] - b[1], dz = a[2] - b[2]; return Math.sqrt(dx * dx + dy * dy + dz * dz); }

  // sharp canvas that redraws on resize; optional animation loop
  function sharp(canvas, draw, animate) {
    var reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches, visible = true, t0 = null;
    function render(t) {
      var dpr = Math.min(window.devicePixelRatio || 1, 2), w = canvas.clientWidth, h = canvas.clientHeight;
      if (!w || !h) return;
      if (canvas.width !== Math.round(w * dpr) || canvas.height !== Math.round(h * dpr)) { canvas.width = Math.round(w * dpr); canvas.height = Math.round(h * dpr); }
      var ctx = canvas.getContext("2d");
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, w, h);
      draw(ctx, w, h, t || 0);
    }
    function loop(ts) {
      if (t0 === null) t0 = ts;
      if (visible && !document.hidden) render((ts - t0) / 1000);
      requestAnimationFrame(loop);
    }
    render(0);
    window.addEventListener("resize", function () { render(0); });
    if ("IntersectionObserver" in window) new IntersectionObserver(function (e) { visible = e[0].isIntersecting; }).observe(canvas);
    if (animate && !reduce) requestAnimationFrame(loop);
    return function () { render(0); };
  }

  var MONO = "'JetBrains Mono', ui-monospace, Consolas, monospace";

  // ---------------------------------------------------------------- the map
  // st: { peb (m), risPeb (m), pulses (bool) }
  function drawMap(ctx, w, h, t, st) {
    var X0 = -3, X1 = 23.5, Y0 = -3, Y1 = 21.5, pad = 22;
    var s = Math.min((w - 2 * pad) / (X1 - X0), (h - 2 * pad) / (Y1 - Y0));
    var ox = (w - s * (X1 - X0)) / 2, oy = (h - s * (Y1 - Y0)) / 2;
    function P(x, y) { return [ox + (x - X0) * s, h - oy - (y - Y0) * s]; }

    // grid, 5 m
    ctx.lineWidth = 1; ctx.font = "10px " + MONO; ctx.fillStyle = "rgba(149,155,200,0.75)";
    for (var g = 0; g <= 20; g += 5) {
      var a = P(g, Y0), b = P(g, Y1), c = P(X0, g), d = P(X1, g);
      ctx.strokeStyle = g === 0 ? "rgba(149,155,200,0.30)" : "rgba(149,155,200,0.12)";
      ctx.beginPath(); ctx.moveTo(a[0], a[1]); ctx.lineTo(b[0], b[1]); ctx.moveTo(c[0], c[1]); ctx.lineTo(d[0], d[1]); ctx.stroke();
      ctx.textAlign = "center"; ctx.textBaseline = "top"; ctx.fillText(g + (g === 20 ? " m" : ""), a[0], a[1] + 3);
      if (g > 0) { ctx.textAlign = "right"; ctx.textBaseline = "middle"; ctx.fillText(g, c[0] - 4, c[1]); }
    }
    ctx.textAlign = "left"; ctx.textBaseline = "top"; ctx.fillText("top view (x, y)", ox + 4, oy + 2);

    var bs = P(GEO.bs[0], GEO.bs[1]), ue = P(GEO.ue[0], GEO.ue[1]);

    // propagation paths
    ctx.setLineDash([]); ctx.lineWidth = 1.6; ctx.strokeStyle = "rgba(228,231,255,0.75)";
    ctx.beginPath(); ctx.moveTo(bs[0], bs[1]); ctx.lineTo(ue[0], ue[1]); ctx.stroke();
    GEO.ris.forEach(function (r, k) {
      var rp = P(r[0], r[1]);
      ctx.setLineDash([5, 5]); ctx.lineWidth = 1.3; ctx.strokeStyle = wheel(RIS_HUE[k], 0.75);
      ctx.beginPath(); ctx.moveTo(bs[0], bs[1]); ctx.lineTo(rp[0], rp[1]); ctx.lineTo(ue[0], ue[1]); ctx.stroke();
    });
    ctx.setLineDash([]);

    // pilot pulses travelling along each path
    if (st.pulses) {
      var paths = [[GEO.bs, GEO.ue]].concat(GEO.ris.map(function (r) { return [GEO.bs, r, GEO.ue]; }));
      paths.forEach(function (pp, k) {
        var segs = [], total = 0;
        for (var i = 0; i < pp.length - 1; i++) { var L = Math.hypot(pp[i + 1][0] - pp[i][0], pp[i + 1][1] - pp[i][1]); segs.push(L); total += L; }
        for (var j = 0; j < 3; j++) {
          var u = ((t * 6 + j * total / 3 + k * 2.3) % total + total) % total, i2 = 0;
          while (i2 < segs.length - 1 && u > segs[i2]) { u -= segs[i2]; i2++; }
          var f = u / segs[i2], A = pp[i2], B = pp[i2 + 1], q = P(A[0] + (B[0] - A[0]) * f, A[1] + (B[1] - A[1]) * f);
          ctx.beginPath(); ctx.arc(q[0], q[1], 2.6, 0, 2 * Math.PI);
          ctx.fillStyle = k === 0 ? "rgba(255,255,255,0.95)" : wheel(RIS_HUE[k - 1], 1); ctx.fill();
        }
      });
    }

    // RIS panels: 6 x 6 tiles coloured by the focusing phase BS -> tile -> UE (illustration)
    var half = 0.95, n = 6, cell = 2 * half / n, lam = 1.05;
    GEO.ris.forEach(function (r, k) {
      for (var i = 0; i < n; i++) for (var j = 0; j < n; j++) {
        var x = r[0] - half + (i + 0.5) * cell, y = r[1] - half + (j + 0.5) * cell, tile = [x, y, r[2]];
        var ph = (dist(tile, GEO.bs) + dist(tile, GEO.ue)) / lam - t * 0.35;
        var c0 = P(x - cell / 2, y + cell / 2);
        ctx.fillStyle = wheel(ph, 0.95);
        ctx.fillRect(c0[0] + 0.6, c0[1] + 0.6, cell * s - 1.2, cell * s - 1.2);
      }
      var rp = P(r[0], r[1]);
      // prior uncertainty: circle of radius RIS PEB (drawn to scale)
      ctx.beginPath(); ctx.arc(rp[0], rp[1], Math.max(st.risPeb * s, 1.5), 0, 2 * Math.PI);
      ctx.strokeStyle = "rgba(6,10,28,0.9)"; ctx.lineWidth = 4; ctx.stroke();
      ctx.strokeStyle = "rgba(79,227,208,1)"; ctx.lineWidth = 1.8; ctx.setLineDash([3, 3]); ctx.stroke(); ctx.setLineDash([]);
      ctx.fillStyle = "rgba(228,231,255,0.92)"; ctx.font = "600 11px " + MONO;
      ctx.textAlign = r[0] > 10 ? "right" : "left"; ctx.textBaseline = "middle";
      ctx.fillText("RIS " + (k + 1), rp[0] + (r[0] > 10 ? -1 : 1) * (half * s + 6), rp[1] + (r[1] > 10 ? -half * s - 2 : half * s + 2));
      ctx.font = "10px " + MONO; ctx.fillStyle = "rgba(149,155,200,0.9)";
      ctx.fillText("z " + r[2] + " m", rp[0] + (r[0] > 10 ? -1 : 1) * (half * s + 6), rp[1] + (r[1] > 10 ? -half * s + 11 : half * s + 15));
    });

    // UE: error circle with radius PEB, velocity arrow
    var R = st.peb * s;
    var grd = ctx.createRadialGradient(ue[0], ue[1], 0, ue[0], ue[1], R);
    grd.addColorStop(0, "rgba(180,155,255,0.38)"); grd.addColorStop(1, "rgba(180,155,255,0.06)");
    ctx.beginPath(); ctx.arc(ue[0], ue[1], R, 0, 2 * Math.PI); ctx.fillStyle = grd; ctx.fill();
    ctx.strokeStyle = "rgba(180,155,255,0.95)"; ctx.lineWidth = 1.6; ctx.stroke();
    var tip = P(GEO.ue[0] + GEO.v[0] * 2.2, GEO.ue[1] + GEO.v[1] * 2.2);
    ctx.strokeStyle = "#ffffff"; ctx.lineWidth = 2;
    ctx.beginPath(); ctx.moveTo(ue[0], ue[1]); ctx.lineTo(tip[0], tip[1]); ctx.stroke();
    var ang = Math.atan2(tip[1] - ue[1], tip[0] - ue[0]);
    ctx.beginPath(); ctx.moveTo(tip[0], tip[1]);
    ctx.lineTo(tip[0] - 8 * Math.cos(ang - 0.45), tip[1] - 8 * Math.sin(ang - 0.45));
    ctx.lineTo(tip[0] - 8 * Math.cos(ang + 0.45), tip[1] - 8 * Math.sin(ang + 0.45)); ctx.closePath();
    ctx.fillStyle = "#ffffff"; ctx.fill();
    ctx.beginPath(); ctx.arc(ue[0], ue[1], 5, 0, 2 * Math.PI); ctx.fillStyle = "#b49bff"; ctx.fill();
    ctx.strokeStyle = "#060a1c"; ctx.lineWidth = 1.5; ctx.stroke();
    ctx.fillStyle = "rgba(228,231,255,0.95)"; ctx.font = "600 11px " + MONO; ctx.textAlign = "left"; ctx.textBaseline = "bottom";
    ctx.fillText("UE", ue[0] + 8, ue[1] - 6);
    ctx.font = "10px " + MONO; ctx.fillStyle = "rgba(180,155,255,1)"; ctx.textBaseline = "top";
    var lx = Math.min(ue[0] + R * 0.72 + 6, w - 78), ly = Math.min(ue[1] + R * 0.72, h - 16);
    ctx.fillStyle = "rgba(6,10,28,0.75)"; ctx.fillRect(lx - 3, ly - 1, 76, 14);
    ctx.fillStyle = "rgba(180,155,255,1)";
    ctx.fillText("PEB " + st.peb.toFixed(2) + " m", lx, ly);

    // BS
    star(ctx, bs[0], bs[1], 9, 4);
    ctx.fillStyle = "rgba(228,231,255,0.95)"; ctx.font = "600 11px " + MONO; ctx.textAlign = "left"; ctx.textBaseline = "top";
    ctx.fillText("BS", bs[0] + 10, bs[1] + 4);
  }

  function star(ctx, x, y, R, r) {
    ctx.beginPath();
    for (var i = 0; i < 10; i++) {
      var a = -Math.PI / 2 + i * Math.PI / 5, rr = i % 2 ? r : R;
      if (i) ctx.lineTo(x + rr * Math.cos(a), y + rr * Math.sin(a)); else ctx.moveTo(x + rr * Math.cos(a), y + rr * Math.sin(a));
    }
    ctx.closePath(); ctx.fillStyle = "#ffffff"; ctx.fill();
  }

  // ---------------------------------------------------------------- the chart under the map
  function drawChart(ctx, w, h, st) {
    var xs = st.mode === "snr" ? DATA.snr : DATA.sp.map(Math.log10);
    var ys = (st.mode === "snr" ? DATA.peb : DATA.pebP).map(Math.log10);
    var padL = 40, padR = 12, padT = 14, padB = 24;
    var x0 = Math.min.apply(null, xs), x1 = Math.max.apply(null, xs), y0 = Math.log10(0.2), y1 = Math.log10(7);
    function P(x, y) { return [padL + (x - x0) / (x1 - x0) * (w - padL - padR), padT + (y1 - y) / (y1 - y0) * (h - padT - padB)]; }
    ctx.font = "10px " + MONO; ctx.lineWidth = 1;
    [0.2, 0.5, 1, 2, 5].forEach(function (v) {
      var p = P(x0, Math.log10(v)), q = P(x1, Math.log10(v));
      ctx.strokeStyle = "rgba(149,155,200,0.14)"; ctx.beginPath(); ctx.moveTo(p[0], p[1]); ctx.lineTo(q[0], q[1]); ctx.stroke();
      if (v === 0.2) return;
      ctx.fillStyle = "rgba(149,155,200,0.85)"; ctx.textAlign = "right"; ctx.textBaseline = "middle"; ctx.fillText(v + "", p[0] - 5, p[1]);
    });
    var ticks = st.mode === "snr" ? [-10, 0, 10, 20, 30] : [0.02, 0.05, 0.1, 0.2, 0.5];
    ticks.forEach(function (v) {
      var p = P(st.mode === "snr" ? v : Math.log10(v), y0);
      ctx.fillStyle = "rgba(149,155,200,0.85)"; ctx.textAlign = "center"; ctx.textBaseline = "top"; ctx.fillText(v + "", p[0], p[1] + 5);
    });
    ctx.textAlign = "left"; ctx.textBaseline = "top"; ctx.fillStyle = "rgba(149,155,200,0.85)";
    ctx.fillText("UE PEB (m) vs " + (st.mode === "snr" ? "SNR (dB)" : "RIS position prior σp (m)"), padL + 4, 0);
    if (st.mode === "snr") {             // the error floor
      var f = P(x0, Math.log10(1.165)), g = P(x1, Math.log10(1.165));
      ctx.setLineDash([4, 4]); ctx.strokeStyle = "rgba(79,227,208,0.7)"; ctx.beginPath(); ctx.moveTo(f[0], f[1]); ctx.lineTo(g[0], g[1]); ctx.stroke(); ctx.setLineDash([]);
      ctx.fillStyle = "rgba(79,227,208,0.9)"; ctx.textAlign = "right"; ctx.textBaseline = "bottom"; ctx.fillText("floor ≈ 1.16 m", g[0], g[1] - 3);
    }
    ctx.beginPath();
    xs.forEach(function (x, i) { var p = P(x, ys[i]); if (i) ctx.lineTo(p[0], p[1]); else ctx.moveTo(p[0], p[1]); });
    ctx.strokeStyle = "#b49bff"; ctx.lineWidth = 2; ctx.stroke();
    xs.forEach(function (x, i) {
      var p = P(x, ys[i]), on = i === st.i;
      ctx.beginPath(); ctx.arc(p[0], p[1], on ? 5.5 : 2.4, 0, 2 * Math.PI);
      ctx.fillStyle = on ? "#ffffff" : "#b49bff"; ctx.fill();
      if (on) { ctx.strokeStyle = "#b49bff"; ctx.lineWidth = 2; ctx.stroke(); }
    });
  }

  // ---------------------------------------------------------------- hero
  function hero(canvas) {
    sharp(canvas, function (ctx, w, h, t) {
      drawMap(ctx, w, h, t, { peb: DATA.peb[12], risPeb: DATA.risP[2], pulses: true });
    }, true);
  }

  // ---------------------------------------------------------------- explorer
  function explorer(root) {
    var map = root.querySelector("canvas.map"), chart = root.querySelector("canvas.chart"), range = root.querySelector("#ris-step");
    var st = { mode: "snr", i: 12 };
    function cur() {
      if (st.mode === "snr") return { peb: DATA.peb[st.i], veb: DATA.veb[st.i], eta: DATA.eta[st.i], dc: DATA.dc[st.i], ris: DATA.risP[2], cond: DATA.cond[st.i] };
      return { peb: DATA.pebP[st.i], veb: DATA.vebP[st.i], eta: null, dc: null, ris: DATA.risP[st.i], cond: null };
    }
    var redrawMap = sharp(map, function (ctx, w, h, t) { var c = cur(); drawMap(ctx, w, h, t, { peb: c.peb, risPeb: c.ris, pulses: true }); }, true);
    var redrawChart = sharp(chart, function (ctx, w, h) { drawChart(ctx, w, h, st); }, false);
    function set(id, v) { var n = root.querySelector(id); if (n) n.textContent = v; }
    function update() {
      st.i = parseInt(range.value, 10);
      var c = cur();
      if (st.mode === "snr") {
        set("#ris-step-out", DATA.snr[st.i] + " dB");
        set("#ris-hint", "RIS prior fixed: σp = 0.1 m, σv = 0.05 m/s per axis. Values from snr_sweep_bounds.csv.");
      } else {
        set("#ris-step-out", "σp " + DATA.sp[st.i] + " m · σv " + DATA.sv[st.i] + " m/s");
        set("#ris-hint", "SNR fixed at 20 dB. Values from prior_sensitivity.csv; that sweep does not report η, δc or the condition number.");
      }
      set("#ris-peb", c.peb.toFixed(3) + " m");
      set("#ris-veb", (c.veb < 10 ? c.veb.toFixed(3) : c.veb.toFixed(1)) + " m/s");
      set("#ris-eta", c.eta == null ? "—" : c.eta.toPrecision(3) + " ppm");
      set("#ris-dc", c.dc == null ? "—" : c.dc.toFixed(3) + " ns");
      set("#ris-rpeb", c.ris.toFixed(3) + " m");
      set("#ris-cond", c.cond == null ? "—" : (c.cond / 1e7).toFixed(2) + "×10⁷");
      redrawMap(); redrawChart();
    }
    range.addEventListener("input", update);
    root.querySelectorAll("[data-sweep]").forEach(function (b) {
      b.addEventListener("click", function () {
        root.querySelectorAll("[data-sweep]").forEach(function (x) { x.setAttribute("aria-pressed", String(x === b)); });
        st.mode = b.dataset.sweep;
        range.max = st.mode === "snr" ? 16 : 4;
        range.value = st.mode === "snr" ? 12 : 2;
        update();
      });
    });
    update();
  }

  function init() {
    var h = document.querySelector("canvas[data-ris-hero]"); if (h) hero(h);
    var e = document.querySelector("[data-ris-lab]"); if (e) explorer(e);
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init); else init();
})();
