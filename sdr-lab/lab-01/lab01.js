/*
 * lab01.js - renders the Lab 01 report page from results.json (computed by lab01-analysis.js in Node)
 * and can recompute everything in the browser from the raw I/Q excerpts in data/.
 */
(function () {
  'use strict';
  var D = window.SDRDSP, L = window.Lab01;
  var R = null, M = null, PRE = null;

  // ================================================================ formatting
  function $(s, el) { return (el || document).querySelector(s); }
  function $$(s, el) { return Array.prototype.slice.call((el || document).querySelectorAll(s)); }
  function mhz(hz, d) { return (hz / 1e6).toFixed(d == null ? 3 : d); }
  function khz(hz, d) { return (hz / 1e3).toFixed(d == null ? 1 : d); }
  function fx(v, d) { return v == null || isNaN(v) ? '–' : Number(v).toFixed(d == null ? 1 : d); }
  function sgn(v, d) { return (v >= 0 ? '+' : '−') + Math.abs(v).toFixed(d == null ? 1 : d); }
  function esc(s) { return String(s).replace(/[&<>"]/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]; }); }
  function css(n) { return getComputedStyle(document.documentElement).getPropertyValue(n).trim(); }
  function setText(key, v) { $$('[data-k="' + key + '"]').forEach(function (e) { e.textContent = v; }); }

  // ================================================================ plotting (canvas)
  function niceStep(span, n) {
    var raw = span / Math.max(1, n), p = Math.pow(10, Math.floor(Math.log10(raw))), m = raw / p;
    return (m < 1.5 ? 1 : m < 3 ? 2 : m < 7 ? 5 : 10) * p;
  }
  function ticks(a, b, n) { var s = niceStep(b - a, n), t = [], v = Math.ceil(a / s) * s; for (; v <= b + s * 1e-9; v += s) t.push(+v.toFixed(10)); return { t: t, s: s }; }
  function decimals(step) { return Math.max(0, -Math.floor(Math.log10(step) + 1e-9)); }

  var plots = [];
  function prep(cv, height) {
    var dpr = Math.min(window.devicePixelRatio || 1, 2), w = cv.clientWidth || cv.parentNode.clientWidth;
    cv.width = Math.round(w * dpr); cv.height = Math.round(height * dpr); cv.style.height = height + 'px';
    var ctx = cv.getContext('2d'); ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    return { ctx: ctx, w: w, h: height };
  }
  function frame(ctx, box, cfg) {
    var C = { text: css('--text'), dim: css('--text-dim'), grid: css('--border') };
    ctx.font = '11px ' + css('--font');
    var xt = ticks(cfg.xmin, cfg.xmax, Math.max(3, Math.floor(box.w / 90))), yt = ticks(cfg.ymin, cfg.ymax, Math.max(3, Math.floor(box.h / 45)));
    var X = function (v) { return box.x + (v - cfg.xmin) / (cfg.xmax - cfg.xmin) * box.w; };
    var Y = function (v) { return box.y + box.h - (v - cfg.ymin) / (cfg.ymax - cfg.ymin) * box.h; };
    ctx.strokeStyle = C.grid; ctx.lineWidth = 1; ctx.fillStyle = C.dim;
    ctx.textAlign = 'center'; ctx.textBaseline = 'top';
    var xd = cfg.xdec != null ? cfg.xdec : decimals(xt.s);
    xt.t.forEach(function (v) { var px = Math.round(X(v)) + 0.5; ctx.beginPath(); ctx.moveTo(px, box.y); ctx.lineTo(px, box.y + box.h); ctx.stroke(); ctx.fillText(v.toFixed(xd), px, box.y + box.h + 4); });
    ctx.textAlign = 'right'; ctx.textBaseline = 'middle';
    var yd = decimals(yt.s);
    yt.t.forEach(function (v) { var py = Math.round(Y(v)) + 0.5; ctx.beginPath(); ctx.moveTo(box.x, py); ctx.lineTo(box.x + box.w, py); ctx.stroke(); ctx.fillText(v.toFixed(yd), box.x - 5, py); });
    ctx.fillStyle = C.text; ctx.textAlign = 'center'; ctx.textBaseline = 'bottom';
    if (cfg.xlabel) ctx.fillText(cfg.xlabel, box.x + box.w / 2, box.y + box.h + 32);
    if (cfg.ylabel) { ctx.save(); ctx.translate(12, box.y + box.h / 2); ctx.rotate(-Math.PI / 2); ctx.textBaseline = 'top'; ctx.fillText(cfg.ylabel, 0, -2); ctx.restore(); }
    if (cfg.title) { ctx.textAlign = 'left'; ctx.textBaseline = 'top'; ctx.font = '600 12px ' + css('--font'); ctx.fillText(cfg.title, box.x, 4); }
    return { X: X, Y: Y };
  }

  function color(c) { return c && c.indexOf('--') === 0 ? css(c) : c; }

  function linePlot(cv, cfg) {
    var g = prep(cv, cfg.height || 300), ctx = g.ctx;
    var box = { x: 58, y: cfg.title ? 24 : 10, w: g.w - 72, h: (cfg.height || 300) - (cfg.title ? 24 : 10) - 42 };
    var T = frame(ctx, box, cfg);
    ctx.save(); ctx.beginPath(); ctx.rect(box.x, box.y, box.w, box.h); ctx.clip();
    (cfg.spans || []).forEach(function (s) { ctx.fillStyle = color(s.fill); var a = T.X(s.a), b = T.X(s.b); ctx.fillRect(Math.min(a, b), box.y, Math.abs(b - a), box.h); });
    (cfg.series || []).forEach(function (s) {
      ctx.strokeStyle = color(s.color); ctx.lineWidth = s.width || 1.2; ctx.setLineDash(s.dash || []); ctx.globalAlpha = s.alpha || 1;
      ctx.beginPath();
      var n = s.y.length, step = Math.max(1, Math.floor(n / (box.w * 2)));
      for (var i = 0; i < n; i += step) {
        var xv = s.xs ? s.xs[i] : s.x0 + i * s.dx, yv = s.y[i];
        if (step > 1) { for (var j = i + 1; j < Math.min(i + step, n); j++) if (s.y[j] > yv) yv = s.y[j]; }
        var px = T.X(xv), py = T.Y(yv);
        if (i === 0) ctx.moveTo(px, py); else ctx.lineTo(px, py);
      }
      ctx.stroke(); ctx.globalAlpha = 1; ctx.setLineDash([]);
    });
    (cfg.hlines || []).forEach(function (l) { ctx.strokeStyle = color(l.color); ctx.setLineDash(l.dash || [4, 3]); ctx.lineWidth = 1; var py = T.Y(l.y); ctx.beginPath(); ctx.moveTo(box.x, py); ctx.lineTo(box.x + box.w, py); ctx.stroke(); ctx.setLineDash([]); });
    (cfg.vlines || []).forEach(function (l) {
      ctx.strokeStyle = color(l.color); ctx.setLineDash(l.dash || [4, 3]); ctx.lineWidth = l.width || 1; var px = T.X(l.x);
      ctx.beginPath(); ctx.moveTo(px, box.y); ctx.lineTo(px, box.y + box.h); ctx.stroke(); ctx.setLineDash([]);
    });
    (cfg.points || []).forEach(function (p) { ctx.fillStyle = color(p.color); ctx.beginPath(); ctx.arc(T.X(p.x), T.Y(p.y), p.r || 4, 0, 2 * Math.PI); ctx.fill(); });
    (cfg.lines || []).forEach(function (l) { ctx.strokeStyle = color(l.color); ctx.lineWidth = l.width || 1.5; ctx.setLineDash(l.dash || []); ctx.beginPath(); ctx.moveTo(T.X(l.x1), T.Y(l.y1)); ctx.lineTo(T.X(l.x2), T.Y(l.y2)); ctx.stroke(); ctx.setLineDash([]); });
    ctx.fillStyle = css('--text'); ctx.font = '10.5px ' + css('--font'); ctx.textAlign = 'center'; ctx.textBaseline = 'bottom';
    (cfg.notes || []).forEach(function (a) { ctx.fillStyle = color(a.color || '--text'); ctx.fillText(a.text, T.X(a.x), T.Y(a.y) - 4); });
    ctx.restore();
    if (cfg.legend) {
      var lx = box.x + box.w - 8, ly = box.y + 8; ctx.font = '11px ' + css('--font'); ctx.textAlign = 'right'; ctx.textBaseline = 'middle';
      cfg.legend.forEach(function (it) { ctx.fillStyle = css('--text'); ctx.fillText(it.text, lx - 22, ly); ctx.strokeStyle = color(it.color); ctx.lineWidth = 2; ctx.setLineDash(it.dash || []); ctx.beginPath(); ctx.moveTo(lx - 18, ly); ctx.lineTo(lx, ly); ctx.stroke(); ctx.setLineDash([]); ly += 16; });
    }
    cv._plot = { cfg: cfg, box: box, T: T };
  }

  // viridis colormap (polynomial fit, Mattias Sundstrom / matplotlib)
  function viridis(t) {
    var c0 = [0.2777, 0.0054, 0.334], c1 = [0.105, 1.4046, 1.3846], c2 = [-0.3309, 0.2148, 0.095], c3 = [-4.6342, -5.7991, -19.3324],
      c4 = [6.2283, 14.1799, 56.6905], c5 = [4.7764, -13.7451, -65.353], c6 = [-5.4355, 4.6459, 26.3124];
    return [0, 1, 2].map(function (i) { return Math.max(0, Math.min(255, Math.round(255 * (c0[i] + t * (c1[i] + t * (c2[i] + t * (c3[i] + t * (c4[i] + t * (c5[i] + t * c6[i]))))))))); });
  }
  var LUT = []; for (var li = 0; li < 256; li++) LUT.push(viridis(li / 255));

  function b64bytes(b64) { var s = atob(b64), u = new Uint8Array(s.length); for (var i = 0; i < s.length; i++) u[i] = s.charCodeAt(i); return u; }

  function waterfallPlot(cv, cfg) {
    var H = cfg.height || 220, g = prep(cv, H), ctx = g.ctx, wf = cfg.wf;
    var box = { x: 58, y: 10, w: g.w - 72, h: H - 52 };
    var tmax = wf.rows * wf.rowSeconds * 1e3;
    frame(ctx, box, { xmin: cfg.xmin, xmax: cfg.xmax, ymin: 0, ymax: tmax, xlabel: cfg.xlabel || 'Frequency (MHz)', ylabel: 'Time (ms)', xdec: cfg.xdec });
    var bytes = cfg._bytes || (cfg._bytes = b64bytes(wf.b64)), img = new ImageData(wf.cols, wf.rows);
    for (var i = 0; i < bytes.length; i++) { var c = LUT[bytes[i]]; img.data[4 * i] = c[0]; img.data[4 * i + 1] = c[1]; img.data[4 * i + 2] = c[2]; img.data[4 * i + 3] = 255; }
    var off = document.createElement('canvas'); off.width = wf.cols; off.height = wf.rows; off.getContext('2d').putImageData(img, 0, 0);
    ctx.imageSmoothingEnabled = false;
    // row 0 = first frames = time 0 at the bottom (time axis grows upwards, as in GNU Radio)
    ctx.save(); ctx.translate(box.x, box.y + box.h); ctx.scale(1, -1); ctx.drawImage(off, 0, 0, box.w, box.h); ctx.restore();
    ctx.fillStyle = css('--text-dim'); ctx.font = '10.5px ' + css('--font'); ctx.textAlign = 'right'; ctx.textBaseline = 'top';
    ctx.fillText('colour: ' + wf.min.toFixed(0) + ' … ' + wf.max.toFixed(0) + ' dBFS/Hz', box.x + box.w, box.y + box.h + 22);
    cv._plot = { cfg: cfg, wf: true };
  }

  function draw(cv, kind, cfg) { (kind === 'wf' ? waterfallPlot : linePlot)(cv, cfg); if (plots.indexOf(cv) < 0) plots.push(cv); cv._kind = kind; }
  function redrawAll() { plots.forEach(function (cv) { if (cv.isConnected && cv._plot) draw(cv, cv._kind, cv._plot.cfg); }); }
  var rt; window.addEventListener('resize', function () { clearTimeout(rt); rt = setTimeout(redrawAll, 120); });
  new MutationObserver(redrawAll).observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });
  if (window.matchMedia) window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', redrawAll);

  // hover readout on line plots
  document.addEventListener('mousemove', function (e) {
    var cv = e.target; if (!(cv instanceof HTMLCanvasElement) || !cv._plot || cv._plot.wf) return;
    var p = cv._plot, r = cv.getBoundingClientRect(), x = e.clientX - r.left, tip = cv.parentNode.querySelector('.tip');
    if (!tip || x < p.box.x || x > p.box.x + p.box.w) { if (tip) tip.hidden = true; return; }
    var xv = p.cfg.xmin + (x - p.box.x) / p.box.w * (p.cfg.xmax - p.cfg.xmin), s = p.cfg.series[0];
    var i = s.xs ? s.xs.reduce(function (b, v, k) { return Math.abs(v - xv) < Math.abs(s.xs[b] - xv) ? k : b; }, 0) : Math.round((xv - s.x0) / s.dx);
    if (i < 0 || i >= s.y.length) { tip.hidden = true; return; }
    tip.hidden = false; tip.textContent = (p.cfg.tipX || function (v) { return v.toFixed(4); })(s.xs ? s.xs[i] : s.x0 + i * s.dx) + '   ' + s.y[i].toFixed(1) + ' ' + (p.cfg.tipUnit || 'dB');
    tip.style.left = Math.min(x + 12, r.width - 150) + 'px'; tip.style.top = (e.clientY - r.top - 28) + 'px';
  });
  document.addEventListener('mouseleave', function () { $$('.tip').forEach(function (t) { t.hidden = true; }); }, true);

  function canvas(host, cls) { var w = document.createElement('div'); w.className = 'plot ' + (cls || ''); w.innerHTML = '<canvas></canvas><div class="tip" hidden></div>'; host.appendChild(w); return w.firstChild; }

  // spectrum (Welch + Max Hold) + waterfall for one recording, from the overview results
  function spectrumBlock(host, id, opt) {
    opt = opt || {};
    var o = R.overview[id], rec = M.byId[id], fc = rec.fc, fs = rec.fs, n = o.psd.length;
    var x0 = (fc + o.f0) / 1e6, dx = o.df / 1e6, xmin = (fc - fs / 2) / 1e6, xmax = (fc + fs / 2) / 1e6;
    var ys = o.psd.concat(o.mh), ymax = Math.max.apply(null, ys) + 5, ymin = Math.min(o.floor - 12, Math.min.apply(null, o.psd) - 2);
    host.innerHTML = '';
    draw(canvas(host), 'line', {
      height: opt.height || 280, xmin: xmin, xmax: xmax, ymin: ymin, ymax: ymax, xlabel: 'Frequency (MHz)', ylabel: 'PSD (dBFS/Hz)',
      title: opt.title || rec.label,
      spans: [{ a: xmin, b: (fc - 0.4 * fs) / 1e6, fill: 'rgba(128,128,128,0.13)' }, { a: (fc + 0.4 * fs) / 1e6, b: xmax, fill: 'rgba(128,128,128,0.13)' }].concat(opt.spans || []),
      series: [{ x0: x0, dx: dx, y: o.psd, color: '--accent', width: 1.3 }, { x0: x0, dx: dx, y: o.mh, color: '--text-dim', width: 0.8, alpha: 0.7 }],
      hlines: [{ y: o.floor, color: '--text-dim' }], vlines: opt.vlines, notes: opt.notes,
      legend: [{ text: 'Welch average', color: '--accent' }, { text: 'Max Hold', color: '--text-dim' }, { text: 'noise floor', color: '--text-dim', dash: [4, 3] }],
      tipX: function (v) { return v.toFixed(4) + ' MHz'; }, tipUnit: 'dBFS/Hz'
    });
    if (!opt.noWaterfall) draw(canvas(host), 'wf', { wf: o.wf, xmin: xmin, xmax: xmax, height: opt.wfHeight || 200 });
  }

  // ================================================================ sections
  function renderInventory() {
    var rows = R.inventory.slice().sort(function (a, b) { return a.id < b.id ? -1 : 1; }).map(function (r) {
      return '<tr><td class="mono small">' + esc(r.file) + '</td><td>' + r.part + '</td><td class="num">' + mhz(r.fc, 3) + '</td><td class="num">' + fx(r.fs / 1e6, 1) +
        '</td><td class="num">' + fx(r.gain, 0) + '</td><td class="num">' + fx(r.durationTotal, 3) + '</td><td class="num">' + r.samplesTotal.toLocaleString('en-US') +
        '</td><td class="num">' + (r.bytesTotal / 1e6).toFixed(3) + ' MB ' + (r.sizeOk ? '<span class="ok">✓</span>' : '<span class="bad">✗</span>') +
        '</td><td class="num">' + fx(r.durationUsed, 2) + ' s</td></tr>';
    });
    $('#inv-body').innerHTML = rows.join('');
    var all = R.inventory.every(function (r) { return r.nameOk && r.sizeOk; });
    setText('inv-check', all ? 'All 11 file names follow teamID_labNN_fc_fs_gain_timestamp.cf32 and every file is exactly 8 bytes × N samples.' : 'Some files failed the name or size check.');
  }

  function renderPart1() {
    var id = '20261101T151432';
    var a = R.table7.filter(function (t) { return t.key.indexOf('wide') === 0; }), gs = R.table7.filter(function (t) { return t.key.indexOf('gsm') === 0; });
    spectrumBlock($('#p1-plot'), id, {
      title: '945 MHz, 20 MS/s, gain 20 dB — GSM900 downlink (band C)',
      notes: a.map(function (t) { return { x: (t.fc + t.obw.fc) / 1e6, y: t.shape.plateau + 4, text: wideClass(t.shape)[0] + ' ' + mhz(t.fc + t.obw.fc, 1) }; })
        .concat(gs.length ? [{ x: gs.reduce(function (s, t) { return s + (t.fc + t.obw.fc) / 1e6; }, 0) / gs.length, y: R.overview[id].floor + 24, text: 'GSM' }] : [])
    });
  }

  function renderLoopback() {
    var lb = R.loopback.slice().sort(function (a, b) { return (a.ftx - b.ftx) || (a.loShift - b.loShift); });
    $('#lb-body').innerHTML = lb.map(function (l) {
      return '<tr><td class="num">' + sgn(l.ftx / 1e3, 0) + ' kHz</td><td class="num">' + sgn(l.loShift / 1e3, 0) + ' kHz</td><td class="num">' + mhz(l.fc, 3) +
        '</td><td class="num">' + mhz(l.expected, 6) + '</td><td class="num">' + mhz(l.measured, 6) + '</td><td class="num">' + sgn(l.error, 2) + ' Hz</td><td class="num">' +
        fx(l.resolution, 0) + ' Hz</td></tr>';
    }).join('');
    var worst = Math.max.apply(null, lb.map(function (l) { return Math.abs(l.error); }));
    setText('lb-worst', worst.toFixed(2));
    var sel = $('#lb-select');
    if (!sel.options.length) lb.forEach(function (l, i) { var o = document.createElement('option'); o.value = l.id; o.textContent = 'f_tx = ' + sgn(l.ftx / 1e3, 0) + ' kHz, lo_shift = ' + sgn(l.loShift / 1e3, 0) + ' kHz'; sel.appendChild(o); });
    function show() {
      var l = R.loopback.filter(function (q) { return q.id === sel.value; })[0], x0 = (l.fc + l.f0) / 1e6, dx = l.df / 1e6;
      var host = $('#lb-plot'); host.innerHTML = '';
      draw(canvas(host), 'line', {
        height: 300, xmin: (l.fc - l.fs / 2) / 1e6, xmax: (l.fc + l.fs / 2) / 1e6, ymin: l.floor - 15, ymax: l.floor + 60, xdec: 2,
        xlabel: 'Frequency (MHz)', ylabel: 'PSD (dBFS/Hz)', title: 'Loopback — f_tune = ' + mhz(l.fc, 3) + ' MHz, TX LO = ' + mhz(l.fTx, 3) + ' MHz',
        spans: [{ a: (l.fc - l.fs / 2) / 1e6, b: (l.fc - 0.4 * l.fs) / 1e6, fill: 'rgba(128,128,128,0.13)' }, { a: (l.fc + 0.4 * l.fs) / 1e6, b: (l.fc + l.fs / 2) / 1e6, fill: 'rgba(128,128,128,0.13)' }],
        series: [{ x0: x0, dx: dx, y: l.psd, color: '--accent' }], hlines: [{ y: l.floor, color: '--text-dim' }],
        vlines: [{ x: l.fc / 1e6, color: '--warn', dash: [2, 3] }, { x: l.fTx / 1e6, color: '--accent-2', dash: [6, 3] }],
        legend: [{ text: 'Welch PSD (N = 1024)', color: '--accent' }, { text: 'RX LO (display centre)', color: '--warn', dash: [2, 3] }, { text: 'TX LO', color: '--accent-2', dash: [6, 3] }],
        tipX: function (v) { return v.toFixed(4) + ' MHz'; }, tipUnit: 'dBFS/Hz'
      });
      $('#lb-peaks').innerHTML = l.peaks.slice(0, 8).map(function (p) { return '<span class="tag">' + mhz(p.label, 4) + ' MHz · ' + fx(p.level, 0) + ' dB</span>'; }).join(' ');
    }
    sel.onchange = show; show();

    // LO test
    var runs = R.loTest.runs, tracks = R.loTest.tracks;
    var cls = function (t) {
      if (t.s === 0 && Math.abs(t.a - 434.25e6) < 5e3) return ['real input: the tone', 'real'];
      if (t.s === 0) return ['real input: TX LO leakage', 'real'];
      if (t.s === 1) return ['receiver: DC / LO leakage', 'rx'];
      if (t.s === 2) return ['receiver: I/Q image', 'rx'];
      return ['receiver: moves with LO', 'rx'];
    };
    $('#lo-head').innerHTML = '<th>Peak</th>' + runs.map(function (r) { return '<th class="num">lo_shift ' + sgn(r.lo / 1e3, 0) + ' kHz<br><span class="dim">f_tune ' + mhz(r.ftune, 1) + '</span></th>'; }).join('') + '<th class="num">slope s</th><th>class</th>';
    $('#lo-body').innerHTML = tracks.map(function (t, i) {
      var c = cls(t);
      return '<tr><td>' + (i + 1) + '</td>' + t.labels.map(function (z) { return '<td class="num">' + mhz(z.label, 4) + '<br><span class="dim">' + fx(z.level, 0) + ' dB</span></td>'; }).join('') +
        '<td class="num"><b>' + sgn(t.s, 0) + '</b></td><td><span class="cls ' + c[1] + '">' + c[0] + '</span></td></tr>';
    }).join('');
    var host = $('#lo-plot'); host.innerHTML = '';
    var pts = [], lines = [], cols = { 0: '--accent', 1: '--warn', '-4': '--accent-2', 4: '--accent-2' };
    tracks.forEach(function (t) {
      var c = cols[t.s] || '--text-dim';
      t.labels.forEach(function (z) { pts.push({ x: z.lo / 1e3, y: z.label / 1e6, color: c, r: 4 }); });
      lines.push({ x1: -120, y1: (t.a - 120e3 * t.s) / 1e6, x2: 220, y2: (t.a + 220e3 * t.s) / 1e6, color: c, width: 1.2, dash: [5, 3] });
    });
    draw(canvas(host), 'line', {
      height: 340, xmin: -120, xmax: 220, ymin: 433.3, ymax: 435.75, xlabel: 'lo_shift (kHz)', ylabel: 'Peak label (MHz)', title: 'LO test: label = a + s · lo_shift',
      series: [{ xs: [], y: [], color: 'transparent' }], points: pts, lines: lines,
      legend: [{ text: 's = 0 (real input)', color: '--accent' }, { text: 's = 1 (RX DC / LO)', color: '--warn' }, { text: 's = ±4 (moves with LO)', color: '--accent-2' }]
    });
  }

  function renderBands() {
    var sel = $('#band-select'), ids = ['20261101T151733', '20261101T151432', '20261101T143653', '20261101T143515', '20261101T144509', '20261101T144709'];
    if (!sel.options.length) ids.forEach(function (id) { var o = document.createElement('option'); o.value = id; o.textContent = M.byId[id].label; sel.appendChild(o); });
    function show() { spectrumBlock($('#band-plot'), sel.value, { height: 290 }); $('#band-note').innerHTML = BAND_NOTES[sel.value] || ''; }
    sel.onchange = show; show();
  }

  var BAND_NOTES = {
    '20261101T151733': 'No FM broadcast station rises clearly above the floor: the GSM/LTE antenna is not made for 88–108 MHz (the manual warns about this). The peaks at 88.008, 90.000 and 91.992 MHz are at −2, 0 and +2 MHz <i>baseband</i> and the pair at ±8.98 MHz appears in every 20 MS/s recording, whatever fc is — they move with the LO and are made inside the receiver.',
    '20261101T151432': 'Two flat 5 MHz blocks (≈ 944.2 and 949.1 MHz) and narrow carriers around 952–954 MHz. The blocks are analysed in Table 7 and question 8; the narrow carriers give the reference-error estimate. The peak at 953.98 MHz is the receiver’s +8.98 MHz baseband spur (it is in every 20 MS/s file) and lies in the untrusted edge.',
    '20261101T143653': 'Two equal lines at fc ± 1 MHz and the ±8.98 MHz pair. The same ±1 MHz pair is in the 2.6 MS/s recording at exactly fc ± 1.000000 MHz (see the 1090 MHz time analysis).',
    '20261101T143515': 'Lines at exactly 1088.000 and 1090.000 MHz (fc ± 1 MHz) and the centre artifact. The 1090 MHz line is continuous — see the gap-free time analysis below.',
    '20261101T144509': 'A symmetric pair of 1.5 MHz-wide humps at fc ± 6.86 MHz with equal level, the ±8.98 MHz spurs and a weak line at 1119.996 MHz (= +6 MHz baseband).',
    '20261101T144709': 'With 20 dB more gain the noise floor rose by ~12 dB but the two humps disappeared; an external signal would have grown with the gain. Only the line at 1119.996 MHz (+6 MHz baseband) remains clearly.'
  };

  function renderTable7() {
    var body = R.table7.map(function (t, i) {
      var o = t.obw, x = t.xdb, warn = t.outsideTrusted ? ' <span class="flag" title="outside the trusted middle 80 % of the display">edge</span>' : '';
      return '<tr><td>' + (i + 1) + '</td><td>' + esc(t.band) + '</td><td class="num">' + mhz(t.fc + o.fc, 4) + warn + '</td><td class="num">' + khz(o.B99, 1) +
        '</td><td class="num">' + mhz(t.fc + x.fc, 4) + '</td><td class="num">' + khz(x.Bx, 1) + '</td><td class="num">' + x.x + '</td><td class="num">' + fx(x.aboveFloor, 1) +
        '</td><td class="num">' + fx(o.powerDbfs, 1) + '</td><td class="num">' + fx(t.fs / 1e6, 1) + ' / ' + fx(t.resolution / 1e3, 2) + '</td><td>' + esc(T7_TEXT[t.key] || t.guess) +
        (t.time ? '<br><span class="dim small">' + (t.time.onFraction >= 0.95 ? 'continuous' : 'bursty') + ': on in ' + fx(100 * t.time.onFraction, 0) + ' % of ' + t.time.frames + ' frames of ' + fx(t.time.frameUs, 0) + ' µs</span>' : '') +
        '</td><td class="mono small">' + esc(t.file.replace(/^Team-XX_lab01_/, '…')) + '</td></tr>';
    });
    $('#t7-body').innerHTML = body.join('');
    var host = $('#t7-plots'); host.innerHTML = '';
    R.table7.forEach(function (t) {
      var x0 = (t.fc + t.f0) / 1e6, dx = t.df / 1e6, n = t.psd.length, o = t.obw, x = t.xdb;
      var ymax = Math.max.apply(null, t.mh) + 4, ymin = t.floor - 10;
      var cell = document.createElement('div'); cell.className = 'card t7cell'; host.appendChild(cell);
      draw(canvas(cell), 'line', {
        height: 230, xmin: x0, xmax: x0 + (n - 1) * dx, ymin: ymin, ymax: ymax, xlabel: 'Frequency (MHz)', ylabel: 'dBFS/Hz', title: T7_SHORT[t.key],
        spans: [{ a: (t.fc + o.fL) / 1e6, b: (t.fc + o.fU) / 1e6, fill: 'rgba(15,123,220,0.12)' }],
        series: [{ x0: x0, dx: dx, y: t.psd, color: '--accent' }, { x0: x0, dx: dx, y: t.mh, color: '--text-dim', width: 0.8, alpha: 0.8 }],
        hlines: [{ y: t.floor, color: '--text-dim' }, { y: x.peakDb - x.x, color: '--warn', dash: [2, 3] }],
        vlines: [{ x: (t.fc + x.fL) / 1e6, color: '--warn', dash: [2, 3] }, { x: (t.fc + x.fU) / 1e6, color: '--warn', dash: [2, 3] }],
        tipX: function (v) { return v.toFixed(4) + ' MHz'; }, tipUnit: 'dBFS/Hz'
      });
    });
    // question 8: wide carriers
    var w = R.table7.filter(function (t) { return t.shape; });
    $('#q8-body').innerHTML = w.map(function (t) {
      var s = t.shape;
      return '<tr><td class="num">' + mhz(t.fc + t.obw.fc, 2) + ' MHz</td><td class="num">' + mhz(s.B3, 2) + '</td><td class="num">' + mhz(s.B12, 2) + '</td><td class="num">' + fx(s.ratio, 2) +
        '</td><td class="num">' + mhz(t.obw.B99, 2) + '</td><td class="num">' + fx(s.slopeDbPerMHz, 0) + '</td><td><b>' + wideClass(s)[0] + '</b> ' + wideClass(s)[1] + '</td></tr>';
    }).join('');
    if (w.length === 2) setText('umts-spacing', mhz((w[1].fc + w[1].obw.fc) - (w[0].fc + w[0].obw.fc), 2));
  }
  // Question 8 decision rule (report, Q8 table): UMTS = RRC on 3.84 Mchip/s -> B_-3dB ~ 3.84 MHz with
  // rounded shoulders (B_-3dB / B_-12dB well below 1); LTE 5 MHz = 300 x 15 kHz -> flat 4.5 MHz, ratio ~ 1.
  function wideClass(s) {
    if (s.B3 > 3.5e6 && s.B3 < 4.1e6 && s.ratio < 0.93) return ['UMTS', '(B₋₃dB close to 3.84 MHz, rounded edges)'];
    if (s.B3 >= 4.3e6 && s.ratio >= 0.93) return ['LTE', '(flat 4.5 MHz, steep edges)'];
    return ['?', '(between the UMTS and LTE signatures)'];
  }

  var T7_SHORT = { gsm1: 'Row 1 — narrow carrier ≈ 952.2 MHz', gsm2: 'Row 2 — narrow carrier ≈ 952.8 MHz', wideA: 'Row 3 — wide block ≈ 944.2 MHz', wideB: 'Row 4 — wide block ≈ 949.1 MHz', hump1114: 'Row 5 — hump ≈ 1107.1 MHz (artifact)', line1090: 'Row 6 — line 1090.000 MHz (artifact)' };
  var T7_TEXT = {
    gsm1: 'GSM900 downlink, ARFCN 86; never off → BCCH carrier',
    gsm2: 'GSM900 downlink, ARFCN 89; never off → BCCH carrier',
    wideA: 'UMTS (WCDMA) 5 MHz carrier; rounded RRC edges',
    wideB: 'UMTS (WCDMA) 5 MHz carrier; rounded RRC edges',
    hump1114: 'Not a real signal: mirror pair at fc ± 6.86 MHz, vanished at 30 dB gain',
    line1090: 'Not ADS-B: continuous CW line exactly at fc + 1.000000 MHz (receiver spur)'
  };

  function renderGsm() {
    var g = R.gsm;
    $('#gsm-body').innerHTML = g.rows.map(function (r) {
      return '<tr><td class="num">' + mhz(r.f, 4) + '</td><td class="num">' + mhz(r.grid, 1) + '</td><td class="num">' + (r.arfcn == null ? '–' : r.arfcn) + '</td><td class="num">' + sgn(r.offset / 1e3, 1) + ' kHz</td><td class="num">' + fx(r.snr, 1) + ' dB</td></tr>';
    }).join('');
    setText('gsm-offset', sgn(g.offset / 1e3, 1)); setText('gsm-offset-unc', fx(g.offsetUnc / 1e3, 1));
    setText('gsm-eps', sgn(g.eps, 1)); setText('gsm-eps-unc', fx(g.epsUnc, 1)); setText('gsm-res', fx(g.resolution / 1e3, 2));
    setText('gsm-spec', fx(25e-6 * g.fc / 1e3, 1));
    var o = R.overview['20261101T151432'], rec = M.byId['20261101T151432'], t = R.table7.filter(function (q) { return q.key.indexOf('gsm') === 0; });
    var host = $('#gsm-plot'); host.innerHTML = '';
    var a = 951.6, b = 953.4, x0, dx, y;
    // use the N = 4096 spectra stored with the two GSM rows (stitched)
    var s1 = t[0], s2 = t[1];
    var xs = [], ys = [];
    [s1, s2].forEach(function (s) { for (var i = 0; i < s.psd.length; i++) { xs.push((s.fc + s.f0 + i * s.df) / 1e6); ys.push(s.psd[i]); } });
    var order = xs.map(function (v, i) { return i; }).sort(function (i, j) { return xs[i] - xs[j]; });
    xs = order.map(function (i) { return xs[i]; }); ys = order.map(function (i) { return ys[i]; });
    var grid = []; for (var gl = Math.ceil(a / 0.2) * 0.2; gl <= b + 1e-9; gl += 0.2) grid.push({ x: +gl.toFixed(1), color: '--border', dash: [] });
    draw(canvas(host), 'line', {
      height: 280, xmin: Math.min(xs[0], a), xmax: Math.max(xs[xs.length - 1], b), ymin: s1.floor - 8, ymax: Math.max.apply(null, ys) + 6, xdec: 1,
      xlabel: 'Frequency (MHz) — grey: 200 kHz GSM channel grid', ylabel: 'PSD (dBFS/Hz)', title: 'GSM carriers vs the 200 kHz grid (N = 4096, Δf = ' + fx(g.resolution / 1e3, 2) + ' kHz)',
      series: [{ xs: xs, y: ys, color: '--accent' }], vlines: grid.concat(g.rows.map(function (r) { return { x: r.f / 1e6, color: '--warn', dash: [3, 2] }; })),
      notes: g.rows.map(function (r) { return { x: r.f / 1e6, y: s1.floor + r.snr + 2, text: sgn(r.offset / 1e3, 1) + ' kHz', color: '--warn' }; }),
      tipX: function (v) { return v.toFixed(4) + ' MHz'; }, tipUnit: 'dBFS/Hz'
    });
  }

  function renderBursts() {
    var b = R.bursts, e = b.envelope, n = e.max.length, host = $('#burst-plot'); host.innerHTML = '';
    var t = Array.from({ length: n }, function (_, i) { return i * e.step * 1e3; });
    draw(canvas(host), 'line', {
      height: 260, xmin: 0, xmax: t[n - 1], ymin: b.floor - 8, ymax: b.thr + 6, xlabel: 'Time (ms)', ylabel: 'Channel power (dBFS)',
      title: 'Power in 1090 MHz ± 150 kHz, every ' + fx(b.frameUs, 1) + ' µs, no gaps (' + b.frames.toLocaleString('en-US') + ' frames)',
      series: [{ xs: t, y: e.max, color: '--accent', width: 1 }, { xs: t, y: e.min, color: '--accent', width: 1, alpha: 0.5 }],
      hlines: [{ y: b.thr, color: '--warn' }, { y: b.floor, color: '--text-dim' }],
      legend: [{ text: 'max / min per ' + fx(e.step * 1e3, 2) + ' ms', color: '--accent' }, { text: 'threshold (floor + 10 dB)', color: '--warn', dash: [4, 3] }],
      tipX: function (v) { return v.toFixed(1) + ' ms'; }, tipUnit: 'dBFS'
    });
    setText('b-count', b.count); setText('b-p50', fx(b.p50, 1)); setText('b-p99', fx(b.p99, 1)); setText('b-max', fx(b.max, 1)); setText('b-thr', fx(b.thr, 1));
    setText('b-frames', b.frames.toLocaleString('en-US')); setText('b-us', fx(b.frameUs, 1));
  }

  function renderQ1() {
    $('#q1-body').innerHTML = R.q1.map(function (q) {
      return '<tr><td>' + esc(q.label) + '</td><td class="num">' + fx(q.fs / 1e6, 1) + '</td><td class="num">' + fx(100 * q.fraction1, 0) + ' %</td><td class="num">' + fx(100 * q.fraction3, 0) + ' %</td></tr>';
    }).join('');
    var f1 = R.q1.map(function (q) { return q.fraction1; }), f3 = R.q1.map(function (q) { return q.fraction3; });
    setText('q1-range1', fx(100 * Math.min.apply(null, f1), 0) + '–' + fx(100 * Math.max.apply(null, f1), 0));
    setText('q1-range3', fx(100 * Math.min.apply(null, f3), 0) + '–' + fx(100 * Math.max.apply(null, f3), 0));
    var host = $('#q1-plot'); host.innerHTML = '';
    var cols = ['--accent', '--accent-2', '--warn', '--text-dim'];
    draw(canvas(host), 'line', {
      height: 280, xmin: -0.5, xmax: 0.5, ymin: -6, ymax: 30, xlabel: 'Baseband frequency / fs', ylabel: 'Floor − centre floor (dB)', title: 'Noise-floor shape across the display',
      spans: [{ a: -0.5, b: -0.4, fill: 'rgba(128,128,128,0.13)' }, { a: 0.4, b: 0.5, fill: 'rgba(128,128,128,0.13)' }],
      series: R.q1.map(function (q, i) { var n = q.shape.length; return { x0: -0.5, dx: 1 / n, y: q.shape.map(function (v) { return v - q.centre; }), color: cols[i % 4] }; }),
      hlines: [{ y: 1, color: '--text-dim' }, { y: -1, color: '--text-dim' }, { y: 3, color: '--text-dim', dash: [1, 3] }],
      legend: R.q1.map(function (q, i) { return { text: q.label.replace(/ \(.*\)/, ''), color: cols[i % 4] }; }),
      tipX: function (v) { return v.toFixed(3) + ' fs'; }, tipUnit: 'dB'
    });
  }

  function renderNumbers() {
    var t = {}; R.table7.forEach(function (q) { t[q.key] = q; });
    if (t.gsm1 && t.gsm2) { setText('gsm1-b99', khz(t.gsm1.obw.B99, 0)); setText('gsm2-b99', khz(t.gsm2.obw.B99, 0)); }
    if (t.wideA && t.wideB) {
      setText('umtsA-b3', mhz(t.wideA.shape.B3, 2)); setText('umtsB-b3', mhz(t.wideB.shape.B3, 2));
      setText('umtsA-b99', mhz(t.wideA.obw.B99, 2)); setText('umtsB-b99', mhz(t.wideB.obw.B99, 2));
      setText('umtsA-err', fx(100 * Math.abs(t.wideA.shape.B3 - 3.84e6) / 3.84e6, 1)); setText('umtsB-err', fx(100 * Math.abs(t.wideB.shape.B3 - 3.84e6) / 3.84e6, 1));
      setText('umtsA-fc', mhz(t.wideA.fc + t.wideA.obw.fc, 2)); setText('umtsB-fc', mhz(t.wideB.fc + t.wideB.obw.fc, 2));
    }
    if (t.gsm1) { setText('gsm1-err', fx(100 * Math.abs(t.gsm1.obw.B99 - 250e3) / 250e3, 0)); setText('gsm2-err', fx(100 * Math.abs(t.gsm2.obw.B99 - 250e3) / 250e3, 0)); }
    var l0 = R.loopback.filter(function (l) { return l.ftx > 0 && l.loShift === 0; })[0];
    if (l0) { setText('lb0-meas', mhz(l0.measured, 6)); setText('lb0-err', sgn(l0.error, 2)); setText('lb0-res', fx(l0.resolution, 0)); }
    var ln = R.loopback.filter(function (l) { return l.ftx < 0; })[0];
    if (ln) setText('lbn-meas', mhz(ln.measured, 6));
    var tr = R.loTest.tracks, s4 = tr.filter(function (q) { return q.s === 4; })[0];
    if (s4) setText('s4-level', fx(s4.labels[s4.labels.length - 1].level, 0));
    setText('generated', new Date(R.generated).toLocaleString('en-GB', { dateStyle: 'medium', timeStyle: 'short' }));
  }

  function renderAll() {
    renderInventory(); renderPart1(); renderLoopback(); renderBands(); renderTable7(); renderGsm(); renderBursts(); renderQ1(); renderNumbers();
  }

  // ================================================================ recompute in the browser
  async function fetchRec(rec, onBytes) {
    var res = await fetch(rec.data); if (!res.ok) throw new Error('HTTP ' + res.status + ' for ' + rec.data);
    var total = +res.headers.get('content-length') || rec.samples_excerpt * 4, reader = res.body && res.body.getReader ? res.body.getReader() : null;
    if (!reader) { var b = await res.arrayBuffer(); onBytes(b.byteLength); return D.decodeCs16(b, rec.scale); }
    var chunks = [], got = 0;
    for (;;) { var r = await reader.read(); if (r.done) break; chunks.push(r.value); got += r.value.length; onBytes(r.value.length); }
    var buf = new Uint8Array(got), o = 0; chunks.forEach(function (c) { buf.set(c, o); o += c.length; });
    return D.decodeCs16(buf.buffer, rec.scale);
  }

  function compare(a, b) {
    var keys = [], bad = [];
    function chk(name, x, y, tol) { keys.push(name); if (!(Math.abs(x - y) <= (tol || 1e-6) * Math.max(1, Math.abs(x)))) bad.push(name); }
    a.table7.forEach(function (t, i) { var u = b.table7[i]; chk(t.key + ' B99', t.obw.B99, u.obw.B99); chk(t.key + ' Bx', t.xdb.Bx, u.xdb.Bx); chk(t.key + ' power', t.obw.powerDbfs, u.obw.powerDbfs); });
    a.loopback.forEach(function (l, i) { chk('tone ' + l.id, l.measured, b.loopback[i].measured, 1e-12); });
    chk('eps', a.gsm.eps, b.gsm.eps); chk('bursts', a.bursts.count, b.bursts.count);
    a.loTest.tracks.forEach(function (t, i) { chk('slope ' + i, t.s, b.loTest.tracks[i] ? b.loTest.tracks[i].s : NaN); });
    return { n: keys.length, bad: bad };
  }

  async function recompute() {
    var btn = $('#recompute'), bar = $('#rc-bar'), msg = $('#rc-msg');
    btn.disabled = true; $('#rc-progress').hidden = false;
    var totalBytes = M.recordings.reduce(function (s, r) { return s + r.samples_excerpt * 4; }, 0), got = 0, t0 = performance.now();
    try {
      var res = await L.run(M, function (rec) {
        msg.textContent = 'Downloading ' + rec.label + '…';
        return fetchRec(rec, function (n) { got += n; bar.style.width = (60 * got / totalBytes).toFixed(1) + '%'; });
      }, function (p, m) { bar.style.width = (60 + 40 * p).toFixed(1) + '%'; msg.textContent = 'Computing: ' + m; return new Promise(function (r) { setTimeout(r, 0); }); });
      var cmp = compare(PRE, res);
      R = res; renderAll();
      msg.innerHTML = 'Recomputed from ' + (totalBytes / 1e6).toFixed(0) + ' MB of raw I/Q in ' + ((performance.now() - t0) / 1000).toFixed(1) + ' s. ' +
        (cmp.bad.length ? '<span class="bad">' + cmp.bad.length + ' of ' + cmp.n + ' checked values differ from results.json: ' + esc(cmp.bad.join(', ')) + '</span>'
          : '<span class="ok">All ' + cmp.n + ' checked values are identical to the published results.json ✓</span>');
      bar.style.width = '100%';
    } catch (e) { msg.innerHTML = '<span class="bad">Failed: ' + esc(e.message) + '</span>'; }
    btn.disabled = false;
  }

  // ================================================================ analyse your own file
  async function ownFile(file) {
    var out = $('#own-out'), meta = D.parseName(file.name);
    var fs = meta ? meta.fs : parseFloat($('#own-fs').value) * 1e6, fc = meta ? meta.fc : parseFloat($('#own-fc').value) * 1e6;
    var cs16 = /\.cs16$/i.test(file.name), bps = cs16 ? 4 : 8, secs = parseFloat($('#own-sec').value) || 0.5;
    if (!(fs > 0) || isNaN(fc)) { out.innerHTML = '<p class="notice">The file name is not in the standard format; enter fc and fs above.</p>'; return; }
    var nBytes = Math.min(file.size, Math.floor(secs * fs) * bps), buf = await file.slice(0, nBytes - (nBytes % bps)).arrayBuffer();
    var x = cs16 ? D.decodeCs16(buf) : D.decodeCf32(buf);
    var nfft = parseInt($('#own-nfft').value, 10) || 1024;
    var lo = parseFloat($('#own-fmin').value), hi = parseFloat($('#own-fmax').value);
    var opts = { nfft: nfft, rows: 160, avg: MH_AVG_OWN };
    if (!isNaN(lo) && !isNaN(hi)) { opts.fmin = lo * 1e6 - fc; opts.fmax = hi * 1e6 - fc; }
    var s = D.signalReport(x, fs, opts), o = s.obw, xb = s.xdb;
    out.innerHTML = '<div class="own-res">' +
      '<span><b>' + esc(file.name) + '</b></span><span>fc ' + mhz(fc, 3) + ' MHz · fs ' + fx(fs / 1e6, 2) + ' MS/s · ' + x.re.length.toLocaleString('en-US') + ' samples (' + fx(x.re.length / fs, 3) + ' s of ' + fx(file.size / bps / fs, 3) + ' s)</span>' +
      '<span>noise floor ' + fx(s.floor, 1) + ' dBFS/Hz · Δf ' + fx(s.resolution / 1e3, 2) + ' kHz</span>' +
      (o ? '<span>99 % OBW <b>' + khz(o.B99, 1) + ' kHz</b> [' + mhz(fc + o.fL, 4) + ' … ' + mhz(fc + o.fU, 4) + ' MHz], centre ' + mhz(fc + o.fc, 4) + ' MHz, power ' + fx(o.powerDbfs, 1) + ' dBFS</span>' : '') +
      '<span>Max-Hold peak ' + fx(xb.aboveFloor, 1) + ' dB above floor → x = ' + xb.x + ' dB, <b>B_x = ' + khz(xb.Bx, 1) + ' kHz</b>, f_c,sig = ' + mhz(fc + xb.fc, 4) + ' MHz</span></div>';
    var p = document.createElement('div'); out.appendChild(p);
    var x0 = (fc + s.f[0]) / 1e6, dx = (s.f[1] - s.f[0]) / 1e6, xmin = (fc - fs / 2) / 1e6, xmax = (fc + fs / 2) / 1e6;
    draw(canvas(p), 'line', {
      height: 280, xmin: xmin, xmax: xmax, ymin: s.floor - 12, ymax: Math.max.apply(null, Array.from(s.maxholdDb)) + 5, xlabel: 'Frequency (MHz)', ylabel: 'PSD (dBFS/Hz)', title: file.name,
      spans: (o ? [{ a: (fc + o.fL) / 1e6, b: (fc + o.fU) / 1e6, fill: 'rgba(15,123,220,0.12)' }] : []).concat([{ a: xmin, b: (fc - 0.4 * fs) / 1e6, fill: 'rgba(128,128,128,0.13)' }, { a: (fc + 0.4 * fs) / 1e6, b: xmax, fill: 'rgba(128,128,128,0.13)' }]),
      series: [{ x0: x0, dx: dx, y: Array.from(s.psdDb), color: '--accent' }, { x0: x0, dx: dx, y: Array.from(s.maxholdDb), color: '--text-dim', width: 0.8, alpha: 0.7 }],
      hlines: [{ y: s.floor, color: '--text-dim' }], legend: [{ text: 'Welch average', color: '--accent' }, { text: 'Max Hold', color: '--text-dim' }],
      tipX: function (v) { return v.toFixed(4) + ' MHz'; }, tipUnit: 'dBFS/Hz'
    });
    var pk = s.waterfall, wf = { rows: pk.rows, cols: pk.cols, data: pk.data };
    // reuse the packing used for the published results
    var lo8 = D.percentile(pk.data, 5), hi8 = -Infinity; for (var i = 0; i < pk.data.length; i++) if (pk.data[i] > hi8) hi8 = pk.data[i];
    var bytes = new Uint8Array(pk.data.length); for (i = 0; i < bytes.length; i++) bytes[i] = Math.max(0, Math.min(255, Math.round(255 * (pk.data[i] - lo8) / (hi8 - lo8))));
    var str = ''; for (i = 0; i < bytes.length; i += 0x8000) str += String.fromCharCode.apply(null, bytes.subarray(i, i + 0x8000));
    draw(canvas(p), 'wf', { wf: { rows: pk.rows, cols: pk.cols, min: lo8, max: hi8, rowSeconds: pk.rowSeconds, b64: btoa(str) }, xmin: xmin, xmax: xmax, height: 200 });
  }
  var MH_AVG_OWN = 8;

  // ================================================================ boot
  async function boot() {
    try {
      var r = await Promise.all([fetch('data/manifest.json', { cache: 'no-cache' }).then(function (x) { return x.json(); }), fetch('results.json', { cache: 'no-cache' }).then(function (x) { return x.json(); })]);
      M = r[0]; M.byId = {}; M.recordings.forEach(function (q) { M.byId[q.id] = q; });
      R = PRE = r[1];
      renderAll();
      $('#rc-size').textContent = (M.recordings.reduce(function (s, q) { return s + q.samples_excerpt * 4; }, 0) / 1e6).toFixed(0);
      $('#recompute').onclick = recompute;
      $('#own-file').onchange = function (e) { if (e.target.files[0]) ownFile(e.target.files[0]); };
      $('#own-run').onclick = function () { var f = $('#own-file').files[0]; if (f) ownFile(f); };
    } catch (e) {
      $('#rc-msg').innerHTML = '<span class="bad">Could not load results.json / manifest.json: ' + esc(e.message) + '</span>';
      $('#rc-progress').hidden = false;
    }
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot); else boot();
})();
