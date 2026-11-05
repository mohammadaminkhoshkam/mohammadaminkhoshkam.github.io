"""
Prepare the Lab 01 recordings for the website.

This script does NOT analyse anything: it only repackages each raw .cf32
recording (complex64, no header) as a shorter, lossless int16 excerpt
(.cs16, interleaved I/Q, little-endian) that the browser can download.

The Pluto's AD9363 has a 12-bit ADC, so every float sample is an exact
multiple of 1/2048; storing round(x * 2048) as int16 loses nothing (the
script checks this). All analysis is done by assets/js/sdr-dsp.js, in the
browser or in Node (tools/precompute_lab01.mjs).

Usage:  python tools/make_lab01_data.py  <recordings folder>
"""
import json
import os
import re
import sys

import numpy as np

OUT = os.path.join(os.path.dirname(__file__), '..', 'sdr-lab', 'lab-01', 'data')
NAME_RE = re.compile(r'^(?P<team>.+)_lab(?P<lab>\d{2})_(?P<fc>\d+)_(?P<fs>\d+)_'
                     r'(?P<gain>-?\d+(?:\.\d+)?)_(?P<ts>\d{8}T\d{6})\.cf32$')

# Role of every recording in the lab (from the lab manual and the session).
# lo_shift / f_tx only apply to the loopback flowgraph (Part 2).
ROLES = {
    '20261101T143515': dict(part=3, group='band', label='1089 MHz, 2.6 MS/s (1090 MHz search, gap-free)', seconds=1.0),
    '20261101T143653': dict(part=3, group='band', label='1089 MHz, 20 MS/s', seconds=0.1),
    '20261101T144509': dict(part=3, group='band', label='1114 MHz, 20 MS/s, gain 10 dB', seconds=0.1),
    '20261101T144709': dict(part=3, group='band', label='1114 MHz, 20 MS/s, gain 30 dB', seconds=0.1),
    '20261101T150359': dict(part=2, group='loopback', label='Loopback, f_tx = +250 kHz, lo_shift = 0',
                            f_tx=250e3, lo_shift=0, seconds=0.5),
    '20261101T150540': dict(part=2, group='loopback', label='Loopback, f_tx = -250 kHz, lo_shift = 0',
                            f_tx=-250e3, lo_shift=0, seconds=0.5),
    '20261101T150804': dict(part=2, group='loopback', label='Loopback, f_tx = +250 kHz, lo_shift = +100 kHz',
                            f_tx=250e3, lo_shift=100e3, seconds=0.5),
    '20261101T150844': dict(part=2, group='loopback', label='Loopback, f_tx = +250 kHz, lo_shift = +200 kHz',
                            f_tx=250e3, lo_shift=200e3, seconds=0.5),
    '20261101T150919': dict(part=2, group='loopback', label='Loopback, f_tx = +250 kHz, lo_shift = -100 kHz',
                            f_tx=250e3, lo_shift=-100e3, seconds=0.5),
    '20261101T151432': dict(part=3, group='band', label='945 MHz, 20 MS/s (GSM900 downlink, band C)', seconds=0.1),
    '20261101T151733': dict(part=3, group='band', label='90 MHz, 20 MS/s (FM broadcast, band A)', seconds=0.1),
}


def main(folder):
    os.makedirs(OUT, exist_ok=True)
    items = []
    for name in sorted(os.listdir(folder)):
        m = NAME_RE.match(name)
        if not m:
            continue
        d = m.groupdict()
        role = ROLES[d['ts']]
        fs = float(d['fs'])
        path = os.path.join(folder, name)
        total = os.path.getsize(path) // 8
        count = min(total, int(round(role['seconds'] * fs)))
        x = np.fromfile(path, dtype=np.complex64, count=count)

        iq = np.empty(2 * count, dtype=np.float32)
        iq[0::2], iq[1::2] = x.real, x.imag
        q = iq * 2048.0
        if np.max(np.abs(q - np.round(q))) != 0 or np.max(np.abs(q)) > 32767:
            raise SystemExit(name + ': samples are not exact 12-bit values')
        # short name (Windows path-length limit); the full standard name stays in the manifest
        out_name = d['ts'].split('T')[1] + '.cs16'
        np.round(q).astype('<i2').tofile(os.path.join(OUT, out_name))

        items.append(dict(
            id=d['ts'], file=name, data='data/' + out_name, team=d['team'], lab=int(d['lab']),
            fc=float(d['fc']), fs=fs, gain=float(d['gain']), time=d['ts'],
            samples_total=int(total), duration_total=total / fs,
            bytes_total=os.path.getsize(path),
            samples_excerpt=int(count), duration_excerpt=count / fs, scale=1 / 2048,
            **{k: v for k, v in role.items() if k != 'seconds'}))
        print('{:52s} {:6.3f} s of {:6.3f} s -> {}'.format(name, count / fs, total / fs, out_name))

    with open(os.path.join(OUT, 'manifest.json'), 'w', encoding='utf-8') as fp:
        json.dump(dict(format='cs16: int16 little-endian, interleaved I,Q; value / 2048 = sample',
                       recordings=items), fp, indent=1)
    print('wrote', os.path.join(OUT, 'manifest.json'))


if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else 'recordings')
