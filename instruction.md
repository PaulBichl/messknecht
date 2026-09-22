### I want to create my instrument driver libary
####  Focused on the following instruments:
+ TTi PL303QMD
+ Keysight InfiniiVision DSO-X 3014T
+ Keysight 33500B
+ Keysight 34450A

manuals can be found in /manuals => *READ THEM!*

# Basic Architecture
* I want a generic basic visa instrument as a base class in /core
    * `Initialize(res, reset, OptionString = "" )` => Optionstring e.g. simulate=true
        * res => Visa resource string
        * reset => bool
        * Optionstring: key value pairs, during initialization has to be parsed
* Handle errors wiht exceptions, if the user wants logging thath is their work
* Drivers should be low level => basically a wrapper for SCPI commands with a seperate Application layer
    * Same moduel for low level + Application layer
    * `app._lowlevel = LowLevel()`  
```
highLevelFunction(self):
  self._lowlevel.foo()
```
* backbone is pyvisa
* Typical functions for the Application layer would be:
    * `dmm.configure.voltageDC(resolution=123, )`
    * `scope.Screenshot(...)`
* All instruments should have a sim mode
    * Best way I know is: if a dedicated read/query function exists for the instument, the expected type is known by the object calling the function, if float: fixed int + noise, otherwise more difficult, if there is no easy way: do not simulate that part
    * more of a nice to have for debugging than a hard prio

# Must have functionality by instrument
## TTi PL303QMD
* Access to all channels
* Output On/Off
* `psu.configure(voltage = 5, currentLimit = 5)` or similar
* properties work really well for these instruments
## Keysight InfiniiVision DSO-X 3014T
* difficult one => extra effort required
* saving Waveforms to e.g. csv
* saving Screenshot (to a path on PC)
* A high degree of functionality is usually not user friendly
    * setting up complex triggers, the right resolution, alligning channels... is usually only possible interactivly directly on the scope
## Keysight 33500B
* Configureing standard waveforms (sin, rect, DC...)
* loading custom arbritary waveforms from e.g. csv
## Keysight 34450A
* priority Voltage DC, others less relevant
    * continious mode should be configurable!
# Testing
+ Integration Tests >> Unit tests
+ best way: short scripts, manually confirmed by user in the lab
    +

# Docs
## User docs
+ Short example scritps for the most basic functions si the goal (e.g for a scope a script connecting, setting up a channel, saving a waveform, taking a screenshot...) => KISS
## Developer Docs
* Bigger focus
* Architecture, design decissions...
* update AGENT.md aswell

# Other
## Codestyle
* follow PEP08, hard rules can be seen in the ruff config
