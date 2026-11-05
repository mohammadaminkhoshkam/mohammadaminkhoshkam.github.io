/*
 * sdr-dsp.js - spectrum analysis of raw I/Q recordings, in the browser or in Node.
 *
 * A JavaScript port of the team's analysis/lab01_analysis.py (NumPy/SciPy):
 * Welch PSD, Max-Hold, noise floor, 99 % occupied bandwidth (ITU-R SM.443),
 * x-dB bandwidth (lab rule), channel power vs time and bursts, fine tone
 * frequency (zero-padded FFT + parabolic interpolation), peak finding and the
 * GSM 200 kHz grid / reference-error (ppm) estimate.
 *
 * Samples are { re: Float32Array, im: Float32Array }. Frequencies are baseband
 * offsets in Hz relative to the recording's centre frequency fc.
 */
(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory();
  else root.SDRDSP = factory();
})(typeof self !== 'undefined' ? self : this, function () {
  'use strict';

  // ------------------------------------------------------------ file names
  var NAME_RE = /^(.+)_lab(\d{2})_(\d+)_(\d+)_(-?\d+(?:\.\d+)?)_(\d{8}T\d{6})\.(cf32|cs16)$/;

  function parseName(name) {
    var m = NAME_RE.exec(name.split(/[\\/]/).pop());
    if (!m) return null;
    return { team: m[1], lab: +m[2], fc: +m[3], fs: +m[4], gain: +m[5], time: m[6], ext: m[7] };
  }

  // ------------------------------------------------------------ decoding
  function decodeCf32(buf) {
    var f = new Float32Array(buf), n = f.length >> 1;
    var re = new Float32Array(n), im = new Float32Array(n);
    for (var i = 0; i < n; i++) { re[i] = f[2 * i]; im[i] = f[2 * i + 1]; }
    return { re: re, im: im };
  }

  function decodeCs16(buf, scale) {
    var s = new Int16Array(buf), n = s.length >> 1, k = scale || 1 / 2048;
    var re = new Float32Array(n), im = new Float32Array(n);
    for (var i = 0; i < n; i++) { re[i] = s[2 * i] * k; im[i] = s[2 * i + 1] * k; }
    return { re: re, im: im };
  }

  function slice(x, a, b) { return { re: x.re.subarray(a, b), im: x.im.subarray(a, b) }; }

  // ------------------------------------------------------------ FFT (radix-2, in place)
  var twCache = {};
  function twiddles(n) {
    if (twCache[n]) return twCache[n];
    var c = new Float64Array(n / 2), s = new Float64Array(n / 2);
    for (var k = 0; k < n / 2; k++) { c[k] = Math.cos(2 * Math.PI * k / n); s[k] = -Math.sin(2 * Math.PI * k / n); }
    return (twCache[n] = { c: c, s: s });
  }

  function fft(re, im) {
    var n = re.length, i, j, k, len, half, step, t;
    for (i = 1, j = 0; i < n; i++) {
      var bit = n >> 1;
      for (; j & bit; bit >>= 1) j ^= bit;
      j ^= bit;
      if (i < j) { t = re[i]; re[i] = re[j]; re[j] = t; t = im[i]; im[i] = im[j]; im[j] = t; }
    }
    var tw = twiddles(n);
    for (len = 2; len <= n; len <<= 1) {
      half = len >> 1; step = n / len;
      for (i = 0; i < n; i += len) {
        for (k = 0; k < half; k++) {
          var wr = tw.c[k * step], wi = tw.s[k * step];
          var a = i + k, b = a + half;
          var xr = re[b] * wr - im[b] * wi, xi = re[b] * wi + im[b] * wr;
          re[b] = re[a] - xr; im[b] = im[a] - xi;
          re[a] += xr; im[a] += xi;
        }
      }
    }
  }

  // ------------------------------------------------------------ windows
  // periodic=true matches scipy.signal.get_window (used by welch);
  // periodic=false matches scipy.signal.windows.blackmanharris(N) / np.hanning(N).
  function blackmanHarris(n, periodic) {
    var w = new Float64Array(n), d = periodic ? n : n - 1;
    for (var k = 0; k < n; k++) {
      var x = 2 * Math.PI * k / d;
      w[k] = 0.35875 - 0.48829 * Math.cos(x) + 0.14128 * Math.cos(2 * x) - 0.01168 * Math.cos(3 * x);
    }
    return w;
  }
  function hann(n) {
    var w = new Float64Array(n);
    for (var k = 0; k < n; k++) w[k] = 0.5 - 0.5 * Math.cos(2 * Math.PI * k / (n - 1));
    return w;
  }
  function sumSq(w) { var s = 0; for (var i = 0; i < w.length; i++) s += w[i] * w[i]; return s; }

  // ------------------------------------------------------------ helpers
  function db(v) { return 10 * Math.log10(Math.max(v, 1e-30)); }
  function dbArr(a) { var o = new Float64Array(a.length); for (var i = 0; i < a.length; i++) o[i] = db(a[i]); return o; }
  function freqAxis(n, fs) { var f = new Float64Array(n); for (var k = 0; k < n; k++) f[k] = (k - n / 2) * fs / n; return f; }

  // numpy.percentile, linear interpolation
  function percentile(arr, q) {
    var a = Float64Array.from(arr).sort(), n = a.length;
    if (!n) return NaN;
    var pos = (q / 100) * (n - 1), lo = Math.floor(pos), hi = Math.ceil(pos);
    return a[lo] + (a[hi] - a[lo]) * (pos - lo);
  }
  function median(arr) { return percentile(arr, 50); }
  function pick(arr, mask) { var o = []; for (var i = 0; i < arr.length; i++) if (mask[i]) o.push(arr[i]); return o; }
  function validMask(f, fs, frac) { frac = frac == null ? 0.4 : frac; return Array.from(f, function (v) { return Math.abs(v) <= frac * fs; }); }
  function noiseFloorDb(pdb, mask) { return percentile(mask ? pick(pdb, mask) : pdb, 20); }

  // |FFT|^2 of one windowed frame starting at sample a, fftshifted, into out (Float64Array n)
  function frameFFT(x, a, w, re, im, out) {
    var n = w.length, i;
    for (i = 0; i < n; i++) { re[i] = x.re[a + i] * w[i]; im[i] = x.im[a + i] * w[i]; }
    fft(re, im);
    var h = n >> 1;
    for (i = 0; i < n; i++) { var k = (i + h) % n; out[i] = re[k] * re[k] + im[k] * im[k]; }
  }

  // ------------------------------------------------------------ spectra
  /** Two-sided Welch PSD (FS^2/Hz), Blackman-Harris, 50 % overlap - scipy.signal.welch. */
  function welch(x, fs, nfft) {
    nfft = nfft || 1024;
    var w = blackmanHarris(nfft, true), scale = 1 / (fs * sumSq(w));
    var re = new Float64Array(nfft), im = new Float64Array(nfft), p = new Float64Array(nfft);
    var acc = new Float64Array(nfft), step = nfft >> 1, n = x.re.length, segs = 0;
    for (var a = 0; a + nfft <= n; a += step) {
      frameFFT(x, a, w, re, im, p);
      for (var i = 0; i < nfft; i++) acc[i] += p[i];
      segs++;
    }
    for (var k = 0; k < nfft; k++) acc[k] *= scale / Math.max(segs, 1);
    return { f: freqAxis(nfft, fs), psd: acc, segments: segs };
  }

  /**
   * Consecutive non-overlapping frames (no gaps): Max-Hold, mean and a waterfall
   * reduced to at most `rows` rows (each row = mean of consecutive frames), all PSD-scaled.
   * Optional band: {f0, bw} -> channel power (dBFS) of every frame.
   */
  function frames(x, fs, nfft, opts) {
    opts = opts || {};
    var w = blackmanHarris(nfft, false), scale = 1 / (fs * sumSq(w));
    var m = Math.floor(x.re.length / nfft);
    if (opts.maxFrames) m = Math.min(m, opts.maxFrames);
    var rows = Math.min(opts.rows || 300, m), per = Math.max(1, Math.floor(m / rows));
    rows = Math.floor(m / per);
    var f = freqAxis(nfft, fs), re = new Float64Array(nfft), im = new Float64Array(nfft), p = new Float64Array(nfft);
    var maxhold = new Float64Array(nfft).fill(0), mean = new Float64Array(nfft), wf = new Float32Array(rows * nfft);
    var acc = new Float64Array(nfft), band = null, sel = null, chan = null;
    // opts.avg > 1: Max Hold of block averages of `avg` frames (GNU Radio's FFT averaging + Max Hold)
    var avg = Math.max(1, opts.avg || 1), blk = avg > 1 ? new Float64Array(nfft) : null;
    if (opts.band) {
      sel = []; for (var b = 0; b < nfft; b++) if (Math.abs(f[b] - opts.band.f0) <= opts.band.bw / 2) sel.push(b);
      chan = new Float64Array(m);
    }
    for (var j = 0; j < m; j++) {
      frameFFT(x, j * nfft, w, re, im, p);
      for (var i = 0; i < nfft; i++) {
        var v = p[i] * scale;
        if (blk) blk[i] += v / avg; else if (v > maxhold[i]) maxhold[i] = v;
        mean[i] += v; acc[i] += v;
      }
      if (blk && (j + 1) % avg === 0) {
        for (var u = 0; u < nfft; u++) { if (blk[u] > maxhold[u]) maxhold[u] = blk[u]; }
        blk.fill(0);
      }
      if (chan) { var s = 0; for (var q = 0; q < sel.length; q++) s += p[sel[q]] * scale; chan[j] = db(s * fs / nfft); }
      if ((j + 1) % per === 0) {
        var r = (j + 1) / per - 1;
        if (r < rows) for (var c = 0; c < nfft; c++) { wf[r * nfft + c] = db(acc[c] / per); }
        acc.fill(0);
      }
    }
    for (var e = 0; e < nfft; e++) mean[e] /= Math.max(m, 1);
    if (chan) band = { t: Float64Array.from({ length: m }, function (_, i) { return i * nfft / fs; }), p: chan, dt: nfft / fs };
    return { f: f, maxhold: maxhold, mean: mean, frames: m, waterfall: { rows: rows, cols: nfft, data: wf, rowSeconds: per * nfft / fs }, band: band };
  }

  // ------------------------------------------------------------ bandwidth metrics
  /** x-dB bandwidth on the Max-Hold curve: x = 20 dB if peak >= 26 dB above floor, else 6 dB. */
  function xdbBandwidth(f, mhDb, floorDb, sel) {
    var idx = []; for (var i = 0; i < f.length; i++) if (sel[i]) idx.push(i);
    var ipk = 0; for (var j = 1; j < idx.length; j++) if (mhDb[idx[j]] > mhDb[idx[ipk]]) ipk = j;
    var peak = mhDb[idx[ipk]], x = peak - floorDb >= 26 ? 20 : 6;
    var lo = ipk, hi = ipk;
    while (lo > 0 && mhDb[idx[lo - 1]] >= peak - x) lo--;
    while (hi < idx.length - 1 && mhDb[idx[hi + 1]] >= peak - x) hi++;
    var fL = f[idx[lo]], fU = f[idx[hi]];
    return { x: x, peakDb: peak, fL: fL, fU: fU, Bx: fU - fL, fc: (fL + fU) / 2, aboveFloor: peak - floorDb };
  }

  function searchsorted(c, v) { var lo = 0, hi = c.length; while (lo < hi) { var m = (lo + hi) >> 1; if (c[m] < v) lo = m + 1; else hi = m; } return lo; }

  /** 99 % occupied bandwidth (0.5 % each side) on the floor-subtracted PSD inside sel. */
  function obw99(f, psd, floorLin, sel, frac) {
    frac = frac || 0.99;
    var idx = []; for (var i = 0; i < f.length; i++) if (sel[i]) idx.push(i);
    var c = new Float64Array(idx.length), s = 0;
    for (var j = 0; j < idx.length; j++) { s += Math.max(psd[idx[j]] - floorLin, 0); c[j] = s; }
    if (s <= 0) return null;
    for (j = 0; j < c.length; j++) c[j] /= s;
    var a = (1 - frac) / 2, iL = searchsorted(c, a), iU = Math.min(searchsorted(c, 1 - a), idx.length - 1);
    var df = f[1] - f[0], pw = 0;
    for (j = iL; j <= iU; j++) pw += psd[idx[j]];
    var fL = f[idx[iL]], fU = f[idx[iU]];
    return { fL: fL, fU: fU, B99: fU - fL, fc: (fL + fU) / 2, powerDbfs: db(pw * df) };
  }

  /** One "Table 7" row: Welch PSD + Max-Hold + 99 % OBW + x-dB bandwidth inside [fmin, fmax]. */
  function signalReport(x, fs, opts) {
    opts = opts || {};
    var nfft = opts.nfft || 1024;
    var wl = welch(x, fs, nfft), fr = frames(x, fs, nfft, { rows: opts.rows || 300, avg: opts.avg });
    var vm = validMask(wl.f, fs), pdb = dbArr(wl.psd), mh = dbArr(fr.maxhold);
    var floor = noiseFloorDb(pdb, vm), floorMh = noiseFloorDb(mh, vm);
    var fmin = opts.fmin != null ? opts.fmin : -0.4 * fs, fmax = opts.fmax != null ? opts.fmax : 0.4 * fs;
    var sel = Array.from(wl.f, function (v) { return v >= fmin && v <= fmax; });
    return {
      f: wl.f, psdDb: pdb, maxholdDb: mh, floor: floor, floorMh: floorMh,
      obw: obw99(wl.f, wl.psd, Math.pow(10, floor / 10), sel),
      xdb: xdbBandwidth(wl.f, mh, floorMh, sel),
      resolution: fs / nfft, frames: fr.frames, waterfall: fr.waterfall
    };
  }

  // ------------------------------------------------------------ bursts
  function findBursts(t, pdb, thr, dt, minGap) {
    var n = pdb.length, on = new Uint8Array(n), i;
    for (i = 0; i < n; i++) on[i] = pdb[i] > thr ? 1 : 0;
    if (minGap) {
      var gap = Math.round(minGap / dt), last = -1;
      for (i = 0; i < n; i++) if (on[i]) { if (last >= 0 && i - last > 1 && i - last <= gap) for (var k = last; k < i; k++) on[k] = 1; last = i; }
    }
    var out = [], start = -1;
    for (i = 0; i < n; i++) {
      if (on[i] && start < 0) start = i;
      if (!on[i] && start >= 0) { out.push([t[start], t[i - 1] + dt]); start = -1; }
    }
    if (start >= 0) out.push([t[start], t[n - 1] + dt]);
    return out;
  }

  /** Channel power vs time in [f0 +/- bw/2] from gap-free frames, bursts above floor + thr dB. */
  function burstReport(x, fs, opts) {
    var nfft = opts.nfft || 256, thrDb = opts.thr == null ? 10 : opts.thr;
    var fr = frames(x, fs, nfft, { band: { f0: opts.f0, bw: opts.bw }, rows: 1 });
    var p = fr.band.p, floor = percentile(p, 20), thr = floor + thrDb;
    var bursts = findBursts(fr.band.t, p, thr, fr.band.dt, opts.bridge || 0);
    var lens = bursts.map(function (b) { return b[1] - b[0]; });
    var starts = bursts.map(function (b) { return b[0]; });
    var per = []; for (var i = 1; i < starts.length; i++) per.push(starts[i] - starts[i - 1]);
    function st(a) { return a.length ? { mean: a.reduce(function (s, v) { return s + v; }, 0) / a.length, min: Math.min.apply(null, a), max: Math.max.apply(null, a) } : null; }
    var total = fr.band.t[fr.band.t.length - 1] + fr.band.dt, pmax = -Infinity;
    for (i = 0; i < p.length; i++) if (p[i] > pmax) pmax = p[i];
    return {
      t: fr.band.t, p: p, dt: fr.band.dt, floor: floor, thr: thr, bursts: bursts, length: st(lens), period: st(per),
      duty: lens.reduce(function (s, v) { return s + v; }, 0) / total, p50: median(p), p99: percentile(p, 99), max: pmax
    };
  }

  // ------------------------------------------------------------ peaks
  /** scipy.signal.find_peaks subset: height, distance (highest first), prominence with wlen. */
  function findPeaks(y, o) {
    o = o || {};
    var n = y.length, cand = [], i = 1;
    while (i < n - 1) {
      if (y[i] > y[i - 1]) {
        var j = i; while (j < n - 1 && y[j + 1] === y[i]) j++;
        if (j < n - 1 && y[j + 1] < y[i]) { cand.push((i + j) >> 1); i = j + 1; continue; }
        i = j + 1; continue;
      }
      i++;
    }
    if (o.height != null) cand = cand.filter(function (k) { return y[k] >= o.height; });
    if (o.distance && o.distance > 1) {
      var keep = new Uint8Array(cand.length).fill(1);
      var order = cand.map(function (k, ix) { return ix; }).sort(function (a, b) { return y[cand[b]] - y[cand[a]]; });
      order.forEach(function (ix) {
        if (!keep[ix]) return;
        for (var l = ix - 1; l >= 0 && cand[ix] - cand[l] < o.distance; l--) keep[l] = 0;
        for (var r = ix + 1; r < cand.length && cand[r] - cand[ix] < o.distance; r++) keep[r] = 0;
      });
      cand = cand.filter(function (_, ix) { return keep[ix]; });
    }
    if (o.prominence != null) {
      var half = o.wlen ? Math.floor(o.wlen / 2) : n;
      cand = cand.filter(function (k) {
        var lmin = y[k], a = k - 1, lo = Math.max(0, k - half), hi = Math.min(n - 1, k + half);
        for (; a >= lo && y[a] <= y[k]; a--) if (y[a] < lmin) lmin = y[a];
        var rmin = y[k], b = k + 1;
        for (; b <= hi && y[b] <= y[k]; b++) if (y[b] < rmin) rmin = y[b];
        return y[k] - Math.max(lmin, rmin) >= o.prominence;
      });
    }
    return cand;
  }

  // zero-padded Hann FFT power spectrum in dB, fftshifted (index k <-> (k - nfft/2) * fs / nfft)
  function paddedSpectrumDb(x, n, nfft) {
    var re = new Float64Array(nfft), im = new Float64Array(nfft), w = hann(n);
    for (var i = 0; i < n; i++) { re[i] = x.re[i] * w[i]; im[i] = x.im[i] * w[i]; }
    fft(re, im);
    var h = nfft >> 1, y = new Float64Array(nfft);
    for (var k = 0; k < nfft; k++) { var q = (k + h) % nfft; y[k] = 10 * Math.log10(re[q] * re[q] + im[q] * im[q] + 1e-30); }
    return y;
  }

  /** Tone frequency far finer than fs/N: zero-padded Hann FFT + parabolic interpolation (dB). */
  function finePeak(x, fs, fGuess, opts) {
    opts = opts || {};
    var n = Math.min(x.re.length, opts.n || (1 << 20)), nfft = opts.nfft || (1 << 21), search = opts.search || 20e3;
    var y = paddedSpectrumDb(x, n, nfft), h = nfft >> 1, df = fs / nfft;
    var k0 = Math.ceil((fGuess - search) / df) + h, k1 = Math.floor((fGuess + search) / df) + h, best = k0;
    for (var k = k0; k <= k1; k++) if (y[k] > y[best]) best = k;
    var a = y[best - 1], b = y[best], c = y[best + 1], delta = 0.5 * (a - c) / (a - 2 * b + c);
    return { f: (best - h + delta) * df, samples: n, nfft: nfft };
  }

  /** Part 2: tone vs fc + f_tx and classification of every other peak (as in the Python script). */
  function loopbackReport(x, fs, opts) {
    var nfft = opts.nfft || 1024, ftx = opts.ftx, thr = opts.thr == null ? 10 : opts.thr;
    var wl = welch(x, fs, nfft), pdb = dbArr(wl.psd), floor = noiseFloorDb(pdb, validMask(wl.f, fs));
    var tone = finePeak(x, fs, ftx), dfb = fs / nfft;
    var pk = findPeaks(pdb, { height: floor + thr, distance: Math.max(1, Math.floor(5e3 / dfb)) });
    var rows = pk.map(function (k) {
      var fb = wl.f[k], kind;
      if (Math.abs(fb - ftx) <= 2 * dfb) kind = 'tone';
      else if (Math.abs(fb) <= 2 * dfb) kind = 'centre';
      else if (Math.abs(fb + ftx) <= 2 * dfb) kind = 'image';
      else if ([2, 3, -2, -3].some(function (m) { return Math.abs(fb - m * ftx) <= 2 * dfb; })) kind = 'harmonic';
      else kind = 'other';
      return { fb: fb, level: pdb[k] - floor, kind: kind };
    }).sort(function (a, b) { return b.level - a.level; });
    return { f: wl.f, psdDb: pdb, floor: floor, tone: tone.f, toneSamples: tone.samples, peaks: rows, resolution: dfb };
  }

  /** Strong narrow peaks with fine frequencies (used by the LO test): fb in Hz, level in dB above the median. */
  function finePeaks(x, fs, opts) {
    opts = opts || {};
    var n = Math.min(x.re.length, opts.n || (1 << 20)), nfft = opts.nfft || (1 << 21);
    var y = paddedSpectrumDb(x, n, nfft), h = nfft >> 1, df = fs / nfft;
    var vm = new Array(nfft); for (var k = 0; k < nfft; k++) vm[k] = Math.abs((k - h) * df) <= 0.45 * fs;
    var floor = median(pick(y, vm));
    var pk = findPeaks(y, { height: floor + (opts.thr || 25), distance: Math.floor((opts.minSep || 5e3) / df) });
    pk = pk.filter(function (k) { return vm[k]; }).sort(function (a, b) { return y[b] - y[a]; }).slice(0, opts.max || 10);
    return pk.map(function (k) {
      var a = y[k - 1], b = y[k], c = y[k + 1], d = 0.5 * (a - c) / (a - 2 * b + c);
      return { fb: (k - h + d) * df, level: b - floor };
    });
  }

  /**
   * LO test: runs = [{lo, peaks:[{label, level}]}] (lo = lo_shift in Hz, label = RF label in Hz).
   * Each peak is modelled as label = a + s * lo_shift with an integer slope s and tracked across runs.
   * The handout's classes: s = 0 real signal at RX1, s = 1 receiver DC / LO leakage, s = 2 receiver I/Q image.
   */
  function loTest(runs, opts) {
    opts = opts || {};
    var tol = opts.tol || 3e3, smax = opts.smax || 5;
    var ref = runs.reduce(function (a, r) { return r.peaks.length > a.peaks.length ? r : a; });
    var tracks = [];
    ref.peaks.forEach(function (p) {
      var best = null;
      for (var s = 0; Math.abs(s) <= smax; s = s > 0 ? -s : 1 - s) {
        var a = p.label - s * ref.lo, hits = 0, labels = [];
        runs.forEach(function (r) {
          var want = a + s * r.lo, m = null;
          r.peaks.forEach(function (q) { if (Math.abs(q.label - want) <= tol && (!m || q.level > m.level)) m = q; });
          if (m) hits++;
          labels.push(m ? { lo: r.lo, label: m.label, level: m.level } : { lo: r.lo, label: null, level: null });
        });
        if (!best || hits > best.hits) best = { s: s, a: a, hits: hits, labels: labels };
        if (hits === runs.length) break;
      }
      // a real track is seen in every run (a peak that hides under a stronger one still matches it);
      // tracks missing in a run are coincidences of unrelated peaks
      var dup = tracks.some(function (t) { return t.s === best.s && Math.abs(t.a - best.a) <= tol; });
      if (best.hits === runs.length && !dup) tracks.push(best);
    });
    return tracks.sort(function (a, b) { return a.a - b.a; });
  }

  // ------------------------------------------------------------ GSM grid / reference error
  function gsmReport(x, fs, fc, opts) {
    opts = opts || {};
    var nfft = opts.nfft || 4096, grid = opts.grid || 200e3, thr = opts.thr == null ? 10 : opts.thr, half = opts.half || 90e3;
    var wl = welch(x, fs, nfft), pdb = dbArr(wl.psd), vm = validMask(wl.f, fs), floor = noiseFloorDb(pdb, vm), df = wl.f[1] - wl.f[0];
    var masked = Float64Array.from(pdb, function (v, i) { return vm[i] ? v : -300; });
    var pk = findPeaks(masked, { height: floor + thr, prominence: thr, wlen: Math.floor(600e3 / df) | 1, distance: Math.max(1, Math.floor(150e3 / df)) });
    var floorLin = Math.pow(10, floor / 10), rows = [];
    pk.forEach(function (k) {
      if (Math.abs(wl.f[k]) + half > 0.4 * fs) return;
      var fb = wl.f[k];
      for (var it = 0; it < 10; it++) {
        var sw = 0, sp = 0;
        for (var i = 0; i < wl.f.length; i++) if (Math.abs(wl.f[i] - fb) <= half) { var p = Math.max(wl.psd[i] - floorLin, 0); sw += wl.f[i] * p; sp += p; }
        var nf = sw / sp;
        if (Math.abs(nf - fb) < df / 20) break;
        fb = nf;
      }
      var frf = fc + fb, g = Math.round(frf / grid) * grid;
      rows.push({ f: frf, grid: g, offset: frf - g, snr: pdb[k] - floor, arfcn: g >= 935e6 && g <= 960e6 ? Math.round((g - 935e6) / 200e3) : null });
    });
    var offs = rows.map(function (r) { return r.offset; }), med = offs.length ? median(offs) : NaN, sd = 0;
    if (offs.length > 1) { var mu = offs.reduce(function (s, v) { return s + v; }, 0) / offs.length; sd = Math.sqrt(offs.reduce(function (s, v) { return s + (v - mu) * (v - mu); }, 0) / (offs.length - 1)); }
    var unc = offs.length > 1 ? sd / Math.sqrt(offs.length) : df;
    return { f: wl.f, psdDb: pdb, floor: floor, rows: rows, offset: med, offsetUnc: unc, eps: -med / fc * 1e6, epsUnc: unc / fc * 1e6, resolution: df };
  }

  // ------------------------------------------------------------ Question 1: trusted part of the display
  /** Smoothed noise-floor shape (running 20th percentile); trusted = where it stays within tolDb of the centre. */
  function trustedFraction(f, pdb, fs, tolDb, bins) {
    var n = pdb.length, k = bins || Math.max(9, n >> 6), sm = new Float64Array(n);
    for (var i = 0; i < n; i++) {
      var a = Math.max(0, i - k), b = Math.min(n, i + k + 1);
      sm[i] = percentile(Array.prototype.slice.call(pdb, a, b), 20);
    }
    var c = n >> 1, ref = median(Array.prototype.slice.call(sm, c - (n >> 4), c + (n >> 4))), lo = c, hi = c;
    tolDb = tolDb || 1;
    while (lo > 0 && Math.abs(sm[lo - 1] - ref) <= tolDb) lo--;
    while (hi < n - 1 && Math.abs(sm[hi + 1] - ref) <= tolDb) hi++;
    var edge = Math.min(Math.abs(f[lo]), Math.abs(f[hi]));
    return { floorShape: sm, centre: ref, edge: edge, fraction: 2 * edge / fs };
  }

  return {
    parseName: parseName, decodeCf32: decodeCf32, decodeCs16: decodeCs16, slice: slice,
    fft: fft, blackmanHarris: blackmanHarris, hann: hann, db: db, dbArr: dbArr, percentile: percentile, median: median,
    welch: welch, frames: frames, validMask: validMask, noiseFloorDb: noiseFloorDb,
    xdbBandwidth: xdbBandwidth, obw99: obw99, signalReport: signalReport,
    findBursts: findBursts, burstReport: burstReport, findPeaks: findPeaks,
    finePeak: finePeak, finePeaks: finePeaks, loopbackReport: loopbackReport, loTest: loTest,
    gsmReport: gsmReport, trustedFraction: trustedFraction
  };
});
