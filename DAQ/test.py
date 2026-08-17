import os, time
import numpy as np
import matplotlib.pyplot as plt
from scipy.optimize import curve_fit

from redpitaya_control.redpitaya_dev import redpitaya_dev
from redpitaya_control.event_logger import EventLogger, unpack, load_run, fit_clock, counter_to_unix
from redpitaya_control import compute_coeff


import numpy as np
import matplotlib.pyplot as plt
from scipy.optimize import curve_fit
from scipy.special import factorial


runfile = 'no_barrier_runfile'
print(runfile)
MAX_Q15 = 32767 / 32768
C1 = 99.90741625
C2 = 1225.60912165
C3 = 1024.0
C4 = 14.4



MAX_Q15 = 32767 / 32768


RP_HOST = os.environ.get("RP_HOST", "171.64.56.120")
dev = redpitaya_dev(RP_HOST, "config/mca_timestamp_1ch_working.json")
dev.base.load_bitfile()
dev.set_register('event_logger', 'reset', 1, raw=True)
time.sleep(0.1)
dev.set_register('event_logger', 'reset', 0, raw=True)

# Signal chain
dev.set_all_registers(
    "iir1",
    compute_coeff.highpass_1st(1e4, Ts=16e-9),
    reset=True,
)

for idx in range(9):
    dev.set_register("fir9", f"h{idx}", 0.109375)

# Do not use raw=True for normalized Q15 values.
dev.set_register("peak_detector", "trig_level", 0.008)
dev.set_register("peak_detector", "invert_input", 0)
dev.set_register("peak_detector", "n_integration", 300)
dev.set_register("peak_detector", "dead_time", 300)
# Histogram
dev.set_register("histogram", "offset", -0.007165694774164504)
dev.set_register("histogram", "gain", 0.08361136196556104)
dev.set_register("histogram", "pulse_width", 1024)

dev.set_register("histogram", "clear_bins", 1)
time.sleep(0.01)
dev.set_register("histogram", "clear_bins", 0)
dev.set_register("histogram", "counting_enable", 1,)

# Configure before arming.
log = EventLogger(dev)
log.configure(
    band_low=0.0,
    band_high=MAX_Q15,
    flush_ms=100,
)
print(dev.get_register("peak_detector", "dead_time", raw=True))

n = log.run(duration=1, output_dir=runfile)
