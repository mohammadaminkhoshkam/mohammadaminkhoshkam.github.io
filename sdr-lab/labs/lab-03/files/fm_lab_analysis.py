#!/usr/bin/env python3
"""
SDR Lab - FM radio session (manual: Experiment 2, session 1) - offline analysis of the raw I/Q files.

Run from the repository root:
    python analysis/fm_lab_analysis.py

Inputs  (240 kS/s complex64 .cf32, recorded after the Frequency Xlating FIR Filter):
    LAB_FM_1_14050821/capture/*.cf32                 broadcast station 90.0 MHz (parts 1-2)
    LAB_FM_1_14050821/grc_FM_Files/FM_lab1/*.cf32    cabled NBFM link 434 MHz (optional part 3)
Outputs:
    analysis/figures/<name>.png and <name>_dark.png   every figure, light and dark theme
    analysis/audio/*.wav                              demodulated audio (48 kHz)
    analysis/results.json                             every number quoted in the report
Needs numpy, scipy and matplotlib only.
"""
import glob
import json
import math
import os
import re

import numpy as np
from scipy import signal, special
from scipy.io import wavfile

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CAP = os.path.join(ROOT, 'LAB_FM_1_14050821', 'capture')
NB = os.path.join(ROOT, 'LAB_FM_1_14050821', 'grc_FM_Files', 'FM_lab1')
FIG = os.path.join(ROOT, 'analysis', 'figures')
AUD = os.path.join(ROOT, 'analysis', 'audio')
os.makedirs(FIG, exist_ok=True)
os.makedirs(AUD, exist_ok=True)

FQ = 240e3          # detector-input rate (= recording rate)
FA = 48e3           # audio rate
FC_BC = 90.0e6
NAME = re.compile(r'(?P<team>.+?)_lab(?P<lab>\d+)_(?P<fc>\d+)_(?P<fs>\d+)_(?P<gain>[\d.]+)_'
                  r'(?P<stamp>\d{8}T\d{6})(?:[_-](?P<tag>.+?))?\.cf32$')

# Values read in the lab (screenshots in capture/ and the datasheet in data/)
LAB = dict(
    P_on_dBFS=[-58.71, -57.27, -58.35, -59.46, -57.45],   # 90.0 MHz, gain 49.6 dB (3, 6, LB_0.5_diff, LB_0.15, LB_0.02_diff)
    P_off_dBFS=-66.86,                                     # 78.0 MHz empty channel, gain 49.6 dB (5.png)
    chan_bw=180e3,                                         # min(2*(75k+15k), 200k)
    f_fine=-150.0,
    nb_P_off=-88.9, nb_P_on=-18.1, nb_SINAD=51.14,         # datasheet sheet 3
    lab1_eps_ppm=-25.85, lab1_eps_unc=7.59,                # Lab 1 report (GSM grid), eps = -offset/fc
)
R = {}   # every number for the report


def load(path):
    d = NAME.match(os.path.basename(path)).groupdict()
    x = np.fromfile(path, np.complex64).astype(np.complex128)
    return x[int(0.05 * FQ):], dict(fc=float(d['fc']), gain=float(d['gain']), stamp=d['stamp'],
                                    tag=d['tag'] or '', base=os.path.splitext(os.path.basename(path))[0])


# ---------------------------------------------------------------- detectors (GNU Radio equivalents)
def disc(x, dev):
    """Quadrature Demod with gain fq/(2*pi*dev): 1.0 == +dev."""
    return np.angle(x[1:] * np.conj(x[:-1])) * FQ / (2 * np.pi * dev)


def loop_coeffs(bw):
    d = math.sqrt(2) / 2
    den = 1 + 2 * d * bw + bw * bw
    return 4 * d * bw / den, 4 * bw * bw / den        # alpha, beta (gr::blocks::control_loop)


def pll(x, dev, bw):
    """gr::analog::pll_freqdet_cf followed by Multiply Const fq/(2*pi*dev)."""
    alpha, beta = loop_coeffs(bw)
    fmax = min(2 * math.pi * 1.5 * dev / FQ, 3.0)
    ph = fr = 0.0
    xr, xi = x.real.tolist(), x.imag.tolist()
    out = [0.0] * len(xr)
    cos, sin, atan2, pi, tp = math.cos, math.sin, math.atan2, math.pi, 2 * math.pi
    for n in range(len(xr)):
        out[n] = fr
        c, s = cos(ph), sin(ph)
        e = atan2(xi[n] * c - xr[n] * s, xr[n] * c + xi[n] * s)
        fr += beta * e
        ph += fr + alpha * e
        if ph > pi or ph < -pi:
            ph = (ph + pi) % tp - pi
        fr = fmax if fr > fmax else (-fmax if fr < -fmax else fr)
    return np.asarray(out) * FQ / (2 * np.pi * dev)


def pll_response(bw, f):
    """Linear closed-loop response (output frequency / input frequency) of the GR PLL."""
    a, b = loop_coeffs(bw)
    z = np.exp(1j * 2 * np.pi * np.asarray(f) / FQ)
    return b * z / ((z - 1) ** 2 + a * (z - 1) + b * z)


def to_audio(y, audio_bw, tau=50e-6):
    """LPF + decimate 5 + DC removal; returns (de-emphasized, raw)."""
    taps = signal.firwin(401, audio_bw, fs=FQ)
    a = signal.resample_poly(signal.lfilter(taps, 1, y), 1, 5)
    a = a - a.mean()
    p = math.exp(-1 / (FA * tau))
    return signal.lfilter([1 - p], [1, -p], a), a


def band_db(y, f0, hb, fs=FQ):
    """Power of band f0+-hb in dB re a full-deviation sine (same convention as the GRC meters)."""
    f, P = signal.welch(y, fs, nperseg=1 << 14)
    s = (f > f0 - hb) & (f < f0 + hb)
    return 10 * np.log10(2 * P[s].sum() * (f[1] - f[0]) + 1e-30)


def sinad(a, fm, fs=FA):
    t = signal.firwin(2001, [fm - 300, fm + 300], fs=fs, pass_zero='bandstop')
    nd = signal.lfilter(t, 1, a)[4000:]
    return 10 * np.log10(np.mean(a[4000:] ** 2) / np.mean(nd ** 2))


def wav(name, a):
    a = a[int(0.1 * FA):]
    wavfile.write(os.path.join(AUD, name), int(FA),
                  (0.9 * a / (np.max(np.abs(a)) + 1e-12) * 32767).astype(np.int16))


def spectrum(x, nper=1 << 14):
    f, P = signal.welch(x, FQ, nperseg=nper, return_onesided=False, window='blackmanharris', scaling='spectrum')
    return np.fft.fftshift(f), np.fft.fftshift(P)


def obw(f, P, frac=0.99):
    c = np.cumsum(P) / P.sum()
    return f[np.searchsorted(c, (1 + frac) / 2)] - f[np.searchsorted(c, (1 - frac) / 2)]


def centroid(x):
    """Carrier frequency from the power spectrum: centroid of the power above the noise floor."""
    f, P = spectrum(x, 8192)
    floor = np.median(P[(np.abs(f) > 95e3) & (np.abs(f) < 100e3)])
    s = np.abs(f) < 95e3
    Pe = np.clip(P[s] - floor, 0, None)
    return float(np.sum(f[s] * Pe) / Pe.sum())


def cnr_lin(p_on, p_off):
    return (10 ** (p_on / 10) - 10 ** (p_off / 10)) / 10 ** (p_off / 10)


# ================================================================ PART 1: broadcast station 90.0 MHz
bc_files = sorted(glob.glob(os.path.join(CAP, '*.cf32')))
rows = []
for p in bc_files:
    x, m = load(p)
    d = disc(x, 75e3)
    ff = 0.0 if m['stamp'].endswith(('142119', '142400')) else LAB['f_fine']
    res_disc, res_cen = float(d.mean() * 75e3), centroid(x)
    rows.append(dict(file=m['base'], gain=m['gain'], tag=m['tag'], dur=round(len(x) / FQ, 2), f_fine=ff,
                     P_dBFS=round(10 * np.log10(np.mean(np.abs(x) ** 2)), 2),
                     resid_disc_Hz=round(res_disc, 1), resid_centroid_Hz=round(res_cen, 1),
                     # residual = delta - f_fine  ->  carrier offset delta = residual + f_fine
                     delta_disc_Hz=round(res_disc + ff, 1), delta_centroid_Hz=round(res_cen + ff, 1),
                     pilot_disc=round(band_db(d, 19e3, 150), 2), noise17_disc=round(band_db(d, 17e3, 400), 2),
                     LR_disc=round(band_db(d, 38e3, 15e3), 2)))
R['broadcast_files'] = rows

pon = float(np.mean(LAB['P_on_dBFS']))
lin = cnr_lin(pon, LAB['P_off_dBFS'])
R['P_on_mean'] = round(pon, 2)
R['P_on_spread'] = [min(LAB['P_on_dBFS']), max(LAB['P_on_dBFS'])]
R['CNR_180k_dB'] = round(10 * np.log10(lin), 2)
R['CNR_200k_dB'] = round(10 * np.log10(lin * 180e3 / 200e3), 2)
R['CNR_min'] = round(10 * np.log10(cnr_lin(min(LAB['P_on_dBFS']), LAB['P_off_dBFS'])), 2)
R['CNR_max'] = round(10 * np.log10(cnr_lin(max(LAB['P_on_dBFS']), LAB['P_off_dBFS'])), 2)

# --- receiver reference error (eps = -delta / fc, same sign convention as the Lab 1 report)
dd_ = np.array([r['delta_disc_Hz'] for r in rows])
dc_ = np.array([r['delta_centroid_Hz'] for r in rows])
allv = np.concatenate([dd_, dc_])
R['delta_disc_mean'] = round(float(dd_.mean()), 1)
R['delta_disc_std'] = round(float(dd_.std(ddof=1)), 1)
R['delta_centroid_mean'] = round(float(dc_.mean()), 1)
R['delta_centroid_std'] = round(float(dc_.std(ddof=1)), 1)
R['delta_all_mean'] = round(float(allv.mean()), 1)
R['delta_all_range'] = [round(float(allv.min()), 1), round(float(allv.max()), 1)]
R['eps_disc_ppm'] = round(-R['delta_disc_mean'] / FC_BC * 1e6, 2)
R['eps_centroid_ppm'] = round(-R['delta_centroid_mean'] / FC_BC * 1e6, 2)
# The disc. mean is biased by noise clicks and programme content at CNR ~ 8 dB (it moves ~500 Hz for a
# 150 Hz change of f_fine); the spectral centroid is consistent before/after the f_fine change -> main estimate.
pre = np.array([r['f_fine'] == 0 for r in rows])
R['check_disc_pre_post'] = [round(float(dd_[pre].mean()), 1), round(float(dd_[~pre].mean()), 1)]
R['check_centroid_pre_post'] = [round(float(dc_[pre].mean()), 1), round(float(dc_[~pre].mean()), 1)]
R['eps_ppm'] = R['eps_centroid_ppm']
R['eps_unc_ppm'] = round(float(dc_.std(ddof=1) / math.sqrt(len(dc_)) / FC_BC * 1e6), 2)
R['lab1_delta_at_90MHz_Hz'] = round(-LAB['lab1_eps_ppm'] * 1e-6 * FC_BC, 0)
R['lab1_delta_unc_Hz'] = round(LAB['lab1_eps_unc'] * 1e-6 * FC_BC, 0)
R['eps_diff_sigma'] = round(abs(R['eps_ppm'] - LAB['lab1_eps_ppm']) / math.hypot(R['eps_unc_ppm'], LAB['lab1_eps_unc']), 2)
R['ppm_f_fine'] = round(-LAB['f_fine'] / FC_BC * 1e6, 3)      # what the setting f_fine = -150 Hz would mean

# --- reference file for the detailed broadcast plots: LB0.3 (10 s, f_fine=-150, gain 49.6)
ref = [p for p in bc_files if p.endswith('LB0.3.cf32')][0]
xr_, mr = load(ref)
seg = xr_[: int(2.0 * FQ)]
dref = disc(seg, 75e3)
f_ch, P_ch = spectrum(xr_)
R['bc_obw99_kHz_incl_noise'] = round(obw(f_ch, P_ch) / 1e3, 1)
pl03 = pll(seg, 75e3, 0.3)
au_d, _ = to_audio(dref - dref.mean(), 15e3)
au_p, _ = to_audio(pl03 - pl03.mean(), 15e3)
au_d75, _ = to_audio(dref - dref.mean(), 15e3, tau=75e-6)

# --- de-emphasis 50 vs 75 us
fr_ = np.array([1e3, 3e3, 5e3, 10e3, 15e3])
h50 = 1 / np.sqrt(1 + (2 * np.pi * fr_ * 50e-6) ** 2)
h75 = 1 / np.sqrt(1 + (2 * np.pi * fr_ * 75e-6) ** 2)
R['deemph_diff_dB'] = {('%d kHz' % (v / 1e3)): round(float(20 * np.log10(a / b)), 2) for v, a, b in zip(fr_, h75, h50)}
R['deemph_corner_Hz'] = [round(1 / (2 * np.pi * 50e-6)), round(1 / (2 * np.pi * 75e-6))]
R['deemph_level_diff_dB'] = round(10 * np.log10(np.mean(au_d75 ** 2) / np.mean(au_d ** 2)), 2)

# audio files for the website
for p in bc_files:
    x, m = load(p)
    au, _ = to_audio(disc(x, 75e3), 15e3)
    wav('%s_disc.wav' % m['base'], au)
au, _ = to_audio(pll(xr_[: int(4 * FQ)], 75e3, 0.15), 15e3)
wav('%s_pll0.15.wav' % mr['base'], au)

# --- Question 1: receiver dev = 37.5 kHz instead of 75 kHz
lp105 = signal.firwin(301, 105e3 / 2, width=105e3 / 8, fs=FQ)
lp180 = signal.firwin(301, 180e3 / 2, width=180e3 / 8, fs=FQ)
y180 = signal.lfilter(lp180, 1, seg)
y105 = signal.lfilter(lp105, 1, seg)
_, r75 = to_audio(disc(y180, 75e3), 15e3)
_, r37g = to_audio(disc(y180, 37.5e3), 15e3)
_, r37 = to_audio(disc(y105, 37.5e3), 15e3)
R['Q1_gain_only_dB'] = round(10 * np.log10(np.mean(r37g ** 2) / np.mean(r75 ** 2)), 2)
R['Q1_with_filter_dB'] = round(10 * np.log10(np.mean(r37 ** 2) / np.mean(r75 ** 2)), 2)
dif = r37 / 2 - r75
R['Q1_extra_distortion_dB'] = round(10 * np.log10(np.mean(dif[2000:] ** 2) / np.mean(r75[2000:] ** 2)), 2)
f_q1, P180 = spectrum(y180)
_, P105 = spectrum(y105)

# ================================================================ PART 2: PLL loop-bandwidth sweep
bws = [0.5, 0.3, 0.15, 0.08, 0.04, 0.02]
p_pilot_d, p_lr_d, p_n17_d = band_db(dref, 19e3, 150), band_db(dref, 38e3, 15e3), band_db(dref, 17e3, 400)
sweep, sweep_psd = [], []
for bw in bws:
    y = pll(seg, 75e3, bw)
    H = pll_response(bw, [19e3, 38e3])
    sweep.append(dict(pll_bw=bw, B_L_kHz=round(1.06 * bw * FQ / 1e3, 2),
                      pilot_diff_meas=round(band_db(y, 19e3, 150) - p_pilot_d, 2),
                      LR_diff_meas=round(band_db(y, 38e3, 15e3) - p_lr_d, 2),
                      noise17_diff_meas=round(band_db(y, 17e3, 400) - p_n17_d, 2),
                      pilot_diff_lin=round(20 * np.log10(abs(H[0])), 2),
                      LR38_diff_lin=round(20 * np.log10(abs(H[1])), 2)))
    sweep_psd.append(signal.welch(y, FQ, nperseg=4096))
R['pll_sweep'] = sweep
R['disc_levels_ref'] = dict(pilot=round(p_pilot_d, 2), LR=round(p_lr_d, 2), noise17=round(p_n17_d, 2))
live = {0.5: 0.0, 0.3: -1.87, 0.15: 0.55, 0.08: 0.18, 0.04: -0.53, 0.02: -17.15}   # datasheet 2a

# --- weak signal: datasheet 2b + offline emulation (white noise added to the raw file)
weak = [(49.6, -59.21, -38.30, -66.39, -37.72, -67.79), (35, -72.03, -38.30, -61.85, -37.62, -61.10),
        (30, -72.81, -42.81, -46.68, -43.54, -47.54)]
R['weak_live'] = [dict(gain=g, P=p, disc=round(a - b, 2), pll=round(c - d, 2), adv=round((c - d) - (a - b), 2))
                  for g, p, a, b, c, d in weak]
seg3 = xr_[: int(1.5 * FQ)]
S = 10 ** (pon / 10) - 10 ** (LAB['P_off_dBFS'] / 10)
N0 = 10 ** (LAB['P_off_dBFS'] / 10) / LAB['chan_bw']
rng = np.random.default_rng(1)
emu = []
for add_db in (None, 0, 3, 6, 10):
    if add_db is None:
        y, Nadd = seg3, 0.0
    else:
        Nadd = N0 * FQ * 10 ** (add_db / 10)
        y = seg3 + np.sqrt(Nadd / 2) * (rng.standard_normal(len(seg3)) + 1j * rng.standard_normal(len(seg3)))
    cnr = 10 * np.log10(S / (N0 * 180e3 + Nadd * 180e3 / FQ))
    dd = disc(y, 75e3)
    row = dict(CNR_dB=round(cnr, 1), disc=round(band_db(dd, 19e3, 150) - band_db(dd, 17e3, 400), 2))
    for bw in (0.15, 0.04):
        pp = pll(y, 75e3, bw)
        row['pll%g' % bw] = round(band_db(pp, 19e3, 150) - band_db(pp, 17e3, 400), 2)
    emu.append(row)
R['weak_emulation'] = emu

# ================================================================ PART 3 (optional): cabled NBFM
nb, nb_plot = {}, []
for p, fm in ((glob.glob(os.path.join(NB, '*fm1000*.cf32'))[0], 1e3),
              (glob.glob(os.path.join(NB, '*fm3000*.cf32'))[0], 3e3)):
    x, m = load(p)
    N = int(FQ)
    nblk = len(x) // N
    X = np.mean(np.abs(np.fft.fft(x[:nblk * N].reshape(nblk, N) * signal.windows.blackmanharris(N), axis=1)) ** 2, 0)
    fr = np.fft.fftfreq(N, 1 / FQ)
    tot = X.sum()
    beta = 5e3 / fm
    lines = []
    for n in range(-12, 13):
        idx = (int(round(n * fm)) + np.arange(-20, 21)) % N
        lines.append((n, 10 * np.log10(X[idx].sum() / tot), 20 * np.log10(abs(special.jv(n, beta)) + 1e-15)))
    L = np.array([l[1] for l in lines])
    Jb = np.array([l[2] for l in lines])
    keep = [l[0] for l in lines if l[1] >= L.max() - 20]
    keepb = [l[0] for l in lines if l[2] >= Jb.max() - 20]
    order = np.argsort(fr)
    pw = special.jv(np.arange(0, 40), beta) ** 2
    cum = pw[0] + 2 * np.cumsum(pw[1:])
    kmin = 1 + int(np.argmax(cum >= 0.99))
    n0 = np.median(X[(np.abs(fr) > 30e3) & (np.abs(fr) < 90e3)])
    d = disc(x, 5e3)
    abw = 3e3 if fm < 2e3 else 3.5e3
    ad, adr = to_audio(d, abw)
    _, apr = to_audio(pll(x[: int(2 * FQ)], 5e3, 0.05), abw)
    wav('nbfm_fm%d_disc.wav' % fm, ad)
    nb['fm%d' % fm] = dict(beta=round(beta, 3), lines=[(a, round(b, 2), round(cc, 2)) for a, b, cc in lines],
                           max_line_err_dB=round(max(abs(b - cc) for a, b, cc in lines if cc > -80), 3),
                           bw20_kHz=(max(keep) - min(keep)) * fm / 1e3,
                           bw20_bessel_kHz=(max(keepb) - min(keepb)) * fm / 1e3,
                           bw99_raw_kHz=round(obw(fr[order], X[order]) / 1e3, 2),
                           bw99_bessel_kHz=2 * kmin * fm / 1e3, carson_kHz=2 * (5e3 + fm) / 1e3,
                           dev_rms_Hz=round(float(np.std(d) * 5e3 * np.sqrt(2)), 1),
                           offset_Hz=round(float(d.mean() * 5e3), 2),
                           CNR200_raw_dB=round(10 * np.log10(tot / (n0 * 200e3)), 1),
                           SINAD_disc=round(sinad(adr, fm), 2), SINAD_pll=round(sinad(apr, fm), 2))
    nb_plot.append((fm, beta, np.fft.fftshift(fr), 10 * np.log10(np.fft.fftshift(X) / tot + 1e-30), lines, L.max()))
R['nbfm'] = nb

z1, z2 = special.jn_zeros(0, 2)
R['null_theory_Hz'] = [round(z1 * 1e3, 2), round(z2 * 1e3, 2)]
unc = {}
for z in (z1, z2):
    nmax = max(abs(special.jv(n, z)) for n in range(1, 15))
    unc['%.4f' % z] = {'%d dB' % v: round(nmax * 10 ** (-v / 20) / abs(special.j1(z)) * 1e3, 2) for v in (30, 60, 69, 85)}
R['null_uncertainty_Hz'] = unc
R['nb_CNR_meas'] = round(10 * np.log10(cnr_lin(LAB['nb_P_on'], LAB['nb_P_off'])), 2)
R['nb_budget_Prx_dBm'] = round(7 - 40 + 20 * np.log10(0.5) - 30 - 0.5, 2)
R['nb_budget_CNR'] = round(R['nb_budget_Prx_dBm'] - (-174 + 10 * np.log10(200e3) + 5), 2)

# ================================================================ figures (light + dark, same palette as the website)
THEMES = {
    '': dict(bg='#ffffff', fg='#121722', dim='#5a6476', grid='#dde2ea',
             c=['#0f7bdc', '#d64545', '#00a88f', '#c77700', '#7c5cff', '#64748b']),
    '_dark': dict(bg='#0c131f', fg='#e6eaf2', dim='#93a0b5', grid='#22304a',
                  c=['#4cc9ff', '#ff7b7b', '#35e0a1', '#ffb84d', '#b49cff', '#8696ad']),
}


def themed(name, draw, size):
    for suf, t in THEMES.items():
        plt.rcParams.update({
            'figure.facecolor': t['bg'], 'axes.facecolor': t['bg'], 'savefig.facecolor': t['bg'], 'text.color': t['fg'],
            'axes.edgecolor': t['grid'], 'axes.labelcolor': t['fg'], 'xtick.color': t['dim'], 'ytick.color': t['dim'],
            'grid.color': t['grid'], 'axes.grid': True, 'grid.linewidth': 0.7, 'font.size': 9.5, 'axes.titlesize': 10.5,
            'axes.titleweight': 'bold', 'legend.frameon': False, 'legend.fontsize': 8, 'font.family': 'DejaVu Sans',
            'axes.spines.top': False, 'axes.spines.right': False, 'lines.linewidth': 1.2,
            'axes.prop_cycle': plt.cycler(color=t['c'])})
        fig = plt.figure(figsize=size, dpi=150)
        draw(fig, t)
        fig.tight_layout()
        fig.savefig(os.path.join(FIG, name + suf + '.png'))
        plt.close(fig)


def fig1(fig, t):
    c = t['c']
    a1, a2, a3 = fig.subplots(3, 1)
    a1.plot((FC_BC + f_ch) / 1e6, 10 * np.log10(P_ch + 1e-30), lw=.6, color=c[0])
    a1.set(title='Channel spectrum at the recorder (90.0 MHz, gain 49.6 dB)', xlabel='Frequency (MHz)', ylabel='Power (dB)')
    for y, k, lab in ((dref, 0, 'Quadrature Demod (non-coherent)'), (pl03, 1, 'PLL, pll_bw = 0.3')):
        fd, Pd = signal.welch(y - y.mean(), FQ, nperseg=4096)
        a2.plot(fd / 1e3, 10 * np.log10(Pd), color=c[k], lw=.7, label=lab)
    for v in (15, 19, 38, 57):
        a2.axvline(v, color=t['dim'], ls=':', lw=.7)
    a2.set(title='Detector outputs (MPX baseband); dotted: 15, 19, 38, 57 kHz', xlabel='Frequency (kHz)',
           ylabel='PSD (dB/Hz)', xlim=(0, 120))
    a2.legend()
    for au_, k, lab in ((au_d, 0, 'Quadrature Demod'), (au_p, 1, 'PLL 0.3')):
        fa, Pa = signal.welch(au_, FA, nperseg=4096)
        a3.plot(fa / 1e3, 10 * np.log10(Pa), color=c[k], lw=.7, label=lab)
    a3.set(title='Audio after 15 kHz LPF + 50 µs de-emphasis', xlabel='Frequency (kHz)', ylabel='PSD (dB/Hz)')
    a3.legend()


def fig2(fig, t):
    ax = fig.subplots()
    ax.plot(f_q1 / 1e3, 10 * np.log10(P180 + 1e-30), lw=.7, label='dev = 75 kHz   → channel filter 180 kHz')
    ax.plot(f_q1 / 1e3, 10 * np.log10(P105 + 1e-30), lw=.7, label='dev = 37.5 kHz → channel filter 105 kHz')
    ax.set(xlabel='Offset from 90.0 MHz (kHz)', ylabel='Power (dB)',
           title='Same received RF signal; only the receiver channel filter changes (Q1)')
    ax.legend()


def fig3(fig, t):
    a1, a2 = fig.subplots(1, 2)
    for bw, (fd, Pd) in zip(bws, sweep_psd):
        a1.plot(fd / 1e3, 10 * np.log10(Pd), lw=.6, label='PLL %g' % bw)
    fd, Pd = signal.welch(dref, FQ, nperseg=4096)
    a1.plot(fd / 1e3, 10 * np.log10(Pd), color=t['fg'], lw=.8, label='Discriminator')
    a1.set(xlim=(0, 120), xlabel='Frequency (kHz)', ylabel='PSD (dB/Hz)', title='Detector output vs loop bandwidth (raw file)')
    a1.legend(ncol=2)
    fg = np.linspace(100, 119e3, 2000)
    for bw in bws:
        a2.plot(fg / 1e3, 20 * np.log10(np.abs(pll_response(bw, fg))), label='pll_bw %g' % bw)
    for v in (19, 38, 57):
        a2.axvline(v, color=t['dim'], ls=':', lw=.7)
    a2.set(xlabel='Frequency (kHz)', ylabel='|H(f)| (dB)', ylim=(-40, 6), title='Linear model of the GNU Radio PLL')
    a2.legend()


def fig4(fig, t):
    ax = fig.subplots()
    ax.semilogx(bws, [live[b] for b in bws], 'o-', label='live meter (datasheet)')
    ax.semilogx(bws, [s['pilot_diff_meas'] for s in sweep], 's-', label='offline: raw file + our PLL')
    ax.semilogx(bws, [s['pilot_diff_lin'] for s in sweep], '^--', label='linear loop model')
    ax.set(xlabel='pll_bw (rad/sample)', ylabel='19 kHz: PLL − discriminator (dB)', title='Pilot attenuation by the PLL')
    ax.grid(True, which='both')
    ax.legend()


def fig5(fig, t):
    a1, a2 = fig.subplots(1, 2)
    a1.plot([w['P'] for w in R['weak_live']], [w['disc'] for w in R['weak_live']], 'o-', label='Discriminator')
    a1.plot([w['P'] for w in R['weak_live']], [w['pll'] for w in R['weak_live']], 's-', label='PLL 0.15')
    a1.set(xlabel='Channel power (dBFS)', ylabel='pilot / noise at 17 kHz (dB)', title='Live readings (datasheet)')
    a1.legend()
    cn = [e['CNR_dB'] for e in emu]
    for k, mk in (('disc', 'o-'), ('pll0.15', 's-'), ('pll0.04', '^-')):
        a2.plot(cn, [e[k] for e in emu], mk, label=k)
    a2.set(xlabel='CNR in 180 kHz (dB)', ylabel='pilot / noise at 17 kHz (dB)', title='Offline: noise added to the raw file')
    a2.legend()


def fig6(fig, t):
    axs = fig.subplots(1, 2)
    for ax, (fm, beta, o, Pdb, lines, Lmax) in zip(axs, nb_plot):
        ax.plot(o / 1e3, Pdb, lw=.5, color=t['c'][0], label='raw file (1 Hz bins)')
        ax.plot([l[0] * fm / 1e3 for l in lines], [l[2] for l in lines], 'o', color=t['c'][1], mfc='none',
                label='Bessel |J_n(%.2f)|²' % beta)
        ax.axhline(Lmax - 20, color=t['c'][2], ls='--', lw=.8, label='20 dB below the largest line')
        ax.set(xlim=(-20, 20), ylim=(-110, 0), xlabel='Offset from 434 MHz (kHz)', ylabel='dB re total power',
               title='NBFM, Δf = 5 kHz, f_m = %d Hz (β = %.2f)' % (fm, beta))
        ax.legend(loc='lower center')


def fig7(fig, t):
    ax = fig.subplots()
    bet = np.linspace(0, 7, 2000)
    for n in range(0, 4):
        ax.plot(bet * 1e3, special.jv(n, bet), label='J%d' % n)
    for z, meas in ((z1, 2405), (z2, 5520)):
        ax.axvline(meas, color=t['dim'], ls='--', lw=.8)
        ax.text(meas + 40, 0.82, 'measured %d Hz\ntheory %.1f Hz' % (meas, z * 1e3), fontsize=8)
    ax.axhline(0, color=t['dim'], lw=.5)
    ax.set(xlabel='Deviation (Hz) with f_m = 1 kHz', ylabel='J_n(β)', title='Carrier (J0) nulls used for deviation calibration')
    ax.legend()


def fig8(fig, t):
    ax = fig.subplots()
    k = np.arange(len(rows))
    lab1, u1 = R['lab1_delta_at_90MHz_Hz'], R['lab1_delta_unc_Hz']
    ax.axhspan(lab1 - u1, lab1 + u1, color=t['c'][3], alpha=.18, lw=0, label='Lab 1 result scaled to 90 MHz (±1σ)')
    ax.axhline(lab1, color=t['c'][3], lw=1)
    ax.plot(k, dd_, 'o', label='mean of discriminator output')
    ax.plot(k, dc_, 's', label='centroid of the channel power spectrum')
    ax.axhline(R['delta_centroid_mean'], color=t['fg'], ls='--', lw=.9, label='this session (centroid): %.0f Hz, ε = %.1f ppm'
               % (R['delta_centroid_mean'], R['eps_ppm']))
    ax.axhline(0, color=t['dim'], lw=.5)
    ax.set_xticks(k)
    ax.set_xticklabels([(r['tag'] or r['file'][-6:]) for r in rows], rotation=30, fontsize=7.5)
    ax.set(ylabel='Carrier offset δ (Hz), f_fine removed', title='Carrier offset of the 90.0 MHz station, every recording')
    ax.legend(fontsize=7.5, loc='center right')


themed('fig1_broadcast_spectra', fig1, (9.6, 9.6))
themed('fig2_q1_dev37k', fig2, (9.2, 3.6))
themed('fig3_pll_bw_sweep', fig3, (11.5, 4.0))
themed('fig4_pilot_vs_bw', fig4, (7.4, 3.8))
themed('fig5_weak_signal', fig5, (10.5, 3.8))
themed('fig6_nbfm_bessel', fig6, (11.5, 4.0))
themed('fig7_carrier_nulls', fig7, (8.6, 3.6))
themed('fig8_freq_error', fig8, (9.2, 4.0))

with open(os.path.join(ROOT, 'analysis', 'results.json'), 'w', encoding='utf-8') as fh:
    json.dump(R, fh, indent=1, ensure_ascii=False, default=float)
print('done:', len(R), 'result groups')
