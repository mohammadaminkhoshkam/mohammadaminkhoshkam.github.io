#!/usr/bin/env python3
"""Generates the two GNU Radio 3.10 flowgraphs of the Lab 3 (FM) pre-lab:

  lab3_fm_sim.grc   - no hardware: FM modulator -> channel (CNR, frequency error) -> receiver
  lab3_fm_link.grc  - ADALM-Pluto cable link at 434 MHz: TX (tone, NBFM/WFM) -> RX, same device

Both receivers follow the rate plan of the handout: 2.4 MS/s -> Freq Xlating FIR /10 -> 240 kHz
-> 2nd channel FIR (NBFM: 10 kHz) -> detector (Quadrature Demod or PLL Freq Det, chosen at run time) -> audio FIR /5 -> 48 kHz
-> FM Deemphasis (50 us) -> audio sink. Parameters are the values of Table 3 of the pre-lab.
Run:  python make_grc.py   then  grcc lab3_fm_sim.grc  (or open them in GNU Radio Companion).
"""
import os
import yaml

HERE = os.path.dirname(os.path.abspath(__file__))


def blk(_name, _bid, _xy, **p):
    return {"name": _name, "id": _bid,
            "parameters": {k: str(v) for k, v in p.items()},
            "states": {"bus_sink": False, "bus_source": False, "bus_structure": None,
                       "coordinate": list(_xy), "rotation": 0, "state": "enabled"}}


def options(fid, title):
    return {"parameters": {"author": "Team SDR (M. A. Khoshkam, S. Yarmohammadi)", "catch_exceptions": "True",
                           "category": "[GRC Hier Blocks]", "generate_options": "qt_gui", "id": fid,
                           "output_language": "python", "placement": "(0,0)", "run": "True",
                           "run_command": "{python} -u {filename}", "run_options": "prompt",
                           "sizing_mode": "fixed", "title": title, "window_size": "(1400,1000)",
                           "max_nouts": "0", "realtime_scheduling": "", "qt_qss_theme": "",
                           "thread_safe_setters": "", "copyright": "", "description": "", "comment": "",
                           "gen_cmake": "On", "gen_linking": "dynamic", "hier_block_src_path": ".:",
                           "cmake_opt": ""},
            "states": {"bus_sink": False, "bus_source": False, "bus_structure": None,
                       "coordinate": [8, 8], "rotation": 0, "state": "enabled"}}


def var(name, value, xy):
    return blk(name, "variable", xy, value=value)


def rng(name, label, value, start, stop, step, xy, hint):
    return blk(name, "variable_qtgui_range", xy, label=f"'{label}'", rangeType="float", value=value, start=start,
               stop=stop, step=step, widget="counter_slider", orient="QtCore.Qt.Horizontal", min_len=200,
               gui_hint=hint)


def chooser(name, label, value, opts, labels, xy, hint, typ="int"):
    p = dict(label=f"'{label}'", type=typ, num_opts=len(opts), value=value, widget="radio_buttons",
             orient="QtCore.Qt.Horizontal", gui_hint=hint, options="[0, 1, 2]", labels="['', '', '']")
    for i, (o, l) in enumerate(zip(opts, labels)):
        p[f"option{i}"] = o
        p[f"label{i}"] = f"'{l}'"
    return blk(name, "variable_qtgui_chooser", xy, **p)


def fsink(name, typ, title, bw, fc, ymin, ymax, xy, hint, n=1, labels=None):
    p = dict(type=typ, name=f"'{title}'", fftsize=4096, freqhalf="True" if typ == "complex" else "False",
             wintype="window.WIN_BLACKMAN_hARRIS", norm_window="False", fc=fc, bw=bw, grid="True",
             autoscale="False", average="0.2", ymin=ymin, ymax=ymax, label="'Relative Gain'", units="'dB'",
             nconnections=n, update_time="0.10", showports="False", gui_hint=hint, tr_mode="qtgui.TRIG_MODE_FREE",
             tr_level="0.0", tr_chan="0", tr_tag="''", ctrlpanel="False", legend="True", axislabels="True")
    for i in range(1, 11):
        p[f"label{i}"] = f"'{labels[i-1]}'" if labels and i <= len(labels) else "''"
        p[f"width{i}"] = 1
        p[f"color{i}"] = ["'blue'", "'red'", "'green'", "'black'", "'cyan'", "'magenta'", "'yellow'",
                          "'dark red'", "'dark green'", "'dark blue'"][i - 1]
        p[f"alpha{i}"] = 1.0
    return blk(name, "qtgui_freq_sink_x", xy, **p)


def tsink(name, title, srate, npts, xy, hint, ymin=-1.5, ymax=1.5):
    p = dict(type="float", name=f"'{title}'", size=npts, srate=srate, grid="True", autoscale="False",
             ymin=ymin, ymax=ymax, nconnections=1, update_time="0.10", entags="True", showports="False",
             gui_hint=hint, tr_mode="qtgui.TRIG_MODE_AUTO", tr_slope="qtgui.TRIG_SLOPE_POS", tr_level="0.0",
             tr_delay="0", tr_chan="0", tr_tag="''", ctrlpanel="False", legend="True", axislabels="True",
             ylabel="'Amplitude'", yunit="''", stemplot="False")
    for i in range(1, 11):
        p[f"label{i}"] = "'audio'" if i == 1 else "''"
        p[f"width{i}"] = 1
        p[f"color{i}"] = "'blue'"
        p[f"style{i}"] = 1
        p[f"marker{i}"] = -1
        p[f"alpha{i}"] = 1.0
    return blk(name, "qtgui_time_sink_x", xy, **p)


def receiver(x0, y0, src):
    """Common receiver: returns (blocks, connections). `src` = (block, port) delivering 2.4 MS/s complex."""
    b = [
        blk("chan_filter", "freq_xlating_fir_filter_xxx", (x0 - 200, y0), type="ccf", decim="decim1",
            taps="firdes.low_pass(1.0, samp_rate, 100e3, 20e3, window.WIN_HAMMING)",
            center_freq="rx_offset", samp_rate="samp_rate"),
        blk("chan_filter2", "fir_filter_xxx", (x0, y0), type="ccf", decim=1,
            taps="firdes.low_pass(1.0, quad_rate, chan_cut, chan_tw, window.WIN_HAMMING)", samp_delay=0),
        blk("quad_demod", "analog_quadrature_demod_cf", (x0 + 300, y0 - 60), gain="quad_rate/(2*math.pi*dev)"),
        blk("pll_det", "analog_pll_freqdet_cf", (x0 + 300, y0 + 40), w="pll_lbw",
            max_freq="2*math.pi*pll_fmax/quad_rate", min_freq="-2*math.pi*pll_fmax/quad_rate"),
        blk("pll_gain", "blocks_multiply_const_vxx", (x0 + 520, y0 + 40), type="float",
            const="quad_rate/(2*math.pi*dev)", vlen=1),
        blk("det_select", "blocks_selector", (x0 + 720, y0), type="float", enabled="True", num_inputs=2,
            num_outputs=1, input_index="detector", output_index=0, vlen=1, showports="True"),
        blk("audio_filter", "fir_filter_xxx", (x0 + 900, y0), type="fff", decim="decim_audio",
            taps="firdes.low_pass(1.0, quad_rate, audio_cut, audio_tw, window.WIN_HAMMING)", samp_delay=0),
        blk("deemph", "analog_fm_deemph", (x0 + 1100, y0), samp_rate="audio_rate", tau="tau"),
        blk("volume_gain", "blocks_multiply_const_vxx", (x0 + 1280, y0), type="float", const="volume", vlen=1),
        blk("audio_out", "audio_sink", (x0 + 1460, y0), samp_rate="int(audio_rate)", device_name="''",
            ok_to_block="True", num_inputs=1),
        fsink("spec_chan", "complex", "Channel (240 kHz complex)", "quad_rate", 0, -100, 10,
              (x0 + 300, y0 + 160), "1,0,1,1"),
        fsink("spec_det", "float", "Detector output (240 kHz): L+R, pilot, L-R, RDS", "quad_rate", 0, -100, 10,
              (x0 + 900, y0 + 160), "1,1,1,1"),
        fsink("spec_audio", "float", "Audio (48 kHz)", "audio_rate", 0, -110, 0, (x0 + 1460, y0 + 160), "2,0,1,1"),
        tsink("scope_audio", "Audio waveform", "audio_rate", 1024, (x0 + 1460, y0 + 320), "2,1,1,1"),
    ]
    c = [[src[0], src[1], "chan_filter", "0"], ["chan_filter", "0", "chan_filter2", "0"],
         ["chan_filter2", "0", "quad_demod", "0"], ["chan_filter2", "0", "pll_det", "0"],
         ["chan_filter2", "0", "spec_chan", "0"],
         ["pll_det", "0", "pll_gain", "0"],
         ["quad_demod", "0", "det_select", "0"], ["pll_gain", "0", "det_select", "1"],
         ["det_select", "0", "audio_filter", "0"], ["det_select", "0", "spec_det", "0"],
         ["audio_filter", "0", "deemph", "0"], ["deemph", "0", "volume_gain", "0"],
         ["volume_gain", "0", "audio_out", "0"], ["deemph", "0", "spec_audio", "0"],
         ["deemph", "0", "scope_audio", "0"]]
    return b, c


def common_vars(y):
    return [
        blk("imports", "import", (200, 8), imports="import math"),
        var("samp_rate", "2.4e6", (330, 8)),
        var("decim1", 10, (450, 8)),
        var("quad_rate", "samp_rate/decim1", (550, 8)),
        var("decim_audio", 5, (680, 8)),
        var("audio_rate", "quad_rate/decim_audio", (800, 8)),
        var("tau", "50e-6", (940, 8)),
        var("chan_cut", "100e3 if mode == 1 else 10e3", (1040, 8)),
        var("chan_tw", "20e3 if mode == 1 else 4e3", (1180, 8)),
        var("audio_cut", "15e3 if mode == 1 else 3.5e3", (1300, 8)),
        var("audio_tw", "5e3 if mode == 1 else 2e3", (1440, 8)),
        var("dev", "75e3 if mode == 1 else 5e3", (1040, 90)),
        var("pll_fmax", "110e3 if mode == 1 else 15e3", (1180, 90)),
        chooser("mode", "Mode", 0, [0, 1], ["NBFM 5 kHz", "WFM 75 kHz"], (200, y), "0,0,1,1"),
        chooser("detector", "Detector", 0, [0, 1], ["Quadrature Demod", "PLL Freq Det"], (380, y), "0,1,1,1"),
        rng("pll_lbw", "PLL Loop Bandwidth (rad/sample)", 0.085, 0.005, 0.8, 0.005, (560, y), "3,0,1,1"),
        rng("volume", "Volume", 0.3, 0, 1, 0.01, (760, y), "3,1,1,1"),
    ]


def save(fg, fname):
    with open(os.path.join(HERE, fname), "w") as f:
        yaml.safe_dump(fg, f, sort_keys=False, default_flow_style=False, width=200)
    print("wrote", fname)


# ---------------------------------------------------------------- 1) simulation, no hardware
b = common_vars(120) + [
    rng("tone_f", "Tone frequency (Hz)", 1000, 100, 15000, 100, (960, 120), "4,0,1,1"),
    rng("cnr_db", "CNR in B_T (dB)", 30, -5, 50, 0.5, (1160, 120), "4,1,1,1"),
    rng("freq_err", "Carrier frequency error (Hz)", 0, -20e3, 20e3, 100, (1360, 120), "5,0,1,1"),
    rng("rx_offset", "Receiver tuning correction (Hz)", 0, -20e3, 20e3, 100, (1560, 120), "5,1,1,1"),
    var("bt", "2*(dev + (15e3 if mode == 1 else 3e3))", (1320, 90)),
    var("noise_amp", "math.sqrt(samp_rate/(bt*10**(cnr_db/10)))", (1460, 90)),
    blk("tone", "analog_sig_source_x", (40, 300), type="float", samp_rate="samp_rate",
        waveform="analog.GR_SIN_WAVE", freq="tone_f", amp=1, offset=0, phase=0, showports="False"),
    blk("fm_mod", "analog_frequency_modulator_fc", (240, 300), sensitivity="2*math.pi*dev/samp_rate"),
    blk("lo_err", "analog_sig_source_x", (240, 400), type="complex", samp_rate="samp_rate",
        waveform="analog.GR_COS_WAVE", freq="freq_err", amp=1, offset=0, phase=0, showports="False"),
    blk("mix_err", "blocks_multiply_xx", (440, 320), type="complex", num_inputs=2, vlen=1),
    blk("noise", "analog_noise_source_x", (440, 420), type="complex", noise_type="analog.GR_GAUSSIAN",
        amp="noise_amp", seed=0),
    blk("add_noise", "blocks_add_xx", (620, 330), type="complex", num_inputs=2, vlen=1),
    blk("throttle", "blocks_throttle2", (760, 330), type="complex", samples_per_second="samp_rate", vlen=1,
        ignoretag="True", limit="auto", maximum="0.1"),
]
c = [["tone", "0", "fm_mod", "0"], ["fm_mod", "0", "mix_err", "0"], ["lo_err", "0", "mix_err", "1"],
     ["mix_err", "0", "add_noise", "0"], ["noise", "0", "add_noise", "1"], ["add_noise", "0", "throttle", "0"]]
rb, rc = receiver(960, 330, ("throttle", "0"))
save({"options": options("lab3_fm_sim", "SDR Lab 3 - FM modulator, channel and coherent / non-coherent receiver (no hardware)"),
      "blocks": b + rb, "connections": c + rc, "metadata": {"file_format": 1, "grc_version": "3.10.12.0"}},
     "lab3_fm_sim.grc")

# ---------------------------------------------------------------- 2) Pluto cable link (same device)
b = common_vars(120) + [
    rng("tone_f", "Tone frequency (Hz)", 1000, 100, 15000, 100, (960, 120), "4,0,1,1"),
    rng("tx_atten", "TX attenuation (dB) - keep >= 36.5 with a 30 dB pad", 40, 36.5, 89.75, 0.25, (1160, 120), "4,1,1,1"),
    rng("rf_gain", "RX gain (dB)", 30, 0, 70, 1, (1360, 120), "5,0,1,1"),
    rng("rx_offset", "Receiver tuning correction (Hz)", 0, -20e3, 20e3, 50, (1560, 120), "5,1,1,1"),
    var("f_c", "434e6", (1320, 90)),
    var("uri", "'usb:'", (1460, 90)),
    blk("tone", "analog_sig_source_x", (40, 300), type="float", samp_rate="samp_rate",
        waveform="analog.GR_SIN_WAVE", freq="tone_f", amp=1, offset=0, phase=0, showports="False"),
    blk("fm_mod", "analog_frequency_modulator_fc", (240, 300), sensitivity="2*math.pi*dev/samp_rate"),
    blk("tx_scale", "blocks_multiply_const_vxx", (440, 300), type="complex", const="0.5", vlen=1),
    blk("pluto_tx", "iio_pluto_sink", (620, 280), uri="uri", frequency="int(f_c)", samplerate="int(samp_rate)",
        bandwidth="int(samp_rate)", buffer_size=32768, cyclic="False", attenuation1="tx_atten",
        filter_source="'Off'", filter="''", fpass=0, fstop=0, len_tag_key="''", type="fc32"),
    blk("pluto_rx", "iio_pluto_source", (40, 480), uri="uri", frequency="int(f_c)", samplerate="int(samp_rate)",
        bandwidth="int(samp_rate)", buffer_size=32768, gain1="'manual'", manual_gain1="rf_gain",
        quadrature="True", rfdc="True", bbdc="True", filter_source="'Off'", filter="''", fpass=0, fstop=0,
        len_tag_key="packet_len", type="fc32"),
]
c = [["tone", "0", "fm_mod", "0"], ["fm_mod", "0", "tx_scale", "0"], ["tx_scale", "0", "pluto_tx", "0"]]
rb, rc = receiver(960, 480, ("pluto_rx", "0"))
save({"options": options("lab3_fm_link", "SDR Lab 3 - FM cable link with ADALM-Pluto at 434 MHz (TX 30 dB pad!)"),
      "blocks": b + rb, "connections": c + rc, "metadata": {"file_format": 1, "grc_version": "3.10.12.0"}},
     "lab3_fm_link.grc")
