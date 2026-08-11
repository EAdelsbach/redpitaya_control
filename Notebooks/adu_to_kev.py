import os, time
import numpy as np
import matplotlib.pyplot as plt
from scipy.optimize import curve_fit

from redpitaya_control.redpitaya_dev import redpitaya_dev
from redpitaya_control.event_logger import EventLogger, unpack, load_run, fit_clock, counter_to_unix
from redpitaya_control import compute_coeff
runfile = 'time_analysis'



def adu_to_kev(adu):

    a = -2.555374e-08
    b = 1.015411e-02
    c = 1.830826e+00
    
    return a * (adu ** 2) + b * adu + c


def kev_to_adu(kev):
    a = -2.555374e-08
    b = 1.015411e-02
    c = 1.830826e+00
    
    # Calculate ADU using the positive root of the quadratic formula
    adu = (-b + np.sqrt(b**2 - 4 * a * (c - kev))) / (2 * a)
    
    return adu


raw = load_run(f"{runfile}/events_*.bin")
ts_us, energy, chb = unpack(raw)
plt.figure(figsize=(8, 4))




plt.hist(energy, bins=4681, log=True)
plt.title("Energy Spectrum")
plt.xlabel("Energy / ADC Channel")
plt.ylabel("Counts (log scale)")
plt.show()