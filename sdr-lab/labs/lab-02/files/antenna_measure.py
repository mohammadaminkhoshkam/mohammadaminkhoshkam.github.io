"""
Pre-lab 02, task 5: run the course script lab02_antenna_response_simulation.py
(class FilterSimulation, unchanged) offscreen, press "Start sweep: 400-3000 MHz"
with the default 20 MHz step, then re-measure both 3 dB edges with 1 MHz steps
using the script's own manual-frequency control and power meter.

Run with the radioconda Python:
    radioconda\\python.exe antenna_measure.py <folder with lab02_antenna_response_simulation.py>
"""
import json
import os
import sys
import time

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import numpy as np
from PyQt5 import QtWidgets

SRC = sys.argv[1] if len(sys.argv) > 1 else '.'
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'out')
os.makedirs(OUT, exist_ok=True)
sys.path.insert(0, SRC)
import lab02_antenna_response_simulation as ant  # noqa: E402

app = QtWidgets.QApplication(sys.argv)
w = ant.FilterSimulation()
w.show()
w.begin()


def pump(cond, timeout):
    t0 = time.time()
    while not cond() and time.time() - t0 < timeout:
        app.processEvents()
        time.sleep(0.005)


# ---- 1. the sweep exactly as in the GUI (default step 20 MHz)
t0 = time.time()
w.start_sweep()
pump(lambda: not w.running_sweep, 600)
coarse = sorted((f / 1e6, float(v)) for f, v in w.points.items())
w.grab().save(os.path.join(OUT, 'gui_antenna.png'))
print('coarse sweep: {} points in {:.0f} s'.format(len(coarse), time.time() - t0), flush=True)

# ---- 2. half-power points from the coarse sweep, then 1 MHz steps around each edge
f = np.array([c[0] for c in coarse]); r = np.array([c[1] for c in coarse])
peak = r.max(); half = peak - 3.0


def interp(fq, rq, a, b):
    return fq[a] + (half - rq[a]) * (fq[b] - fq[a]) / (rq[b] - rq[a])


def rising(fq, rq):   # first point at/above the half-power level -> lower edge
    i0 = int(np.argmax(rq >= half))
    return interp(fq, rq, i0 - 1, i0)


def falling(fq, rq):  # last point at/above the half-power level -> upper edge
    above = rq >= half
    i1 = len(above) - 1 - int(np.argmax(above[::-1]))
    return interp(fq, rq, i1, i1 + 1)


cL, cH = rising(f, r), falling(f, r)
fine = {}
for centre in (cL, cH):
    for mhz in np.arange(round(centre) - 25, round(centre) + 26, 1.0):
        rf = round(mhz * 1e6)
        w.points.pop(rf, None)
        w.frequency.setValue(mhz)
        pump(lambda: rf in w.points, 30)
        fine[float(mhz)] = float(w.points[rf])
ff = np.array(sorted(fine)); rr = np.array([fine[k] for k in ff])
# the fine points include the 3 dB level of the coarse peak; use the same reference (peak of the coarse sweep)
lo_mask = ff < (cL + cH) / 2
fL = rising(ff[lo_mask], rr[lo_mask])
fH = falling(ff[~lo_mask], rr[~lo_mask])
res = dict(peak_db=float(peak), peak_mhz=float(f[np.argmax(r)]), coarse=coarse, fine=sorted(fine.items()),
           coarse_fL=float(cL), coarse_fH=float(cH), fL=float(fL), fH=float(fH), BW=float(fH - fL),
           step_coarse=20.0, step_fine=1.0)
with open(os.path.join(OUT, 'antenna.json'), 'w') as fp:
    json.dump(res, fp, indent=1)
np.savetxt(os.path.join(OUT, 'antenna.csv'), np.array(coarse), delimiter=',',
           header='rf_equivalent_frequency_mhz,response_db', comments='')
print('peak {:.2f} dB at {:.0f} MHz | coarse fL {:.1f} fH {:.1f} | fine fL {:.2f} fH {:.2f} BW {:.2f} MHz'.format(
    peak, res['peak_mhz'], cL, cH, fL, fH, fH - fL), flush=True)
w.close()
os._exit(0)
