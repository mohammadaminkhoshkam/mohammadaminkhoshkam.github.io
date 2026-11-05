"""
Pre-lab 02 report: every number comes from the simulation outputs in out/ or from the
formulas of the handout, computed here. Writes figures, prelab-data.json and prelab.html.

    python make_report.py
"""
import json
import math
import os
import re

import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
OUTD = os.path.join(HERE, 'out')
SITE = os.path.join(HERE, '..', 'site', 'sdr-lab', 'lab-02')
IMG = os.path.join(SITE, 'img')
os.makedirs(IMG, exist_ok=True)

S = json.load(open(os.path.join(OUTD, 'sim_results.json')))
X = json.load(open(os.path.join(OUTD, 'sim_extra.json')))
A = json.load(open(os.path.join(OUTD, 'antenna.json')))
M = S['model']
D = {}


def db(x):
    return 10 * math.log10(x)


def lin(x):
    return 10 ** (x / 10)


def f2(v, d=2):
    return '{:.{}f}'.format(v, d).replace('-', '−')


T0, K0 = 290.0, -174.0

# =============================================================== task 2 (theory)
for nf in (1, 3, 6, 10):
    D['te%d' % nf] = f2(T0 * (lin(nf) - 1), 1)
G1, F1 = lin(20), lin(1)
Lf = lin(3)
Ff, Gf = Lf, 1 / Lf
F3 = lin(15)
Fa = F1 + (Ff - 1) / G1 + (F3 - 1) / (G1 * Gf)
Fb = Ff + (F1 - 1) / Gf + (F3 - 1) / (Gf * G1)
D.update(q1_c2=f2((Ff - 1) / G1, 4), q1_c3=f2((F3 - 1) / (G1 * Gf), 3), q1_F=f2(Fa, 3), q1_NF=f2(db(Fa)),
         q1b_c2=f2((F1 - 1) / Gf, 3), q1b_c3=f2((F3 - 1) / (Gf * G1), 3), q1b_F=f2(Fb, 3), q1b_NF=f2(db(Fb)),
         q1_diff=f2(db(Fb) - db(Fa)))
# Q3: sensitivity of NF to a 0.1 dB error in Y
q3 = []
for enr_db, nf_db in ((15, 6), (15, 25)):
    E, F = lin(enr_db), lin(nf_db)
    Y = 1 + E / F
    rows = []
    for e in (+0.1, -0.1):
        Ye = lin(db(Y) + e)
        rows.append(db(E / (Ye - 1)) - nf_db)
    q3.append(dict(enr=enr_db, nf=nf_db, Ydb=db(Y), up=rows[0], dn=rows[1]))
D.update(q3a_Y=f2(q3[0]['Ydb']), q3a_up=f2(q3[0]['up']), q3a_dn=f2(q3[0]['dn']),
         q3b_Y=f2(q3[1]['Ydb']), q3b_up=f2(q3[1]['up']), q3b_dn=f2(q3[1]['dn']))
# Q4: P1dB / IIP3 ratio for y = a1 x + a3 x^3
c1 = 1 - 10 ** (-1 / 20)                   # |a3|/|a1| (3/4) A1dB^2 = c1
ratio = (4 / 3) / (4 * c1 / 3)            # A_IIP3^2 / A_1dB^2
D['q4_ratio'] = f2(db(ratio), 2)
# Q5: SFDR
for B, key in ((200e3, 'q5a'), (10e3, 'q5b')):
    nfl = K0 + 8 + db(B)
    D[key + '_floor'] = f2(nfl, 1)
    D[key + '_sfdr'] = f2(2 / 3 * (-10 - nfl), 1)

# =============================================================== task 4 (simulation)
pfs = M['p_fs0']
kT0B = K0 + 0.02 + db(M['samp_rate'])     # the flowgraph uses -173.98 dBm/Hz
D['kT0B'] = f2(-173.98 + db(M['samp_rate']))
# analytic model of the noise figure: front end + 8-bit ADC (0.5 LSB rms dither per rail + rounding)
adc_fs = (0.5 * math.sqrt(2) / 127) ** 2 + 2 / (12 * 127 ** 2)
D['adc_dbfs'] = f2(db(adc_fs))


def nf_model(g):
    n_adc_in = adc_fs * lin(pfs - g)        # mW, over the full 2.048 MHz
    return db(lin(M['nf_fe']) + n_adc_in / lin(-173.98 + db(M['samp_rate'])))


nf_all = S['nf'] + X['nf']


def pick_nf(g):
    """ENR choice rule: noise-on level <= -10 dBFS (linear receiver), smallest ENR with Y >= 6 dB,
    otherwise the reading with the largest Y."""
    rows = [r for r in nf_all if r['gain'] == g and r['on'] <= -10]
    ok = sorted([r for r in rows if r['Ydb'] >= 6], key=lambda r: r['enr'])
    return ok[0] if ok else max(rows, key=lambda r: r['Ydb'])


sweeps = dict(S['sweep1']); sweeps.update(X['sweep1'])


def p1db(pts):
    p = np.array(pts); G = p[:, 1] - p[:, 0]; gss = float(np.median(G[:8])); d = G - gss
    i = int(np.argmax(d <= -1.0))
    pin = p[i - 1, 0] + (-1 - d[i - 1]) * (p[i, 0] - p[i - 1, 0]) / (d[i] - d[i - 1])
    return pin, gss


gains = sorted(int(g) for g in sweeps)
table = []
for g in gains:
    r = pick_nf(g); pin, gss = p1db(sweeps[str(g)])
    floor10 = K0 + r['NF'] + db(10e3)
    table.append(dict(gain=g, enr=r['enr'], Ydb=r['Ydb'], NF=r['NF'], NFmodel=nf_model(g), P1dB=pin, Gss=gss,
                      fs_in=pfs - g, floor10=floor10, DR=pin - floor10))
best = max(table, key=lambda t: t['DR'])
D['best_gain'] = str(best['gain']); D['best_dr'] = f2(best['DR'], 1)
rows_html = []
for t in table:
    cls = ' class="best"' if t is best else ''
    rows_html.append('<tr{}><td class="num">{}</td><td class="num">{}</td><td class="num">{}</td><td class="num">{}</td><td class="num">{}</td>'
                     '<td class="num">{}</td><td class="num">{}</td><td class="num">{}</td><td class="num">{}</td></tr>'.format(
                         cls, t['gain'], t['enr'], f2(t['Ydb']), f2(t['NF']), f2(t['NFmodel']), f2(t['P1dB']), f2(t['fs_in'], 0),
                         f2(t['floor10'], 1), f2(t['DR'], 1)))
D['table45'] = '\n'.join(rows_html)
T = {t['gain']: t for t in table}
D.update(nf40=f2(T[40]['NF']), nf10=f2(T[10]['NF']), y40=f2(T[40]['Ydb']), y10=f2(T[10]['Ydb']), enr10=str(T[10]['enr']),
         p1_40=f2(T[40]['P1dB']), p1_0=f2(T[0]['P1dB']), g40=f2(T[40]['Gss'], 1), g0=f2(T[0]['Gss'], 1),
         nf50=f2(T[50]['NF']), nf30=f2(T[30]['NF']), nf20=f2(T[20]['NF']), nf0=f2(T[0]['NF']),
         p1_10=f2(T[10]['P1dB']), p1_20=f2(T[20]['P1dB']), p1_30=f2(T[30]['P1dB']), p1_50=f2(T[50]['P1dB']))
r40 = [r for r in S['nf'] if r['gain'] == 40 and r['enr'] == 15][0]
D.update(off40=f2(r40['off']), on40=f2(r40['on']))
r10_15 = [r for r in S['nf'] if r['gain'] == 10 and r['enr'] == 15][0]
D.update(y10_15=f2(r10_15['Ydb']), nf10_15=f2(r10_15['NF']), off10_15=f2(r10_15['off']), on10_15=f2(r10_15['on']))
r10 = pick_nf(10); D.update(off10=f2(r10['off']), on10=f2(r10['on']))
# gain at which the input-referred ADC noise equals kT0 B
D['g_eq'] = f2(db(adc_fs) + pfs - (-173.98 + db(M['samp_rate'])), 1)
r50_35 = [r for r in S['nf'] if r['gain'] == 50 and r['enr'] == 35][0]
D.update(nf50_35=f2(r50_35['NF']), on50_35=f2(r50_35['on']))
rep = S['nf_repeat']['Ydb']; D['rep_std'] = f2(float(np.std(rep, ddof=1)), 3)
dY = float(np.std(rep, ddof=1)); E15, Y40 = lin(15), lin(float(np.mean(rep)))
D['rep_nf_std'] = f2(abs(db(E15 / (lin(db(Y40) + dY) - 1)) - db(E15 / (Y40 - 1))), 3)

# fluctuation of the 400 kHz reading vs averaging time
fl = S['fluct']
D['fluct_rows'] = '\n'.join('<tr><td class="num">{}</td><td class="num">{}</td><td class="num">{}</td></tr>'.format(
    f2(r['tau'] * 1e3, 0), f2(r['std'], 3), f2(4.343 / math.sqrt(400e3 * r['tau']), 3)) for r in fl)
tau_need = (4.343 / 0.05) ** 2 / 400e3
D['tau_need'] = f2(tau_need * 1e3, 1)

# two-tone at gain 0
p = np.array(S['two']['0']); pin = p[:, 0]; tone = (p[:, 1] + p[:, 2]) / 2; im = (p[:, 3] + p[:, 4]) / 2
fl0 = S['floor10']['0']
sel = (im > fl0 + 10) & (pin <= T[0]['P1dB'] - 3)
slope, icpt = np.polyfit(pin[sel], im[sel], 1)
iip3s = pin[sel] + (tone[sel] - im[sel]) / 2
D.update(tt_slope=f2(slope, 2), tt_n=str(int(sel.sum())), tt_range='{} … {}'.format(f2(pin[sel].min(), 0), f2(pin[sel].max(), 0)),
         iip3_0=f2(float(np.mean(iip3s))), iip3_0_sd=f2(float(np.std(iip3s, ddof=1)), 2),
         p1_96=f2(T[0]['P1dB'] + 9.6), iip3_minus_p1=f2(float(np.mean(iip3s)) - T[0]['P1dB']), floor10_0=f2(fl0, 1))
D['tt0_rows'] = '\n'.join('<tr><td class="num">{}</td><td class="num">{}</td><td class="num">{}</td><td class="num">{}</td><td class="num">{}</td></tr>'.format(
    f2(a, 0), f2(b), f2(c), f2(b - c), f2(a + (b - c) / 2)) for a, b, c, s in zip(pin, tone, im, sel) if s)
IIP3_0 = float(np.mean(iip3s))

# two-tone at gain 40
q = np.array(S['two']['40']); qin = q[:, 0]; qt = (q[:, 1] + q[:, 2]) / 2; qi = (q[:, 3] + q[:, 4]) / 2
fl40 = S['floor10']['40']
j = int(np.argmax(qi > fl40 + 3))
D.update(g40_jump_pin=f2(qin[j], 0), g40_jump=f2(qi[j] - qi[j - 1], 1), g40_floor=f2(fl40, 1),
         g40_clip=f2(pfs - 40 - db(4), 1), g40_slope=f2((qi[j] - qi[j - 1]) / (qin[j] - qin[j - 1]), 1))

# =============================================================== task 3 (design table)
nf7, nf30 = 7.0, 30.0
D['y_enr15_nf7'] = f2(db(1 + lin(15) / lin(nf7)))
D['y_enr35_nf30'] = f2(db(1 + lin(35) / lin(nf30)))
D['y_enr15_nf30'] = f2(db(1 + lin(15) / lin(nf30)), 2)
# two-tone level for IM3 >= 10 dB above the 10 kHz floor at gain 0 (model: IIP3 measured, NF measured)
floor_in_0 = K0 + T[0]['NF'] + 40
pmin_tt = (floor_in_0 + 10 + 2 * IIP3_0) / 3
D.update(tt_floor_in=f2(floor_in_0, 1), tt_pmin=f2(pmin_tt, 1))

# =============================================================== task 5 (antenna)
D.update(ant_fL=f2(A['fL'], 1), ant_fH=f2(A['fH'], 1), ant_BW=f2(A['BW'], 1), ant_cfL=f2(A['coarse_fL'], 1),
         ant_cfH=f2(A['coarse_fH'], 1), ant_cBW=f2(A['coarse_fH'] - A['coarse_fL'], 1), ant_peak=f2(A['peak_db'], 2),
         ant_peakf=f2(A['peak_mhz'], 0), ant_fc=f2((A['fL'] + A['fH']) / 2, 1))

# =============================================================== task 6 (predictions from the model)
D.update(pr_y=f2(db(1 + lin(15) / lin(7))), pr_nf_drop=f2(T[30]['NF'] - T[50]['NF'], 1),
         pr_p1_10=f2(T[30]['P1dB'] - T[40]['P1dB'], 1), pr_p1_0=f2(T[0]['P1dB'] - T[10]['P1dB'], 1))
D['runtime'] = f2(S['runtime_s'], 0); D['grver'] = S['gnuradio']

# =============================================================== figures
plt.rcParams.update({'font.size': 10, 'axes.grid': True, 'grid.alpha': 0.3, 'figure.dpi': 130, 'savefig.bbox': 'tight'})
C1, C2, C3, C4 = '#0f7bdc', '#00a88f', '#c77700', '#d64545'

# NF / P1dB vs gain
fig, ax = plt.subplots(1, 2, figsize=(10.5, 3.8))
gg = np.array([t['gain'] for t in table]); gm = np.linspace(0, 50, 101)
ax[0].plot(gm, [nf_model(g) for g in gm], color='0.5', lw=1, label='model: F_fe + ADC noise / (kT₀B)')
ax[0].plot(gg, [t['NF'] for t in table], 'o', color=C1, label='Y-factor (simulation)')
ax[0].set_xlabel('Receiver gain (dB)'); ax[0].set_ylabel('Noise figure (dB)'); ax[0].legend(fontsize=8); ax[0].set_title('Noise figure vs gain')
ax[1].plot(gg, [t['P1dB'] for t in table], 'o-', color=C3, label='input P1dB')
ax[1].plot(gg, [t['floor10'] for t in table], 's-', color=C1, label='noise floor, 10 kHz (−174 + NF + 40)')
ax2 = ax[1].twinx(); ax2.plot(gg, [t['DR'] for t in table], 'd--', color=C2, label='P1dB − floor'); ax2.set_ylabel('P1dB − floor (dB)', color=C2); ax2.grid(False)
ax[1].set_xlabel('Receiver gain (dB)'); ax[1].set_ylabel('Input-referred level (dBm)'); ax[1].set_title('Linearity and noise floor vs gain')
h1, l1 = ax[1].get_legend_handles_labels(); h2, l2 = ax2.get_legend_handles_labels(); ax[1].legend(h1 + h2, l1 + l2, fontsize=8, loc='lower left')
fig.savefig(os.path.join(IMG, 'nf_p1db_vs_gain.png')); plt.close(fig)

# P1dB sweeps
fig, ax = plt.subplots(1, 2, figsize=(10.5, 3.8))
for a, g in zip(ax, (40, 0)):
    pts = np.array(sweeps[str(g)]); pin_, gss = p1db(pts)
    a.plot(pts[:, 0], pts[:, 1], '.-', color=C1, ms=3, label='output tone (f1 meter)')
    a.plot(pts[:, 0], pts[:, 0] + gss, '--', color='0.5', lw=1, label='linear: Pin + {:.1f} dB'.format(gss))
    a.axvline(pin_, color=C3, ls=':', lw=1); a.annotate('P1dB = {:.2f} dBm'.format(pin_), (pin_, pts[:, 1].max() - 6), color=C3, fontsize=9, ha='right')
    a.set_xlabel('Tone power at the input (dBm)'); a.set_ylabel('Output (dBFS)'); a.set_title('Single-tone sweep, gain {} dB'.format(g)); a.legend(fontsize=8, loc='lower right')
    a.set_ylim(pts[:, 1].min() - 3, 8)
fig.savefig(os.path.join(IMG, 'p1db_sweeps.png')); plt.close(fig)

# two-tone gain 0 and gain 40
fig, ax = plt.subplots(1, 2, figsize=(10.5, 4))
a = ax[0]
a.plot(pin, tone, 'o', color=C1, ms=3, label='tones f1, f2')
a.plot(pin, im, 's', color=C4, ms=3, label='IM3 (2f1−f2, 2f2−f1)')
xx = np.linspace(pin.min(), IIP3_0 + 3, 50)
gss0 = float(np.median(tone[:8] - pin[:8]))
a.plot(xx, xx + gss0, '--', color=C1, lw=1)
a.plot(xx, slope * xx + icpt, '--', color=C4, lw=1, label='fit, slope {:.2f}'.format(slope))
a.axhline(fl0, color='0.5', ls=':', lw=1, label='10 kHz meter floor')
a.plot([IIP3_0], [IIP3_0 + gss0], 'k*', ms=9); a.annotate('IIP3 ≈ {:.1f} dBm'.format(IIP3_0), (IIP3_0, IIP3_0 + gss0), xytext=(-110, 4), textcoords='offset points', fontsize=9)
a.set_xlabel('Power per tone at the input (dBm)'); a.set_ylabel('Output (dBFS)'); a.set_title('Two-tone test, gain 0 dB'); a.legend(fontsize=7.5, loc='lower right'); a.set_ylim(-80, 10)
a = ax[1]
a.plot(qin, qt, 'o', color=C1, ms=3, label='tones'); a.plot(qin, qi, 's', color=C4, ms=3, label='IM3')
a.axhline(fl40, color='0.5', ls=':', lw=1, label='meter floor')
a.axvline(pfs - 40 - db(4), color=C3, ls=':', lw=1, label='two-tone peak = full scale')
a.set_xlabel('Power per tone at the input (dBm)'); a.set_ylabel('Output (dBFS)'); a.set_title('Two-tone test, gain 40 dB'); a.legend(fontsize=7.5, loc='upper left'); a.set_ylim(-80, 10)
fig.savefig(os.path.join(IMG, 'two_tone.png')); plt.close(fig)

# noise-reading fluctuation
fig, a = plt.subplots(figsize=(5.2, 3.4))
tt = np.array([r['tau'] for r in fl]); ss = np.array([r['std'] for r in fl]); tx = np.logspace(-3, -0.9, 50)
a.loglog(tt * 1e3, ss, 'o', color=C1, label='simulation (30 readings each)')
a.loglog(tx * 1e3, 4.343 / np.sqrt(400e3 * tx), '--', color='0.5', label='4.34 / √(B·τ), B = 400 kHz')
a.axhline(0.05, color=C3, ls=':', lw=1); a.set_xlabel('Averaging time τ (ms)'); a.set_ylabel('Std. of the reading (dB)'); a.legend(fontsize=8); a.set_title('Noise-power reading vs averaging time')
fig.savefig(os.path.join(IMG, 'noise_fluctuation.png')); plt.close(fig)

# antenna response
fig, a = plt.subplots(figsize=(10.5, 3.8))
cf = np.array(A['coarse']); ff = np.array(A['fine'])
a.plot(cf[:, 0], cf[:, 1], 'o-', color=C1, ms=3, lw=1, label='sweep 400–3000 MHz, 20 MHz steps')
a.plot(ff[:, 0], ff[:, 1], '.', color=C3, ms=3, label='1 MHz steps around the edges')
a.axhline(A['peak_db'] - 3, color='0.4', ls='--', lw=1, label='peak − 3 dB')
for v in (A['fL'], A['fH']):
    a.axvline(v, color=C4, ls=':', lw=1)
a.annotate('f_L = {:.1f} MHz'.format(A['fL']), (A['fL'], -20), xytext=(6, 0), textcoords='offset points', color=C4, fontsize=9)
a.annotate('f_H = {:.1f} MHz'.format(A['fH']), (A['fH'], -20), xytext=(-98, 0), textcoords='offset points', color=C4, fontsize=9)
a.set_xlim(400, 3000); a.set_ylim(-110, 5); a.set_xlabel('RF-equivalent frequency (MHz)'); a.set_ylabel('Output / input power (dB)')
a.set_title('Simulated antenna (filter) response'); a.legend(fontsize=8, loc='lower right')
fig.savefig(os.path.join(IMG, 'antenna_response.png')); plt.close(fig)

# =============================================================== write data + html
with open(os.path.join(SITE, 'prelab-data.json'), 'w') as fp:
    json.dump(dict(table45=table, iip3_gain0=IIP3_0, im3_slope_gain0=slope, antenna=dict(fL=A['fL'], fH=A['fH'], BW=A['BW']),
                   nf_readings=nf_all, fluct=fl), fp, indent=1)
tpl = open(os.path.join(HERE, 'prelab_template.html'), encoding='utf-8').read()
missing = sorted(set(re.findall(r'\{\{(\w+)\}\}', tpl)) - set(D))
if missing:
    raise SystemExit('missing keys: ' + ', '.join(missing))
html = re.sub(r'\{\{(\w+)\}\}', lambda m: D[m.group(1)], tpl)
open(os.path.join(SITE, 'prelab.html'), 'w', encoding='utf-8').write(html)
print('ok:', len(D), 'values;', ', '.join('{}={}'.format(k, D[k]) for k in ('nf40', 'nf10', 'p1_40', 'p1_0', 'iip3_0', 'tt_slope', 'best_gain', 'best_dr', 'ant_BW')))
