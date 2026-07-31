# Config / Bitfile Index

| Config file | Bitfile | Status | Used in example |
|---|---|---|---|
| `iir2nd_coupled.json` | `iir2nd_coupled_1ch.bit` | active | — |
| `iir2nd_coupled_2ch.json` | `iir2nd_coupled_2ch.bit` | active | — |
| `iir2nd_coupled_2ch_stream.json` | `iir2nd_coupled_2ch_stream.bit` | active | `iir2nd_coupled_example.py`, `stream4channel_overlaid.py` |
| `iir2nd_direct.json` | `iir2nd_direct_1ch.bit` | active | — |
| `iir2nd_direct_2ch.json` | `iir2nd_direct_2ch.bit` | active | — |
| `iir2nd_direct_gpio.json` | *(no matching bitfile)* | **check** | — |
| `mca_simple_1ch.json` | `mca_simple_1ch.bit` | active | `mca_example.py` |
| `mca_timestamp_1ch.json` | `mca_timestamp_1ch.bit` | active | `mca_timestamp_example.ipynb` |
| `pid_simple_1ch.json` | `pid_simple_1ch.bit` | active | — |
| `pid_simple_2ch.json` | `pid_simple_2ch.bit` | active | — |
| `stream_bram_4ch.json` | *(no matching bitfile)* | **check** | `stream4channel_bram_example.py` |
| `stream_cdma_4ch.json` | `stream_cdma_4ch.bit` | active | `stream4channel_cdma_example.py`, `stream_2devices_overlaid.py` |
| `stream_cdma_8ch.json` | *(no matching bitfile)* | **check** | — |
| `z_control.json` | `z_control.bit` | active | — |
| `z_control_stream.json` | `z_control_stream.bit` | active | *(commented ref in `stream4channel_overlaid.py`)* |
| `z_control_v2_stream.json` | `z_control_v2_stream.bit` | active | `stream4channel_psd.py` |
| `z_control_v3_stream.json` | *(references `z_control_v2_stream.bit` — no v3 bitfile)* | **check** | — |
| `z_control_v4_stream.json` | `z_control_v4_stream.bit` | active | `stream5channel_overlaid.py`, `stream6channel_psd.py` |

## Notes

- **check**: config exists but no dedicated bitfile was found in `bitfiles/` — verify the correct bitfile path or whether this design has been built.
- `mca_example.py` references `config/mca_simple.json` (without `_1ch` suffix) — this may be a typo; the actual file is `mca_simple_1ch.json`.
