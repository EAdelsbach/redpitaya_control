from redpitaya_control.redpitaya_dev import redpitaya_dev
from redpitaya_control import compute_coeff
import os
import time
import numpy as np

# Connect to Red Pitaya
RP_HOST = os.environ.get("RP_HOST", "171.64.56.120")
dev = redpitaya_dev(RP_HOST, "config/mca_simple_1ch.json")
dev.base.load_bitfile()

# Configure signal chain
dev.set_all_registers('iir1', compute_coeff.highpass_1st(1e4, Ts=16e-9), reset=True)
dev.set_register('fir9', 'h0',0.99) #not =1 or above
#h0 to h9 

# Configure peak detector
dev.set_register("peak_detector", "invert_input", 0)
dev.set_register("peak_detector", "trig_level", 0.01)
dev.set_register("peak_detector", "integration_mode", 0)# if 0: simple peak, 1: integration
dev.set_register("peak_detector", "n_integration", 1000) #each timestep is 8ns (or 16?)
dev.set_register("peak_detector", "log_attenuation", 0)

# Configure histogram
dev.set_register("histogram", "offset", 0)
dev.set_register("histogram", "gain", 0.1)
dev.set_register("histogram", "band_low", 0.03)
dev.set_register("histogram", "band_high", 0.35)
dev.set_register("histogram", "pulse_width", 1024)
dev.set_register("histogram", "clear_bins", 1)
time.sleep(0.01)
dev.set_register("histogram", "clear_bins", 0)
dev.set_register("histogram", "counting_enable", 1)
#dev.set_register("histogram", "reset", 0)

# Wait for data
time.sleep(10)

# Read histogram
print("Reading histogram...")
dev.set_register("histogram", "counting_enable", 0)  # Pause for stable readout
histogram = dev.read_sequential_axi_data("histogram", "read_address", "read_data", 0, 1023)
dev.set_register("histogram", "counting_enable", 1)  # Resume counting

# Display results
total_counts = histogram.sum()
max_bin = histogram.argmax()
max_count = histogram[max_bin]
nonzero_bins = np.count_nonzero(histogram)

print(f"\nHistogram Summary:")
print(f"  Total counts: {total_counts}")
print(f"  Non-zero bins: {nonzero_bins}")
print(f"  Peak bin: {max_bin} with {max_count} counts")

if nonzero_bins > 0:
    active_bins = np.where(histogram > 0)[0]
    print(f"  Active bins: {active_bins[:20]}")
