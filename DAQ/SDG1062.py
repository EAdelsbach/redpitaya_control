"""
SIGLENT SDG1062X Plus

In progress. Code to run the SDG1062 function generator for Mossbauer axion experiment control.

Dual channel. Max output amplitude 20 Vpp. 1 GSa/s sampling rate. 16-bit vertical resolution.
"""

import time

import pyvisa

class SDG1062:

    def __init__(self, resource = 'USB0::0xF4EC::0x1103::SDG1PA0C900656::INSTR'):
        """
        Opens a connection to SDG1062 over the given VISA resource string
        """
        self.rm = pyvisa.ResourceManager()
        available_resources = self.rm.list_resources()

        if resource not in available_resources:
            print(f"Available resources: {available_resources}")
            raise Exception(f"The given SDG1062 resource string {resource} was not in the list of available resources. Check connections.")
        self.instrument = self.rm.open_resource(resource)
        self.instrument.timeout = 5000
        self.identify()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, exc_tb):
        self.close()

    def cfg_chan_output(self, channel, freq, high=9, low=1):

        if high > 10:
            raise Exception(f"High voltage value {high}V is too high to be compatible with NPC3SG piezo controller (must be <=10V).")
        if low < 0:
            raise Exception(f"Low voltage value {low}V is too low to be compatible with NPC3SG piezo controller (must be >= 0V).")

        # symmetric triangle wave
        self.instrument.write(f"{channel}:BSWV WVTP,RAMP") # set waveform type to RAMP
        self.instrument.write(f"{channel}:BSWV SYM,50") # set symmetry to 50%

        # calculate amplitude and offset
        amp_pp = high-low
        offset = (high+low)/2

        self.instrument.write(f"{channel}:BSWV FRQ,{freq}HZ") # set frequency
        self.instrument.write(f"{channel}:BSWV AMP,{amp_pp}V") # set peak-to-peak amplitude
        self.instrument.write(f"{channel}:BSWV OFST,{offset}V") # set DC offset

    def cfg_chan_square(self, channel, freq, high, low, phase=0):
        """
        50% duty square wave, used as a ramp-direction flag on the scope.
        Not voltage-clamped: this channel goes to the scope, not the piezo
        controller.
        """
        amp_pp = high - low
        offset = (high + low) / 2

        self.instrument.write(f"{channel}:BSWV WVTP,SQUARE")
        self.instrument.write(f"{channel}:BSWV FRQ,{freq}HZ")
        self.instrument.write(f"{channel}:BSWV AMP,{amp_pp}V")
        self.instrument.write(f"{channel}:BSWV OFST,{offset}V")
        self.instrument.write(f"{channel}:BSWV DUTY,50")
        self.instrument.write(f"{channel}:BSWV PHSE,{phase}")


    def identify(self):
        idn = self.instrument.query("*IDN?")
        print(f"Connected to: {idn.strip()}")

    def set_load(self, channel, load="HZ"):
        """
        Sets the output load for a channel. Amplitude and offset are referenced
        to this value, and the default is 50 ohm: driving a high-impedance
        input while the generator still assumes 50 ohm gives DOUBLE the
        requested voltage at the connector. Call this before setting levels.
        load: "HZ" for high impedance, or a resistance in ohms (50-100000).
        """
        self.instrument.write(f"{channel}:OUTP LOAD,{load}")

    def outputs_on(self, *channels):
        print("Turning on outputs")
        self.instrument.write(f"C1:OUTP ON")
        time.sleep(5)
        self.instrument.write(f"C2:OUTP ON")
        time.sleep(5)

    def outputs_off(self, *channels):
        self.instrument.write(f"C1:OUTP OFF")
        time.sleep(1)
        self.instrument.write(f"C2:OUTP OFF")
        time.sleep(1)

    def read_chan_settings(self, channel):
        settings = self.instrument.query(f"{channel}:BSWV?")
        print(f"Current basic waveform settings: {settings.strip()}")

        output_state = self.instrument.query(f"{channel}:OUTP?")
        print(f"Output state: {output_state}")

    def align_phase(self):
        """
        Resets both channels' phase accumulators so their PHSE settings are
        meaningful relative to each other.
        Call AFTER both channels are configured. Any later frequency change on
        either channel breaks the alignment and requires calling this again.
        """
        self.instrument.write("EQPHASE")

    def close(self):
        self.instrument.close()
        self.rm.close()