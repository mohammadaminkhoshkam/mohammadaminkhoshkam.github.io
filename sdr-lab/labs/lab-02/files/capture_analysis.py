#!/usr/bin/env python3
"""Lab 2 - analysis of the hardware I/Q captures (ADALM-Pluto, 8.192 MS/s, cf32).

For every capture written by the course recorder block it computes
  * total level, peak sample and the share of clipped samples,
  * the averaged power spectrum (Welch, Hann, 250 Hz bins),
  * the readings of the five meters of lab02_combined.grc, reproduced from the
    spectrum with the exact FIR responses of the flowgraph (400 kHz noise meter at
    -500 kHz, 10 kHz tone meters at f1, f2, 2f1-f2, 2f2-f1),
  * "narrow" tone / IM3 powers (+-1.5 kHz around each line) that are free of the
    leakage of the neighbouring tone through the meter filter,
and classifies the capture (noise off, noise on, one tone, two tones).

Burst-resolved part.  The transmitter of the same Pluto could not be fed fast enough at
8.192 MS/s, so its output is ON only about two thirds of the time (bursts of ~2 ms
separated by ~1.5 ms gaps).  The script therefore splits every capture into ON and OFF
blocks (256-sample block power), and computes separate spectra from 4096-sample frames
that lie completely inside a burst or completely inside a gap.  This gives the true ON
levels (tone, IM3, N_on) and, from the gaps of the same capture, N_off.

Usage:  python capture_analysis.py <captures_dir> <out.json>
"""
import glob, json, os, sys
import numpy as np

FS = 8_192_000.0
NFFT = 32768                      # 250 Hz bins
F1, F2 = 300e3, 400e3
F_NOISE, BW_NOISE, BW_TONE = -500e3, 400e3, 10e3


def firdes_low_pass(gain, fs, fc, tw):
    """GNU Radio firdes.low_pass with the default Hamming window."""
    ntaps = int(53.0 * fs / (22.0 * tw))
    if ntaps % 2 == 0:
        ntaps += 1
    m = (ntaps - 1) // 2
    n = np.arange(-m, m + 1)
    w = 0.54 - 0.46 * np.cos(2 * np.pi * (n + m) / (ntaps - 1))
    fwt0 = 2 * np.pi * fc / fs
    with np.errstate(divide="ignore", invalid="ignore"):
        taps = np.where(n == 0, fwt0 / np.pi, np.sin(n * fwt0) / (n * np.pi)) * w
    return taps * gain / taps.sum()


def response_sq(taps, f_off):
    """|H|^2 of a low-pass prototype evaluated at baseband offsets f_off (Hz)."""
    n = np.arange(len(taps)) - (len(taps) - 1) / 2
    out = np.empty(len(f_off))
    for i in range(0, len(f_off), 2048):          # chunked to keep memory small
        ff = f_off[i:i + 2048]
        out[i:i + 2048] = np.abs(np.exp(-2j * np.pi * np.outer(ff, n) / FS) @ taps) ** 2
    return out


FREQ = np.fft.fftshift(np.fft.fftfreq(NFFT, 1 / FS))
TAPS_N = firdes_low_pass(1, FS, BW_NOISE / 2, BW_NOISE / 4)
TAPS_T = firdes_low_pass(1, FS, BW_TONE / 2, BW_TONE / 2)
H_NOISE = response_sq(TAPS_N, FREQ - F_NOISE)
LINES = {"f1": F1, "f2": F2, "im_lo": 2 * F1 - F2, "im_hi": 2 * F2 - F1}
H_LINE = {k: response_sq(TAPS_T, FREQ - f) for k, f in LINES.items()}
ENBW_NOISE = FS * np.sum(TAPS_N ** 2) / np.sum(TAPS_N) ** 2
ENBW_TONE = FS * np.sum(TAPS_T ** 2) / np.sum(TAPS_T) ** 2


def db(x):
    return 10 * np.log10(np.maximum(x, 1e-30))


def analyse(path):
    x = np.memmap(path, dtype="<c8", mode="r")
    n = len(x)
    win = np.hanning(NFFT).astype(np.float32)
    wsum = float(np.sum(win.astype(np.float64) ** 2))
    acc = np.zeros(NFFT)
    nseg = 0
    p_tot = 0.0
    peak = 0.0
    nclip = 0
    blocks = []
    chunk = NFFT * 64
    for i in range(0, n - NFFT + 1, chunk):
        seg = np.asarray(x[i:i + chunk])
        m = (len(seg) // NFFT) * NFFT
        if m == 0:
            break
        seg = seg[:m]
        p = float(np.mean(seg.real.astype(np.float64) ** 2 + seg.imag.astype(np.float64) ** 2))
        blocks.append(p)
        p_tot += p * m
        a = np.maximum(np.abs(seg.real), np.abs(seg.imag))
        peak = max(peak, float(a.max()))
        nclip += int(np.count_nonzero(a >= 2046.5 / 2048))
        S = np.fft.fft(seg.reshape(-1, NFFT) * win, axis=1)
        acc += np.sum(S.real.astype(np.float64) ** 2 + S.imag.astype(np.float64) ** 2, axis=0)
        nseg += m // NFFT
    psd_bin = np.fft.fftshift(acc / nseg / wsum / NFFT)     # power per 250 Hz bin, Parseval-scaled
    used = nseg * NFFT

    def narrow(f, half=1500.0):
        return float(np.sum(psd_bin[np.abs(FREQ - f) <= half]))

    # median noise density away from the lines and from DC (dBFS/Hz)
    mask = (np.abs(FREQ) > 1.0e6) & (np.abs(FREQ) < 3.0e6)
    dens = float(np.median(psd_bin[mask]) / (FS / NFFT))    # after averaging many segments, median ~ mean
    out = dict(
        file=os.path.basename(path), samples=int(n), seconds=n / FS,
        total_dbfs=float(db(p_tot / used)), peak_fs=peak, clip_fraction=nclip / (2 * used),
        block_spread_db=float(db(max(blocks)) - db(min(blocks))),
        noise_meter_dbfs=float(db(np.sum(psd_bin * H_NOISE))),
        noise_density_dbfs_hz=float(db(dens)),
        meters={k: float(db(np.sum(psd_bin * H_LINE[k]))) for k in LINES},
        narrow={k: float(db(narrow(f))) for k, f in LINES.items()},
        dc_dbfs=float(db(narrow(0.0))),
    )
    # coarse spectrum for plots: max-hold decimation to 4 kHz steps
    k = 16
    out["spec_f_khz"] = [round(float(v), 1) for v in FREQ.reshape(-1, k).mean(axis=1) / 1e3]
    out["spec_db_per_bin"] = [round(float(v), 2) for v in db(psd_bin.reshape(-1, k).max(axis=1))]
    nb = narrow_floor = float(db(dens * 3000.0))
    t1, t2 = out["narrow"]["f1"], out["narrow"]["f2"]
    if t1 > nb + 15 and abs(t1 - t2) < 6:        # a second tone, not the skirt of the first one
        kind = "two-tone"
    elif t1 > nb + 15:
        kind = "one-tone"
    else:
        kind = "noise"
    out["kind"] = kind
    out["narrow_floor_dbfs"] = narrow_floor
    return out


NG = 4096                         # frame for burst-resolved spectra (0.5 ms, 2 kHz bins)
BLK = 256                         # block for the ON/OFF decision (31 us)
FREQ_G = np.fft.fftshift(np.fft.fftfreq(NG, 1 / FS))
H_NOISE_G = response_sq(TAPS_N, FREQ_G - F_NOISE)


def blackman_harris(n):
    k = np.arange(n)
    a = (0.35875, 0.48829, 0.14128, 0.01168)
    return (a[0] - a[1] * np.cos(2 * np.pi * k / n) + a[2] * np.cos(4 * np.pi * k / n)
            - a[3] * np.cos(6 * np.pi * k / n))


def runs(mask):
    edges = np.flatnonzero(np.diff(mask.astype(np.int8))) + 1
    b = np.concatenate(([0], edges, [len(mask)]))
    return b[:-1], b[1:], mask[b[:-1]]


def gated(path):
    x = np.memmap(path, dtype="<c8", mode="r")
    n = (len(x) // BLK) * BLK
    pw = np.empty(n // BLK)
    step = BLK * 16384
    for i in range(0, n, step):
        s = np.asarray(x[i:min(n, i + step)])
        pw[i // BLK:i // BLK + len(s) // BLK] = (s.real.astype(np.float64) ** 2 + s.imag.astype(np.float64) ** 2).reshape(-1, BLK).mean(axis=1)
    pdb = db(pw)
    lo, hi = np.percentile(pdb, [5, 95])
    if hi - lo < 6:                       # stationary capture (source really off)
        return dict(gated=False, duty=None)
    on = pdb > (lo + hi) / 2
    start, stop, val = runs(on)
    w = blackman_harris(NG)
    s1, s2 = float(w.sum()), float((w ** 2).sum())
    acc = {True: np.zeros(NG), False: np.zeros(NG)}
    cnt = {True: 0, False: 0}
    guard = 2
    for a, b, v in zip(start, stop, val):
        a, b = (a + guard) * BLK, (b - guard) * BLK
        if b - a < NG:
            continue
        nfr = (b - a - NG) // (NG // 2) + 1
        idx = a + (NG // 2) * np.arange(nfr)
        fr = np.stack([np.asarray(x[i:i + NG]) for i in idx]) * w
        S = np.fft.fft(fr, axis=1)
        acc[bool(v)] += np.sum(S.real.astype(np.float64) ** 2 + S.imag.astype(np.float64) ** 2, axis=0)
        cnt[bool(v)] += nfr
    out = dict(gated=True, duty=float(on.mean()),
               on_ms_median=float(np.median((stop - start)[val]) * BLK / FS * 1e3),
               off_ms_median=float(np.median((stop - start)[~val]) * BLK / FS * 1e3),
               on_total_dbfs=float(db(pw[on].mean())), off_total_dbfs=float(db(pw[~on].mean())))
    for v, name in ((True, "on"), (False, "off")):
        if cnt[v] == 0:
            continue
        m = np.fft.fftshift(acc[v] / cnt[v])
        line = m / s1 ** 2                 # power of a sine that sits exactly on a bin
        pbin = m / (NG * s2)               # Parseval-scaled power per bin (for noise)
        out[name] = dict(
            frames=int(cnt[v]),
            noise_meter_dbfs=float(db(np.sum(pbin * H_NOISE_G))),
            lines={k: float(db(line[np.argmin(np.abs(FREQ_G - f))])) for k, f in LINES.items()},
            harm={"h2": float(db(line[np.argmin(np.abs(FREQ_G - 2 * F1))])),
                  "h3": float(db(line[np.argmin(np.abs(FREQ_G + 3 * F1))])),
                  "h3p": float(db(line[np.argmin(np.abs(FREQ_G - 3 * F1))])),
                  "img": float(db(line[np.argmin(np.abs(FREQ_G + F1))]))},
            line_floor_dbfs=float(db(np.median(line[(np.abs(FREQ_G) > 1.0e6) & (np.abs(FREQ_G) < 3.0e6)]))),
            spec_f_khz=[round(float(f), 1) for f in FREQ_G / 1e3],
            spec_line_db=[round(float(v), 2) for v in db(line)],
        )
    return out


def main():
    src, dst = sys.argv[1], sys.argv[2]
    res = []
    for p in sorted(glob.glob(os.path.join(src, "*.cf32"))):
        r = analyse(p)
        r["burst"] = g = gated(p)
        side = p[:-5] + ".json"
        if os.path.exists(side):
            with open(side, encoding="utf-8") as f:
                r["meta"] = json.load(f)
        res.append(r)
        print(f"{r['file'][15:]:62s} {r['kind']:8s} tot {r['total_dbfs']:7.2f} pk {r['peak_fs']:.3f} clip {r['clip_fraction']:.1e} "
              f"N {r['noise_meter_dbfs']:7.2f} | f1 {r['narrow']['f1']:7.2f} f2 {r['narrow']['f2']:7.2f} "
              f"imL {r['narrow']['im_lo']:7.2f} imH {r['narrow']['im_hi']:7.2f} | meters "
              + " ".join(f"{r['meters'][k]:7.2f}" for k in LINES) + f" spread {r['block_spread_db']:.2f}"
              + (f" | duty {g['duty']:.3f} ON: N {g['on']['noise_meter_dbfs']:.2f} f1 {g['on']['lines']['f1']:.2f} f2 {g['on']['lines']['f2']:.2f} imL {g['on']['lines']['im_lo']:.2f} imH {g['on']['lines']['im_hi']:.2f} flr {g['on']['line_floor_dbfs']:.1f} OFF: N {g['off']['noise_meter_dbfs']:.2f}" if g["gated"] else " | not gated"), flush=True)
    with open(dst, "w", encoding="utf-8") as f:
        json.dump(dict(fs_hz=FS, nfft=NFFT, enbw_noise_hz=ENBW_NOISE, enbw_tone_hz=ENBW_TONE,
                       taps_noise=len(TAPS_N), taps_tone=len(TAPS_T), captures=res), f)
    print("ENBW noise meter %.1f Hz, tone meter %.1f Hz" % (ENBW_NOISE, ENBW_TONE))


if __name__ == "__main__":
    main()
