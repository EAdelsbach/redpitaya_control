import sys
import os
import time

from SDG1062 import SDG1062
from picoscope2000a import Picoscope2207B
from NPC3SG import NPC3SG


import numpy as np
import matplotlib.pyplot as plt
from scipy.optimize import curve_fit

from redpitaya_control.redpitaya_dev import redpitaya_dev
from redpitaya_control.event_logger import EventLogger, unpack, load_run, fit_clock, counter_to_unix
from redpitaya_control import compute_coeff


import numpy as np

FLAG_PHASE = 90
flag_low = 0
flag_high = 1

MAX_VELOCITY = 1 # mm/s
RANGE = 320 # microns, closed loop
period = 2 * RANGE / MAX_VELOCITY / 1000

freq = 1 / period



velocities = [0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9]
for velocity in velocities:
    runfile = f'{velocity*100}_runfile'
    # velocity = 1 # mm/s  # @ Ezri, can change velocity here
    amp = period * velocity / 2 * 1000 # microns
    voltage_pp = amp * 10 / RANGE

    low_level = 0
    high_level = voltage_pp
    offset = -1/2 * voltage_pp
    range = 1/2 * voltage_pp

    with SDG1062() as func_gen:

        # CURRENT_DIRECTORY = os.path.dirname(os.path.abspath(__file__))

        # save_path_data = os.path.join(CURRENT_DIRECTORY, "data", f"{velocity}mms.csv")
        # save_path_plot = os.path.join(CURRENT_DIRECTORY, "visualization", f"{velocity}mms.png")

        # scope.set_all_channels_range(channel_range=range, coupling="DC", offset=offset, auto_adjust=True)
        # time.sleep(5)

        # scope.capture(duration=20, sampling_rate=SAMPLING_RATE, output_path=save_path_data)

        print(f"Running code to set piezo velocity to {velocity} mm/s...")
        print(f"Please do not disconnect computer from function generator during this process.")

        func_gen.set_load("C1", "HZ")
        time.sleep(1)
        func_gen.set_load("C2", "HZ")
        time.sleep(1)

        print("Configuring piezo output...")
        func_gen.cfg_chan_output(channel="C1", freq=freq, high=high_level, low=low_level)
        time.sleep(1)
        func_gen.cfg_chan_square(channel="C2", freq=freq, high=flag_high, low=flag_low)
        time.sleep(1)

        func_gen.align_phase()
        time.sleep(1)
        func_gen.instrument.write(f"C2:BSWV PHSE,{FLAG_PHASE}")
        time.sleep(2)

        print("Turning on piezo output...")
        func_gen.outputs_on("C1", "C2")
        time.sleep(2) # let the piezo settle into the ramp before capturing
        # scope.capture(duration=120, sampling_rate=SAMPLING_RATE,
        # output_path=save_path_data)

        print("Piezo output is now running! Can disconnect function generator.")
    



    print(f'currently running{runfile}')
    


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
        flush_ms=100,
    )
    print(dev.get_register("peak_detector", "dead_time", raw=True))

    n = log.run(duration=601, output_dir=runfile)

    

















 

    velocity = 1 # mm/s  # @ Ezri, can change velocity here
    amp = period * velocity / 2 * 1000 # microns
    voltage_pp = amp * 10 / RANGE

    low_level = 0
    high_level = voltage_pp
    offset = -1/2 * voltage_pp
    range = 1/2 * voltage_pp

    with SDG1062() as func_gen:

        # CURRENT_DIRECTORY = os.path.dirname(os.path.abspath(__file__))

        # save_path_data = os.path.join(CURRENT_DIRECTORY, "data", f"{velocity}mms.csv")
        # save_path_plot = os.path.join(CURRENT_DIRECTORY, "visualization", f"{velocity}mms.png")

        # scope.set_all_channels_range(channel_range=range, coupling="DC", offset=offset, auto_adjust=True)
        # time.sleep(5)

        # scope.capture(duration=20, sampling_rate=SAMPLING_RATE, output_path=save_path_data)

        print(f"Running code to set piezo velocity to {velocity} mm/s...")
        print(f"Please do not disconnect computer from function generator during this process.")

        func_gen.set_load("C1", "HZ")
        time.sleep(1)
        func_gen.set_load("C2", "HZ")
        time.sleep(1)

        print("Configuring piezo output...")
        func_gen.cfg_chan_output(channel="C1", freq=freq, high=high_level, low=low_level)
        time.sleep(1)
        func_gen.cfg_chan_square(channel="C2", freq=freq, high=flag_high, low=flag_low)
        time.sleep(1)

        func_gen.align_phase()
        time.sleep(1)
        func_gen.instrument.write(f"C2:BSWV PHSE,{FLAG_PHASE}")
        time.sleep(2)

        print("Turning on piezo output...")
        func_gen.outputs_on("C1", "C2")
        time.sleep(2) # let the piezo settle into the ramp before capturing
        # scope.capture(duration=120, sampling_rate=SAMPLING_RATE,
        # output_path=save_path_data)

        print("Piezo output is now running! Can disconnect function generator.")