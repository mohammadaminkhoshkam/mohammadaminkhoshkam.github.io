#!/usr/bin/env python3
"""Lab 2 report - derived quantities and figures.

Inputs
  measurements.json      readings of the two data sheets (dBFS, time-averaged meters)
  antenna_sweep.json     antenna sweep digitised from the GUI screenshot
  <captures.json>        output of capture_analysis.py (burst-resolved spectra)
  <captures_dir>         raw .cf32 captures (only for the envelope figure; optional)
Outputs
  <out_dir>/report-data.json, <out_dir>/capture_results.json, <out_dir>/img/report/*.png

Usage: python report_analysis.py <captures.json> <out_dir> [captures_dir]
"""
import glob, json, os, sys
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = os.path.dirname(os.path.abspath(__file__))
M = json.load(open(os.path.join(HERE, "measurements.json"), encoding="utf-8"))
ANT = json.load(open(os.path.join(HERE, "antenna_sweep.json"), encoding="utf-8"))
CAPJ = json.load(open(sys.argv[1], encoding="utf-8"))
OUT = sys.argv[2]
CAPDIR = sys.argv[3] if len(sys.argv) > 3 else None
IMG = os.path.join(OUT, "img", "report")
os.makedirs(IMG, exist_ok=True)

FG = M["flowgraph"]
FS = FG["fs_hz"]
ENBW = CAPJ["enbw_noise_hz"]
ENBW_TONE = CAPJ["enbw_tone_hz"]
GAINS = ["49.6", "40.2", "29.7"]


def db(x):
    return 10 * np.log10(np.maximum(x, 1e-30))


def lin(x):
    return 10 ** (np.asarray(x, dtype=float) / 10)


def enr(a_tx, a_pad):
    return FG["p_max_dbm"] - a_tx + 20 * np.log10(FG["a_noise"]) - 10 * np.log10(FS) - a_pad + 174


def p_tone(a_tx, a_pad):
    return FG["p_max_dbm"] - a_tx + 20 * np.log10(FG["a_tone"]) - a_pad


def nf_y(enr_db, y_db):
    return float(enr_db - db(lin(y_db) - 1))


# ----------------------------------------------------------------- captures
caps = []
for c in CAPJ["captures"]:
    m = c["meta"]
    caps.append(dict(c, fc=round(m["fc_hz"] / 1e6), gain="%.1f" % m["gain_db"], utc=m["started_utc"][9:15]))


def cap(utc):
    return next(c for c in caps if c["utc"] == utc)


gated = [c for c in caps if c["burst"]["gated"]]
DUTY = float(np.mean([c["burst"]["duty"] for c in gated]))
DUTY_MIN = float(np.min([c["burst"]["duty"] for c in gated]))
DUTY_MAX = float(np.max([c["burst"]["duty"] for c in gated]))
ON_MS = float(np.median([c["burst"]["on_ms_median"] for c in gated]))
OFF_MS = float(np.median([c["burst"]["off_ms_median"] for c in gated]))
DUTY_DB = float(db(DUTY))

R = dict(enbw_noise_hz=ENBW, enbw_tone_hz=ENBW_TONE, duty=dict(mean=DUTY, min=DUTY_MIN, max=DUTY_MAX, db=DUTY_DB,
         on_ms=ON_MS, off_ms=OFF_MS, n=len(gated)))


def burst_correct(n_on_avg, n_off):
    """Averaged N_on reading -> level during the bursts (source really on)."""
    return float(db((lin(n_on_avg) - (1 - DUTY) * lin(n_off)) / DUTY))


# ----------------------------------------------------------------- part 1: direct method
cal = M["final"]["calibration_434MHz_rx_port_open"]
R["direct_manual"] = {g: dict(n_off=cal[g], nf=float(cal[g] - 20 - 10 * np.log10(400e3) + 174)) for g in GAINS}

# conversion factor G_FS (dBFS - dBm) from the single-tone captures in the linear range
tone_caps = {60: "113455", 55: "113721", 50: "114153", 45: "114312", 44: "114411", 43: "114658", 42: "114817", 41: "114846", 40: "114954"}
gfs_pts = [cap(tone_caps[a])["burst"]["on"]["lines"]["f1"] - p_tone(a, 0.0) for a in (60, 55, 50, 45)]
GFS0 = float(np.mean(gfs_pts))                 # with A_pad = 0
R["gfs"] = dict(pad0=GFS0, pad30=GFS0 + 30, spread=float(np.ptp(gfs_pts)), p_fs_dbm_pad0=-GFS0)

# ----------------------------------------------------------------- part 2: Y factor
ncap = {  # (fc, gain, tx_atten) -> utc of the noise-on capture
    (434, "49.6", 60): "104633", (434, "40.2", 60): "104656", (434, "29.7", 60): "104741",
    (404, "29.7", 60): "104956", (404, "40.2", 60): "105040", (414, "49.6", 60): "105213",
    (414, "40.2", 80): "111537", (414, "49.6", 80): "112220",
}
noff_cap = {(414, "40.2"): "111417", (414, "49.6"): "112037", (414, "29.7"): "112303"}
# N_off with the transmitter connected, per gain: every gap of a noise-on capture + the source-off captures
vals = {g: [] for g in GAINS}
for c in caps:
    if c["kind"] == "noise" and c["burst"]["gated"]:
        vals[c["gain"]].append(c["burst"]["off"]["noise_meter_dbfs"])
for (fc, g), u in noff_cap.items():
    vals[g].append(cap(u)["noise_meter_dbfs"])
NOFF_CONN = {g: float(db(np.mean(lin(vals[g])))) for g in GAINS}
R["n_off_connected"] = {g: dict(mean=NOFF_CONN[g], values=vals[g], open_port=cal[g], open_minus_connected=cal[g] - NOFF_CONN[g]) for g in GAINS}

rows = []
on60 = M["final"]["noise_on_tx_atten_60"]
y80 = M["final"]["y_factor_414MHz_tx_atten_80"]
for fc in (434, 404, 414):
    for g in GAINS:
        r = dict(fc=fc, gain=g, tx=60, n_on_log=on60[str(fc)][g])
        key = (fc, g, 60)
        if key in ncap:
            b = cap(ncap[key])["burst"]
            r.update(n_on=b["on"]["noise_meter_dbfs"], n_off=b["off"]["noise_meter_dbfs"], src="capture",
                     n_on_cap_avg=cap(ncap[key])["noise_meter_dbfs"], duty=b["duty"])
        else:
            n_off = y80[g]["n_off"] if fc == 414 else NOFF_CONN[g]
            r.update(n_on=burst_correct(r["n_on_log"], n_off), n_off=n_off, src="sheet")
        rows.append(r)
for g in GAINS:
    r = dict(fc=414, gain=g, tx=80, n_on_log=y80[g]["n_on"], n_off_log=y80[g]["n_off"])
    key = (414, g, 80)
    if key in ncap:
        b = cap(ncap[key])["burst"]
        r.update(n_on=b["on"]["noise_meter_dbfs"], n_off=b["off"]["noise_meter_dbfs"], src="capture", duty=b["duty"])
    else:
        r.update(n_on=burst_correct(r["n_on_log"], r["n_off_log"]), n_off=r["n_off_log"], src="sheet")
    rows.append(r)
for r in rows:
    r["y"] = r["n_on"] - r["n_off"]
    r["enr_pad0"] = float(enr(r["tx"], 0))
    r["enr_pad30"] = float(enr(r["tx"], 30))
    r["nf"] = nf_y(r["enr_pad0"], r["y"])
    r["nf_pad30"] = nf_y(r["enr_pad30"], r["y"])
    if "n_off_log" in r:                       # as read from the averaged meters
        r["y_log"] = r["n_on_log"] - r["n_off_log"]
        r["nf_log"] = nf_y(r["enr_pad0"], r["y_log"])
        r["nf_log_pad30"] = nf_y(r["enr_pad30"], r["y_log"])
    r["y_vs_open"] = r["n_on_log"] - cal[r["gain"]]
R["yfactor"] = rows


def row(fc, g, tx):
    return next(r for r in rows if r["fc"] == fc and r["gain"] == g and r["tx"] == tx)


def src_part(r):
    return float(db(lin(r["n_on"]) - lin(r["n_off"])))


# receiver linearity between ENR 17.4 and 37.4 dB (414 MHz, 49.6 dB): source part of N_on
r80, r60 = row(414, "49.6", 80), row(414, "49.6", 60)
R["linearity_20dB"] = dict(step_measured=src_part(r60) - src_part(r80), nf80=r80["nf"], nf60=r60["nf"])

# relative gain steps from the source noise (burst ON, source part only), 434 MHz, tx 60
STEP_HI = src_part(row(434, "49.6", 60)) - src_part(row(434, "40.2", 60))
STEP_LO = src_part(row(434, "40.2", 60)) - src_part(row(434, "29.7", 60))
R["gain_steps"] = dict(hi=STEP_HI, lo=STEP_LO, nominal_hi=9.4, nominal_lo=10.5,
                       hi_414_tx80=src_part(row(414, "49.6", 80)) - src_part(row(414, "40.2", 80)),
                       lo_404=src_part(row(404, "40.2", 60)) - src_part(row(404, "29.7", 60)))
GFS = {"49.6": GFS0 + STEP_HI, "40.2": GFS0, "29.7": GFS0 - STEP_LO}
R["gfs_by_gain"] = GFS
R["direct_corrected"] = {g: dict(n_off=NOFF_CONN[g], nf=float(NOFF_CONN[g] - GFS[g] + 174 - 10 * np.log10(ENBW)),
                                 nf_open=float(cal[g] - GFS[g] + 174 - 10 * np.log10(ENBW))) for g in GAINS}

# best NF estimate per gain: mean of the 434 / 414 MHz Y-factor values
NF = {}
for g in GAINS:
    v = [row(434, g, 60)["nf"], row(414, g, 60)["nf"], row(414, g, 80)["nf"]]
    NF[g] = dict(mean=float(np.mean(v)), min=float(np.min(v)), max=float(np.max(v)), nf404=row(404, g, 60)["nf"])
R["nf"] = NF


def sens(y_db, d=0.1):
    """Change of NF when Y is read d dB too high."""
    return float(-(db(lin(y_db + d) - 1) - db(lin(y_db) - 1)))


ys = [(r["y_log"], "414 MHz, gain %s, tx_atten 80 (as read)" % r["gain"]) for r in rows if "y_log" in r]
ymin = min(ys)
R["q2"] = dict(y_min=ymin[0], where=ymin[1], d_plus=sens(ymin[0], 0.1), d_minus=sens(ymin[0], -0.1),
               y_burst=row(414, "29.7", 80)["y"], d_burst=sens(row(414, "29.7", 80)["y"], 0.1),
               y_big=row(434, "49.6", 60)["y"], d_big=sens(row(434, "49.6", 60)["y"], 0.1),
               y_first=6.35, d_first=sens(6.35, 0.1), d_y1=sens(1.0, 0.1), d_y3=sens(3.0, 0.1), d_y15=sens(15.0, 0.1))

# first-pass sheet (handwritten): Y and the 3 dB linearity test
fp = M["first_pass"]
fy = []
for g, d in fp["y_factor_low_enr"].items():
    s0 = db(lin(d["n_on"]) - lin(d["n_off"]))
    s1 = db(lin(d["n_on_after_minus_3dB"]) - lin(d["n_off"]))
    y = d["n_on"] - d["n_off"]
    fy.append(dict(gain=g, tx=d["tx_atten"], n_off=d["n_off"], n_on=d["n_on"], y=y, enr=float(enr(d["tx_atten"], 0)),
                   nf=nf_y(enr(d["tx_atten"], 0), y), n_on3=d["n_on_after_minus_3dB"], step=float(s1 - s0)))
R["first_pass_y"] = fy
R["first_pass_y60"] = {g: {f: dict(n_off=v[0], n_on=v[1], y=v[1] - v[0]) for f, v in d.items()} for g, d in fp["y_factor_tx_atten_60"].items()}

# ----------------------------------------------------------------- part 3: single tone
st = M["final"]["single_tone_434MHz_gain_40.2"]
tx = np.array(st["tx_atten"], dtype=float)
f1_log = np.array([np.mean(v) for v in st["f1"]])
f1_sd = np.array([np.std(v, ddof=1) for v in st["f1"]])
tot_log = np.array([np.mean(v) for v in st["total"]])
on = np.array([cap(tone_caps[int(a)])["burst"]["on"]["lines"]["f1"] for a in tx])
avg_cap = np.array([cap(tone_caps[int(a)])["meters"]["f1"] for a in tx])
clipf = np.array([cap(tone_caps[int(a)])["clip_fraction"] / cap(tone_caps[int(a)])["burst"]["duty"] for a in tx])
h3 = np.array([cap(tone_caps[int(a)])["burst"]["on"]["harm"]["h3"] for a in tx])
h2 = np.array([cap(tone_caps[int(a)])["burst"]["on"]["harm"]["h2"] for a in tx])
lin_idx = [0, 1, 2, 3]
off_log = float(np.mean(f1_log[lin_idx] + tx[lin_idx]))          # f1(avg) = off_log - tx
off_on = float(np.mean(on[lin_idx] + tx[lin_idx]))               # f1(on)  = off_on - tx
dev_log = (off_log - tx) - f1_log
dev_on = (off_on - tx) - on
# effective attenuation if the 43 dB entry did not take effect (same reading as 44 dB)
tx_eff = tx.copy()
tx_eff[tx <= 43] += 1.0
dev_on_eff = (off_on - tx_eff) - on
dev_log_eff = (off_log - tx_eff) - f1_log


def clip_model(a_db):
    """Fundamental of a complex tone of amplitude a (re full scale) whose I and Q are hard-limited to +-1."""
    a = 10 ** (a_db / 20)
    if a <= 1:
        return float(a_db)
    th = np.arccos(1 / a)
    return float(20 * np.log10(a * (1 - (2 / np.pi) * (th - np.sin(2 * th) / 2))))


xs = np.linspace(-3, 6, 901)
comp = xs - np.array([clip_model(v) for v in xs])
P1_OVER_FS = float(np.interp(1.0, comp, xs))
A_FS = off_on                                         # tx_atten at which the tone would reach 0 dBFS
P_FS = float(p_tone(A_FS, 0))
P1_TX = A_FS - P1_OVER_FS
R["single"] = dict(
    tx=tx.tolist(), tx_eff=tx_eff.tolist(), pin_pad0=[float(p_tone(a, 0)) for a in tx], f1_log=f1_log.tolist(), f1_sd=f1_sd.tolist(),
    total_log=tot_log.tolist(), conv_log=(f1_log - np.array([p_tone(a, 0) for a in tx])).tolist(),
    conv_pad30=(f1_log - np.array([p_tone(a, 30) for a in tx])).tolist(),
    f1_cap_avg=avg_cap.tolist(), f1_on=on.tolist(), clip=clipf.tolist(), h3=h3.tolist(), h2=h2.tolist(),
    dev_log=dev_log.tolist(), dev_on=dev_on.tolist(), dev_on_eff=dev_on_eff.tolist(), dev_log_eff=dev_log_eff.tolist(),
    a_tx_fs=A_FS, p_fs_dbm=P_FS, p1_over_fs_model=P1_OVER_FS, p1_tx_model=P1_TX, p1_dbm_model=float(p_tone(P1_TX, 0)),
    p1_out_on_model=float(clip_model(P1_OVER_FS)), p1_out_avg_model=float(clip_model(P1_OVER_FS) + DUTY_DB),
    p1_literal_tx=float(np.interp(1.0, dev_log[4:6], tx[4:6][::1])) if dev_log[5] >= 1 > dev_log[4] else None,
    small_signal_conv_pad0=GFS0, small_signal_conv_avg_pad0=float(off_log - (FG["p_max_dbm"] + 20 * np.log10(FG["a_tone"]))),
    model_dev_at=dict(eff42=float((A_FS - 42) - clip_model(A_FS - 42)), eff41=float((A_FS - 41) - clip_model(A_FS - 41))),
    first_pass=fp["single_tone_434MHz_gain_40.2"])
if R["single"]["p1_literal_tx"] is not None:
    R["single"]["p1_literal_dbm"] = float(p_tone(R["single"]["p1_literal_tx"], 0))

# ----------------------------------------------------------------- part 4: two tone
tt = fp["two_tone_434MHz_gain_40.2"]
ttx = np.array(tt["tx_atten"], dtype=float)
tone = (np.array(tt["f1"]) + np.array(tt["f2"])) / 2
im = db((lin(tt["im_lo"]) + lin(tt["im_hi"])) / 2)
delta = tone - im
pin = np.array([p_tone(a, 0) for a in ttx])
iip3 = pin + delta / 2
s_tone = np.polyfit(-ttx, tone, 1)
s_im = np.polyfit(-ttx, im, 1)
R["two_first"] = dict(tx=ttx.tolist(), pin=pin.tolist(), f1=tt["f1"], f2=tt["f2"], im_lo=tt["im_lo"], im_hi=tt["im_hi"],
                      delta=delta.tolist(), iip3=iip3.tolist(), slope_tone=float(s_tone[0]), slope_im=float(s_im[0]),
                      im_step_per_2db=float(2 * s_im[0]))
tc = []
for u in ("120651", "120723", "120954", "120839"):
    c = cap(u)
    o = c["burst"]["on"]
    t_on = (o["lines"]["f1"] + o["lines"]["f2"]) / 2
    i_on = float(db((lin(o["lines"]["im_lo"]) + lin(o["lines"]["im_hi"])) / 2))
    t_avg = (c["meters"]["f1"] + c["meters"]["f2"]) / 2
    i_avg = float(db((lin(c["meters"]["im_lo"]) + lin(c["meters"]["im_hi"])) / 2))
    tc.append(dict(utc=u, tone_avg=t_avg, im_avg=i_avg, d_avg=t_avg - i_avg, tone_on=t_on, im_on=i_on, d_on=t_on - i_on,
                   pin=t_on - GFS0, peak=float(2 * 10 ** (t_on / 20)), clip=c["clip_fraction"] / c["burst"]["duty"], on_total=c["burst"]["on_total_dbfs"]))
R["two_caps"] = tc
# skirt of the gated source seen by the IM3 bins (single-tone captures): level at +-100 and +200 kHz from the tone
sk100, sk200, sk_avg100, sk_avg200 = [], [], [], []
for a in (60, 55, 50, 45, 44):
    c = cap(tone_caps[a])
    o = c["burst"]["on"]["lines"]
    sk100.append(((o["f2"] + o["im_lo"]) / 2) - o["f1"])
    sk200.append(o["im_hi"] - o["f1"])
    sk_avg100.append(((c["meters"]["f2"] + c["meters"]["im_lo"]) / 2) - c["meters"]["f1"])
    sk_avg200.append(c["meters"]["im_hi"] - c["meters"]["f1"])
SK_ON = float(db(lin(np.mean(sk100)) + lin(np.mean(sk200))))
SK_AVG = float(db(lin(np.mean(sk_avg100)) + lin(np.mean(sk_avg200))))
R["skirt"] = dict(on_100k=float(np.mean(sk100)), on_200k=float(np.mean(sk200)), avg_100k=float(np.mean(sk_avg100)),
                  avg_200k=float(np.mean(sk_avg200)), two_tone_floor_on=SK_ON, two_tone_floor_avg=SK_AVG)
best = tc[2]
R["iip3_bound"] = dict(pin=best["pin"], delta=best["d_on"], iip3=best["pin"] + best["d_on"] / 2,
                       above_fs=best["pin"] + best["d_on"] / 2 - P_FS, minus_p1=best["pin"] + best["d_on"] / 2 - R["single"]["p1_dbm_model"])
shots = M["final"]["two_tone_screenshots_434MHz_gain_40.2"]
for s in shots:
    s["tone"] = (s["f1"] + s["f2"]) / 2
    s["im"] = float(db((lin(s["im_lo"]) + lin(s["im_hi"])) / 2))
    s["delta"] = s["tone"] - s["im"]
    s["tone_on_est"] = s["tone"] - DUTY_DB
    s["peak_est"] = float(2 * 10 ** (s["tone_on_est"] / 20))
R["two_shots"] = shots

# ----------------------------------------------------------------- part 5: antenna
f = np.array(ANT["f_mhz"], dtype=float)
v = np.array(ANT["p_db"], dtype=float)
pk = int(np.argmax(v))


def crossing(drop):
    th = v[pk] - drop
    lo = next(i for i in range(pk - 1, -1, -1) if v[i] < th)
    hi = next(i for i in range(pk + 1, len(v)) if v[i] < th)
    fl = float(np.interp(th, v[lo:lo + 2], f[lo:lo + 2]))
    fh = float(np.interp(th, v[hi - 1:hi + 1][::-1], f[hi - 1:hi + 1][::-1]))
    return fl, fh


fl3, fh3 = crossing(3)
fl6, fh6 = crossing(6)
R["antenna"] = dict(peak_mhz=float(f[pk]), peak_db=float(v[pk]), fl3=fl3, fh3=fh3, bw3=fh3 - fl3, fl6=fl6, fh6=fh6, bw6=fh6 - fl6,
                    p434=float(np.interp(434, f, v)), p1000=float(v[list(f).index(1000)]), p2400=float(v[list(f).index(2400)]))

# ----------------------------------------------------------------- trade-off vs gain
B_REF = 10e3
actual_gain = {"49.6": STEP_HI, "40.2": 0.0, "29.7": -STEP_LO}
trade = {}
for g in GAINS:
    nf = NF[g]["mean"]
    floor = -174 + nf + 10 * np.log10(B_REF)
    pfs = -GFS[g]
    p1 = pfs + P1_OVER_FS
    trade[g] = dict(nf=nf, floor_10k=float(floor), p_fs=float(pfs), p1=float(p1), dr=float(p1 - floor), rel_gain=actual_gain[g],
                    two_tone_headroom=float(pfs - 6.02 - floor))
R["trade"] = trade
# two-term noise model  N_off(g) = a * G(g) + b  (front end + noise added after the variable gain), fitted in relative terms
gl = np.array([lin(actual_gain[g]) for g in GAINS])
nl = np.array([lin(NOFF_CONN[g]) for g in GAINS])
A_, B_ = np.linalg.lstsq(np.vstack([gl, np.ones(3)]).T / nl[:, None], np.ones(3), rcond=None)[0]
R["noise_model"] = dict(front_end_at_40_dbfs=float(db(A_)), fixed_floor_dbfs=float(db(B_)), fixed_floor_dbfs_hz=float(db(B_) - 10 * np.log10(ENBW)),
                        knee_rel_gain_db=float(db(B_ / A_)), fit_err_db=[float(db(A_ * lin(actual_gain[g]) + B_) - NOFF_CONN[g]) for g in GAINS])
R["model"] = dict(a_pad_assumed=0.0, p_tone_at_tx60=float(p_tone(60, 0)), enr60=float(enr(60, 0)), enr80=float(enr(80, 0)),
                  enr60_pad30=float(enr(60, 30)), enr80_pad30=float(enr(80, 30)), ktb_fs_dbm=float(-174 + 10 * np.log10(FS)),
                  dens_40_dbfs_hz=float(NOFF_CONN["40.2"] - 10 * np.log10(ENBW)),
                  dens_40_dbm_hz_pad30=float(NOFF_CONN["40.2"] - 10 * np.log10(ENBW) - (GFS0 + 30)),
                  dens_40_dbm_hz_pad0=float(NOFF_CONN["40.2"] - 10 * np.log10(ENBW) - GFS0))

json.dump(R, open(os.path.join(OUT, "report-data.json"), "w", encoding="utf-8"), indent=1)
slim = []
for c in caps:
    d = {k: c[k] for k in ("file", "fc", "gain", "utc", "kind", "seconds", "total_dbfs", "peak_fs", "clip_fraction", "noise_meter_dbfs", "meters")}
    b = c["burst"]
    d["burst"] = dict(gated=b["gated"])
    if b["gated"]:
        d["burst"].update(duty=b["duty"], on_total_dbfs=b["on_total_dbfs"], off_total_dbfs=b["off_total_dbfs"],
                          on={k: b["on"][k] for k in ("noise_meter_dbfs", "lines", "harm", "line_floor_dbfs", "frames")},
                          off={k: b["off"][k] for k in ("noise_meter_dbfs", "frames")})
    slim.append(d)
json.dump(dict(fs_hz=FS, enbw_noise_hz=ENBW, enbw_tone_hz=ENBW_TONE, captures=slim), open(os.path.join(OUT, "capture_results.json"), "w", encoding="utf-8"), indent=1)

# =================================================================== figures
THEMES = {
    "": dict(bg="#ffffff", fg="#121722", dim="#5a6476", grid="#dde2ea", c=["#0f7bdc", "#00a88f", "#c77700", "#d64545", "#7c5cff", "#64748b"]),
    "_dark": dict(bg="#0c131f", fg="#e6eaf2", dim="#93a0b5", grid="#22304a", c=["#4cc9ff", "#35e0a1", "#ffb84d", "#ff7b7b", "#b49cff", "#8696ad"]),
}


def themed(name, draw, size):
    for suf, t in THEMES.items():
        plt.rcParams.update({
            "figure.facecolor": t["bg"], "axes.facecolor": t["bg"], "savefig.facecolor": t["bg"], "text.color": t["fg"],
            "axes.edgecolor": t["grid"], "axes.labelcolor": t["fg"], "xtick.color": t["dim"], "ytick.color": t["dim"],
            "grid.color": t["grid"], "axes.grid": True, "grid.linewidth": 0.7, "font.size": 9.5, "axes.titlesize": 10.5,
            "axes.titleweight": "bold", "legend.frameon": False, "legend.fontsize": 8.5, "font.family": "DejaVu Sans",
            "axes.spines.top": False, "axes.spines.right": False, "lines.linewidth": 1.6})
        fig = plt.figure(figsize=size, dpi=160)
        draw(fig, t)
        fig.savefig(os.path.join(IMG, name + suf + ".png"))
        plt.close(fig)


NG = 4096
k_ = np.arange(NG)
w_ = 0.35875 - 0.48829 * np.cos(2 * np.pi * k_ / NG) + 0.14128 * np.cos(4 * np.pi * k_ / NG) - 0.01168 * np.cos(6 * np.pi * k_ / NG)
LINE2DENS = 10 * np.log10(FS * (w_ ** 2).sum()) - 20 * np.log10(w_.sum())       # line-scaled dB -> dBFS/Hz: subtract


def spec(utc, state="on"):
    s = cap(utc)["burst"][state]
    return np.array(s["spec_f_khz"]) / 1e3, np.array(s["spec_line_db"])


def fig_burst(fig, t):
    ax1, ax2 = fig.subplots(1, 2, gridspec_kw=dict(width_ratios=[1.6, 1]))
    if CAPDIR:
        p = glob.glob(os.path.join(CAPDIR, "*T114312*.cf32"))[0]
        x = np.memmap(p, dtype="<c8", mode="r")
        n0 = 4_000_000
        seg = np.abs(np.asarray(x[n0:n0 + 327_680]))
        env = seg.reshape(-1, 64).max(axis=1)
        tt_ = np.arange(len(env)) * 64 / FS * 1e3
        ax1.fill_between(tt_, 0, env, color=t["c"][0], alpha=0.85, lw=0)
        ax1.set_xlim(0, tt_[-1])
        ax1.set_ylim(0, 1.0)
    ax1.set_xlabel("time (ms)")
    ax1.set_ylabel("|x|  (full scale = 1)")
    ax1.set_title("Received envelope: one tone, tx_atten 45 dB")
    d = [c["burst"]["duty"] for c in gated]
    col = [t["c"][1] if c["kind"] == "noise" else t["c"][0] for c in gated]
    ax2.scatter(range(1, len(d) + 1), d, c=col, s=26, zorder=3)
    ax2.axhline(DUTY, color=t["c"][2], lw=1.2, ls="--")
    ax2.text(len(d) + 0.3, DUTY + 0.004, "mean %.3f" % DUTY, color=t["c"][2], ha="right", va="bottom", fontsize=8.5)
    ax2.set_ylim(0.6, 0.72)
    ax2.set_xlabel("capture (time order)")
    ax2.set_ylabel("fraction of time the source is ON")
    ax2.set_title("Duty cycle, %d source-on captures" % len(d))
    ax2.scatter([], [], color=t["c"][1], s=26, label="noise")
    ax2.scatter([], [], color=t["c"][0], s=26, label="tones")
    ax2.legend(loc="lower left", ncol=2)
    fig.tight_layout()


themed("burst", fig_burst, (9.2, 3.3))


def fig_noise(fig, t):
    axs = fig.subplots(1, 2, sharey=True)
    for ax, (u, ttl) in zip(axs, (("111537", "414 MHz, gain 40.2, tx_atten 80"), ("104656", "434 MHz, gain 40.2, tx_atten 60"))):
        fo, so = spec(u, "on")
        ff, sf = spec(u, "off")
        k = 8
        dec = lambda a: db(lin(a[: len(a) // k * k]).reshape(-1, k).mean(axis=1))
        fx = fo[: len(fo) // k * k].reshape(-1, k).mean(axis=1)
        ax.axvspan(-0.7, -0.3, color=t["c"][2], alpha=0.16, lw=0)
        ax.plot(fx, dec(so) - LINE2DENS, color=t["c"][0], lw=1.1, label="source ON (inside bursts)")
        ax.plot(fx, dec(sf) - LINE2DENS, color=t["c"][5], lw=1.1, label="source OFF (inside gaps)")
        b = cap(u)["burst"]
        ax.set_title(ttl)
        ax.set_xlabel("baseband frequency (MHz)")
        ax.set_xlim(-4.096, 4.096)
        ax.text(0.03, 0.05, "Y = %.2f dB in the meter band" % (b["on"]["noise_meter_dbfs"] - b["off"]["noise_meter_dbfs"]), transform=ax.transAxes, color=t["fg"], fontsize=8.8)
    axs[0].set_ylabel("noise density (dBFS/Hz)")
    axs[0].legend(loc="upper right")
    axs[1].text(-0.5, axs[1].get_ylim()[1] - 1.0, "400 kHz\nmeter", ha="center", va="top", color=t["c"][2], fontsize=8)
    fig.tight_layout()


themed("noise_spectra", fig_noise, (9.2, 3.4))


def fig_nf(fig, t):
    ax = fig.subplots()
    x = np.arange(3)
    gg = GAINS[::-1]
    series = [
        ("Y-factor, 434 MHz, tx_atten 60", [row(434, g, 60)["nf"] for g in gg], t["c"][0], "o"),
        ("Y-factor, 414 MHz, tx_atten 60", [row(414, g, 60)["nf"] for g in gg], t["c"][1], "s"),
        ("Y-factor, 414 MHz, tx_atten 80", [row(414, g, 80)["nf"] for g in gg], t["c"][4], "D"),
        ("Y-factor, 404 MHz, tx_atten 60", [row(404, g, 60)["nf"] for g in gg], t["c"][2], "^"),
        ("direct method, measured G_FS", [R["direct_corrected"][g]["nf"] for g in gg], t["c"][3], "x"),
    ]
    for i, (lab, y, c, mk) in enumerate(series):
        ax.plot(x + (i - 2) * 0.05, y, mk, color=c, ms=6.5, mew=1.6, label=lab, ls="-" if i < 3 else "none", lw=0.9, alpha=0.95)
    ax.plot(x, [row(414, g, 80)["nf_log"] for g in gg], "v", color=t["c"][5], ms=6, ls=":", lw=1, label="414 MHz, tx_atten 80, averaged meters (uncorrected)")
    ax.set_xticks(x)
    ax.set_xticklabels(["rf_gain %s" % g for g in gg])
    ax.set_ylabel("noise figure (dB)")
    ax.set_ylim(0, 14)
    ax.legend(loc="upper right")
    ax.set_title("Noise figure vs gain setting  (A_pad = 0, P_max = 6.5 dBm)")
    fig.tight_layout()


themed("nf_vs_gain", fig_nf, (7.4, 4.0))


def fig_single(fig, t):
    ax, ax2 = fig.subplots(1, 2, gridspec_kw=dict(width_ratios=[1.35, 1]))
    pin_ = np.array([p_tone(a, 0) for a in tx])
    pe = np.array([p_tone(a, 0) for a in tx_eff])
    xx = np.linspace(-66.5, -44, 200)
    ax.plot(xx, xx + GFS0, color=t["c"][5], ls="--", lw=1, label="slope 1 (conversion %.1f dB)" % GFS0)
    ax.plot(xx, [clip_model(v_ + GFS0) for v_ in xx], color=t["c"][2], lw=1.1, label="ideal I/Q hard limiter at 0 dBFS")
    ax.axhline(0, color=t["c"][3], lw=0.9, ls=":")
    ax.text(-66.2, 0.4, "ADC full scale", color=t["c"][3], fontsize=8.3)
    ax.plot(pin_, f1_log, "o-", color=t["c"][1], ms=4.5, lw=1, label="f1 meter, time average (data sheet)")
    ax.plot(pin_, on, "o", color=t["c"][0], ms=5.5, label="f1 inside the bursts (captures)")
    fpd = fp["single_tone_434MHz_gain_40.2"]
    ax.plot([p_tone(a, 0) for a in fpd["tx_atten"]], fpd["f1"], "x", color=t["c"][5], ms=5, label="first pass (handwritten sheet)")
    ax.set_xlabel("tone power at the RX port (dBm), A_pad = 0")
    ax.set_ylabel("f1 level (dBFS)")
    ax.set_xlim(-66.5, -44)
    ax.set_ylim(-26, 3)
    ax.legend(loc="lower right", fontsize=7.8)
    ax.set_title("Single-tone sweep, 434 MHz, rf_gain 40.2")
    ax2.plot(pin_, dev_on, "o--", color=t["c"][5], ms=4.5, lw=1, label="tx_atten as written")
    ax2.plot(pe, dev_on_eff, "o-", color=t["c"][0], ms=5.5, label="'43 dB' counted as 44 dB")
    ax2.plot(xx, [v_ + GFS0 - clip_model(v_ + GFS0) for v_ in xx], color=t["c"][2], lw=1.1, label="ideal hard limiter")
    ax2.axhline(1, color=t["c"][3], lw=0.9, ls=":")
    ax2.set_xlim(-52, -44)
    ax2.set_ylim(-0.3, 2.2)
    ax2.set_xlabel("tone power at the RX port (dBm)")
    ax2.set_ylabel("gain compression (dB)")
    ax2.set_title("Compression of the fundamental")
    ax2.legend(loc="upper left", fontsize=7.8)
    fig.tight_layout()


themed("single_tone", fig_single, (9.4, 3.9))


def fig_sspec(fig, t):
    axs = fig.subplots(1, 2, sharey=True)
    c1, c2 = cap("114312"), cap("114954")
    ttl = ("tx_atten 45: tone at %.1f dBFS, no clipped samples" % c1["burst"]["on"]["lines"]["f1"],
           "tx_atten 40: %.0f %% of the samples clipped" % (100 * c2["clip_fraction"] / c2["burst"]["duty"]))
    for ax, u, tl, c in zip(axs, ("114312", "114954"), ttl, (t["c"][0], t["c"][3])):
        fx, s = spec(u)
        ax.plot(fx, s, color=c, lw=0.9)
        ax.set_title(tl)
        ax.set_xlim(-4.096, 4.096)
        ax.set_ylim(-100, 8)
        ax.set_xlabel("baseband frequency (MHz)")
    axs[0].set_ylabel("level in 4 kHz noise bandwidth (dBFS)")
    axs[1].annotate("-3·f1", xy=(-0.9, c2["burst"]["on"]["harm"]["h3"]), xytext=(-2.6, -4), color=t["fg"], fontsize=8.5, arrowprops=dict(arrowstyle="-", color=t["dim"], lw=0.7))
    fig.tight_layout()


themed("single_tone_spectra", fig_sspec, (9.2, 3.3))


def fig_two(fig, t):
    ax, ax2 = fig.subplots(1, 2, gridspec_kw=dict(width_ratios=[1.15, 1]))
    for u, c, lab in (("120839", t["c"][3], "ADC clipping (tones %.1f dBFS)"), ("120954", t["c"][0], "below clipping (tones %.1f dBFS)")):
        fx, s = spec(u)
        o = cap(u)["burst"]["on"]["lines"]
        ax.plot(fx, s, color=c, lw=0.9, label=lab % ((o["f1"] + o["f2"]) / 2))
    ax.set_xlim(-0.4, 1.1)
    ax.set_ylim(-95, 8)
    for fq, lab in ((0.2, "2f1-f2"), (0.3, "f1"), (0.4, "f2"), (0.5, "2f2-f1")):
        ax.text(fq, 3.0, lab, ha="center", fontsize=8, color=t["dim"])
    ax.set_xlabel("baseband frequency (MHz)")
    ax.set_ylabel("level in 4 kHz noise bandwidth (dBFS)")
    ax.set_title("Two-tone spectra inside the bursts")
    ax.legend(loc="lower right")
    ax2.plot(tone, im, "x", color=t["c"][5], ms=6, mew=1.5, label="first pass, meters (data sheet)")
    ax2.plot([s["tone"] for s in shots], [s["im"] for s in shots], "s", color=t["c"][2], ms=5.5, label="screenshots, meters")
    ax2.plot([c["tone_avg"] for c in tc], [c["im_avg"] for c in tc], "o", color=t["c"][1], ms=5.5, label="captures, meters (time average)")
    ax2.plot([c["tone_on"] for c in tc], [c["im_on"] for c in tc], "o", color=t["c"][0], ms=6, label="captures, inside the bursts")
    xx = np.linspace(-22, 0, 50)
    ax2.plot(xx, xx + SK_AVG, color=t["c"][1], lw=0.9, ls=":", label="source splatter in the meters (%.1f dBc)" % SK_AVG)
    ax2.plot(xx, xx + SK_ON, color=t["c"][0], lw=0.9, ls=":", label="source skirt inside bursts (%.1f dBc)" % SK_ON)
    ax2.plot(xx, 3 * (xx - tc[2]["tone_on"]) + tc[2]["im_on"], color=t["c"][3], lw=0.9, ls="--", label="slope 3 reference")
    ax2.axvline(-6.02, color=t["dim"], lw=0.8, ls="-.")
    ax2.text(-5.8, -78, "two-tone peak\n= full scale", fontsize=7.8, color=t["dim"])
    ax2.set_xlim(-22, 0)
    ax2.set_ylim(-80, -8)
    ax2.set_xlabel("level of each tone (dBFS)")
    ax2.set_ylabel("level at 2f1-f2 and 2f2-f1 (dBFS)")
    ax2.set_title("Third-order products vs tone level")
    ax2.legend(loc="upper left", fontsize=7.2)
    fig.tight_layout()


themed("two_tone", fig_two, (9.6, 4.2))


def fig_ant(fig, t):
    ax = fig.subplots()
    ax.plot(f, v, color=t["c"][0], marker="o", ms=2.5, lw=1.3)
    a = R["antenna"]
    ax.axhline(a["peak_db"] - 3, color=t["c"][2], lw=0.9, ls="--")
    ax.axhline(a["peak_db"] - 6, color=t["c"][4], lw=0.9, ls="--")
    ax.axvspan(a["fl6"], a["fh6"], color=t["c"][4], alpha=0.10, lw=0)
    ax.axvspan(a["fl3"], a["fh3"], color=t["c"][2], alpha=0.18, lw=0)
    ax.text(2980, a["peak_db"] - 3 + 0.5, "peak - 3 dB (link): %.0f-%.0f MHz" % (a["fl3"], a["fh3"]), color=t["c"][2], ha="right", fontsize=8.5)
    ax.text(2980, a["peak_db"] - 6 - 2.4, "peak - 6 dB (link) = - 3 dB per antenna: %.0f-%.0f MHz" % (a["fl6"], a["fh6"]), color=t["c"][4], ha="right", fontsize=8.5)
    ax.set_xlim(400, 3000)
    ax.set_xlabel("RF frequency (MHz)")
    ax.set_ylabel("received tone power (dB, relative)")
    ax.set_title("Antenna-to-antenna link response, 400-3000 MHz, 20 MHz steps")
    fig.tight_layout()


themed("antenna", fig_ant, (8.6, 3.6))


def fig_trade(fig, t):
    ax, ax2 = fig.subplots(1, 2)
    gx = np.linspace(-24, 12, 200)
    ref = "49.6"
    f_ref = (A_ * lin(actual_gain[ref]) + B_) / (A_ * lin(actual_gain[ref]))
    f_model = db((A_ * lin(gx) + B_) / (A_ * lin(gx)) / f_ref) + NF[ref]["mean"]
    ax.plot(gx, f_model, color=t["c"][5], lw=1, ls="--", label="two-term noise model (fit)")
    ax.plot([actual_gain[g] for g in GAINS], [NF[g]["mean"] for g in GAINS], "o", color=t["c"][0], ms=6.5, label="Y-factor (mean of 434 / 414 MHz)")
    for g in GAINS:
        ax.annotate("rf_gain %s" % g, (actual_gain[g], NF[g]["mean"]), textcoords="offset points", xytext=(6, 6), fontsize=8, color=t["dim"])
    ax.set_xlabel("gain relative to rf_gain 40.2 (dB, measured)")
    ax.set_ylabel("noise figure (dB)")
    ax.set_ylim(0, 24)
    ax.set_title("Noise figure vs gain")
    ax.legend(loc="upper right")
    pfs = -GFS0 - gx
    floor = -174 + f_model + 10 * np.log10(B_REF)
    ax2.plot(gx, pfs + P1_OVER_FS - floor, color=t["c"][1], lw=1.4, label="P1dB - noise floor (10 kHz)")
    ax2.plot(gx, pfs - 6.02 - floor, color=t["c"][2], lw=1.4, label="two-tone clip level - noise floor")
    for g in GAINS:
        ax2.plot(actual_gain[g], trade[g]["dr"], "o", color=t["c"][1], ms=6)
        ax2.plot(actual_gain[g], trade[g]["two_tone_headroom"], "o", color=t["c"][2], ms=6)
    ax2.axvline(db(B_ / A_), color=t["dim"], lw=0.8, ls="-.")
    ax2.text(db(B_ / A_) + 0.6, ax2.get_ylim()[0] + 1.5, "front-end noise\n= fixed noise", fontsize=7.8, color=t["dim"])
    ax2.set_xlabel("gain relative to rf_gain 40.2 (dB, measured)")
    ax2.set_ylabel("dynamic range (dB)")
    ax2.set_title("Dynamic range in a 10 kHz channel")
    ax2.legend(loc="upper right")
    fig.tight_layout()


themed("tradeoff", fig_trade, (9.4, 3.7))
print("duty %.4f (%.2f dB)  G_FS %.2f  A_fs %.2f  P_fs %.2f  P1 over FS %.2f" % (DUTY, DUTY_DB, GFS0, A_FS, P_FS, P1_OVER_FS))
