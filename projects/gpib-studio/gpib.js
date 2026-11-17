// GPIB Studio page: a CRT that shows each of the four instruments, and the test-library filter.
//
// The traces are computed in the browser from the DUT model of gpib_lab/simulator.py
// (4th-order Butterworth bandpass 2.44 GHz / 80 MHz, 1.8 dB loss, Rapp amplifier 20 dB gain,
// Psat 12 dBm, p = 2, cable 0.9 dB/sqrt(GHz)), and the source and scope states shown in the
// repository's screenshots. Display settings such as RBW are those of this drawing.
(function () {
  "use strict";

  var GREEN = "#5cff8a", AMBER = "#f5a524", DIM = "rgba(92,255,138,0.55)", GRID = "rgba(92,255,138,0.16)";
  var MONO = "'JetBrains Mono', ui-monospace, Consolas, monospace";

  // ---------------------------------------------------------------- DUT model (port of simulator.py)
  var DUT = { f0: 2.44e9, bw: 80e6, order: 4, loss: 1.8, gain: 20, psat: 12, p: 2, cable: 0.9 };
  function cmul(a, b) { return [a[0] * b[0] - a[1] * b[1], a[0] * b[1] + a[1] * b[0]]; }
  function cdiv(a, b) { var d = b[0] * b[0] + b[1] * b[1]; return [(a[0] * b[0] + a[1] * b[1]) / d, (a[1] * b[0] - a[0] * b[1]) / d]; }
  function cabs(a) { return Math.hypot(a[0], a[1]); }
  var POLES = [];
  for (var k = 0; k < DUT.order; k++) { var ang = Math.PI * (2 * k + DUT.order + 1) / (2 * DUT.order); POLES.push([Math.cos(ang), Math.sin(ang)]); }
  function filterS(f) {
    var w = Math.max(f, 1) / DUT.f0, s = [0, (w - 1 / w) * DUT.f0 / DUT.bw], e = [1, 0], sn = [1, 0];
    POLES.forEach(function (p) { e = cmul(e, [s[0] - p[0], s[1] - p[1]]); sn = cmul(sn, s); });
    var s21 = cdiv([1, 0], e), s11 = cdiv(sn, e), l = Math.pow(10, -DUT.loss / 20);
    return { s21: cabs(s21) * l, s11: cabs(s11) };
  }
  function cableDb(f) { return DUT.cable * Math.sqrt(Math.max(f, 0) / 1e9); }
  function ampOut(pin) {
    var g = Math.pow(10, DUT.gain / 10), pl = g * Math.pow(10, pin / 10), sat = Math.pow(10, DUT.psat / 10);
    return 10 * Math.log10(pl / Math.pow(1 + Math.pow(pl / sat, DUT.p), 1 / DUT.p));
  }
  function db(x) { return 10 * Math.log10(Math.max(x, 1e-30)); }

  // comb 10 MHz steps, 2.30-2.60 GHz, -40 dBm (one of the simulator's test signals) through filter + amplifier + cable
  var COMB = [];
  for (var fc = 2.30e9; fc <= 2.60e9 + 1; fc += 10e6) {
    var lvl = -40 + 20 * Math.log10(Math.max(filterS(fc).s21, 1e-12));
    COMB.push([fc, ampOut(lvl) - cableDb(fc)]);
  }

  function gauss() { return (Math.random() + Math.random() + Math.random() + Math.random() - 2) * 1.7; }

  // ---------------------------------------------------------------- screen helpers
  function frame(ctx, w, h) {
    var top = 30, bot = 26, left = 10, right = 10;
    var g = { x: left, y: top, w: w - left - right, h: h - top - bot };
    ctx.strokeStyle = GRID; ctx.lineWidth = 1;
    ctx.beginPath();
    for (var i = 0; i <= 10; i++) { var x = Math.round(g.x + g.w * i / 10) + 0.5; ctx.moveTo(x, g.y); ctx.lineTo(x, g.y + g.h); }
    for (var j = 0; j <= 8; j++) { var y = Math.round(g.y + g.h * j / 8) + 0.5; ctx.moveTo(g.x, y); ctx.lineTo(g.x + g.w, y); }
    ctx.stroke();
    ctx.strokeStyle = "rgba(92,255,138,0.32)"; ctx.strokeRect(g.x + 0.5, g.y + 0.5, g.w, g.h);
    return g;
  }
  function text(ctx, s, x, y, align, color, size, bold) {
    ctx.font = (bold ? "700 " : "") + (size || 10) + "px " + MONO;
    ctx.fillStyle = color || GREEN; ctx.textAlign = align || "left"; ctx.textBaseline = "middle";
    ctx.fillText(s, x, y);
  }
  function glowLine(ctx, pts, color, width, upto) {
    var n = Math.max(2, Math.min(pts.length, upto == null ? pts.length : upto));
    ctx.save();
    ctx.shadowColor = color; ctx.shadowBlur = 7; ctx.strokeStyle = color; ctx.lineWidth = width || 1.4; ctx.lineJoin = "round";
    ctx.beginPath();
    for (var i = 0; i < n; i++) { if (i) ctx.lineTo(pts[i][0], pts[i][1]); else ctx.moveTo(pts[i][0], pts[i][1]); }
    ctx.stroke(); ctx.restore();
  }

  // ---------------------------------------------------------------- the four instruments
  var MODES = {
    spectrum: { addr: "GPIB0::18", name: "HP 8563E · spectrum analyzer" },
    network: { addr: "GPIB0::16", name: "HP 8720D · network analyzer" },
    source: { addr: "GPIB0::19", name: "HP 83752B · signal source" },
    scope: { addr: "LAN :3000", name: "GDS-1104B · oscilloscope" }
  };

  var specTrace = null, specPrev = null, specSweep = -1;
  function newSpectrum() {
    var n = 601, f0 = 2.28e9, f1 = 2.62e9, rbw = 1e6, sig = rbw / 2.355, out = [];
    var floor = -164 + 10 * Math.log10(rbw);
    for (var i = 0; i < n; i++) {
      var f = f0 + (f1 - f0) * i / (n - 1), p = Math.pow(10, (floor + gauss()) / 10);
      for (var c = 0; c < COMB.length; c++) { var d = (f - COMB[c][0]) / sig; if (Math.abs(d) < 6) p += Math.pow(10, COMB[c][1] / 10) * Math.exp(-0.5 * d * d); }
      out.push([f, db(p)]);
    }
    return out;
  }

  function drawSpectrum(ctx, w, h, t) {
    var g = frame(ctx, w, h), ref = -20, per = 10;
    var sweep = Math.floor(t / 1.6);
    if (!specTrace || sweep !== specSweep) { specPrev = specTrace || newSpectrum(); specTrace = newSpectrum(); specSweep = sweep; }
    var prog = Math.min(1, (t - sweep * 1.6) / 0.9);
    function toPts(tr) {
      return tr.map(function (p) {
        var y = g.y + (ref - p[1]) / (per * 8) * g.h;
        return [g.x + (p[0] - 2.28e9) / 0.34e9 * g.w, Math.min(g.y + g.h, Math.max(g.y, y))];
      });
    }
    var pts = toPts(specTrace), n = Math.round(pts.length * prog);
    if (n < pts.length) glowLine(ctx, toPts(specPrev).slice(n), "rgba(92,255,138,0.35)", 1, null);
    glowLine(ctx, pts, GREEN, 1.2, n);
    var best = specTrace.reduce(function (a, b) { return b[1] > a[1] ? b : a; });
    var bx = g.x + (best[0] - 2.28e9) / 0.34e9 * g.w, by = g.y + (ref - best[1]) / (per * 8) * g.h;
    if (prog >= 1) { ctx.fillStyle = AMBER; ctx.beginPath(); ctx.moveTo(bx, by - 3); ctx.lineTo(bx - 5, by - 11); ctx.lineTo(bx + 5, by - 11); ctx.closePath(); ctx.fill(); }
    text(ctx, "REF -20.0 dBm   10 dB/", g.x, 10); text(ctx, "SIMULATED", g.x + g.w, 10, "right", AMBER);
    text(ctx, "MKR " + (best[0] / 1e9).toFixed(4) + " GHz  " + best[1].toFixed(2) + " dBm", g.x, 22, "left", AMBER);
    text(ctx, "START 2.280 GHz", g.x, h - 12); if (w > 440) text(ctx, "RBW 1 MHz · 601 pts", g.x + g.w / 2, h - 12, "center", DIM); text(ctx, "STOP 2.620 GHz", g.x + g.w, h - 12, "right");
  }

  var NET = (function () {
    var out = [];
    for (var i = 0; i < 201; i++) {
      var f = 2.0e9 + 0.9e9 * i / 200, s = filterS(f);
      out.push([f, 20 * Math.log10(Math.max(s.s21, 1e-9)) + DUT.gain - cableDb(f), 20 * Math.log10(Math.max(s.s11, 1e-9))]);
    }
    return out;
  })();
  function drawNetwork(ctx, w, h, t) {
    var g = frame(ctx, w, h), ref = 30, per = 10;
    function Y(v) { return Math.min(g.y + g.h, Math.max(g.y, g.y + (ref - v) / (per * 8) * g.h)); }
    var ripple = Math.sin(t * 3) * 0.05;
    var s21 = NET.map(function (p) { return [g.x + (p[0] - 2.0e9) / 0.9e9 * g.w, Y(p[1] + ripple * Math.random())]; });
    var s11 = NET.map(function (p) { return [g.x + (p[0] - 2.0e9) / 0.9e9 * g.w, Y(p[2])]; });
    glowLine(ctx, s11, AMBER, 1.2); glowLine(ctx, s21, GREEN, 1.5);
    var mi = NET.reduce(function (a, b, i) { return Math.abs(b[0] - 2.44e9) < Math.abs(NET[a][0] - 2.44e9) ? i : a; }, 0);
    var mx = s21[mi][0], my = s21[mi][1];
    ctx.strokeStyle = GREEN; ctx.beginPath(); ctx.moveTo(mx - 5, my - 9); ctx.lineTo(mx, my - 2); ctx.lineTo(mx + 5, my - 9); ctx.stroke();
    text(ctx, "CH1 S21 LOG MAG  10 dB/  REF 30 dB", g.x, 10); text(ctx, "CH2 S11", g.x + g.w, 10, "right", AMBER);
    text(ctx, "MKR 2.4400 GHz  S21 " + NET[mi][1].toFixed(2) + " dB", g.x, 22, "left", GREEN);
    text(ctx, "START 2.000 GHz", g.x, h - 12); if (w > 440) text(ctx, "201 pts", g.x + g.w / 2, h - 12, "center", DIM); text(ctx, "STOP 2.900 GHz", g.x + g.w, h - 12, "right");
  }

  function drawSource(ctx, w, h, t) {
    var cx = w / 2, big = Math.max(18, Math.min(38, w / 13));
    ctx.strokeStyle = GRID; ctx.strokeRect(10.5, 30.5, w - 21, h - 57);
    text(ctx, "SCPI · CW MODE", 14, 12); text(ctx, "SIMULATED", w - 14, 12, "right", AMBER);
    text(ctx, "FREQ", 22, h * 0.34, "left", DIM, 11);
    ctx.save(); ctx.shadowColor = GREEN; ctx.shadowBlur = 10;
    text(ctx, "2480.000000", cx + big * 0.6, h * 0.34, "right", GREEN, big, true);
    ctx.restore();
    text(ctx, "MHz", cx + big * 0.9, h * 0.34 + big * 0.12, "left", GREEN, Math.round(big * 0.45));
    text(ctx, "POWER", 22, h * 0.56, "left", DIM, 11);
    ctx.save(); ctx.shadowColor = GREEN; ctx.shadowBlur = 10;
    text(ctx, "-20.00", cx + big * 0.6, h * 0.56, "right", GREEN, big, true);
    ctx.restore();
    text(ctx, "dBm", cx + big * 0.9, h * 0.56 + big * 0.12, "left", GREEN, Math.round(big * 0.45));
    var blink = Math.floor(t * 1.4) % 2 === 0;
    ctx.fillStyle = blink ? AMBER : "rgba(245,165,36,0.35)";
    ctx.fillRect(22, h * 0.72, 64, 18);
    text(ctx, "RF OFF", 54, h * 0.72 + 9, "center", "#1d1203", 11, true);
    text(ctx, "ALC INT", 100, h * 0.72 + 9, "left", GREEN, 11);
    text(ctx, "ceiling -20 dBm", w - 22, h * 0.72 + 9, "right", DIM, 10);
    text(ctx, "programmed state, not measured RF", cx, h - 12, "center", DIM);
  }

  function drawScope(ctx, w, h, t) {
    var g = frame(ctx, w, h), vdiv = 0.5, tdiv = 500e-6, f = 1000, delay = 20e-6;
    var shift = (t * 0.25) % 1e-3;
    function trace(phaseDelay, color, off) {
      var pts = [];
      for (var i = 0; i <= 400; i++) {
        var tt = -5 * tdiv + 10 * tdiv * i / 400;
        var v = Math.round(Math.sin(2 * Math.PI * f * (tt - phaseDelay + shift * 0)) * 125) / 125;
        pts.push([g.x + g.w * i / 400, g.y + g.h / 2 - (v + off) / vdiv * (g.h / 8)]);
      }
      glowLine(ctx, pts, color, 1.4);
    }
    trace(0, AMBER, 0); trace(delay, GREEN, 0);
    ctx.strokeStyle = "rgba(92,255,138,0.35)"; ctx.setLineDash([3, 4]);
    ctx.beginPath(); ctx.moveTo(g.x + g.w / 2 + 0.5, g.y); ctx.lineTo(g.x + g.w / 2 + 0.5, g.y + g.h); ctx.stroke(); ctx.setLineDash([]);
    text(ctx, "CH1 500mV  CH2 500mV", g.x, 10, "left", AMBER); text(ctx, "SIMULATED", g.x + g.w, 10, "right", AMBER);
    text(ctx, "Vpp 2.00 V  RMS 0.707 V  f 1.000 kHz", g.x, 22, "left", GREEN);
    text(ctx, "500 µs/div", g.x, h - 12); if (w > 440) text(ctx, "10k samples", g.x + g.w / 2, h - 12, "center", DIM); text(ctx, "TRIG CH1", g.x + g.w, h - 12, "right");
  }

  var DRAW = { spectrum: drawSpectrum, network: drawNetwork, source: drawSource, scope: drawScope };

  function instrument(root) {
    var canvas = root.querySelector("canvas"), keys = root.querySelectorAll("[data-mode]");
    var addr = root.querySelector("[data-addr]"), name = root.querySelector("[data-name]");
    var mode = "spectrum", userPicked = false, t0 = null, lastSwitch = 0, visible = true;
    var reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    function setMode(m) {
      mode = m;
      keys.forEach(function (k) { k.setAttribute("aria-pressed", String(k.dataset.mode === m)); });
      addr.textContent = MODES[m].addr; name.textContent = MODES[m].name;
    }
    keys.forEach(function (k) { k.addEventListener("click", function () { userPicked = true; setMode(k.dataset.mode); render(lastT); }); });
    var lastT = 0;
    function render(t) {
      var dpr = Math.min(window.devicePixelRatio || 1, 2), w = canvas.clientWidth, h = canvas.clientHeight;
      if (!w || !h) return;
      if (canvas.width !== Math.round(w * dpr) || canvas.height !== Math.round(h * dpr)) { canvas.width = Math.round(w * dpr); canvas.height = Math.round(h * dpr); }
      var ctx = canvas.getContext("2d");
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0); ctx.clearRect(0, 0, w, h);
      DRAW[mode](ctx, w, h, reduce ? 99 : t);
    }
    function loop(ts) {
      if (t0 === null) t0 = ts;
      var t = (ts - t0) / 1000; lastT = t;
      if (!userPicked && t - lastSwitch > 7) {
        lastSwitch = t;
        var order = ["spectrum", "network", "source", "scope"];
        setMode(order[(order.indexOf(mode) + 1) % order.length]);
      }
      if (visible && !document.hidden) render(t);
      requestAnimationFrame(loop);
    }
    setMode("spectrum");
    render(0);
    window.addEventListener("resize", function () { render(lastT); });
    if ("IntersectionObserver" in window) new IntersectionObserver(function (e) { visible = e[0].isIntersecting; }).observe(canvas);
    if (!reduce) requestAnimationFrame(loop); else render(99);
  }

  // ---------------------------------------------------------------- test-library filter
  function library(root) {
    var buttons = root.querySelectorAll("[data-filter]"), cards = root.querySelectorAll(".t"), count = root.querySelector("[data-count]");
    function apply(f) {
      var n = 0;
      cards.forEach(function (c) { var show = f === "all" || c.dataset.inst.split(" ").indexOf(f) > -1; c.hidden = !show; if (show) n++; });
      buttons.forEach(function (b) { b.setAttribute("aria-pressed", String(b.dataset.filter === f)); });
      if (count) count.textContent = n + (n === 1 ? " test" : " tests");
    }
    buttons.forEach(function (b) { b.addEventListener("click", function () { apply(b.dataset.filter); }); });
    apply("all");
  }

  function init() {
    var i = document.querySelector("[data-instrument]"); if (i) instrument(i);
    var l = document.querySelector("[data-library]"); if (l) library(l);
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init); else init();
})();
