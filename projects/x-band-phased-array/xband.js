// X-band phased-array page: array-factor model of the 3-element array (d = lambda0/2).
// It draws the normalised pattern on a half-disc (broadside up) for a chosen steering angle
// and amplitude taper. This is the textbook array factor, optionally multiplied by a
// cos(psi) element pattern - not the HFSS result shown in the figures.
(function () {
  "use strict";

  var KD = Math.PI;                 // k*d for d = lambda0/2
  var LAMBDA_G = 24.22;             // guided wavelength on the 50-ohm line in mm (HFSS project variable)
  var DB_MIN = -30;
  var TAPERS = {
    uniform: [1, 1, 1],
    cheb: [Math.sqrt(0.2345), Math.sqrt(0.5310), Math.sqrt(0.2345)],        // Dolph-Chebyshev target (power)
    built: [Math.sqrt(0.2344), Math.sqrt(0.4036), Math.sqrt(0.2333)]        // -6.30 / -3.94 / -6.32 dB as simulated
  };
  var STOPS = [[0, 27, 43, 214], [0.2, 26, 143, 224], [0.38, 25, 200, 192], [0.55, 47, 209, 107], [0.72, 233, 226, 58], [0.86, 240, 138, 43], [1, 229, 52, 43]];

  function cmap(u) {
    u = Math.min(1, Math.max(0, u));
    var k = 0;
    while (k < STOPS.length - 2 && u > STOPS[k + 1][0]) k++;
    var a = STOPS[k], b = STOPS[k + 1], t = (u - a[0]) / (b[0] - a[0]);
    return "rgb(" + Math.round(a[1] + (b[1] - a[1]) * t) + "," + Math.round(a[2] + (b[2] - a[2]) * t) + "," + Math.round(a[3] + (b[3] - a[3]) * t) + ")";
  }

  // power pattern over psi = -90..90 deg (from broadside), 0.25 deg steps
  function pattern(steerDeg, w, element) {
    var alpha = -KD * Math.sin(steerDeg * Math.PI / 180), n = 721, p = new Float64Array(n), norm = 0;
    for (var m = 0; m < w.length; m++) norm += w[m] * w[m];
    for (var i = 0; i < n; i++) {
      var psi = (-90 + i * 0.25) * Math.PI / 180, re = 0, im = 0, ph = KD * Math.sin(psi) + alpha;
      for (var e = 0; e < w.length; e++) { re += w[e] * Math.cos(e * ph); im += w[e] * Math.sin(e * ph); }
      var v = (re * re + im * im) / norm;                 // equal total input power for every taper
      if (element) v *= Math.cos(psi) * Math.cos(psi);
      p[i] = v;
    }
    return { p: p, alpha: alpha * 180 / Math.PI };
  }

  function analyse(p) {
    var n = p.length, imax = 0, i;
    for (i = 1; i < n; i++) if (p[i] > p[imax]) imax = i;
    var peak = p[imax], lo = imax, hi = imax;
    while (lo > 0 && p[lo] > peak / 2) lo--;
    while (hi < n - 1 && p[hi] > peak / 2) hi++;
    // walk down both sides of the main lobe to its nulls, then take the highest remaining level
    var l = imax, r = imax;
    while (l > 0 && p[l - 1] < p[l]) l--;
    while (r < n - 1 && p[r + 1] < p[r]) r++;
    var side = 0;
    for (i = 0; i < n; i++) if ((i < l || i > r) && p[i] > side) side = p[i];
    return {
      beam: -90 + imax * 0.25, peak: peak, hpbw: (hi - lo) * 0.25, edge: lo === 0 || hi === n - 1,
      sll: side > 0 ? 10 * Math.log10(side / peak) : -Infinity
    };
  }

  function draw(canvas, st) {
    var dpr = Math.min(window.devicePixelRatio || 1, 2), w = canvas.clientWidth, h = canvas.clientHeight;
    if (!w || !h) return null;
    if (canvas.width !== Math.round(w * dpr)) { canvas.width = Math.round(w * dpr); canvas.height = Math.round(h * dpr); }
    var ctx = canvas.getContext("2d");
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, w, h);
    var pad = 26, cx = w / 2, cy = h - 30, R = Math.min(w / 2 - pad, cy - 18);
    var mono = "10px 'JetBrains Mono', ui-monospace, Consolas, monospace";

    function pt(psiDeg, r) { var a = psiDeg * Math.PI / 180; return [cx + r * Math.sin(a), cy - r * Math.cos(a)]; }

    // graticule
    ctx.lineWidth = 1; ctx.font = mono; ctx.textBaseline = "middle";
    for (var g = 0; g <= 3; g++) {
      var rr = R * (1 - g / 3);
      ctx.beginPath(); ctx.arc(cx, cy, rr, Math.PI, 2 * Math.PI);
      ctx.strokeStyle = g === 0 ? "rgba(230,160,100,0.55)" : "rgba(142,171,156,0.20)"; ctx.stroke();
      if (g > 0 && g < 3) { ctx.fillStyle = "rgba(142,171,156,0.8)"; ctx.textAlign = "left"; ctx.fillText((-10 * g) + " dB", cx + 4, cy - rr + 8); }
    }
    for (var a = -90; a <= 90; a += 30) {
      var e1 = pt(a, R), e2 = pt(a, R + 12);
      ctx.beginPath(); ctx.moveTo(cx, cy); ctx.lineTo(e1[0], e1[1]); ctx.strokeStyle = "rgba(142,171,156,0.16)"; ctx.stroke();
      ctx.fillStyle = "rgba(142,171,156,0.9)"; ctx.textAlign = a < 0 ? "right" : a > 0 ? "left" : "center";
      ctx.fillText((a > 0 ? "+" : "") + a + "°", e2[0], e2[1] - (a === 0 ? 2 : 0));
    }

    var pat = pattern(st.steer, st.w, st.element), info = analyse(pat.p), n = pat.p.length, i;
    function radius(v) { var d = 10 * Math.log10(Math.max(v / info.peak, 1e-9)); return R * Math.max(0, (d - DB_MIN) / -DB_MIN); }

    // reference trace (uniform taper) when another taper is selected
    if (st.ghost) {
      var gp = pattern(st.steer, st.ghost, st.element), gi = analyse(gp.p);
      ctx.beginPath();
      for (i = 0; i < n; i++) {
        var gd = 10 * Math.log10(Math.max(gp.p[i] / gi.peak, 1e-9)), q = pt(-90 + i * 0.25, R * Math.max(0, (gd - DB_MIN) / -DB_MIN));
        if (i) ctx.lineTo(q[0], q[1]); else ctx.moveTo(q[0], q[1]);
      }
      ctx.setLineDash([4, 4]); ctx.strokeStyle = "rgba(227,239,232,0.45)"; ctx.lineWidth = 1.2; ctx.stroke(); ctx.setLineDash([]);
    }

    // filled pattern
    ctx.beginPath(); ctx.moveTo(cx, cy);
    for (i = 0; i < n; i++) { var f = pt(-90 + i * 0.25, radius(pat.p[i])); ctx.lineTo(f[0], f[1]); }
    ctx.closePath();
    var fill = ctx.createRadialGradient(cx, cy, 0, cx, cy, R);
    fill.addColorStop(0, "rgba(27,43,214,0.10)"); fill.addColorStop(0.6, "rgba(47,209,107,0.16)"); fill.addColorStop(1, "rgba(229,52,43,0.30)");
    ctx.fillStyle = fill; ctx.fill();

    // outline coloured by level, like a field plot
    ctx.lineWidth = 2.4; ctx.lineCap = "round";
    for (i = 1; i < n; i++) {
      var p0 = pt(-90 + (i - 1) * 0.25, radius(pat.p[i - 1])), p1 = pt(-90 + i * 0.25, radius(pat.p[i]));
      var lvl = 10 * Math.log10(Math.max(pat.p[i] / info.peak, 1e-9));
      ctx.beginPath(); ctx.moveTo(p0[0], p0[1]); ctx.lineTo(p1[0], p1[1]);
      ctx.strokeStyle = cmap((lvl - DB_MIN) / -DB_MIN); ctx.stroke();
    }

    // steering target and found main beam
    var t1 = pt(st.steer, R + 2);
    ctx.setLineDash([5, 5]); ctx.strokeStyle = "rgba(61,220,151,0.9)"; ctx.lineWidth = 1.2;
    ctx.beginPath(); ctx.moveTo(cx, cy); ctx.lineTo(t1[0], t1[1]); ctx.stroke(); ctx.setLineDash([]);
    var b1 = pt(info.beam, R);
    ctx.beginPath(); ctx.arc(b1[0], b1[1], 4, 0, 2 * Math.PI); ctx.fillStyle = "#fff3e2"; ctx.fill();

    // the three elements on the board
    ctx.fillStyle = "#e6a064";
    for (var e = -1; e <= 1; e++) ctx.fillRect(cx + e * 30 - 9, cy + 6, 18, 9);
    ctx.fillStyle = "rgba(142,171,156,0.9)"; ctx.textAlign = "center"; ctx.fillText("d = λ₀/2", cx, cy + 23);
    ctx.textAlign = "left"; ctx.fillText("array axis →", 6, cy + 11);

    return { alpha: pat.alpha, info: info };
  }

  function wrap180(a) { a = ((a + 180) % 360 + 360) % 360 - 180; return a; }

  // ----- hero: steer from broadside to the design angle once -----
  function hero(canvas) {
    var reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches, t0 = null;
    var st = { steer: reduce ? 60 : 0, w: TAPERS.uniform, element: true, ghost: null };
    function frame(ts) {
      if (t0 === null) t0 = ts;
      var u = Math.min(1, (ts - t0 - 500) / 2400);
      u = u < 0 ? 0 : 1 - Math.pow(1 - u, 3);
      st.steer = 60 * u; draw(canvas, st);
      if (u < 1) requestAnimationFrame(frame);
    }
    draw(canvas, st);
    if (!reduce) requestAnimationFrame(frame);
    window.addEventListener("resize", function () { draw(canvas, st); });
  }

  // ----- lab: interactive -----
  function lab(root) {
    var canvas = root.querySelector("canvas"), range = root.querySelector("#xb-steer"), chk = root.querySelector("#xb-element");
    var st = { steer: 60, w: TAPERS.uniform, element: true, ghost: null };
    function out(id, txt) { var n = root.querySelector(id); if (n) n.textContent = txt; }
    function update() {
      st.steer = parseFloat(range.value); st.element = chk.checked;
      var r = draw(canvas, st);
      if (!r) return;
      var al = wrap180(r.alpha), dl = (((-r.alpha % 360) + 360) % 360) / 360 * LAMBDA_G;
      out("#xb-steer-out", (st.steer > 0 ? "+" : "") + st.steer.toFixed(0) + "°");
      out("#xb-axis", (90 - st.steer).toFixed(0) + "°");
      out("#xb-alpha", (r.alpha).toFixed(1) + "°" + (Math.abs(al - r.alpha) > 0.05 ? " (≡ " + al.toFixed(1) + "°)" : ""));
      out("#xb-dl", dl.toFixed(2) + " mm");
      out("#xb-beam", (r.info.beam > 0 ? "+" : "") + r.info.beam.toFixed(1) + "°");
      out("#xb-sll", isFinite(r.info.sll) ? r.info.sll.toFixed(1) + " dB" : "—");
      out("#xb-hpbw", r.info.edge ? "—" : r.info.hpbw.toFixed(0) + "°");
      var ref = analyse(pattern(st.steer, TAPERS.uniform, st.element).p);
      out("#xb-rel", (10 * Math.log10(r.info.peak / ref.peak)).toFixed(2) + " dB");
    }
    range.addEventListener("input", update);
    chk.addEventListener("change", update);
    root.querySelectorAll("[data-taper]").forEach(function (b) {
      b.addEventListener("click", function () {
        root.querySelectorAll("[data-taper]").forEach(function (x) { x.setAttribute("aria-pressed", String(x === b)); });
        st.w = TAPERS[b.dataset.taper]; st.ghost = b.dataset.taper === "uniform" ? null : TAPERS.uniform;
        update();
      });
    });
    var reset = root.querySelector("#xb-reset");
    if (reset) reset.addEventListener("click", function () { range.value = 60; update(); });
    window.addEventListener("resize", update);
    update();
  }

  function init() {
    var h = document.querySelector("canvas[data-xb-hero]"); if (h) hero(h);
    var l = document.querySelector("[data-xb-lab]"); if (l) lab(l);
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init); else init();
})();
