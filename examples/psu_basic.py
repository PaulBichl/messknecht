"""TTi PL303QMD: power a circuit from CH1 and read back voltage and current."""

import time

from messknecht import TTiPL303QMD

psu = TTiPL303QMD()
psu.initialize("ASRL/dev/ttyACM0::INSTR", reset=True)

psu.ch1.voltage = 5.0
psu.ch1.current_limit = 0.1
psu.ch1.output = True
time.sleep(0.5)

print(f"{psu.ch1.measured_voltage:.3f} V")
print(f"{psu.ch1.measured_current * 1000:.2f} mA")

psu.ch1.output = False
psu.close()
