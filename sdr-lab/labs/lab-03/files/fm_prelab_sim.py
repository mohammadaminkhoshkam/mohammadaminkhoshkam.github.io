#!/usr/bin/env python3
"""
SDR Lab - Lab 3 pre-lab (handout: "Experiment 2 - FM radio, stereo and RDS").
Team SDR: Mohammad Amin Khoshkam, Sobhan Yarmohammadi.

Offline simulations that check every number of the pre-lab with the real GNU Radio 3.10
blocks used in the session (Frequency Mod, Quadrature Demod, PLL Freq Det, Freq Xlating FIR,
Rational Resampler, PLL Carrier Regeneration, FM Deemphasis). Signals are produced in numpy,
pushed through GNU Radio flowgraphs with vector sources/sinks and analysed in numpy.

Run with the radioconda Python:
    python fm_prelab_sim.py            -> writes ../results/*.png and ../results/sim_results.json
"""
import json
import os
import time
from fractions import Fraction

import numpy as np
from scipy import signal, special

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from gnuradio import gr, blocks, analog, filter as grf
from gnuradio.filter import firdes
from gnuradio.fft import window

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "results")
os.makedirs(OUT, exist_ok=True)
RNG = np.random.default_rng(2026)
FS = 240e3                      # detector rate of the lab (Fig. 5 of the handout)
HAM = window.WIN_HAMMING
R = {}                          # all numeric results -> sim_results.json

plt.rcParams.update({"figure.dpi": 110, "font.size": 9, "axes.grid": True, "grid.alpha": .3,
                     "axes.spines.top": False, "axes.spines.right": False})
C1, C2, C3, C4 = "#0f7bdc", "#e8711a", "#2a9d5c", "#c0392b"


# ------------------------------------------------------------------ GNU Radio helpers
def run(chain, x):
    """Push numpy vector x through a list of GNU Radio blocks, return the output as numpy."""
    tb = gr.top_block()
    if np.iscomplexobj(x):
        src = blocks.vector_source_c(np.asarray(x, np.complex64), False)
    else:
        src = blocks.vector_source_f(np.asarray(x, np.float32), False)
    item = chain[-1].output_signature().sizeof_stream_item(0)
    snk = blocks.vector_sink_c() if item == 8 else blocks.vector_sink_f()
    tb.connect(src, *chain, snk)
    tb.run()
    return np.array(snk.data())


def fm_mod(m, dev, fs=FS):
    return run([analog.frequency_modulator_fc(2 * np.pi * dev / fs)], m)


def quad_demod(x, dev, fs=FS):
    return run([analog.quadrature_demod_cf(fs / (2 * np.pi * dev))], x)


def pll_demod(x, dev, lbw, fmax_hz, fs=FS):
    w = 2 * np.pi * fmax_hz / fs
    return run([analog.pll_freqdet_cf(lbw, w, -w),
                blocks.multiply_const_ff(fs / (2 * np.pi * dev))], x)


def lowpass(x, fs, cut, tw, decim=1):
    taps = firdes.low_pass(1.0, fs, cut, tw, HAM)
    blk = grf.fir_filter_ccf(decim, taps) if np.iscomplexobj(x) else grf.fir_filter_fff(decim, taps)
    return run([blk], x)


def awgn(n, var):
    return np.sqrt(var / 2) * (RNG.standard_normal(n) + 1j * RNG.standard_normal(n))


def tone_metrics(y, fs, f0, band=(20.0, None), skip=0.05):
    """SINAD of a tone: signal = bins around f0, noise+distortion = the rest of `band`.
    Returns (SINAD dB, tone amplitude)."""
    y = np.asarray(y[int(skip * fs):], float)
    y = y - y.mean()
    n = len(y)
    w = signal.windows.blackmanharris(n)
    Y = np.abs(np.fft.rfft(y * w)) ** 2
    f = np.fft.rfftfreq(n, 1 / fs)
    df = fs / n
    k = 8                                                     # BH main lobe = +-4 bins, keep margin
    i0 = int(round(f0 / df))
    sig = Y[max(i0 - k, 0):i0 + k + 1].sum()
    hi = band[1] if band[1] else fs / 2
    m = (f >= band[0]) & (f <= hi)
    m[max(i0 - k, 0):i0 + k + 1] = False
    nd = Y[m].sum()
    amp = np.sqrt(4 * sig / (n * (w ** 2).sum()))           # Parseval, one-sided spectrum
    return 10 * np.log10(sig / nd), amp


def obw(x, fs, frac):
    """Occupied bandwidth that holds `frac` of the power (from the Welch PSD)."""
    f, p = signal.welch(x, fs, nperseg=1 << 14, return_onesided=False, window="blackmanharris")
    o = np.argsort(f)
    f, p = f[o], p[o]
    c = np.cumsum(p) / p.sum()
    lo = f[np.searchsorted(c, (1 - frac) / 2)]
    hi = f[np.searchsorted(c, 1 - (1 - frac) / 2)]
    return hi - lo, f, p


def rds_baseband(fs, n):
    """Differentially coded, biphase (Manchester) RDS data at 1187.5 bit/s, band-limited to 2.4 kHz.
    Built at 228 kHz (exactly 192 samples/bit) and resampled to fs. Returns (waveform, data bits)."""
    f0 = 228e3
    n0 = int(np.ceil(n * f0 / fs)) + 400
    nb = n0 // 192 + 2
    b = RNG.integers(0, 2, nb)
    d = np.zeros(nb, int)
    for k in range(1, nb):
        d[k] = b[k] ^ d[k - 1]                                # differential coding
    bb = np.repeat(2 * d - 1, 192).astype(float) * np.tile(np.r_[np.ones(96), -np.ones(96)], nb)
    h = signal.firwin(801, 2.4e3, fs=f0)
    bb = signal.lfilter(h, 1, bb)[400:]                       # remove the FIR delay
    bb = bb / np.max(np.abs(bb))
    if fs != f0:
        fr = Fraction(int(fs), int(f0)).limit_denominator(2000)
        bb = signal.resample_poly(bb, fr.numerator, fr.denominator)
    return bb[:n], b


def mpx_signal(fs, L, R_, rds=True, rds_amp=0.04):
    """Stereo multiplex of eq. (10)."""
    tt = np.arange(len(L)) / fs
    wp = 2 * np.pi * 19e3
    m = 0.9 * ((L + R_) / 2 + (L - R_) / 2 * np.sin(2 * wp * tt)) + 0.1 * np.sin(wp * tt)
    bits = None
    if rds:
        rb, bits = rds_baseband(fs, len(L))
        m = m + rds_amp * rb * np.sin(3 * wp * tt)
    return m, bits


def audio_noise(fs, n, lo=30, hi=15e3):
    h = signal.firwin(1023, [lo, hi], pass_zero=False, fs=fs)
    a = signal.lfilter(h, 1, RNG.standard_normal(n + 1023))[1023:]
    return a / np.std(a)


def first_stable(x, values, thr):
    """First x from which all values stay >= thr."""
    values = np.asarray(values)
    for i in range(len(x)):
        if np.all(values[i:] >= thr):
            return float(x[i])
    return None


T0 = time.time()

# =========================================================== 1. Bessel lines, carrier nulls
print("1) carrier nulls ...")
fm = 1e3
n = int(0.1 * FS)                                            # 0.1 s = 100 tone periods -> exact bins
t = np.arange(n) / FS
tone = np.cos(2 * np.pi * fm * t)
devs = np.arange(0, 7001, 10.0)
pc = np.array([np.abs(np.mean(fm_mod(tone, d))) ** 2 for d in devs])   # carrier = DC bin
pc_db = 10 * np.log10(np.maximum(pc, 1e-12))
nulls = []
for lo, hi in [(1500, 3500), (4500, 6500)]:
    m = (devs >= lo) & (devs <= hi)
    d0 = devs[m][np.argmin(pc_db[m])]
    fine = np.arange(d0 - 15, d0 + 15.1, 0.5)
    pf = [np.abs(np.mean(fm_mod(tone, d))) ** 2 for d in fine]
    nulls.append(float(fine[int(np.argmin(pf))]))
R["carrier_nulls_hz_sim"] = nulls
R["carrier_nulls_hz_theory"] = [2404.8, 5520.1]
print("   nulls:", nulls)

fig, ax = plt.subplots(1, 3, figsize=(11, 3.1), gridspec_kw={"width_ratios": [1.4, 1, 1]})
ax[0].plot(devs / 1e3, 20 * np.log10(np.abs(special.jv(0, devs / fm)) + 1e-9), color="k", lw=1,
           label="20 log|J$_0$(Δf/f$_m$)|")
ax[0].plot(devs / 1e3, pc_db, "--", color=C1, lw=1.4, label="GNU Radio Frequency Mod, DC bin")
for v in nulls:
    ax[0].axvline(v / 1e3, color=C4, lw=.8, ls=":")
    ax[0].text(v / 1e3, -5, f" {v:.0f} Hz", color=C4, fontsize=8)
ax[0].set_ylim(-70, 3)
ax[0].set_xlabel("deviation Δf (kHz), f$_m$ = 1 kHz")
ax[0].set_ylabel("carrier power (dB)")
ax[0].legend(loc="lower left", fontsize=7.5)
for a, beta, col in [(ax[1], 2.405, C1), (ax[2], 5.0, C2)]:
    x = fm_mod(tone, beta * fm)
    X = np.abs(np.fft.fftshift(np.fft.fft(x))) / n
    f = np.fft.fftshift(np.fft.fftfreq(n, 1 / FS))
    nn = np.arange(-9, 10)
    idx = [np.argmin(np.abs(f - k * fm)) for k in nn]
    a.stem(nn, X[idx], linefmt=col, markerfmt="o", basefmt=" ")
    a.plot(nn, np.abs(special.jv(nn, beta)), "kx", ms=5, label="|J$_n$(β)|")
    a.set_title(f"β = {beta}", fontsize=9)
    a.set_xlabel("n  (f = f$_c$ + n f$_m$)")
    a.legend(fontsize=7.5)
fig.tight_layout()
fig.savefig(os.path.join(OUT, "fig1_carrier_null.png"))
plt.close(fig)

# =========================================================== 2. Occupied bandwidth / Carson
print("2) bandwidth ...")
FSW = 1.2e6
nW = int(1.0 * FSW)
tW = np.arange(nW) / FSW
cases = {}
for key, dev, f_m in [("nbfm_tone", 5e3, 3e3), ("wfm_tone", 75e3, 15e3)]:
    x = fm_mod(np.cos(2 * np.pi * f_m * tW), dev, FSW)
    b98, f, p = obw(x, FSW, 0.98)
    b99, _, _ = obw(x, FSW, 0.99)
    beta = dev / f_m
    kk = 0
    while special.jv(0, beta) ** 2 + 2 * np.sum(special.jv(np.arange(1, kk + 1), beta) ** 2) < 0.98:
        kk += 1
    cases[key] = dict(dev=dev, fm=f_m, carson=2 * (dev + f_m), obw98=b98, obw99=b99,
                      bessel98=2 * kk * f_m, f=f, p=p)
# stereo MPX + RDS, program-like audio, normalised to |m| <= 1 (peak deviation 75 kHz)
n228 = int(1.0 * 228e3)
L = audio_noise(228e3, n228)
Rr = 0.6 * L + 0.8 * audio_noise(228e3, n228)
mm, _ = mpx_signal(228e3, 0.35 * L, 0.35 * Rr)
mm = signal.resample_poly(mm, 100, 19)                       # 228 kHz -> 1.2 MS/s
mm = mm / np.max(np.abs(mm))
x = fm_mod(mm, 75e3, FSW)
b98, f, p = obw(x, FSW, 0.98)
b99, _, _ = obw(x, FSW, 0.99)
cases["wfm_mpx"] = dict(dev=75e3, fm=53e3, carson=2 * (75e3 + 53e3), obw98=b98, obw99=b99,
                        bessel98=None, f=f, p=p, rms_dev=float(75e3 * np.std(mm)))
R["bandwidth"] = {k: {kk: (float(vv) if vv is not None else None) for kk, vv in v.items() if kk not in ("f", "p")}
                  for k, v in cases.items()}
print("   ", {k: (round(v["obw98"] / 1e3, 1), v["carson"] / 1e3) for k, v in cases.items()})

fig, ax = plt.subplots(1, 3, figsize=(11, 3.1))
for a, key, title, span in [(ax[0], "nbfm_tone", "NBFM: Δf = 5 kHz, f$_m$ = 3 kHz", 40e3),
                            (ax[1], "wfm_tone", "WFM: Δf = 75 kHz, f$_m$ = 15 kHz", 300e3),
                            (ax[2], "wfm_mpx", "WFM: stereo MPX + RDS (peak 75 kHz)", 400e3)]:
    c = cases[key]
    a.plot(c["f"] / 1e3, 10 * np.log10(c["p"] / c["p"].max() + 1e-14), color=C1, lw=.8)
    for xv in (-c["carson"] / 2, c["carson"] / 2):
        a.axvline(xv / 1e3, color=C4, ls="--", lw=.9)
    for xv in (-c["obw98"] / 2, c["obw98"] / 2):
        a.axvline(xv / 1e3, color=C3, ls=":", lw=1.2)
    a.set_xlim(-span / 2e3, span / 2e3)
    a.set_ylim(-80, 3)
    a.set_title(title, fontsize=9)
    a.set_xlabel("frequency offset (kHz)")
    a.text(0.02, 0.95, f"Carson (red) {c['carson']/1e3:.0f} kHz\n98 % OBW (green) {c['obw98']/1e3:.1f} kHz",
           transform=a.transAxes, va="top", fontsize=7.5, bbox=dict(fc="white", ec="0.8"))
ax[0].set_ylabel("PSD (dB, normalised)")
fig.tight_layout()
fig.savefig(os.path.join(OUT, "fig2_bandwidth.png"))
plt.close(fig)

# =========================================================== 3. Discriminator range and gain mismatch
print("3) discriminator range ...")
tt = np.arange(int(0.25 * FS)) / FS
s1k = np.sin(2 * np.pi * 1e3 * tt)
dlist = np.arange(10e3, 150e3 + 1, 5e3)
sinad_q = []
for d in dlist:
    y = quad_demod(fm_mod(s1k, d), d)                        # receiver gain uses the true deviation
    sinad_q.append(tone_metrics(y, FS, 1e3, band=(20, 15e3), skip=0.01)[0])
x75 = fm_mod(s1k, 75e3)
_, a_true = tone_metrics(quad_demod(x75, 75e3), FS, 1e3, skip=0.01)
_, a_double = tone_metrics(quad_demod(x75, 150e3), FS, 1e3, skip=0.01)
R["discriminator"] = dict(max_dev_theory_hz=FS / 2, amp_true=float(a_true), amp_double_dev=float(a_double),
                          change_db=float(20 * np.log10(a_double / a_true)),
                          sinad_vs_dev_khz={f"{d/1e3:.0f}": float(s) for d, s in zip(dlist, sinad_q)})
print("   amplitude with true / doubled deviation:", a_true, a_double)

fig, ax = plt.subplots(1, 2, figsize=(9.5, 3))
ax[0].plot(dlist / 1e3, sinad_q, "o-", color=C1, ms=3)
ax[0].axvline(120, color=C4, ls="--", lw=.9)
ax[0].text(121, 40, "f$_s$/2 = 120 kHz", color=C4, fontsize=8)
ax[0].set_xlabel("peak deviation Δf (kHz), f$_s$ = 240 kHz")
ax[0].set_ylabel("SINAD of 1 kHz tone (dB)")
ax[0].set_title("Quadrature Demod: exact while |k$_f$ m| < π", fontsize=9)
seg = slice(2000, 2000 + 720)
tm = np.arange(720) / FS * 1e3
ax[1].plot(tm, quad_demod(x75, 75e3)[seg], color=C1, label="Δf = 75 kHz, gain for 75 kHz")
ax[1].plot(tm, quad_demod(x75, 150e3)[seg], color=C2, label="Δf = 75 kHz, gain for 150 kHz (×0.5)")
ax[1].plot(tm, quad_demod(fm_mod(s1k, 130e3), 130e3)[seg], color=C4, lw=.8, label="Δf = 130 kHz > f$_s$/2: phase wraps")
ax[1].set_xlabel("time (ms)")
ax[1].set_ylabel("detector output")
ax[1].legend(fontsize=7, loc="lower left")
fig.tight_layout()
fig.savefig(os.path.join(OUT, "fig3_discriminator.png"))
plt.close(fig)

# =========================================================== 4. PLL loop bandwidth
print("4) PLL loop bandwidth sweep ...")
# A PLL that does not follow the message fast enough acts in two ways: (1) as long as the phase error
# stays small it is a linear low-pass on the instantaneous frequency -> the audio is attenuated
# (frequency-response error, still a clean sine); (2) when the phase error grows it slips cycles ->
# real distortion. Both are measured: |H(f)| = PLL amplitude / discriminator amplitude and SINAD,
# with a full-deviation tone swept over the band of interest.
lbws = np.round(np.geomspace(0.005, 0.8, 24), 4)


def pll_response(dev, fmax_hz, tones, dur=0.12):
    tt = np.arange(int(dur * FS)) / FS
    H = np.zeros((len(lbws), len(tones)))
    S = np.zeros_like(H)
    for j, f_t in enumerate(tones):
        x = fm_mod(np.sin(2 * np.pi * f_t * tt), dev)
        _, aq = tone_metrics(quad_demod(x, dev), FS, f_t, skip=0.02)
        for i, lb in enumerate(lbws):
            s, ap = tone_metrics(pll_demod(x, dev, lb, fmax_hz), FS, f_t, band=(20, 0.45 * FS), skip=0.02)
            H[i, j] = 20 * np.log10(ap / aq)
            S[i, j] = s
    return H, S


def min_lbw(H, S, tones, f_top, tol_db=1.0, sinad_min=40.0):
    """Smallest LBW (and all larger) with |H| within tol for every tone <= f_top and SINAD >= sinad_min."""
    sel = np.asarray(tones) <= f_top
    ok = (np.abs(H[:, sel]) <= tol_db).all(1) & (S[:, sel] >= sinad_min).all(1)
    for i in range(len(lbws)):
        if ok[i:].all():
            return float(lbws[i])
    return None


tones_nb = [300, 1e3, 2e3, 3e3]
tones_wb = [1e3, 5e3, 10e3, 15e3, 19e3, 38e3, 53e3, 57e3]
H_nb, S_nb = pll_response(5e3, 15e3, tones_nb)
H_wb, S_wb = pll_response(75e3, 110e3, tones_wb)
R["pll_sweep"] = dict(
    lbw=lbws.tolist(),
    nbfm=dict(tones=tones_nb, H_db=H_nb.tolist(), sinad=S_nb.tolist(),
              min_lbw_3k=min_lbw(H_nb, S_nb, tones_nb, 3e3)),
    wfm=dict(tones=tones_wb, H_db=H_wb.tolist(), sinad=S_wb.tolist(),
             min_lbw_15k=min_lbw(H_wb, S_wb, tones_wb, 15e3),
             min_lbw_53k=min_lbw(H_wb, S_wb, tones_wb, 53e3),
             min_lbw_57k=min_lbw(H_wb, S_wb, tones_wb, 57e3)),
)
for key in ("nbfm", "wfm"):
    for kk in list(R["pll_sweep"][key]):
        if kk.startswith("min_lbw") and R["pll_sweep"][key][kk]:
            R["pll_sweep"][key][kk.replace("min_lbw", "BL_hz")] = 1.06 * R["pll_sweep"][key][kk] * FS
print("   min LBW:", {k: v for k, v in R["pll_sweep"]["nbfm"].items() if k.startswith("min")},
      {k: v for k, v in R["pll_sweep"]["wfm"].items() if k.startswith("min")})

fig, ax = plt.subplots(1, 3, figsize=(11.5, 3.3))
cmap = plt.get_cmap("viridis")
for j, f_t in enumerate(tones_nb):
    ax[0].semilogx(lbws, H_nb[:, j], "o-", ms=2.5, color=cmap(j / len(tones_nb)), label=f"{f_t/1e3:g} kHz")
ax[0].set_title("NBFM (Δf 5 kHz): |H| of PLL vs discriminator", fontsize=8.5)
for j, f_t in enumerate(tones_wb):
    ax[1].semilogx(lbws, H_wb[:, j], "o-", ms=2.5, color=cmap(j / len(tones_wb)), label=f"{f_t/1e3:g} kHz")
ax[1].set_title("WFM (Δf 75 kHz): |H| of PLL vs discriminator", fontsize=8.5)
for a in ax[:2]:
    a.axhspan(-1, 1, color=C3, alpha=.12)
    a.set_ylim(-25, 8)
    a.set_xlabel("Loop Bandwidth (rad/sample)")
    a.set_ylabel("tone level (dB)")
    a.legend(fontsize=6.5, ncol=2, loc="lower right", title="tone", title_fontsize=6.5)
for j, f_t in enumerate(tones_wb):
    ax[2].semilogx(lbws, np.minimum(S_wb[:, j], 100), "o-", ms=2.5, color=cmap(j / len(tones_wb)))
for j, f_t in enumerate(tones_nb):
    ax[2].semilogx(lbws, np.minimum(S_nb[:, j], 100), "x:", ms=3, color="0.5")
ax[2].axhline(40, color="0.4", ls=":", lw=.9)
ax[2].set_title("SINAD, clipped at 100 dB (WFM: colours, NBFM: grey)", fontsize=8.5)
ax[2].set_xlabel("Loop Bandwidth (rad/sample)")
ax[2].set_ylabel("SINAD (dB)")
ax[2].set_ylim(-5, 105)
for a in ax:
    sec = a.secondary_xaxis("top", functions=(lambda v: 1.06 * v * FS / 1e3, lambda b: b * 1e3 / (1.06 * FS)))
    sec.set_xlabel("B$_L$ (kHz)", fontsize=7.5)
fig.tight_layout()
fig.savefig(os.path.join(OUT, "fig4_pll_loop_bw.png"))
plt.close(fig)


def pick_lbw(m, factor=1.5):
    """Design value: 1.5 x the smallest loop bandwidth without audible error, rounded."""
    return float(min(np.round(m * factor, 3), 0.8))


LBW_NB = pick_lbw(R["pll_sweep"]["nbfm"]["min_lbw_3k"])
LBW_WB = pick_lbw(R["pll_sweep"]["wfm"]["min_lbw_15k"])
R["pll_design"] = dict(nbfm_lbw=LBW_NB, wfm_lbw=LBW_WB)
print("   design LBW:", LBW_NB, LBW_WB)

# =========================================================== 5. SNR_o vs CNR (threshold)
print("5) SNR vs CNR ...")


def snr_curve(dev, W, BT, lbw, fmax_hz, f_m=1e3, cnrs=np.arange(-2, 31, 1.0), dur=1.0):
    n = int(dur * FS)
    tt = np.arange(n) / FS
    x = fm_mod(np.sin(2 * np.pi * f_m * tt), dev)
    ctaps = firdes.low_pass(1.0, FS, BT / 2, BT / 8, HAM)
    ataps = firdes.low_pass(1.0, FS, W, W / 4, HAM)
    out = {"quad": [], "pll": []}
    for c in cnrs:
        var = FS / (BT * 10 ** (c / 10))                     # CNR = Pc/(N0 BT) with Pc = 1
        rc = run([grf.fir_filter_ccf(1, ctaps)], x + awgn(n, var))
        yq = run([grf.fir_filter_fff(1, ataps)], quad_demod(rc, dev))
        yp = run([grf.fir_filter_fff(1, ataps)], pll_demod(rc, dev, lbw, fmax_hz))
        out["quad"].append(tone_metrics(yq, FS, f_m, band=(20, W))[0])
        out["pll"].append(tone_metrics(yp, FS, f_m, band=(20, W))[0])
    theory = cnrs + 10 * np.log10(1.5 * (dev / W) ** 2 * BT / W)
    return cnrs, out, theory


def threshold(cnrs, meas, theory, drop=1.0):
    """Lowest CNR from which the curve stays within `drop` dB of eq. (8)."""
    d = theory - np.array(meas)
    for i in range(len(cnrs)):
        if np.all(d[i:] <= drop):
            return float(cnrs[i])
    return None


snr = {"NBFM": snr_curve(5e3, 3e3, 16e3, LBW_NB, 15e3),
       "WFM": snr_curve(75e3, 15e3, 180e3, LBW_WB, 110e3)}
R["snr_vs_cnr"] = {}
for k, (cn, o, th) in snr.items():
    i20 = list(cn).index(20)
    i10 = list(cn).index(10)
    R["snr_vs_cnr"][k] = dict(cnr=cn.tolist(), quad=list(map(float, o["quad"])), pll=list(map(float, o["pll"])),
                              theory=th.tolist(), improvement_db=float(th[0] - cn[0]),
                              thr_quad_1db=threshold(cn, o["quad"], th), thr_pll_1db=threshold(cn, o["pll"], th),
                              at_cnr20={"quad": float(o["quad"][i20]), "pll": float(o["pll"][i20]), "theory": float(th[i20])},
                              at_cnr10={"quad": float(o["quad"][i10]), "pll": float(o["pll"][i10]), "theory": float(th[i10])})
    print("  ", k, "1 dB thresholds quad/pll:", R["snr_vs_cnr"][k]["thr_quad_1db"], R["snr_vs_cnr"][k]["thr_pll_1db"])

fig, ax = plt.subplots(1, 2, figsize=(10, 3.4))
for a, k, ttl in [(ax[0], "NBFM", f"NBFM: Δf 5 kHz, W 3 kHz, B$_T$ 16 kHz, PLL LBW {LBW_NB}"),
                  (ax[1], "WFM", f"WFM: Δf 75 kHz, W 15 kHz, B$_T$ 180 kHz, PLL LBW {LBW_WB}")]:
    cn, o, th = snr[k]
    a.plot(cn, th, "k--", lw=1, label="eq. (8)")
    a.plot(cn, o["quad"], "o-", ms=3, color=C1, label="Quadrature Demod")
    a.plot(cn, o["pll"], "s-", ms=3, color=C2, label="PLL Freq Det")
    a.axvline(10, color=C4, ls=":", lw=.9)
    a.set_title(ttl, fontsize=8.5)
    a.set_xlabel("CNR in B$_T$ (dB)")
    a.set_ylabel("SNR$_o$ in W (dB)")
    a.legend(fontsize=7.5, loc="upper left")
fig.tight_layout()
fig.savefig(os.path.join(OUT, "fig5_snr_vs_cnr.png"))
plt.close(fig)

# =========================================================== 6. Carrier frequency error
print("6) frequency error ...")
tt = np.arange(int(0.5 * FS)) / FS
x = fm_mod(np.sin(2 * np.pi * 1e3 * tt), 5e3)
offs = np.arange(0, 16.01, 1.0) * 1e3
fe = {}
for cut in (8e3, 12e3):
    taps = firdes.low_pass(1, FS, cut, 2e3, HAM)
    s_, dc_ = [], []
    for df in offs:
        y = quad_demod(run([grf.fir_filter_ccf(1, taps)], x * np.exp(2j * np.pi * df * tt)), 5e3)
        dc_.append(float(np.mean(y[int(.05 * FS):])))
        s_.append(tone_metrics(lowpass(y, FS, 3e3, 1e3), FS, 1e3, band=(20, 3e3))[0])
    fe[int(cut / 1e3)] = (s_, dc_)
dfe = 30e-6 * 434e6
R["freq_error"] = dict(delta_f_hz=dfe, dc_expected=dfe / 5e3, offsets=offs.tolist(),
                       sinad_cut8=fe[8][0], dc_cut8=fe[8][1], sinad_cut12=fe[12][0], dc_cut12=fe[12][1])
fig, ax = plt.subplots(1, 2, figsize=(9.5, 3))
ax[0].plot(offs / 1e3, fe[8][1], "o-", ms=3, color=C1, label="measured DC, cut-off 8 kHz")
ax[0].plot(offs / 1e3, fe[12][1], "s-", ms=3, color=C2, label="measured DC, cut-off 12 kHz")
ax[0].plot(offs / 1e3, offs / 5e3, "k--", lw=1, label="δf/Δf")
ax[0].axvline(dfe / 1e3, color=C4, ls=":")
ax[0].set_xlabel("carrier frequency error δf (kHz)")
ax[0].set_ylabel("DC at discriminator output")
ax[0].legend(fontsize=7.5)
ax[1].plot(offs / 1e3, fe[8][0], "o-", ms=3, color=C1, label="channel filter cut-off 8 kHz (B$_T$/2)")
ax[1].plot(offs / 1e3, fe[12][0], "s-", ms=3, color=C2, label="channel filter cut-off 12 kHz")
ax[1].axvline(dfe / 1e3, color=C4, ls=":")
ax[1].text(dfe / 1e3 + .2, 45, "30 ppm @ 434 MHz\n= 13.0 kHz", color=C4, fontsize=7.5)
ax[1].set_xlabel("carrier frequency error δf (kHz)")
ax[1].set_ylabel("SINAD of 1 kHz tone (dB)")
ax[1].legend(fontsize=7.5, loc="lower left")
fig.tight_layout()
fig.savefig(os.path.join(OUT, "fig6_freq_error.png"))
plt.close(fig)

# =========================================================== 7. De-emphasis
print("7) de-emphasis ...")
fa = 48e3
imp = np.zeros(1 << 15)
imp[0] = 1
fig, ax = plt.subplots(figsize=(6.5, 3))
R["deemph"] = {}
for tau, c in [(50e-6, C1), (75e-6, C2)]:
    h = run([analog.fm_deemph(fa, tau)], imp)
    H = np.fft.rfft(h)
    f = np.fft.rfftfreq(len(h), 1 / fa)
    f1 = 1 / (2 * np.pi * tau)
    Ha = 1 / np.sqrt(1 + (f / f1) ** 2)
    ax.semilogx(f[1:], 20 * np.log10(np.abs(H[1:])), color=c, label=f"GNU Radio FM Deemphasis, τ = {tau*1e6:.0f} µs")
    ax.semilogx(f[1:], 20 * np.log10(Ha[1:]), "--", color=c, lw=.9, label=f"analog RC, f$_1$ = {f1:.0f} Hz")
    out = {}
    for fx in (1e3, 10e3, 15e3, 20e3):
        i = np.argmin(np.abs(f - fx))
        out[f"{fx/1e3:.0f}k"] = dict(gr=float(20 * np.log10(abs(H[i]))), rc=float(20 * np.log10(Ha[i])))
    R["deemph"][f"{tau*1e6:.0f}us"] = dict(f1=f1, **out)
R["deemph"]["wrong_tau_db_15k"] = float(20 * np.log10(np.sqrt(1 + (15e3 / 3183.1) ** 2) / np.sqrt(1 + (15e3 / 2122.1) ** 2)))
ax.set_xlim(50, 24e3)
ax.set_ylim(-22, 2)
ax.set_xlabel("audio frequency (Hz), f$_s$ = 48 kHz")
ax.set_ylabel("|H$_{de}$| (dB)")
ax.legend(fontsize=7)
fig.tight_layout()
fig.savefig(os.path.join(OUT, "fig7_deemphasis.png"))
plt.close(fig)

# =========================================================== 8. Full rate plan: 2.4 MS/s -> 48 kHz, stereo, RDS
print("8) full receiver chain at 2.4 MS/s ...")
FSR = 2.4e6
n228 = int(1.0 * 228e3)
t228 = np.arange(n228) / 228e3
Ltone = 0.8 * np.sin(2 * np.pi * 1e3 * t228)               # station A: L = 1 kHz, R = 0, RDS
mA, bitsA = mpx_signal(228e3, Ltone, 0 * Ltone, rds=True)
mA = mA / np.max(np.abs(mA))
mB = np.clip(0.3 * audio_noise(228e3, n228), -1, 1)          # station B: mono programme
mA_r = signal.resample_poly(mA, 200, 19)                     # 228 kHz -> 2.4 MS/s
mB_r = signal.resample_poly(mB, 200, 19)
nR = min(len(mA_r), len(mB_r))
tR = np.arange(nR) / FSR
fA, fB = 500e3, -400e3
rf = fm_mod(mA_r[:nR], 75e3, FSR) * np.exp(2j * np.pi * fA * tR) \
    + 0.5 * fm_mod(mB_r[:nR], 75e3, FSR) * np.exp(2j * np.pi * fB * tR)
rf += awgn(nR, 10 ** (-40 / 10))                             # 40 dB SNR over 2.4 MHz

pil_taps = firdes.complex_band_pass(1, FS, 18.5e3, 19.5e3, 1e3, HAM)
pil_delay = (len(pil_taps) - 1) // 2
a_taps = firdes.low_pass(1, FS, 15e3, 4e3, HAM)


def stereo_decode(mpx):
    ref = run([grf.fir_filter_fcc(1, pil_taps),
               analog.pll_refout_cc(0.001, 2 * np.pi * 19.2e3 / FS, 2 * np.pi * 18.8e3 / FS)], mpx)
    mpx_d = np.r_[np.zeros(pil_delay), mpx[:-pil_delay]]    # Delay block: match the pilot filter
    sub38 = -np.imag(ref ** 2)                               # pilot sin(wp t) -> sin(2 wp t)
    s = run([grf.fir_filter_fff(5, a_taps)], mpx_d)          # 48 kHz
    d = run([grf.fir_filter_fff(5, a_taps)], 2 * mpx_d * sub38)
    return s, s + d, s - d


sep_vs_cut = {}
for cut in (80e3, 100e3, 115e3):
    taps_c = firdes.low_pass(1, FSR, cut, 20e3, HAM)
    m_c = run([grf.freq_xlating_fir_filter_ccf(10, taps_c, fA, FSR),
               analog.quadrature_demod_cf(FS / (2 * np.pi * 75e3))], rf)
    _, Lc, Rc = stereo_decode(m_c)
    sep_vs_cut[f"{cut/1e3:.0f}"] = float(20 * np.log10(tone_metrics(Lc, 48e3, 1e3, skip=0.3)[1] /
                                                      tone_metrics(Rc, 48e3, 1e3, skip=0.3)[1]))
print("   separation vs channel cut-off:", sep_vs_cut)
ch_taps = firdes.low_pass(1, FSR, 100e3, 20e3, HAM)
mpx = run([grf.freq_xlating_fir_filter_ccf(10, ch_taps, fA, FSR),
           analog.quadrature_demod_cf(FS / (2 * np.pi * 75e3))], rf)            # 240 kHz real MPX
sum_, Lo, Ro = stereo_decode(mpx)
sL, aL = tone_metrics(Lo, 48e3, 1e3, band=(20, 15e3), skip=0.3)
_, aR = tone_metrics(Ro, 48e3, 1e3, band=(20, 15e3), skip=0.3)
_, aM = tone_metrics(sum_, 48e3, 1e3, band=(20, 15e3), skip=0.3)
sep = 20 * np.log10(aL / aR)
# RDS: shift 57 kHz, /10 -> 24 kHz, x19/24 -> 19 kHz = 16 samples per bit
rds_taps = firdes.low_pass(1, FS, 2.6e3, 1.5e3, HAM)
z = run([grf.freq_xlating_fir_filter_fcc(10, rds_taps, 57e3, FS),
         grf.rational_resampler_ccc(interpolation=19, decimation=24, taps=[], fractional_bw=0)], mpx)
z = z[int(0.2 * 19e3):]
z = z * np.exp(-1j * 0.5 * np.angle(np.sum(z ** 2)))         # BPSK phase (offline; Costas loop in the lab)
zr = np.real(z)
mf = np.convolve(zr, np.r_[np.ones(8), -np.ones(8)][::-1], mode="valid")   # biphase matched filter
best = max(range(16), key=lambda o: np.mean(np.abs(mf[o::16])))
dhat = (mf[best::16] > 0).astype(int)
bhat = dhat[1:] ^ dhat[:-1]                                  # differential decoding
best_err, best_lag = 1.0, 0
for lag in range(0, 400):
    seg = bitsA[lag:lag + len(bhat) - 20]
    e = np.mean(seg != bhat[:len(seg)])
    if e < best_err:
        best_err, best_lag = e, lag
R["rate_plan"] = dict(
    fs_in=FSR, ch_decim=10, f_det=FS, audio_decim=5, f_audio=48e3,
    ch_taps=len(ch_taps), audio_taps=len(a_taps), pilot_taps=len(pil_taps), pilot_delay=pil_delay,
    rds_taps=len(rds_taps), f_rds=19e3, samples_per_bit=19e3 / 1187.5, stereo_sep_db=float(sep),
    stereo_sep_vs_chan_cut_khz=sep_vs_cut,
    L_sinad_db=float(sL), mono_level=float(aM), L_level=float(aL), rds_bits=int(len(bhat)),
    rds_bit_errors=int(round(best_err * (len(bhat) - 20))), rds_ber=float(best_err),
    rds_bit_rate=1187.5, groups_per_s=1187.5 / 104, n_samples_rf=int(nR))
print(f"   stereo separation {sep:.1f} dB, RDS bit errors {R['rate_plan']['rds_bit_errors']} / {len(bhat)}")

# MPX spectrum (programme-like L and R) and the RDS waveform
nS = int(1.0 * 228e3)
L = audio_noise(228e3, nS)
Rr = 0.5 * L + 0.86 * audio_noise(228e3, nS)
mS, _ = mpx_signal(228e3, 0.35 * L, 0.35 * Rr, rds=True)
mS = signal.resample_poly(mS / np.max(np.abs(mS)), 20, 19)
ys = quad_demod(fm_mod(mS, 75e3) + awgn(len(mS), 10 ** (-35 / 10)), 75e3)
f, p = signal.welch(ys, FS, nperseg=1 << 13, window="blackmanharris")
fig, ax = plt.subplots(1, 2, figsize=(10.5, 3.1), gridspec_kw={"width_ratios": [1.7, 1]})
ax[0].plot(f / 1e3, 10 * np.log10(p / p.max()), color=C1, lw=.8)
for xv, lab in [(15, "15"), (19, "pilot 19"), (23, "23"), (38, "38"), (53, "53"), (57, "RDS 57")]:
    ax[0].axvline(xv, color="0.6", ls=":", lw=.8)
    ax[0].text(xv, 2, lab, fontsize=7, ha="center")
ax[0].set_xlim(0, 70)
ax[0].set_ylim(-80, 6)
ax[0].set_xlabel("frequency (kHz)")
ax[0].set_ylabel("PSD (dB)")
ax[0].set_title("Simulated stereo MPX at the Quadrature Demod output (240 kHz)", fontsize=9)
ax[1].plot(np.arange(16 * 30) / 16, zr[best + 8:best + 8 + 16 * 30] / np.max(np.abs(zr)), color=C3, lw=.9)
ax[1].set_xticks(range(0, 31, 5))
ax[1].set_xlabel("RDS bit index (19 kHz, 16 samples/bit)")
ax[1].set_title(f"RDS biphase at 19 kHz: {R['rate_plan']['rds_bit_errors']} errors / {len(bhat)} bits", fontsize=8.5)
fig.tight_layout()
fig.savefig(os.path.join(OUT, "fig8_mpx_rds.png"))
plt.close(fig)

# =========================================================== 9. design constants (Table 3)
print("9) design table ...")


def n_est(fs, tw):
    return int(np.ceil(3.3 * fs / tw))


def n_gr(fs, cut, tw):
    return len(firdes.low_pass(1, fs, cut, tw, HAM))


R["design"] = dict(
    chan_wfm=dict(fs=2.4e6, cut=100e3, tw=20e3, n_est=n_est(2.4e6, 20e3), n_gr=n_gr(2.4e6, 100e3, 20e3)),
    chan_nbfm_stage2=dict(fs=240e3, cut=10e3, tw=4e3, n_est=n_est(240e3, 4e3), n_gr=n_gr(240e3, 10e3, 4e3)),
    chan_nbfm_single=dict(fs=2.4e6, cut=10e3, tw=4e3, n_est=n_est(2.4e6, 4e3), n_gr=n_gr(2.4e6, 10e3, 4e3)),
    audio_wfm=dict(fs=240e3, cut=15e3, tw=5e3, n_est=n_est(240e3, 5e3), n_gr=n_gr(240e3, 15e3, 5e3)),
    audio_nbfm=dict(fs=240e3, cut=3.5e3, tw=2e3, n_est=n_est(240e3, 2e3), n_gr=n_gr(240e3, 3.5e3, 2e3)),
    gains=dict(quad_gain_5k=240e3 / (2 * np.pi * 5e3), quad_gain_75k=240e3 / (2 * np.pi * 75e3),
               sens_5k=2 * np.pi * 5e3 / 240e3, sens_75k=2 * np.pi * 75e3 / 240e3),
    pll=dict(nbfm_lbw=LBW_NB, nbfm_BL=1.06 * LBW_NB * FS, nbfm_fmax=2 * np.pi * 15e3 / FS,
             wfm_lbw=LBW_WB, wfm_BL=1.06 * LBW_WB * FS, wfm_fmax=2 * np.pi * 110e3 / FS),
    link=dict(p_tx_max=7.0, pad=30.0, cable=0.5, att_for_m60=7 - 30 - 0.5 + 60,
              p_rx_att40=7 - 40 - 30 - 0.5, margin_to_m10=-10 - (7 - 40 - 30 - 0.5)),
)
R["runtime_s"] = round(time.time() - T0, 1)
R["gnuradio"] = gr.version()
with open(os.path.join(OUT, "sim_results.json"), "w") as fp:
    json.dump(R, fp, indent=1, default=float)
print("done in", R["runtime_s"], "s")
