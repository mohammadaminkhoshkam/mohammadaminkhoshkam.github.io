// SDR "scope" background: an animated spectrum trace with peak hold and a waterfall,
// drawn on <canvas data-scope data-fc="434" data-span="8.192">.
// The scene is synthetic but borrows from Lab 2: two tones at +300 / +400 kHz with their
// third-order products, transmitted in bursts (about 2/3 duty) as our Pluto did.
(function () {
  "use strict";

  // Waterfall colour map (dark blue -> cyan -> green -> yellow -> red)
  var STOPS = [
    [0.00, 4, 8, 20], [0.20, 10, 30, 92], [0.40, 0, 128, 186], [0.58, 34, 214, 160],
    [0.76, 246, 220, 78], [0.90, 255, 128, 44], [1.00, 255, 70, 70]
  ];
  var LUT = new Uint8Array(256 * 3);
  for (var i = 0; i < 256; i++) {
    var u = i / 255, k = 0;
    while (k < STOPS.length - 2 && u > STOPS[k + 1][0]) k++;
    var a = STOPS[k], b = STOPS[k + 1], t = (u - a[0]) / (b[0] - a[0]);
    for (var c = 0; c < 3; c++) LUT[i * 3 + c] = Math.round(a[c + 1] + (b[c + 1] - a[c + 1]) * Math.min(1, Math.max(0, t)));
  }

  var DB_TOP = -5, DB_BOT = -95;

  function start(canvas) {
    var ctx = canvas.getContext("2d");
    var fc = parseFloat(canvas.dataset.fc || "434");
    var span = parseFloat(canvas.dataset.span || "8.192");
    var reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    var host = canvas.parentElement;
    var w = 0, h = 0, dpr = 1, bins = 0, visible = true;
    var smooth, hold, wf, wfCtx, rowImg, cursor = null, last = 0, tick = 0;
    var ROWS = 150;

    // offsets in MHz, widths in MHz, powers in dBFS
    var scene = [
      { f: 0.30, w: 0.010, p: -16, gate: true },
      { f: 0.40, w: 0.010, p: -16, gate: true },
      { f: 0.20, w: 0.010, p: -58, gate: true },
      { f: 0.50, w: 0.010, p: -58, gate: true },
      { f: -1.85, w: 0.075, p: -38, wander: 0.11 },
      { f: 2.75, w: 0.95, p: -56, flat: true, burst: 0.55 },
      { f: -3.20, w: 0.012, p: -47 },
      { f: 0.0, w: 0.006, p: -62 }
    ];
    var gateOn = true, gateLeft = 0, burstOn = true, burstLeft = 0;

    function resize() {
      dpr = Math.min(window.devicePixelRatio || 1, 2);
      w = canvas.clientWidth; h = canvas.clientHeight;
      if (!w || !h) return;
      canvas.width = Math.round(w * dpr); canvas.height = Math.round(h * dpr);
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      bins = Math.max(160, Math.min(720, Math.round(w / 2)));
      smooth = new Float32Array(bins).fill(-88);
      hold = new Float32Array(bins).fill(-95);
      wf = document.createElement("canvas");
      wf.width = bins; wf.height = ROWS;
      wfCtx = wf.getContext("2d");
      wfCtx.fillStyle = "#04060e"; wfCtx.fillRect(0, 0, bins, ROWS);
      rowImg = wfCtx.createImageData(bins, 1);
      for (var r = 0; r < ROWS; r++) step(true);
      draw();
    }

    function gauss() { return (Math.random() + Math.random() + Math.random() + Math.random() - 2) * 1.2; }

    // one new spectrum row
    function step(silent) {
      tick++;
      if (--gateLeft <= 0) { gateOn = Math.random() < 0.665; gateLeft = gateOn ? 2 + Math.random() * 7 : 1 + Math.random() * 4; }
      if (--burstLeft <= 0) { burstOn = Math.random() < 0.55; burstLeft = 4 + Math.random() * 16; }
      var data = rowImg.data;
      for (var i = 0; i < bins; i++) {
        var f = (i / (bins - 1) - 0.5) * span;
        // receiver noise floor with a gentle band shape and chi-square texture
        var edge = Math.abs(f) / (span / 2);
        var lin = Math.pow(10, (-84 - 5 * edge * edge * edge) / 10) * (0.35 + 0.65 * (-Math.log(1 - Math.random() * 0.999)));
        for (var s = 0; s < scene.length; s++) {
          var sg = scene[s];
          if (sg.gate && !gateOn) continue;
          if (sg.burst && !burstOn) continue;
          var f0 = sg.f + (sg.wander ? sg.wander * Math.sin(tick * 0.045 + 1.7 * Math.sin(tick * 0.011)) : 0);
          var d = (f - f0) / sg.w, g;
          if (sg.flat) { g = Math.abs(d) < 0.5 ? (0.55 + 0.45 * (-Math.log(1 - Math.random() * 0.999))) : Math.exp(-(Math.abs(d) - 0.5) * 22); }
          else { g = 1 / (1 + d * d * 4) + 0.00000012 / (0.0001 + (f - f0) * (f - f0)); }
          lin += Math.pow(10, sg.p / 10) * g;
        }
        var dbv = 10 * Math.log10(lin) + gauss() * 0.4;
        smooth[i] += (dbv - smooth[i]) * 0.42;
        hold[i] = Math.max(hold[i] - 0.10, smooth[i]);
        var q = Math.round(Math.min(1, Math.max(0, (dbv - DB_BOT - 4) / (DB_TOP - DB_BOT - 12))) * 255);
        data[i * 4] = LUT[q * 3]; data[i * 4 + 1] = LUT[q * 3 + 1]; data[i * 4 + 2] = LUT[q * 3 + 2]; data[i * 4 + 3] = 255;
      }
      wfCtx.drawImage(wf, 0, 1);
      wfCtx.putImageData(rowImg, 0, 0);
      if (!silent) draw();
    }

    function yOf(dbv, top, height) { return top + (DB_TOP - dbv) / (DB_TOP - DB_BOT) * height; }

    function draw() {
      if (!w) return;
      var ruler = 22;
      var specH = Math.round((h - ruler) * 0.56), wfTop = specH, wfH = h - ruler - specH;
      ctx.fillStyle = "#050a12"; ctx.fillRect(0, 0, w, h);

      // graticule
      ctx.lineWidth = 1; ctx.strokeStyle = "rgba(120,220,255,0.085)";
      ctx.beginPath();
      for (var gx = 0; gx <= 10; gx++) { var x = Math.round(gx / 10 * w) + 0.5; ctx.moveTo(x, 0); ctx.lineTo(x, specH); }
      for (var gy = 0; gy <= 6; gy++) { var y = Math.round(gy / 6 * specH) + 0.5; ctx.moveTo(0, y); ctx.lineTo(w, y); }
      ctx.stroke();

      // waterfall
      ctx.imageSmoothingEnabled = true;
      ctx.drawImage(wf, 0, 0, bins, ROWS, 0, wfTop, w, wfH);
      var fade = ctx.createLinearGradient(0, wfTop, 0, wfTop + wfH);
      fade.addColorStop(0, "rgba(5,10,18,0)"); fade.addColorStop(1, "rgba(5,10,18,0.55)");
      ctx.fillStyle = fade; ctx.fillRect(0, wfTop, w, wfH);

      // peak hold
      ctx.beginPath();
      for (var i = 0; i < bins; i++) { var px = i / (bins - 1) * w, py = yOf(hold[i], 0, specH); if (i) ctx.lineTo(px, py); else ctx.moveTo(px, py); }
      ctx.strokeStyle = "rgba(255,196,87,0.42)"; ctx.lineWidth = 1; ctx.stroke();

      // live trace with glow and fill
      ctx.beginPath();
      for (var j = 0; j < bins; j++) { var qx = j / (bins - 1) * w, qy = yOf(smooth[j], 0, specH); if (j) ctx.lineTo(qx, qy); else ctx.moveTo(qx, qy); }
      ctx.strokeStyle = "#5ee6ff"; ctx.lineWidth = 1.4; ctx.shadowColor = "rgba(94,230,255,0.75)"; ctx.shadowBlur = 8; ctx.stroke(); ctx.shadowBlur = 0;
      ctx.lineTo(w, specH); ctx.lineTo(0, specH); ctx.closePath();
      var fill = ctx.createLinearGradient(0, 0, 0, specH);
      fill.addColorStop(0, "rgba(94,230,255,0.22)"); fill.addColorStop(1, "rgba(94,230,255,0.02)");
      ctx.fillStyle = fill; ctx.fill();

      // dB labels (right) and frequency ruler (bottom)
      ctx.font = "10px 'JetBrains Mono', ui-monospace, Consolas, monospace";
      ctx.fillStyle = "rgba(127,151,170,0.9)"; ctx.textAlign = "right"; ctx.textBaseline = "middle";
      for (var k = 1; k < 6; k++) ctx.fillText(Math.round(DB_TOP - k * (DB_TOP - DB_BOT) / 6) + " dBFS", w - 6, k / 6 * specH - 7);
      ctx.fillStyle = "#070d17"; ctx.fillRect(0, h - ruler, w, ruler);
      ctx.strokeStyle = "rgba(120,220,255,0.25)"; ctx.beginPath(); ctx.moveTo(0, h - ruler + 0.5); ctx.lineTo(w, h - ruler + 0.5); ctx.stroke();
      ctx.fillStyle = "rgba(160,190,208,0.95)"; ctx.textBaseline = "middle";
      var nt = w < 560 ? 4 : 8;
      for (var m = 0; m <= nt; m++) {
        var fx = m / nt * w, fv = fc + (m / nt - 0.5) * span;
        ctx.textAlign = m === 0 ? "left" : m === nt ? "right" : "center";
        ctx.fillText(fv.toFixed(span < 20 ? 2 : 0) + (m === nt ? " MHz" : ""), Math.min(w - 4, Math.max(4, fx)), h - ruler / 2);
        ctx.beginPath(); ctx.moveTo(Math.round(fx) + 0.5, h - ruler); ctx.lineTo(Math.round(fx) + 0.5, h - ruler + 4); ctx.stroke();
      }

      // tuning cursor
      if (cursor !== null) {
        var cx = cursor * w, bi = Math.min(bins - 1, Math.max(0, Math.round(cursor * (bins - 1))));
        ctx.strokeStyle = "rgba(70,240,176,0.8)"; ctx.setLineDash([4, 4]);
        ctx.beginPath(); ctx.moveTo(cx + 0.5, 0); ctx.lineTo(cx + 0.5, h - ruler); ctx.stroke(); ctx.setLineDash([]);
        var label = (fc + (cursor - 0.5) * span).toFixed(3) + " MHz  " + smooth[bi].toFixed(1) + " dBFS";
        var tw = ctx.measureText(label).width + 12, lx = Math.min(w - tw - 4, Math.max(4, cx + 8));
        ctx.fillStyle = "rgba(4,12,10,0.88)"; ctx.fillRect(lx, 8, tw, 18);
        ctx.strokeStyle = "rgba(70,240,176,0.6)"; ctx.strokeRect(lx + 0.5, 8.5, tw - 1, 17);
        ctx.fillStyle = "#46f0b0"; ctx.textAlign = "left"; ctx.fillText(label, lx + 6, 17.5);
      }
    }

    function loop(ts) {
      if (visible && !document.hidden && ts - last > 55) { last = ts; step(false); }
      requestAnimationFrame(loop);
    }

    host.addEventListener("pointermove", function (e) {
      var r = canvas.getBoundingClientRect();
      cursor = Math.min(1, Math.max(0, (e.clientX - r.left) / r.width));
      if (reduce) draw();
    });
    host.addEventListener("pointerleave", function () { cursor = null; if (reduce) draw(); });

    resize();
    var rt;
    window.addEventListener("resize", function () { clearTimeout(rt); rt = setTimeout(resize, 120); });
    if ("IntersectionObserver" in window) {
      new IntersectionObserver(function (e) { visible = e[0].isIntersecting; }).observe(canvas);
    }
    if (!reduce) requestAnimationFrame(loop);
  }

  function init() { document.querySelectorAll("canvas[data-scope]").forEach(start); }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init); else init();
})();
