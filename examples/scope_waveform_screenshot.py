"""Keysight DSO-X 3014T: save CH1 as CSV and take a screenshot.

Set up signal and trigger at the scope first; reset=False keeps that setup.
"""

from messknecht import KeysightDSOX3000T

scope = KeysightDSOX3000T()
scope.initialize("USB0::0x2A8D::0x1766::MY12345678::INSTR", reset=False)

scope.save_waveform_csv("waveform.csv", channels=1)
scope.screenshot("screen.png")

print(f"Vpp = {scope.measure_vpp(1):.3f} V")
print(f"f   = {scope.measure_frequency(1):.1f} Hz")

scope.close()
