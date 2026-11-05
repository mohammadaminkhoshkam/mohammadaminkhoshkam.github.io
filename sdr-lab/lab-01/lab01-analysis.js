/*
 * lab01-analysis.js - the analyses required by the Lab 01 manual, run on the raw I/Q recordings.
 *
 * run(manifest, load, progress) -> results (plain JSON).
 *   load(rec) must resolve to { re: Float32Array, im: Float32Array } for one recording.
 * The same code runs in Node (tools/precompute_lab01.mjs -> results.json) and in the browser
 * ("Recompute from the raw I/Q" on the lab page), so the published numbers can be re-derived.
 */
(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory(require('../../assets/js/sdr-dsp.js'));
  else root.Lab01 = factory(root.SDRDSP);
})(typeof self !== 'undefined' ? self : this, function (D) {
  'use strict';

  // ---------------------------------------------------------------- what to measure
  // Table 7 rows: signal windows (baseband Hz, relative to the recording's fc) chosen from the
  // overview spectra; nfft so that fs/N <= B/20 (manual, Part 3 step 8).
  var TABLE7 = [
    { key: 'gsm1', rec: '20261101T151432', fmin: 7.05e6, fmax: 7.35e6, nfft: 4096, band: 'C', guess: 'GSM900 downlink carrier (200 kHz, GMSK)' },
    { key: 'gsm2', rec: '20261101T151432', fmin: 7.65e6, fmax: 7.95e6, nfft: 4096, band: 'C', guess: 'GSM900 downlink carrier (200 kHz, GMSK)' },
    { key: 'wideA', rec: '20261101T151432', fmin: -3.6e6, fmax: 1.9e6, nfft: 1024, band: 'C', guess: 'Wideband 5 MHz carrier (UMTS or LTE)', wide: true },
    { key: 'wideB', rec: '20261101T151432', fmin: 1.6e6, fmax: 6.5e6, nfft: 1024, band: 'C', guess: 'Wideband 5 MHz carrier (UMTS or LTE)', wide: true },
    { key: 'hump1114', rec: '20261101T144509', fmin: -7.6e6, fmax: -6.1e6, nfft: 1024, band: '1.1 GHz', guess: 'see text' },
    { key: 'line1090', rec: '20261101T143515', fmin: 0.85e6, fmax: 1.15e6, nfft: 4096, band: '1090 MHz', guess: 'see text' }
  ];

  // Question 1 (trusted part of the display): recordings whose spectrum is mostly empty noise floor
  var Q1 = ['20261101T150359', '20261101T143653', '20261101T151733', '20261101T144509'];
  // Max Hold for Table 7 = Max Hold of 8-frame averages (the session used GNU Radio's FFT averaging
  // with Max Hold; a raw single-frame Max Hold of 0.1 s of a noisy carrier is dominated by noise spikes)
  var MH_AVG = 8;

  function r2(v) { return Math.round(v * 100) / 100; }
  function arr2(a) { return Array.from(a, r2); }

  // Waterfall -> 8-bit image (base64) so results.json stays small; columns max-pooled to <= 512.
  function packWaterfall(wf) {
    var pool = Math.max(1, Math.ceil(wf.cols / 512)), cols = Math.floor(wf.cols / pool), rows = wf.rows;
    var img = new Float32Array(rows * cols);
    for (var r = 0; r < rows; r++) for (var c = 0; c < cols; c++) {
      var m = -Infinity; for (var q = 0; q < pool; q++) m = Math.max(m, wf.data[r * wf.cols + c * pool + q]);
      img[r * cols + c] = m;
    }
    var lo = D.percentile(img, 5), hi = -Infinity;
    for (var i = 0; i < img.length; i++) if (img[i] > hi) hi = img[i];
    var bytes = new Uint8Array(img.length);
    for (i = 0; i < img.length; i++) bytes[i] = Math.max(0, Math.min(255, Math.round(255 * (img[i] - lo) / (hi - lo))));
    var s = ''; for (i = 0; i < bytes.length; i += 0x8000) s += String.fromCharCode.apply(null, bytes.subarray(i, i + 0x8000));
    var b64 = typeof btoa === 'function' ? btoa(s) : Buffer.from(bytes).toString('base64');
    return { rows: rows, cols: cols, min: r2(lo), max: r2(hi), rowSeconds: wf.rowSeconds, b64: b64 };
  }

  function window_(f, a, b) { var i0 = 0, i1 = f.length - 1; while (i0 < f.length && f[i0] < a) i0++; while (i1 > 0 && f[i1] > b) i1--; return [i0, i1 + 1]; }

  // ---------------------------------------------------------------- wideband carrier shape (question 8)
  // Plateau = median PSD of the middle half of the 99 % band; edges where the PSD falls 3 dB / 12 dB
  // below it; edge steepness between those two levels. LTE 5 MHz: flat 4.5 MHz with steep edges and a
  // DC-subcarrier notch; UMTS: RRC roll-off (B_3dB ~ 3.84 MHz, rounded shoulders).
  function wideShape(f, psdDb, obw) {
    var mid = [], i;
    for (i = 0; i < f.length; i++) if (Math.abs(f[i] - obw.fc) <= obw.B99 / 4) mid.push(psdDb[i]);
    var plateau = D.median(mid);
    function edges(drop) {
      var c = 0; for (i = 0; i < f.length; i++) if (Math.abs(f[i] - obw.fc) < Math.abs(f[c] - obw.fc)) c = i;
      var lo = c, hi = c;
      while (lo > 0 && psdDb[lo - 1] >= plateau - drop) lo--;
      while (hi < f.length - 1 && psdDb[hi + 1] >= plateau - drop) hi++;
      return [f[lo], f[hi]];
    }
    var e3 = edges(3), e12 = edges(12);
    var slopeL = 9 / ((e3[0] - e12[0]) / 1e6), slopeU = 9 / ((e12[1] - e3[1]) / 1e6);
    return { plateau: r2(plateau), B3: e3[1] - e3[0], B12: e12[1] - e12[0], ratio: (e3[1] - e3[0]) / (e12[1] - e12[0]),
      edgeL: e3[0], edgeU: e3[1], slopeDbPerMHz: r2((slopeL + slopeU) / 2) };
  }

  // ---------------------------------------------------------------- main
  async function run(manifest, load, progress) {
    progress = progress || function () {};
    var recs = manifest.recordings, byId = {};
    recs.forEach(function (r) { byId[r.id] = r; });
    var cache = {};
    async function get(id) { if (!cache[id]) cache[id] = await load(byId[id]); return cache[id]; }
    var out = { generated: new Date().toISOString(), inventory: [], overview: {}, table7: [], loopback: [], loTest: null, gsm: null, bursts: null, q1: [] };
    var step = 0, steps = recs.length + TABLE7.length + 4;
    function tick(msg) { progress(++step / steps, msg); }

    // 0. inventory (name check + size check 8 * N) and 1. overview spectrum / Max Hold / waterfall
    for (var i = 0; i < recs.length; i++) {
      var r = recs[i], x = await get(r.id), meta = D.parseName(r.file);
      var rep = D.signalReport(x, r.fs, { nfft: 1024, rows: 160 });
      out.inventory.push({ id: r.id, file: r.file, nameOk: !!meta, fc: r.fc, fs: r.fs, gain: r.gain, part: r.part, label: r.label,
        samplesTotal: r.samples_total, durationTotal: r.duration_total, bytesTotal: r.bytes_total, sizeOk: r.bytes_total === 8 * r.samples_total,
        samplesUsed: x.re.length, durationUsed: x.re.length / r.fs });
      out.overview[r.id] = { f0: rep.f[0], df: rep.f[1] - rep.f[0], psd: arr2(rep.psdDb), mh: arr2(rep.maxholdDb), floor: r2(rep.floor),
        floorMh: r2(rep.floorMh), frames: rep.frames, wf: packWaterfall(rep.waterfall) };
      if (Q1.indexOf(r.id) >= 0) {
        var tf1 = D.trustedFraction(rep.f, rep.psdDb, r.fs, 1), tf3 = D.trustedFraction(rep.f, rep.psdDb, r.fs, 3);
        out.q1.push({ id: r.id, fs: r.fs, fc: r.fc, label: r.label, fraction1: tf1.fraction, fraction3: tf3.fraction,
          shape: arr2(tf1.floorShape), centre: r2(tf1.centre) });
      }
      tick('overview ' + r.label);
    }

    // 2. Table 7 rows: Welch + Max Hold + 99 % OBW + x-dB bandwidth + power (+ shape for wide carriers)
    for (var t = 0; t < TABLE7.length; t++) {
      var row = TABLE7[t], rr = byId[row.rec], xs = await get(row.rec);
      var s = D.signalReport(xs, rr.fs, { nfft: row.nfft, fmin: row.fmin, fmax: row.fmax, rows: 1, avg: MH_AVG });
      var pad = (row.fmax - row.fmin) * 0.6, w = window_(s.f, row.fmin - pad, row.fmax + pad);
      var item = { key: row.key, rec: row.rec, file: rr.file, fc: rr.fc, fs: rr.fs, band: row.band, guess: row.guess, nfft: row.nfft,
        fmin: row.fmin, fmax: row.fmax, resolution: s.resolution, floor: r2(s.floor), floorMh: r2(s.floorMh), mhAvg: MH_AVG,
        outsideTrusted: !!s.obw && Math.abs(s.obw.fc) + s.obw.B99 / 2 > 0.4 * rr.fs,
        obw: s.obw, xdb: s.xdb, f0: s.f[w[0]], df: s.f[1] - s.f[0],
        psd: arr2(s.psdDb.subarray(w[0], w[1])), mh: arr2(s.maxholdDb.subarray(w[0], w[1])) };
      if (row.wide && s.obw) item.shape = wideShape(s.f, s.psdDb, s.obw);
      // time behaviour inside the 99 % band: channel power of gap-free frames
      // "on" = channel power at least 3 dB above the noise power in the same bandwidth (floor x B)
      if (s.obw) {
        var bw = Math.max(s.obw.B99, 4 * s.resolution);
        var b = D.burstReport(xs, rr.fs, { f0: s.obw.fc, bw: bw, nfft: row.wide ? 1024 : 4096, thr: 6 });
        var noiseDb = s.floor + 10 * Math.log10(bw), on = 0;
        for (var u = 0; u < b.p.length; u++) if (b.p[u] > noiseDb + 3) on++;
        item.time = { p50: r2(b.p50), p99: r2(b.p99), max: r2(b.max), frames: b.p.length, frameUs: b.dt * 1e6,
          noiseDb: r2(noiseDb), onFraction: on / b.p.length };
      }
      out.table7.push(item);
      tick('signal ' + row.key);
    }

    // 3. loopback: tone frequency vs fc + f_tx, peak classes; 4. LO test slopes
    var lb = recs.filter(function (q) { return q.group === 'loopback'; });
    var runs = [];
    for (var l = 0; l < lb.length; l++) {
      // the TX LO stays at fc while the RX LO is fc + lo_shift, so the tone sits at f_tx - lo_shift in baseband
      var q = lb[l], xl = await get(q.id);
      var rep2 = D.loopbackReport(xl, q.fs, { ftx: q.f_tx - q.lo_shift, nfft: 1024, thr: 10 });
      var fine = D.finePeaks(xl, q.fs, { thr: 25, max: 10 });
      out.loopback.push({ id: q.id, file: q.file, fc: q.fc, fs: q.fs, ftx: q.f_tx, loShift: q.lo_shift, fTx: q.fc - q.lo_shift,
        expected: q.fc - q.lo_shift + q.f_tx, measured: q.fc + rep2.tone, error: q.fc + rep2.tone - (q.fc - q.lo_shift + q.f_tx),
        toneSamples: rep2.toneSamples, resolution: rep2.resolution, floor: r2(rep2.floor),
        f0: rep2.f[0], df: rep2.f[1] - rep2.f[0], psd: arr2(rep2.psdDb),
        peaks: fine.map(function (p) { return { label: q.fc + p.fb, level: r2(p.level) }; }) });
      if (q.f_tx > 0) runs.push({ lo: q.lo_shift, ftune: q.fc, peaks: fine.map(function (p) { return { label: q.fc + p.fb, level: p.level }; }) });
    }
    runs.sort(function (a, b) { return a.lo - b.lo; });
    out.loTest = { runs: runs.map(function (r) { return { lo: r.lo, ftune: r.ftune }; }), tracks: D.loTest(runs, { tol: 3e3 }) };
    tick('loopback');

    // 5. reference error from the GSM carriers (200 kHz grid)
    var g = byId['20261101T151432'], gr = D.gsmReport(await get(g.id), g.fs, g.fc, { nfft: 4096, thr: 10 });
    out.gsm = { file: g.file, fc: g.fc, fs: g.fs, nfft: 4096, resolution: gr.resolution, floor: r2(gr.floor), rows: gr.rows,
      offset: gr.offset, offsetUnc: gr.offsetUnc, eps: gr.eps, epsUnc: gr.epsUnc };
    tick('gsm');

    // 6. gap-free time analysis of the 1090 MHz line (ADS-B would be bursty)
    var a = byId['20261101T143515'], xa = await get(a.id), br = D.burstReport(xa, a.fs, { f0: 1e6, bw: 300e3, nfft: 64, thr: 10 });
    var env = 2000, per = Math.ceil(br.p.length / env), tmin = [], tmax = [];
    for (var k = 0; k < br.p.length; k += per) {
      var lo = Infinity, hi = -Infinity;
      for (var j = k; j < Math.min(k + per, br.p.length); j++) { lo = Math.min(lo, br.p[j]); hi = Math.max(hi, br.p[j]); }
      tmin.push(r2(lo)); tmax.push(r2(hi));
    }
    var ref = D.burstReport(xa, a.fs, { f0: 0.5e6, bw: 300e3, nfft: 64, thr: 10 });
    out.bursts = { file: a.file, fc: a.fc, fs: a.fs, f0: 1e6, bw: 300e3, nfft: 64, frameUs: br.dt * 1e6, frames: br.p.length,
      floor: r2(br.floor), thr: r2(br.thr), p50: r2(br.p50), p99: r2(br.p99), max: r2(br.max), count: br.bursts.length,
      envelope: { step: per * br.dt, min: tmin, max: tmax },
      reference: { f0: 0.5e6, p50: r2(ref.p50), p99: r2(ref.p99), max: r2(ref.max) } };
    tick('bursts');
    return out;
  }

  return { run: run, TABLE7: TABLE7 };
});
