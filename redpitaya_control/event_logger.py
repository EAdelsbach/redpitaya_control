"""Host-side driver for the FPGA event_logger core.

Usage:
    dev = redpitaya_dev("171.64.56.120", "config/mca_timestamp_1ch.json")
    dev.base.load_bitfile()
    # ... configure MCA chain with dev.set_register(...) as usual ...

    log = EventLogger(dev)
    log.configure(flush_ms=100)
    log.run(duration=60, output_dir="run1")   # None = run until Ctrl+C

Record layout (64-bit little-endian):
    bits [47:0]  timestamp  (microseconds since clear_ts)
    bits [62:48] energy     (15-bit peak height)
    bit  [63]    chb_bit    (channel-B digital input)
"""

import os, time, signal, base64
import numpy as np

TS_BITS = 48
E_BITS  = 15
TS_MASK = (1 << TS_BITS) - 1
E_MASK  = (1 << E_BITS) - 1


def unpack(u64):
    """Decode raw uint64 array -> (timestamp_us, energy, chb_bit)."""
    u64 = np.asarray(u64, dtype='<u8')
    ts     = (u64 & TS_MASK).astype('u8')
    energy = ((u64 >> TS_BITS) & E_MASK).astype('u2')
    chb    = ((u64 >> 63) & 1).astype('u1')
    return ts, energy, chb


class EventLogger:
    def __init__(self, dev):
        """
        dev: a connected redpitaya_dev instance whose config has an
             'event_logger' module and an 'acquisition' section.
        """
        self.dev = dev
        self.rp  = dev.base

        acq = dev.config['acquisition']
        self.bram_addr = self.rp._to_int(acq['logger_bram'])
        self.cdma_addr = self.rp._to_int(acq['cdma_addr'])
        self.ddr_addr  = self.rp._to_int(acq['ddr_addr'])
        self.frame_len = acq.get('frame_len', 4096)
        self.mon       = '/opt/redpitaya/bin/monitor'
        self._armed    = False

    def configure(self, presc=125, band_low=-1.0, band_high=1.0,
                  chb_thr=0.0, flush_ms=100, frame_len=None):
        """Configure the logger. Uses dev.set_register for everything."""
        if frame_len is not None:
            self.frame_len = frame_len

        self.dev.set_register('event_logger', 'arm', 0, raw=True)
        self.dev.set_register('event_logger', 'presc', presc, raw=True)
        self.dev.set_register('event_logger', 'frame_len', self.frame_len, raw=True)
        self.dev.set_register('event_logger', 'flush_ticks', int(flush_ms * 1000), raw=True)
        self.dev.set_register('event_logger', 'band_low', band_low)
        self.dev.set_register('event_logger', 'band_high', band_high)
        self.dev.set_register('event_logger', 'chb_threshold', chb_thr)

    def arm(self, clear=True):
        if clear:
            self.dev.set_register('event_logger', 'clear_ts', 1, raw=True)
            self.dev.set_register('event_logger', 'arm', 1, raw=True)
            self.dev.set_register('event_logger', 'clear_ts', 0, raw=True)
        else:
            self.dev.set_register('event_logger', 'arm', 1, raw=True)
        self._armed = True

    def disarm(self):
        self.dev.set_register('event_logger', 'arm', 0, raw=True)
        self._armed = False

    def snap_counter(self):
        """Latch and read the 48-bit microsecond counter."""
        self.dev.set_register('event_logger', 'snap', 1, raw=True)
        self.dev.set_register('event_logger', 'snap', 0, raw=True)
        lo = self.dev.get_register('event_logger', 'ts_snap_lo', raw=True)
        hi = self.dev.get_register('event_logger', 'ts_snap_hi', raw=True)
        return (hi << 32) | lo

    def tie_point(self):
        """Return (host_unix_ns, fpga_counter_us)."""
        # t0 = time.clock_gettime_ns(time.CLOCK_REALTIME)
        # Cross-platform fallback check:
        if hasattr(time, 'clock_gettime_ns') and hasattr(time, 'CLOCK_REALTIME'):
            t0 = time.clock_gettime_ns(time.CLOCK_REALTIME)
        else:
            t0 = time.time_ns()

        ctr = self.snap_counter()
        # Cross-platform fallback check:
        if hasattr(time, 'clock_gettime_ns') and hasattr(time, 'CLOCK_REALTIME'):
            t1 = time.clock_gettime_ns(time.CLOCK_REALTIME)
        else:
            t1 = time.time_ns()

        # t1 = time.clock_gettime_ns(time.CLOCK_REALTIME)
        return (t0 + t1) // 2, ctr

    def _drain_once(self):
        """CDMA one ready buffer to host. Returns raw bytes or None.
        Does NOT ack — caller must ack after durable write."""
        base = self.rp._to_int(
            self.dev.modules['event_logger']['registers']['status']['base'])
        b = base
        c, d = self.cdma_addr, self.ddr_addr
        R_STATUS = 0x20
        R_COUNT  = 0x24
        script = f"""sh -lc '
ST=$({self.mon} $(({b}+{R_STATUS})))
if [ $((ST & 0x1)) -eq 0 ]; then echo NOTREADY; exit 0; fi
BUF=$(( (ST>>1) & 1 ))
CNT=$({self.mon} $(({b}+{R_COUNT})))
N=$((CNT * 8))
SA=$(( {self.bram_addr} + BUF * {self.frame_len} * 8 ))
{self.mon} $(({c}+0x00)) 4 >/dev/null
{self.mon} $(({c}+0x00)) 0 >/dev/null
{self.mon} $(({c}+0x18)) $SA >/dev/null
{self.mon} $(({c}+0x20)) {d} >/dev/null
{self.mon} $(({c}+0x28)) $N >/dev/null
for i in $(seq 1 100000); do
    CST=$({self.mon} $(({c}+0x04)))
    [ $((CST & 0x2)) -ne 0 ] && break
    [ $((CST & 0x10)) -ne 0 ] && echo "ERROR: CDMA error $CST" >&2 && exit 1
done
dd if=/dev/mem bs=$N count=1 iflag=skip_bytes skip={d} 2>/dev/null | base64
'"""
        out = self.rp._sh(script).strip()
        if out == "" or out.startswith("NOTREADY"):
            return None
        return base64.b64decode(out)

    def _ack(self):
        self.dev.set_register('event_logger', 'ack', 1, raw=True)
        self.dev.set_register('event_logger', 'ack', 0, raw=True)

    def dropped(self):
        return self.dev.get_register('event_logger', 'dropped', raw=True)

    def run(self, duration=None, output_dir="events", tie_period_s=1.0,
            idle_sleep_s=0.001, verbose=True):
        """Continuous acquisition. Ctrl+C stops gracefully.

        duration: seconds, or None for infinite.
        Output: output_dir/events_YYYYMMDD_HH.bin + tiepoints.csv
        """
        os.makedirs(output_dir, exist_ok=True)
        tp_path = os.path.join(output_dir, "tiepoints.csv")

        self.arm(clear=True)

        stop = [False]
        prev_handler = signal.getsignal(signal.SIGINT)
        def _handler(sig, frame):
            stop[0] = True
        signal.signal(signal.SIGINT, _handler)

        t_end    = (time.time() + duration) if duration else float('inf')
        next_tie = time.time()
        n_rec    = 0
        cur_key  = None
        ef       = None

        tf = open(tp_path, 'a')
        if tf.tell() == 0:
            tf.write("# host_unix_ns,fpga_counter_us\n"); tf.flush()
        try:
            while time.time() < t_end and not stop[0]:
                if time.time() >= next_tie:
                    host_ns, ctr = self.tie_point()
                    tf.write(f"{host_ns},{ctr}\n"); tf.flush(); os.fsync(tf.fileno())
                    next_tie += tie_period_s

                data = self._drain_once()
                if data:
                    key = time.strftime("%Y%m%d_%H", time.localtime())
                    if key != cur_key:
                        if ef: ef.close()
                        ef = open(os.path.join(output_dir, f"events_{key}.bin"), 'ab')
                        cur_key = key
                    ef.write(data); ef.flush(); os.fsync(ef.fileno())
                    self._ack()
                    n_rec += len(data) // 8
                else:
                    time.sleep(idle_sleep_s)
        finally:
            if ef: ef.close()
            tf.close()
            self.disarm()
            signal.signal(signal.SIGINT, prev_handler)

        if verbose:
            print(f"Logged {n_rec} events, dropped={self.dropped()}")
        return n_rec


# ---------------------------------------------------------------- offline tools
def fit_clock(tiepoint_path):
    """Fit host_unix_ns = a + b*counter. Returns (a, b, ppm)."""
    data = np.loadtxt(tiepoint_path, delimiter=',', comments='#')
    ctr, host_ns = data[:, 1], data[:, 0]
    b, a = np.polyfit(ctr, host_ns, 1)
    ppm = (b / 1000.0 - 1.0) * 1e6
    return a, b, ppm


def counter_to_unix(counter_us, a, b):
    """Map FPGA counter -> absolute UNIX time (seconds)."""
    return (a + b * np.asarray(counter_us, dtype=float)) / 1e9


def load_run(events_glob):
    """Load hourly event files, concatenate, dedup restarts."""
    import glob
    u = [np.fromfile(f, dtype='<u8') for f in sorted(glob.glob(events_glob))]
    u = np.concatenate(u) if u else np.zeros(0, dtype='<u8')
    if u.size:
        keep = np.ones(u.size, dtype=bool)
        keep[1:] = u[1:] != u[:-1]
        u = u[keep]
    return u
