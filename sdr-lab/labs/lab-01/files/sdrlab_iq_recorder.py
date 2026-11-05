"""
SDR Lab IQ Recorder -- Embedded Python Block (GNU Radio 3.10)

Records raw complex64 I/Q samples to
    teamID_labNN_fc_fs_gain_timestamp.cf32
e.g. Team-07_lab01_945000000_2600000_20.0_20261005T101502.cf32

States (Lab 01 manual, Fig. 8):
    IDLE      -- no file open; record = True opens a new file -> RECORDING
    RECORDING -- file open; closes when
                   (a) record -> False                     -> IDLE
                   (b) floor(max_seconds * fs) samples hit -> WAIT
                   (c) fc / fs / gain changed              -> WAIT
                   (d) flowgraph stopped (stop())
    WAIT      -- file closed automatically; waits for record -> False
                 so that no new file is opened by itself  -> IDLE

Paste this file into an Embedded Python Block (Open in Editor) and set:
    team, lab, fc=f_tune, fs=samp_rate, gain=rf_gain, record=rec,
    max_seconds=rec_sec, folder="recordings"
"""

import os
import time

import numpy as np
from gnuradio import gr

IDLE, RECORDING, WAIT = 'IDLE', 'RECORDING', 'WAIT'


class blk(gr.sync_block):
    """SDR Lab IQ Recorder: writes raw complex64 I/Q (.cf32) with the
    standard lab file name. Tick `record` to start; the file closes when
    the tick is removed, after max_seconds, when fc/fs/gain change, or
    when the flowgraph stops."""

    def __init__(self, team='Team-00', lab=1, fc=100e6, fs=2.6e6, gain=0.0,
                 record=False, max_seconds=5.0, folder='.'):
        gr.sync_block.__init__(
            self,
            name='SDR Lab IQ Recorder',
            in_sig=[np.complex64],
            out_sig=None,
        )
        # Same names as the arguments, so GRC callbacks update them at run time.
        self.team = team
        self.lab = lab
        self.fc = fc
        self.fs = fs
        self.gain = gain
        self.record = record
        self.max_seconds = max_seconds
        self.folder = folder

        self._state = IDLE
        self._file = None
        self._path = ''
        self._settings = None    # (fc, fs, gain) at the moment the file opened
        self._target = 0         # floor(max_seconds * fs)
        self._written = 0

    # ---------------------------------------------------------------- helpers
    def _current_settings(self):
        return (int(round(float(self.fc))),
                int(round(float(self.fs))),
                round(float(self.gain), 1))

    def _open(self):
        fc, fs, gain = self._settings = self._current_settings()
        folder = str(self.folder) or '.'
        os.makedirs(folder, exist_ok=True)
        stamp = time.strftime('%Y%m%dT%H%M%S')
        name = '{}_lab{:02d}_{}_{}_{:.1f}_{}.cf32'.format(
            self.team, int(self.lab), fc, fs, gain, stamp)
        self._path = os.path.join(folder, name)
        self._file = open(self._path, 'wb')
        self._target = int(np.floor(float(self.max_seconds) * fs))
        self._written = 0
        self._state = RECORDING
        print('[REC] start {}'.format(name), flush=True)

    def _close(self, reason, next_state):
        if self._file is not None:
            self._file.close()
            self._file = None
            fs = self._settings[1] if self._settings else float(self.fs)
            print('[REC] stop  {} samples = {:.2f} s ({})'.format(
                self._written, self._written / fs, reason), flush=True)
        self._state = next_state

    # ------------------------------------------------------------------- work
    def work(self, input_items, output_items):
        x = input_items[0]
        record = bool(self.record)

        if self._state == IDLE:
            if record:
                self._open()
        elif self._state == WAIT:
            if not record:
                self._state = IDLE

        if self._state == RECORDING:
            if not record:
                self._close('record unchecked', IDLE)
            elif self._current_settings() != self._settings:
                # This buffer already belongs to the new settings: do not write it.
                self._close('fc/fs/gain changed', WAIT)
            else:
                n = min(len(x), self._target - self._written)
                if n > 0:
                    x[:n].astype(np.complex64, copy=False).tofile(self._file)
                    self._written += n
                if self._written >= self._target:
                    self._close('max_seconds reached', WAIT)

        return len(x)

    def stop(self):
        self._close('flowgraph stopped', IDLE)
        return True
