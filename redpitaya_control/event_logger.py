# event_logger.py -- host-side driver for the FPGA event_logger core
#
# Continuous timestamped-event acquisition for the MCA chain:
#   * arms the ping-pong logger, drains full buffers over CDMA (BRAM->DDR->base64)
#   * takes ~1 Hz NTP tie-points (host_time <-> FPGA counter) so absolute time
#     and crystal drift can be reconstructed offline (see fit_clock()).
#
# Record layout (64-bit little-endian word per event):
#   bits [47:0]  timestamp  (microseconds since clear_ts)
#   bits [62:48] energy     (15-bit peak height)
#   bit  [63]    chb_bit    (channel-B digital input, thresholded)

import time
import base64
import numpy as np

TS_BITS = 48
E_BITS  = 15
TS_MASK = (1 << TS_BITS) - 1
E_MASK  = (1 << E_BITS) - 1


def unpack(u64):
    """Decode raw uint64 record array -> (timestamp_us, energy, chb_bit) arrays."""
    u64 = np.asarray(u64, dtype='<u8')
    ts     = (u64 & TS_MASK).astype('u8')
    energy = ((u64 >> TS_BITS) & E_MASK).astype('u2')
    chb    = ((u64 >> 63) & 1).astype('u1')
    return ts, energy, chb


class EventLogger:
    # ---- register offsets (see event_logger_axi_wrap.v) ----
    R_CONTROL = 0x00
    R_PRESC   = 0x04
    R_FRAME   = 0x08
    R_FLUSH   = 0x0C
    R_BANDLO  = 0x10
    R_BANDHI  = 0x14
    R_CHBTHR  = 0x18
    R_STATUS  = 0x20   # [0]ready [1]ready_buf [2]dropped_nonzero
    R_COUNT   = 0x24
    R_DROPPED = 0x28
    R_TS_LO   = 0x2C
    R_TS_HI   = 0x30
    R_EV_LO   = 0x34
    R_EV_HI   = 0x38

    # ---- control bits ----
    ARM      = 1 << 0
    CLEAR_TS = 1 << 1
    RESET    = 1 << 2
    SNAP     = 1 << 3
    ACK      = 1 << 4

    def __init__(self, rp, base, bram_addr, cdma_addr, ddr_addr,
                 frame_len=4096, mon='/opt/redpitaya/bin/monitor'):
        """
        rp        : connected redpitaya_base instance
        base      : AXI base of event_logger regs   (e.g. 0x40004000)
        bram_addr : AXI base of the record BRAM      (e.g. 0x41000000)
        cdma_addr : AXI Central DMA control base     (e.g. 0x7E200000)
        ddr_addr  : DDR scratch for CDMA landing     (e.g. 0x10000000)
        frame_len : records per ping-pong buffer (must match the value armed)
        """
        self.rp        = rp
        self.base      = base
        self.bram_addr = bram_addr
        self.cdma_addr = cdma_addr
        self.ddr_addr  = ddr_addr
        self.frame_len = frame_len
        self.mon       = mon
        self._ctrl     = 0   # shadow of the level control bits (arm/clear)

    # ------------------------------------------------------------------ config
    def configure(self, presc=125, frame_len=None, band_low=-32768, band_high=32767,
                  chb_thr=0, flush_ms=100):
        """Program the logger. presc=125 -> 1 us tick @125 MHz clock.
        Default band = full range (log every peak); narrow it to filter in HW.
        flush_ms forces a partial-buffer swap if events are slow (0 = never)."""
        if frame_len is not None:
            self.frame_len = frame_len
        flush_ticks = int(flush_ms * 1000)  # us
        # disarm first so config regs are quiescent
        self._ctrl = 0
        self.rp.write_word(self.base + self.R_CONTROL, self._ctrl)
        self.rp.write_word(self.base + self.R_PRESC,   presc & 0xFFFF)
        self.rp.write_word(self.base + self.R_FRAME,   self.frame_len)
        self.rp.write_word(self.base + self.R_FLUSH,   flush_ticks & 0xFFFFFFFF)
        self.rp.write_word(self.base + self.R_BANDLO,  band_low & 0xFFFF)
        self.rp.write_word(self.base + self.R_BANDHI,  band_high & 0xFFFF)
        self.rp.write_word(self.base + self.R_CHBTHR,  chb_thr & 0xFFFF)
        # readback sanity (catches wrong bitfile / address)
        rb = self.rp.read_word(self.base + self.R_FRAME) & ((1 << 13) - 1)
        if rb != self.frame_len:
            raise RuntimeError(f"configure: frame_len readback {rb} != {self.frame_len} "
                               f"(wrong bitfile or base address?)")

    def _set_ctrl(self, level_bits):
        self._ctrl = level_bits
        self.rp.write_word(self.base + self.R_CONTROL, self._ctrl)

    def arm(self, clear=True):
        bits = self.ARM | (self.CLEAR_TS if clear else 0)
        self._set_ctrl(bits)
        if clear:                      # release clear, keep armed
            self._set_ctrl(self.ARM)

    def disarm(self):
        self._set_ctrl(0)

    # -------------------------------------------------------------- tie-points
    def snap_counter(self):
        """Latch and read the 48-bit microsecond counter atomically."""
        # pulse SNAP (rising edge), keeping current level bits
        self.rp.write_word(self.base + self.R_CONTROL, self._ctrl | self.SNAP)
        self.rp.write_word(self.base + self.R_CONTROL, self._ctrl)
        lo = self.rp.read_word(self.base + self.R_TS_LO) & 0xFFFFFFFF
        hi = self.rp.read_word(self.base + self.R_TS_HI) & 0xFFFF
        return (hi << 32) | lo

    def tie_point(self):
        """Return (host_unix_ns, fpga_counter): NTP wall clock vs FPGA counter.
        Host time is bracketed around the snap and reported as the midpoint,
        so the ~ms SSH latency averages out across many tie-points."""
        t0 = time.clock_gettime_ns(time.CLOCK_REALTIME)
        ctr = self.snap_counter()
        t1 = time.clock_gettime_ns(time.CLOCK_REALTIME)
        return (t0 + t1) // 2, ctr

    # ------------------------------------------------------------------- drain
    def drain_once(self):
        """If a full buffer is ready, CDMA it to DDR and return its raw bytes
        (frame_len or fewer records x 8 B), or None if nothing is ready.
        Does NOT ack -- the buffer stays frozen until you call ack(), so the
        caller can durably persist the data first (at-least-once semantics).
        Poll+CDMA run as one on-target script to avoid SSH round-trips."""
        b, c, d = self.base, self.cdma_addr, self.ddr_addr
        script = f"""sh -lc '
ST=$({self.mon} $(({b}+{self.R_STATUS})))
if [ $((ST & 0x1)) -eq 0 ]; then echo NOTREADY; exit 0; fi
BUF=$(( (ST>>1) & 1 ))
CNT=$({self.mon} $(({b}+{self.R_COUNT})))
N=$((CNT * 8))
SA=$(( {self.bram_addr} + BUF * {self.frame_len} * 8 ))
# CDMA: BRAM buffer -> DDR scratch
{self.mon} $(({c}+0x00)) 4 >/dev/null      # soft reset
{self.mon} $(({c}+0x00)) 0 >/dev/null
{self.mon} $(({c}+0x18)) $SA >/dev/null     # source
{self.mon} $(({c}+0x20)) {d} >/dev/null     # dest
{self.mon} $(({c}+0x28)) $N >/dev/null      # BTT -> starts transfer
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

    def ack(self):
        """Free the ready buffer for reuse. Call only AFTER the drained data is
        durably written (fsync'd), so a crash before ack re-drains that buffer
        (a possible duplicate, removed offline) rather than losing it."""
        self.rp.write_word(self.base + self.R_CONTROL, self._ctrl | self.ACK)
        self.rp.write_word(self.base + self.R_CONTROL, self._ctrl)

    def dropped(self):
        return self.rp.read_word(self.base + self.R_DROPPED)

    # -------------------------------------------------------------------- main
    def run(self, duration_s, output_dir, tiepoint_path=None, tie_period_s=1.0,
            idle_sleep_s=0.001, verbose=True):
        """Continuous acquisition into output_dir for duration_s seconds.

          * events -> hourly files events_YYYYMMDD_HH.bin (raw 8-B records),
            rolled on the host's local-time hour at a drain boundary. Opened in
            append mode so a restart resumes the same hour's file.
          * tie-points -> one continuous CSV (default output_dir/tiepoints.csv).

        Durability: each drained buffer is written + fsync'd BEFORE it is acked,
        so a host crash re-drains the un-acked buffer next time (at-least-once).
        Offline, load_run() concatenates the hourly files and drops any exact
        duplicate records a restart may have produced."""
        import os
        os.makedirs(output_dir, exist_ok=True)
        if tiepoint_path is None:
            tiepoint_path = os.path.join(output_dir, "tiepoints.csv")

        self.arm(clear=True)
        t_end    = time.time() + duration_s
        next_tie = time.time()
        n_rec    = 0
        cur_key  = None
        ef       = None
        tf = open(tiepoint_path, 'a')
        if tf.tell() == 0:
            tf.write("# host_unix_ns,fpga_counter_us\n"); tf.flush()
        try:
            while time.time() < t_end:
                if time.time() >= next_tie:
                    host_ns, ctr = self.tie_point()
                    tf.write(f"{host_ns},{ctr}\n"); tf.flush(); os.fsync(tf.fileno())
                    next_tie += tie_period_s

                data = self.drain_once()
                if data:
                    key = time.strftime("%Y%m%d_%H", time.localtime())
                    if key != cur_key:                       # hourly rotation
                        if ef:
                            ef.close()
                        ef = open(os.path.join(output_dir, f"events_{key}.bin"), 'ab')
                        cur_key = key
                    ef.write(data); ef.flush(); os.fsync(ef.fileno())  # durable...
                    self.ack()                                          # ...then free buffer
                    n_rec += len(data) // 8
                else:
                    time.sleep(idle_sleep_s)
        finally:
            if ef:
                ef.close()
            tf.close()
            self.disarm()
        if verbose:
            print(f"logged {n_rec} events, dropped={self.dropped()}")
        return n_rec


# --------------------------------------------------------------- offline tools
def fit_clock(tiepoint_path):
    """Least-squares fit host_unix_ns = a + b*counter over the tie-points.
    Returns (a, b): a = UNIX-ns at counter 0, b = true ns per counter tick
    (nominally 1000 ns; deviation from 1000 IS the crystal's ppm error)."""
    data = np.loadtxt(tiepoint_path, delimiter=',', comments='#')
    ctr, host_ns = data[:, 1], data[:, 0]
    b, a = np.polyfit(ctr, host_ns, 1)
    ppm = (b / 1000.0 - 1.0) * 1e6
    return a, b, ppm


def counter_to_unix(counter_us, a, b):
    """Map FPGA counter values -> absolute UNIX time (seconds) using fit_clock()."""
    return (a + b * np.asarray(counter_us, dtype=float)) / 1e9


def load_run(events_glob):
    """Load and concatenate the hourly event files matching events_glob
    (e.g. 'run1/events_*.bin') in filename order, returning one uint64 array.
    Removes exact-duplicate consecutive records that an at-least-once restart
    may have re-appended (safe: real events are strictly time-ordered, so back
    -to-back identical 64-bit records only occur from a re-drained buffer)."""
    import glob
    u = [np.fromfile(f, dtype='<u8') for f in sorted(glob.glob(events_glob))]
    u = np.concatenate(u) if u else np.zeros(0, dtype='<u8')
    if u.size:
        keep = np.ones(u.size, dtype=bool)
        keep[1:] = u[1:] != u[:-1]
        u = u[keep]
    return u


if __name__ == "__main__":
    from redpitaya_base import redpitaya_base
    rp = redpitaya_base("171.64.56.58", "../bitfiles/mca_timestamp_1ch.bit")
    rp.connect(); rp.load_bitfile()
    log = EventLogger(rp, base=0x40004000, bram_addr=0x41000000,
                      cdma_addr=0x7E200000, ddr_addr=0x10000000, frame_len=4096)
    log.configure(presc=125, band_low=-32768, band_high=32767, chb_thr=0, flush_ms=100)
    log.run(60, output_dir="run1", tie_period_s=1.0)          # -> run1/events_*.bin
    a, b, ppm = fit_clock("run1/tiepoints.csv")
    print(f"clock fit: {b:.3f} ns/tick  ({ppm:+.1f} ppm)")
    ts, energy, chb = unpack(load_run("run1/events_*.bin"))
    print(f"{len(ts)} events; first abs time = {counter_to_unix(ts[:3], a, b)}")
