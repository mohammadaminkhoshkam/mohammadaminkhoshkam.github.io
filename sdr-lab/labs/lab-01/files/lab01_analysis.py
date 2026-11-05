"""
Lab 01 post-session analysis of raw .cf32 recordings.

Every number comes from the raw I/Q file (complex64, no header) and its
standard name  teamID_labNN_fc_fs_gain_timestamp.cf32.

Usage (radioconda prompt, project folder):
    python analysis/lab01_analysis.py info      recordings/*.cf32
    python analysis/lab01_analysis.py signal    FILE [--fmin=-1e6 --fmax=1e6]
    python analysis/lab01_analysis.py bursts    FILE --f0=-1.08e6 --bw 100e3
    python analysis/lab01_analysis.py loopback  FILE --ftx 250e3
    python analysis/lab01_analysis.py gsm       FILE [--grid 200e3]
    python analysis/lab01_analysis.py stitch    FILE FILE ... [--out name]
    python analysis/lab01_analysis.py occupancy FILE [--chan 200e3]
    python analysis/lab01_analysis.py sigmf     FILE [FILE ...]

Frequencies given on the command line are baseband offsets in Hz
(relative to the file's fc). Write negative values as --f0=-1.08e6.
Figures go to ./figures, one PNG per analysis, with axes, units and title.
"""
import argparse
import datetime as dt
import json
import os
import re
import sys

import numpy as np
from scipy import signal

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt  # noqa: E402

NAME_RE = re.compile(
    r'^(?P<team>.+)_lab(?P<lab>\d{2})_(?P<fc>\d+)_(?P<fs>\d+)_'
    r'(?P<gain>-?\d+(?:\.\d+)?)_(?P<ts>\d{8}T\d{6})\.cf32$')

FIG_DIR = 'figures'


# =============================================================== file I/O
def parse_name(path):
    m = NAME_RE.match(os.path.basename(path))
    if not m:
        raise ValueError('not a standard lab file name: ' + os.path.basename(path))
    d = m.groupdict()
    return dict(team=d['team'], lab=int(d['lab']), fc=float(d['fc']),
                fs=float(d['fs']), gain=float(d['gain']),
                time=dt.datetime.strptime(d['ts'], '%Y%m%dT%H%M%S'))


def load(path, max_seconds=None):
    meta = parse_name(path)
    count = -1 if max_seconds is None else int(max_seconds * meta['fs'])
    x = np.fromfile(path, dtype=np.complex64, count=count)
    return x, meta


def save_fig(fig, path, kind):
    os.makedirs(FIG_DIR, exist_ok=True)
    out = os.path.join(FIG_DIR, os.path.splitext(os.path.basename(path))[0]
                       + '_' + kind + '.png')
    fig.savefig(out, dpi=130, bbox_inches='tight')
    plt.close(fig)
    print('  figure:', out)
    return out


def short_title(meta):
    return '{} lab{:02d}  fc = {:.3f} MHz, fs = {:.2f} MS/s, gain = {:.0f} dB'.format(
        meta['team'], meta['lab'], meta['fc'] / 1e6, meta['fs'] / 1e6, meta['gain'])


# ============================================================ spectra
def welch_psd(x, fs, nfft=1024):
    """Two-sided Welch PSD (linear, FS^2/Hz), frequency axis in baseband Hz."""
    f, p = signal.welch(x, fs=fs, window='blackmanharris', nperseg=nfft,
                        noverlap=nfft // 2, return_onesided=False,
                        detrend=False, scaling='density')
    return np.fft.fftshift(f), np.fft.fftshift(p)


def frame_spectra(x, fs, nfft=1024, max_frames=None):
    """|X_m[k]|^2 of consecutive non-overlapping Blackman-Harris frames.
    Returns (f_baseband, t_frame_start, P[m, k]) normalised as a PSD."""
    m = len(x) // nfft
    if max_frames is not None:
        m = min(m, max_frames)
    w = signal.windows.blackmanharris(nfft).astype(np.float32)
    frames = x[:m * nfft].reshape(m, nfft) * w
    X = np.fft.fftshift(np.fft.fft(frames, axis=1), axes=1)
    P = (np.abs(X) ** 2) / (fs * np.sum(w ** 2))
    f = (np.arange(nfft) - nfft // 2) * fs / nfft
    t = np.arange(m) * nfft / fs
    return f, t, P


def db(v):
    return 10 * np.log10(np.maximum(v, 1e-30))


def noise_floor_db(p_db):
    """Noise floor estimate: 20th percentile of the spectrum (robust to signals)."""
    return float(np.percentile(p_db, 20))


def valid_mask(f, fs, frac=0.4):
    """Bins inside the trusted middle 80 % of the display (|f_bb| <= 0.4 fs)."""
    return np.abs(f) <= frac * fs


# ======================================================= bandwidth metrics
def xdb_bandwidth(f, maxhold_db, floor_db, sel):
    """x-dB bandwidth on the Max-Hold curve (lab rule: x = 20 dB if the peak is
    >= 26 dB above the floor, else x = 6 dB). Edges are the outermost bins of
    the contiguous region around the peak that stay above peak - x."""
    idx = np.flatnonzero(sel)
    seg = maxhold_db[idx]
    ipk = int(np.argmax(seg))
    peak = float(seg[ipk])
    x = 20.0 if peak - floor_db >= 26.0 else 6.0
    above = seg >= peak - x
    lo = ipk
    while lo > 0 and above[lo - 1]:
        lo -= 1
    hi = ipk
    while hi < len(seg) - 1 and above[hi + 1]:
        hi += 1
    fL, fU = f[idx[lo]], f[idx[hi]]
    return dict(x=x, peak_db=peak, fL=fL, fU=fU, Bx=fU - fL, fc=(fL + fU) / 2)


def obw99(f, psd, floor_lin, sel, frac=0.99):
    """99 % occupied bandwidth (ITU-R SM.443 beta/2 = 0.5 % each side), computed
    on the PSD with the noise floor subtracted, inside the selected window."""
    idx = np.flatnonzero(sel)
    p = np.clip(psd[idx] - floor_lin, 0, None)
    c = np.cumsum(p)
    if c[-1] <= 0:
        return None
    c /= c[-1]
    a = (1 - frac) / 2
    iL = int(np.searchsorted(c, a))
    iU = int(np.searchsorted(c, 1 - a))
    fL, fU = f[idx[iL]], f[idx[min(iU, len(idx) - 1)]]
    df = f[1] - f[0]
    power = float(np.sum(psd[idx[iL:iU + 1]]) * df)  # FS^2, incl. noise in band
    return dict(fL=fL, fU=fU, B99=fU - fL, fc=(fL + fU) / 2,
                power_dbfs=db(power))


# ================================================================ commands
def cmd_info(args):
    for path in args.files:
        meta = parse_name(path)
        n = os.path.getsize(path) // 8
        print('{}\n  team={team} lab={lab:02d} fc={fc:.0f} Hz fs={fs:.0f} S/s '
              'gain={gain} dB time={time}\n  samples={n}  duration={d:.3f} s  '
              'size check 8*N = {s} bytes'.format(
                  os.path.basename(path), n=n, d=n / meta['fs'],
                  s=8 * n, **meta))


def cmd_signal(args):
    """Welch PSD, 99 % OBW, x-dB bandwidth (Max Hold), waterfall: one Table 7 row."""
    x, meta = load(args.file, args.max_seconds)
    fs, fc = meta['fs'], meta['fc']
    f, psd = welch_psd(x, fs, args.nfft)
    fF, tF, P = frame_spectra(x, fs, args.nfft)
    maxhold = db(P.max(axis=0))
    floor = noise_floor_db(db(psd[valid_mask(f, fs)]))
    fmin = args.fmin if args.fmin is not None else -0.4 * fs
    fmax = args.fmax if args.fmax is not None else 0.4 * fs
    sel = (f >= fmin) & (f <= fmax)

    o = obw99(f, psd, 10 ** (floor / 10), sel)
    floor_mh = noise_floor_db(maxhold[valid_mask(fF, fs)])
    xb = xdb_bandwidth(fF, maxhold, floor_mh, (fF >= fmin) & (fF <= fmax))

    print('\n' + os.path.basename(args.file))
    print('  noise floor (Welch)    : {:.1f} dBFS/Hz'.format(floor))
    if o:
        print('  99% OBW                : {:.1f} kHz   [{:.4f} .. {:.4f} MHz]'.format(
            o['B99'] / 1e3, (fc + o['fL']) / 1e6, (fc + o['fU']) / 1e6))
        print('  centre (99% edges)     : {:.4f} MHz'.format((fc + o['fc']) / 1e6))
        print('  power in 99% band      : {:.1f} dBFS'.format(o['power_dbfs']))
    print('  Max-Hold peak          : {:.1f} dB ({:.1f} dB above floor) -> x = {:.0f} dB'.format(
        xb['peak_db'], xb['peak_db'] - floor_mh, xb['x']))
    print('  x-dB bandwidth B_x     : {:.1f} kHz   f_c,sig = {:.4f} MHz'.format(
        xb['Bx'] / 1e3, (fc + xb['fc']) / 1e6))
    print('  frequency resolution   : {:.2f} kHz (fs/N)'.format(fs / args.nfft / 1e3))

    # ---- figure: PSD + Max Hold + waterfall
    fig, (a1, a2) = plt.subplots(2, 1, figsize=(10, 8), sharex=True,
                                 gridspec_kw=dict(height_ratios=[1, 1.3]))
    fr = (fc + f) / 1e6
    a1.plot((fc + fF) / 1e6, maxhold, color='0.6', lw=0.8, label='Max Hold')
    a1.plot(fr, db(psd), color='C0', lw=1.0, label='Welch average')
    a1.axhline(floor, color='k', ls=':', lw=0.8, label='noise floor')
    if o:
        for e in (o['fL'], o['fU']):
            a1.axvline((fc + e) / 1e6, color='C3', ls='--', lw=0.9)
        a1.axvspan((fc + o['fL']) / 1e6, (fc + o['fU']) / 1e6, color='C3',
                   alpha=0.08, label='99 % OBW = {:.1f} kHz'.format(o['B99'] / 1e3))
    a1.axvspan((fc - fs / 2) / 1e6, (fc - 0.4 * fs) / 1e6, color='0.85', zorder=0)
    a1.axvspan((fc + 0.4 * fs) / 1e6, (fc + fs / 2) / 1e6, color='0.85', zorder=0)
    a1.set_ylabel('PSD (dBFS/Hz)')
    a1.legend(loc='upper right', fontsize=8)
    a1.grid(alpha=0.3)
    a1.set_title(short_title(meta))
    _waterfall(a2, fF, tF, P, fc)
    a2.set_xlabel('Frequency (MHz)')
    save_fig(fig, args.file, 'psd')
    return dict(o=o, xb=xb, floor=floor)


def _waterfall(ax, f, t, P, fc, rows=600):
    m = P.shape[0]
    k = max(1, m // rows)
    Pa = P[:(m // k) * k].reshape(m // k, k, -1).mean(axis=1)
    img = db(Pa)
    vmin, vmax = np.percentile(img, 5), img.max()
    ext = [(fc + f[0]) / 1e6, (fc + f[-1]) / 1e6, t[(m // k) * k - 1] * 1e3, 0]
    im = ax.imshow(img, aspect='auto', extent=ext, cmap='viridis',
                   vmin=vmin, vmax=vmax, interpolation='nearest')
    ax.set_ylabel('Time (ms)')
    # Inset colorbar: does not shrink the axes, so the frequency axis stays
    # aligned with the spectrum panel above it.
    cax = ax.inset_axes([1.01, 0.0, 0.015, 1.0])
    plt.colorbar(im, cax=cax, label='dBFS/Hz')


def band_power(x, fs, f0, bw, nfft=256):
    """Power vs time inside [f0 - bw/2, f0 + bw/2] (baseband), resolution nfft/fs."""
    f, t, P = frame_spectra(x, fs, nfft)
    sel = np.abs(f - f0) <= bw / 2
    return t, db(P[:, sel].sum(axis=1) * (fs / nfft))


def find_bursts(t, p_db, thr_db, dt_frame, min_gap=None):
    on = p_db > thr_db
    if min_gap:  # bridge short drops (OOK bits inside one burst)
        gap = int(round(min_gap / dt_frame))
        idx = np.flatnonzero(on)
        for a, b in zip(idx[:-1], idx[1:]):
            if 1 < b - a <= gap:
                on[a:b] = True
    edges = np.diff(on.astype(int))
    starts = list(np.flatnonzero(edges == 1) + 1)
    stops = list(np.flatnonzero(edges == -1) + 1)
    if on[0]:
        starts.insert(0, 0)
    if on[-1]:
        stops.append(len(on))
    return [(t[a], t[b - 1] + dt_frame) for a, b in zip(starts, stops)]


def cmd_bursts(args):
    """Burst lengths and repetition period inside one channel (gap-free file)."""
    x, meta = load(args.file, args.max_seconds)
    fs, fc = meta['fs'], meta['fc']
    t, p = band_power(x, fs, args.f0, args.bw, args.nfft)
    dt_frame = args.nfft / fs
    floor = float(np.percentile(p, 20))
    thr = floor + args.thr
    bursts = find_bursts(t, p, thr, dt_frame, args.bridge)
    lens = np.array([b - a for a, b in bursts])
    starts = np.array([a for a, _ in bursts])
    print('\n' + os.path.basename(args.file))
    print('  channel: {:.4f} MHz +/- {:.0f} kHz, time resolution {:.1f} us'.format(
        (fc + args.f0) / 1e6, args.bw / 2e3, dt_frame * 1e6))
    print('  floor {:.1f} dB, threshold {:.1f} dB, bursts found: {}'.format(
        floor, thr, len(bursts)))
    for i, (a, b) in enumerate(bursts):
        print('    #{:<3d} start {:9.3f} ms  length {:8.3f} ms'.format(
            i + 1, a * 1e3, (b - a) * 1e3))
    if len(bursts):
        print('  length : mean {:.3f} ms  (min {:.3f}, max {:.3f})'.format(
            lens.mean() * 1e3, lens.min() * 1e3, lens.max() * 1e3))
    if len(bursts) > 1:
        per = np.diff(starts)
        print('  period : mean {:.3f} ms  (min {:.3f}, max {:.3f})'.format(
            per.mean() * 1e3, per.min() * 1e3, per.max() * 1e3))
        print('  duty cycle: {:.1f} %'.format(100 * lens.sum() / (t[-1] + dt_frame)))

    fig, (a1, a2) = plt.subplots(2, 1, figsize=(10, 7),
                                 gridspec_kw=dict(height_ratios=[1, 1.4]))
    a1.plot(t * 1e3, p, lw=0.7)
    a1.axhline(thr, color='C3', ls='--', lw=0.9, label='threshold')
    for a, b in bursts:
        a1.axvspan(a * 1e3, b * 1e3, color='C1', alpha=0.15)
    a1.set_xlabel('Time (ms)')
    a1.set_ylabel('Channel power (dBFS)')
    a1.set_title('Bursts at {:.4f} MHz - {}'.format((fc + args.f0) / 1e6, short_title(meta)),
                 fontsize=9)
    a1.legend(fontsize=8)
    a1.grid(alpha=0.3)
    fF, tF, P = frame_spectra(x, fs, 1024)
    _waterfall(a2, fF, tF, P, fc)
    a2.set_xlabel('Frequency (MHz)')
    save_fig(fig, args.file, 'bursts')
    return dict(bursts=bursts)


def fine_peak(x, fs, f_guess, search=20e3, nfft=None):
    """Tone frequency much finer than fs/N: long zero-padded Hann FFT plus
    parabolic interpolation of the log magnitude."""
    n = min(len(x), 1 << 20)
    nfft = nfft or (1 << 22)
    w = np.hanning(n).astype(np.float32)
    X = np.fft.fftshift(np.fft.fft(x[:n] * w, nfft))
    f = (np.arange(nfft) - nfft // 2) * fs / nfft
    sel = np.flatnonzero(np.abs(f - f_guess) <= search)
    k = sel[np.argmax(np.abs(X[sel]))]
    a, b, c = (20 * np.log10(np.abs(X[k + i]) + 1e-30) for i in (-1, 0, 1))
    delta = 0.5 * (a - c) / (a - 2 * b + c)
    return f[k] + delta * fs / nfft, n


def cmd_loopback(args):
    """Section 2: tone frequency vs fc + f_tx, and classify every other peak."""
    x, meta = load(args.file, args.max_seconds)
    fs, fc = meta['fs'], meta['fc']
    f, psd = welch_psd(x, fs, args.nfft)
    pdb = db(psd)
    floor = noise_floor_db(pdb[valid_mask(f, fs)])
    f_est, n = fine_peak(x, fs, args.ftx)
    df_fft = fs / args.nfft
    print('\n' + os.path.basename(args.file))
    print('  expected tone      : {:.6f} MHz (fc + f_tx = {:.3f} + {:.3f})'.format(
        (fc + args.ftx) / 1e6, fc / 1e6, args.ftx / 1e6))
    print('  measured tone      : {:.6f} MHz'.format((fc + f_est) / 1e6))
    print('  difference         : {:+.1f} Hz  (display resolution fs/N = {:.0f} Hz,'
          ' estimator span {} samples)'.format(f_est - args.ftx, df_fft, n))
    print('  note: TX and RX share the same reference clock, so its ppm error cancels.')

    peaks, props = signal.find_peaks(pdb, height=floor + args.thr,
                                     distance=max(1, int(5e3 / df_fft)))
    rows = []
    for k in peaks:
        fb = f[k]
        if abs(fb - args.ftx) <= 2 * df_fft:
            kind = 'real tone (fc + f_tx)'
        elif abs(fb) <= 2 * df_fft:
            kind = 'centre artifact: LO leakage / DC offset (moves with LO)'
        elif abs(fb + args.ftx) <= 2 * df_fft:
            kind = 'I/Q image (-f_tx): gain/phase imbalance'
        elif any(abs(fb - m * args.ftx) <= 2 * df_fft for m in (2, 3, -2, -3)):
            kind = 'harmonic / intermod of the tone'
        else:
            kind = 'other spur'
        rows.append((fc + fb, pdb[k] - floor, kind))
    print('  peaks above floor + {:.0f} dB:'.format(args.thr))
    for fr, h, kind in sorted(rows, key=lambda r: -r[1]):
        print('    {:12.6f} MHz  {:5.1f} dB  {}'.format(fr / 1e6, h, kind))

    fig, ax = plt.subplots(figsize=(10, 4.5))
    ax.plot((fc + f) / 1e6, pdb, lw=0.9)
    ax.axhline(floor, color='k', ls=':', lw=0.8)
    for fr, h, kind in rows:
        ax.annotate(kind.split(':')[0], ((fr) / 1e6, floor + h), fontsize=7,
                    xytext=(0, 6), textcoords='offset points', ha='center')
    ax.set_xlabel('Frequency (MHz)')
    ax.set_ylabel('PSD (dBFS/Hz)')
    ax.set_title('Loopback - ' + short_title(meta), fontsize=9)
    ax.grid(alpha=0.3)
    save_fig(fig, args.file, 'loopback')
    return dict(f_est=f_est, peaks=rows)


def cmd_gsm(args):
    """Reference error from GSM carriers: label offset from the 200 kHz grid."""
    x, meta = load(args.file, args.max_seconds)
    fs, fc = meta['fs'], meta['fc']
    nfft = args.nfft
    f, psd = welch_psd(x, fs, nfft)
    pdb = db(psd)
    vm = valid_mask(f, fs)
    floor = noise_floor_db(pdb[vm])
    df = f[1] - f[0]
    # Prominence (not just height) rejects the shoulders/sidelobes on the skirt
    # of a strong GMSK carrier, which would otherwise count as extra carriers.
    peaks, _ = signal.find_peaks(np.where(vm, pdb, -300), height=floor + args.thr,
                                 prominence=args.thr, wlen=int(600e3 / df) | 1,
                                 distance=max(1, int(150e3 / df)))
    rows = []
    half = 90e3
    for k in peaks:
        # Skip carriers whose window reaches the untrusted edge (roll-off/aliases).
        if abs(f[k]) + half > 0.4 * fs:
            continue
        # Power-weighted centroid over +/- 90 kHz (GMSK spectrum is symmetric),
        # re-centred until it converges: a window centred on the noisy peak bin
        # of the flat top would bias the result toward that bin.
        fb = f[k]
        for _ in range(10):
            sel = np.abs(f - fb) <= half
            p = np.clip(psd[sel] - 10 ** (floor / 10), 0, None)
            new = float(np.sum(f[sel] * p) / np.sum(p))
            if abs(new - fb) < df / 20:
                break
            fb = new
        f_rf = fc + fb
        grid = round(f_rf / args.grid) * args.grid
        rows.append((f_rf, grid, f_rf - grid, pdb[k] - floor))
    print('\n' + os.path.basename(args.file))
    if not rows:
        print('  no carriers found above floor + {} dB'.format(args.thr))
        return None
    print('  {:>14s} {:>14s} {:>10s} {:>8s} {:>6s}'.format(
        'label (MHz)', 'grid (MHz)', 'offset Hz', 'SNR dB', 'ARFCN'))
    for f_rf, grid, off, snr in rows:
        n = (grid - 935e6) / 200e3 if 935e6 <= grid <= 960e6 else float('nan')
        print('  {:14.6f} {:14.6f} {:10.0f} {:8.1f} {:>6s}'.format(
            f_rf / 1e6, grid / 1e6, off, snr, '' if np.isnan(n) else '{:.0f}'.format(n)))
    offs = np.array([r[2] for r in rows])
    med = float(np.median(offs))
    unc = float(np.std(offs, ddof=1) / np.sqrt(len(offs))) if len(offs) > 1 else df
    eps = -med / fc * 1e6
    print('  median label offset    : {:+.0f} Hz (+/- {:.0f} Hz, std. error)'.format(med, unc))
    print('  reference error eps    : {:+.2f} ppm  (+/- {:.2f} ppm)'.format(eps, unc / fc * 1e6))
    print('  sign convention: label = f_true - eps*fc, so eps > 0 means the Pluto clock is fast.')
    print('  limits: bin width {:.0f} Hz, network carriers are themselves within 0.05 ppm.'.format(df))

    fig, ax = plt.subplots(figsize=(10, 4.5))
    ax.plot((fc + f) / 1e6, pdb, lw=0.9)
    lo, hi = fc - 0.4 * fs, fc + 0.4 * fs
    for gl in np.arange(np.ceil(lo / args.grid), np.floor(hi / args.grid) + 1) * args.grid:
        ax.axvline(gl / 1e6, color='0.75', lw=0.6, zorder=0)
    for f_rf, grid, off, snr in rows:
        ax.annotate('{:+.1f} kHz'.format(off / 1e3), (f_rf / 1e6, floor + snr),
                    xytext=(0, 6), textcoords='offset points', ha='center', fontsize=8)
    ax.set_xlim(lo / 1e6, hi / 1e6)
    ax.set_xlabel('Frequency (MHz)  - grey lines: 200 kHz channel grid')
    ax.set_ylabel('PSD (dBFS/Hz)')
    ax.set_title('GSM carriers, eps = {:+.2f} ppm - {}'.format(eps, short_title(meta)), fontsize=9)
    ax.grid(alpha=0.2, axis='y')
    save_fig(fig, args.file, 'gsm')
    return dict(rows=rows, eps_ppm=eps, offset=med)


def cmd_stitch(args):
    """Combine several recordings (a manual sweep) into one wide spectrum,
    keeping only the trusted middle |f_bb| <= 0.4 fs of each."""
    segs = []
    for path in args.files:
        x, meta = load(path, args.max_seconds)
        f, psd = welch_psd(x, meta['fs'], args.nfft)
        mh = db(frame_spectra(x, meta['fs'], args.nfft)[2].max(axis=0))
        vm = valid_mask(f, meta['fs'])
        segs.append(((meta['fc'] + f[vm]) / 1e6, db(psd[vm]), mh[vm], meta))
    fig, ax = plt.subplots(figsize=(12, 4.8))
    for i, (fr, p, mh, meta) in enumerate(segs):
        ax.plot(fr, mh, color='0.7', lw=0.6, label='Max Hold' if i == 0 else None)
        ax.plot(fr, p, color='C{}'.format(i % 10), lw=0.9,
                label='step {} (fc {:.0f} MHz)'.format(i + 1, meta['fc'] / 1e6))
    ax.set_xlabel('Frequency (MHz)')
    ax.set_ylabel('PSD (dBFS/Hz)')
    ax.set_title(args.title or 'Stitched sweep ({} steps, middle 80 % of each)'.format(len(segs)))
    ax.grid(alpha=0.3)
    ax.legend(fontsize=7, ncol=2)
    os.makedirs(FIG_DIR, exist_ok=True)
    out = os.path.join(FIG_DIR, (args.out or 'stitched') + '.png')
    fig.savefig(out, dpi=130, bbox_inches='tight')
    plt.close(fig)
    print('  figure:', out)
    # step-seam check: overlap regions should agree
    for a, b in zip(segs[:-1], segs[1:]):
        lo, hi = max(a[0][0], b[0][0]), min(a[0][-1], b[0][-1])
        if hi > lo:
            pa = np.interp(np.linspace(lo, hi, 50), a[0], a[1])
            pb = np.interp(np.linspace(lo, hi, 50), b[0], b[1])
            print('  overlap {:.2f}-{:.2f} MHz: mean level difference {:.2f} dB'.format(
                lo, hi, float(np.mean(pa - pb))))


def cmd_occupancy(args):
    """Fraction of time each channel is above floor + thr (optional exercise 4)."""
    x, meta = load(args.file, args.max_seconds)
    fs, fc = meta['fs'], meta['fc']
    f, t, P = frame_spectra(x, fs, args.nfft)
    floor = noise_floor_db(db(np.median(P, axis=0))[valid_mask(f, fs)])
    edges = np.arange(-0.4 * fs, 0.4 * fs + 1, args.chan)
    print('\n' + os.path.basename(args.file))
    print('  floor {:.1f} dBFS/Hz, threshold floor + {:.0f} dB, {} frames of {:.0f} us'.format(
        floor, args.thr, len(t), args.nfft / fs * 1e6))
    occ = []
    for a, b in zip(edges[:-1], edges[1:]):
        sel = (f >= a) & (f < b)
        busy = db(P[:, sel].mean(axis=1)) > floor + args.thr
        occ.append(busy.mean())
        if busy.mean() > 0:
            print('  {:10.4f} MHz  {:5.1f} %'.format((fc + (a + b) / 2) / 1e6, 100 * busy.mean()))
    return occ


def cmd_sigmf(args):
    """Write a SigMF .sigmf-meta next to each recording (optional exercise 5)."""
    for path in args.files:
        meta = parse_name(path)
        base = os.path.splitext(path)[0]
        doc = {
            'global': {
                'core:datatype': 'cf32_le',
                'core:sample_rate': meta['fs'],
                'core:version': '1.0.0',
                'core:author': meta['team'],
                'core:hw': 'ADALM-Pluto (AD9363), RX1, manual gain {} dB'.format(meta['gain']),
                'core:description': 'SDR Lab {:02d} recording'.format(meta['lab']),
                'core:recorder': 'SDR Lab IQ Recorder (GNU Radio 3.10)',
            },
            'captures': [{
                'core:sample_start': 0,
                'core:frequency': meta['fc'],
                'core:datetime': meta['time'].strftime('%Y-%m-%dT%H:%M:%SZ'),
            }],
            'annotations': [],
        }
        # SigMF pairs NAME.sigmf-meta with NAME.sigmf-data; the .cf32 is not renamed,
        # so the dataset file is named explicitly.
        doc['global']['core:dataset'] = os.path.basename(path)
        with open(base + '.sigmf-meta', 'w', encoding='utf-8') as fp:
            json.dump(doc, fp, indent=2)
        print('  wrote', base + '.sigmf-meta')


# ==================================================================== CLI
def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd', required=True)

    def common(p, many=False):
        if many:
            p.add_argument('files', nargs='+')
        else:
            p.add_argument('file')
        p.add_argument('--nfft', type=int, default=1024)
        p.add_argument('--max-seconds', type=float, default=None,
                       help='only read the first seconds of the file')
        return p

    p = sub.add_parser('info')
    p.add_argument('files', nargs='+')
    p = common(sub.add_parser('signal'))
    p.add_argument('--fmin', type=float, help='baseband Hz (default -0.4 fs)')
    p.add_argument('--fmax', type=float, help='baseband Hz (default +0.4 fs)')
    p = common(sub.add_parser('bursts'))
    p.set_defaults(nfft=256)
    p.add_argument('--f0', type=float, required=True, help='channel centre, baseband Hz')
    p.add_argument('--bw', type=float, default=100e3, help='channel width Hz')
    p.add_argument('--thr', type=float, default=10.0, help='dB above floor')
    p.add_argument('--bridge', type=float, default=0.0,
                   help='merge gaps shorter than this (s), e.g. 2e-3 for OOK bits')
    p = common(sub.add_parser('loopback'))
    p.add_argument('--ftx', type=float, default=250e3)
    p.add_argument('--thr', type=float, default=10.0)
    p = common(sub.add_parser('gsm'))
    p.set_defaults(nfft=4096)
    p.add_argument('--grid', type=float, default=200e3)
    p.add_argument('--thr', type=float, default=10.0)
    p = common(sub.add_parser('stitch'), many=True)
    p.add_argument('--out')
    p.add_argument('--title')
    p = common(sub.add_parser('occupancy'))
    p.add_argument('--chan', type=float, default=200e3)
    p.add_argument('--thr', type=float, default=10.0)
    p = sub.add_parser('sigmf')
    p.add_argument('files', nargs='+')

    args = ap.parse_args(argv)
    return {'info': cmd_info, 'signal': cmd_signal, 'bursts': cmd_bursts,
            'loopback': cmd_loopback, 'gsm': cmd_gsm, 'stitch': cmd_stitch,
            'occupancy': cmd_occupancy, 'sigmf': cmd_sigmf}[args.cmd](args)


if __name__ == '__main__':
    main()
