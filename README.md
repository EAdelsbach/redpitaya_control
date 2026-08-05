# redpitaya_control

Python control and data acquisition library for Red Pitaya FPGA projects.
check this, [[iir2nd_direct_2ch]], [[z_control]], [[mca_simple]]

## Installation

```bash

pip install -e .
```

## Usage

```python
from redpitaya_control.redpitaya_dev import redpitaya_dev
from redpitaya_control import compute_coeff

# Connect to Red Pitaya
dev = redpitaya_dev("171.64.56.120", "config/stream_cdma_4ch.json")
dev.base.load_bitfile()

# Read CDMA frame
config = dev.setup_cdma(frame_len=1024, sampling_frequency=125e6)
ch0, ch1, ch2, ch3 = dev.read_cdma_frame()
```

## Examples

See `examples/` directory:
- `stream4channel_psd.py` - 4-channel time trace and ASD visualization
- `stream4channel_overlaid.py` - Overlaid In/Out pairs
- `iir2nd_coupled_example.py` - Configure coupled IIR filters
- `iir2nd_direct_example.py` - Configure direct form IIR filters
- `mca_example.py` - Multi-channel analyzer example

## Structure

- `redpitaya_control/` - Main package
  - `redpitaya_dev.py` - High-level device interface
  - `redpitaya_base.py` - Low-level SSH/register access
  - `compute_coeff.py` - Filter coefficient calculation
- `config/` - JSON configuration files for different FPGA designs (see `config/INDEX.md`)
- `bitfiles/` - Compiled FPGA bitfiles
- `examples/` - Example scripts

## Architecture

```
your script
    |
redpitaya_dev       ← high-level: loads JSON config, named register access
    |
redpitaya_base      ← low-level: SSH connection, bitfile upload, raw read/write
    |
paramiko SSH
    |
Red Pitaya FPGA board
```

`redpitaya_dev` wraps `redpitaya_base` and exposes `get_register("module", "name")` / `set_register(...)` by resolving names to addresses using the JSON config. `redpitaya_base` exposes `read_word(addr)` / `write_word(addr, val)` and the bit-field helpers `read_reg` / `write_reg`.

## Config file format

Each JSON file in `config/` describes one FPGA bitfile's register map. See `config/INDEX.md` for a complete config/bitfile cross-reference.

Top-level keys:
- `"bitfile"` — path relative to repo root (e.g. `"bitfiles/pid_simple_1ch.bit"`)
- `"description"` — human-readable description of the design
- `"modules"` — dict of named FPGA modules

Each module entry has:
- `"type"` — module type string (informational)
- `"settings"` — FPGA parameters (timebase, bit widths, memory addresses, etc.)
- `"registers"` — dict of named registers

Each register entry:
```json
"Kp": {"base": "0x40001000", "offset": 4, "msb": 31, "lsb": 0, "signed": true, "log_scale": 16}
```
- `base` + `offset` = absolute AXI address
- `msb` / `lsb` = bit slice within the 32-bit word
- `log_scale` = physical value = raw value / 2^log_scale (omit for dimensionless registers)

## Register access quick reference

```python
dev.get_register("pid0", "Kp")                       # returns physical value
dev.get_register("pid0", "Kp", raw=True)             # returns raw integer
dev.set_register("pid0", "Kp", 0.5)                  # write physical value
dev.set_all_registers("pid0", coeffs, reset=True)    # write dict of values, briefly resets module
dev.reset("pid0")                                    # pulse reset register
dev.enable("pid0", True)                             # clear reset register (enable output)
```

## Running examples

Set `RP_HOST` (or `RP_HOST1`/`RP_HOST2` for two-device scripts) before running:

```bash
export RP_HOST=192.168.1.100
python examples/mca_example.py
```

Install example dependencies with:
```bash
pip install -e ".[examples]"
# or: pip install -r requirements-examples.txt
```
