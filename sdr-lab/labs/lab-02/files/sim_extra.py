"""
Pre-lab 02, task 4: extra points on the same flowgraph (lab02_sim.py, unchanged):
  - gain 0 dB with ENR = 45 dB (with 35 dB the Y factor was only 2.2 dB),
  - noise figure and single-tone sweep at gains 5, 15 and 25 dB, to locate the gain
    with the largest P1dB - noise floor more finely than the 10 dB grid of task 4.5.
Same averaging meters as sim_measure.py.
"""
import json
import math
import os
import sys
import threading

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import numpy as np
from PyQt5 import Qt
from gnuradio import gr

SRC = sys.argv[1] if len(sys.argv) > 1 else '.'
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'out')
sys.path.insert(0, SRC)
import lab02_sim  # noqa: E402


class AvgPower(gr.sync_block):
    def __init__(self, name):
        gr.sync_block.__init__(self, name=name, in_sig=[np.complex64], out_sig=None)
        self.lock = threading.Lock(); self.skip = self.n = self.cnt = 0; self.acc = 0.0
        self.done = threading.Event(); self.done.set()

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
                    k = min(self.skip, len(x)); self.skip -= k
                if self.skip == 0 and k < len(x):
                    y = x[k:k + (self.n - self.cnt)]
                    self.acc += float(np.vdot(y, y).real); self.cnt += len(y)
                    if self.cnt >= self.n:
                        self.done.set()
        return len(x)

    def mean_db(self):
        return 10 * math.log10(max(self.acc / max(self.cnt, 1), 1e-30))


app = Qt.QApplication(sys.argv)
tb = lab02_sim.lab08_sim()
FS = tb.samp_rate
meters = {}
for name, src, rate in (('t1', tb.t1_band, FS / 64), ('noise', tb.noise_band, FS / 4)):
    m = AvgPower(name); tb.connect((src, 0), (m, 0)); meters[name] = (m, rate)
tb.throttle.set_sample_rate(1e9)
tb.start()


def measure(nm, settle=0.15, seconds=0.25):
    m, rate = meters[nm]; m.arm(settle * rate, seconds * rate); m.done.wait(); app.processEvents()
    return m.mean_db()


def yfactor(gain, enr):
    tb.set_gain(gain); tb.set_enr_db(enr); tb.set_mode(0)
    off = measure('noise', seconds=0.5)
    tb.set_mode(1)
    on = measure('noise', seconds=0.5)
    Y = 10 ** ((on - off) / 10)
    return dict(gain=gain, enr=enr, off=off, on=on, Ydb=on - off, NF=10 * math.log10(10 ** (enr / 10) / (Y - 1)))


res = {'nf': [], 'sweep1': {}}
res['nf'].append(yfactor(0, 45))
for g, enr in ((5, 35), (15, 25), (25, 25)):
    res['nf'].append(yfactor(g, enr))
for g in (5, 15, 25):
    fs_in = tb.p_fs0 - g
    pts, p = [], fs_in - 40
    while p <= min(fs_in + 8, -10.0) + 1e-9:
        tb.set_gain(g); tb.set_p_in(p); tb.set_mode(2)
        pts.append([p, measure('t1', seconds=0.1)])
        p += 1.0 if p < fs_in - 12 else 0.25
    res['sweep1'][str(g)] = pts
for row in res['nf']:
    print('gain {gain:2d} ENR {enr:2d}  Y {Ydb:6.2f} dB  NF {NF:6.2f} dB  (on {on:.2f} dBFS)'.format(**row), flush=True)
with open(os.path.join(OUT, 'sim_extra.json'), 'w') as fp:
    json.dump(res, fp, indent=1)
tb.stop(); tb.wait()
os._exit(0)
