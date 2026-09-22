"""Keysight 34450A: measure a DC voltage."""

from messknecht import Keysight34450A

dmm = Keysight34450A()
dmm.initialize("USB0::0x2A8D::0x8E01::CN12345678::INSTR", reset=True)

dmm.configure.voltage_dc(range=10)

for _ in range(5):
    print(f"{dmm.read():.6f} V")

dmm.close()
