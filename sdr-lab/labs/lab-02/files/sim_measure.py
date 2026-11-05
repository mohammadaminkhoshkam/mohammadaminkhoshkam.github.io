"""
Pre-lab 02, task 4: run the course flowgraph lab02_sim.py (class lab08_sim, unchanged)
headless and take every measurement of the task with its own meters.

The flowgraph's meters are RMS -> 20 log10 of the band-filter outputs (dBFS). Here an
averaging sink is attached to the same band filters (t1_band, t2_band, im_lo_band,
im_hi_band: 10 kHz; noise_band: 400 kHz), so each reading is the mean power over a fixed
number of samples after a settling time, instead of a value read off a moving GUI number.
The throttle is opened up so the simulation runs faster than real time; all timing is in
samples, so results do not depend on the CPU speed.

Run with the radioconda Python:  radioconda\\python.exe sim_measure.py <folder with lab02_sim.py>
"""
import json
import math
import os
import sys
import threading
import time

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import numpy as np
from PyQt5 import Qt
from gnuradio import gr, blocks

SRC = sys.argv[1] if len(sys.argv) > 1 else '.'
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'out')
os.makedirs(OUT, exist_ok=True)
sys.path.insert(0, SRC)
import lab02_sim  # noqa: E402


class AvgPower(gr.sync_block):
    """Mean |x|^2 over n samples, after skipping `skip` samples (settling / old buffers)."""

    def __init__(self, name):
        gr.sync_block.__init__(self, name=name, in_sig=[np.complex64], out_sig=None)
        self.lock = threading.Lock()
        self.skip, self.n, self.acc, self.cnt = 0, 0, 0.0, 0
        self.done = threading.Event()
        self.done.set()

    def arm(self, skip, n):
        with self.lock:
            self.skip, self.n, self.acc, self.cnt = int(skip), int(n), 0.0, 0
            self.done.clear()

    def work(self, input_items, output_items):
        x = input_items[0]
        with self.lock:
            if not self.done.is_set():
                k = 0
                if self.skip > 0:
                    k = min(self.skip, len(x))
                    self.skip -= k
                if self.skip == 0 and k < len(x):
                    y = x[k:k + (self.n - self.cnt)]
                    self.acc += float(np.vdot(y, y).real)
                    self.cnt += len(y)
                    if self.cnt >= self.n:
                        self.done.set()
        return len(x)

    def mean_db(self):
        return 10 * math.log10(max(self.acc / max(self.cnt, 1), 1e-30))


app = Qt.QApplication(sys.argv)
tb = lab02_sim.lab08_sim()
FS = tb.samp_rate
meters = {}
for name, src, rate in (('t1', tb.t1_band, FS / 64), ('t2', tb.t2_band, FS / 64), ('im_lo', tb.im_lo_band, FS / 64),
                        ('im_hi', tb.im_hi_band, FS / 64), ('noise', tb.noise_band, FS / 4)):
    m = AvgPower(name)
    tb.connect((src, 0), (m, 0))
    meters[name] = (m, rate)
tb.throttle.set_sample_rate(1e9)          # run as fast as the CPU allows (timing is in samples)
tb.start()


def measure(names, settle=0.15, seconds=0.25):
    """Arm the listed meters; settle/seconds are in simulated time."""
    for nm in names:
        m, rate = meters[nm]
        m.arm(settle * rate, seconds * rate)
    for nm in names:
        meters[nm][0].done.wait()
        app.processEvents()
    return {nm: meters[nm][0].mean_db() for nm in names}


def setup(mode=None, gain=None, p_in=None, enr=None):
    if gain is not None:
        tb.set_gain(gain)
    if enr is not None:
        tb.set_enr_db(enr)
    if p_in is not None:
        tb.set_p_in(p_in)
    if mode is not None:
        tb.set_mode(mode)


results = {'model': dict(samp_rate=FS, p_fs0=tb.p_fs0, nf_fe=tb.nf_fe, iip3_fe=tb.iip3_fe, f1=tb.f1, f2=tb.f2,
                         f_noise=tb.f_noise, bw_tone=tb.bw_tone, bw_noise=tb.bw_noise)}
t_start = time.time()

# ------------------------------------------------------------------ 4.1 / 4.5  Y-factor noise figure
nf_rows = []
for gain in (0, 10, 20, 30, 40, 50):
    for enr in (15, 25, 35):
        setup(mode=0, gain=gain, enr=enr)
        off = measure(['noise'], seconds=0.5)['noise']
        setup(mode=1)
        on = measure(['noise'], seconds=0.5)['noise']
        Ydb = on - off
        Y = 10 ** (Ydb / 10)
        F = 10 ** (enr / 10) / (Y - 1) if Y > 1 else float('inf')
        nf_rows.append(dict(gain=gain, enr=enr, off=off, on=on, Ydb=Ydb, NF=10 * math.log10(F)))
        print('NF  gain {:2d}  ENR {:2d}  off {:7.2f}  on {:7.2f}  Y {:6.2f} dB  NF {:6.2f} dB'.format(gain, enr, off, on, Ydb, nf_rows[-1]['NF']), flush=True)
results['nf'] = nf_rows

# repeatability of one Y-factor reading (gain 40, ENR 15): 10 independent repeats
rep = []
for i in range(10):
    setup(mode=0, gain=40, enr=15)
    off = measure(['noise'], seconds=0.5)['noise']
    setup(mode=1)
    on = measure(['noise'], seconds=0.5)['noise']
    rep.append(on - off)
results['nf_repeat'] = dict(gain=40, enr=15, Ydb=rep)

# fluctuation of the 400 kHz noise reading vs averaging time (gain 40, source off)
setup(mode=0, gain=40, enr=15)
fluct = []
for tau in (0.002, 0.005, 0.01, 0.02, 0.05, 0.1):
    vals = [measure(['noise'], settle=0.02, seconds=tau)['noise'] for _ in range(30)]
    fluct.append(dict(tau=tau, std=float(np.std(vals, ddof=1)), mean=float(np.mean(vals))))
    print('noise reading  tau {:6.3f} s  std {:.4f} dB'.format(tau, fluct[-1]['std']), flush=True)
results['fluct'] = fluct

# ------------------------------------------------------------------ 4.2 / 4.5  single-tone sweep (P1dB)
sweep1 = {}
for gain in (0, 10, 20, 30, 40, 50):
    fs_in = tb.p_fs0 - gain                      # input power that reaches full scale (dBm)
    lo, hi = fs_in - 40, min(fs_in + 8, -10.0)   # never above -10 dBm (safety rule of the lab)
    pts = []
    p = lo
    while p <= hi + 1e-9:
        setup(mode=2, gain=gain, p_in=p)
        out = measure(['t1'], seconds=0.1)['t1']
        pts.append([p, out])
        p += 1.0 if p < fs_in - 12 else 0.25    # 1 dB steps, 0.25 dB near compression
    sweep1[str(gain)] = pts
    print('sweep1 gain {:2d}: {} points {:.1f}..{:.1f} dBm'.format(gain, len(pts), lo, hi), flush=True)
results['sweep1'] = sweep1

# ------------------------------------------------------------------ 4.3 / 4.4  two-tone test
two = {}
for gain in (0, 40):
    fs_in = tb.p_fs0 - gain
    pts = []
    p = fs_in - 45
    while p <= min(fs_in + 3, -10.0) + 1e-9:
        setup(mode=3, gain=gain, p_in=p)
        r = measure(['t1', 't2', 'im_lo', 'im_hi'], seconds=0.25)
        pts.append([p, r['t1'], r['t2'], r['im_lo'], r['im_hi']])
        p += 1.0
    two[str(gain)] = pts
    print('two-tone gain {:2d}: {} points'.format(gain, len(pts)), flush=True)
# noise floor of the 10 kHz meters (no signal), for every gain
floor10 = {}
for gain in (0, 10, 20, 30, 40, 50):
    setup(mode=0, gain=gain)
    r = measure(['t1', 'im_lo'], seconds=0.5)
    floor10[str(gain)] = (r['t1'] + r['im_lo']) / 2
results['two'] = two
results['floor10'] = floor10

# ------------------------------------------------------------------ GUI screenshots (offscreen)
shots = {}
tb.throttle.set_sample_rate(FS)   # real-time again so the Qt sinks update as in the session
tb.resize(1100, 1500)
tb.show()
for key, (mode, gain, p_in) in {'two_tone_gain0': (3, 0, -40), 'two_tone_gain40': (3, 40, -75), 'noise_on_gain40': (1, 40, -80)}.items():
    setup(mode=mode, gain=gain, p_in=p_in, enr=15)
    t0 = time.time()
    while time.time() - t0 < 3.0:
        app.processEvents()
        time.sleep(0.02)
    path = os.path.join(OUT, 'gui_' + key + '.png')
    tb.grab().save(path)
    shots[key] = os.path.basename(path)
results['shots'] = shots

results['runtime_s'] = time.time() - t_start
results['gnuradio'] = gr.version()
with open(os.path.join(OUT, 'sim_results.json'), 'w') as fp:
    json.dump(results, fp, indent=1)
print('done in {:.0f} s'.format(results['runtime_s']), flush=True)
tb.stop()
tb.wait()
os._exit(0)
