"""Keysight 33500B: output a 1 kHz sine, then an arbitrary waveform from a CSV file."""

from messknecht import Keysight33500B

wfg = Keysight33500B()
wfg.initialize("TCPIP0::192.168.1.20::INSTR", reset=True)

wfg.set_output_load("highz")  # scope input; use 50 for a 50 Ohm terminated load
wfg.configure_sine(frequency=1e3, amplitude=1.0)
wfg.output(True)
input("Sine on CH1 - press Enter for the arb...")

# One sample per line, e.g. exported from Excel or MATLAB.
wfg.load_arbitrary_csv("my_waveform.csv", sample_rate=100e3, amplitude=1.0)
input("Arb on CH1 - press Enter to stop...")

wfg.output(False)
wfg.close()
