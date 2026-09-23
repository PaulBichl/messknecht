# Known issues

Found during lab testing. Remove an entry once it is fixed.

## Scope lab test: `test_waveform_measurement` passes with no signal connected

**Found:** 2026-09-23 (DSO-X 3014T over LAN, firmware 07.60.2023080430).

When the test ran, nothing was connected to CH1: the screen shows a flat line
and "Freq(1): Low signal". The test still passed, because noise gave
`Vpp = 101 µV`, which satisfies `assert vpp > 0.0`. The assertion should use a
realistic threshold (e.g. > 10 mV), or the test should check that the frequency
measurement is valid.
