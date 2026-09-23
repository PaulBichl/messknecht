"""Driver for Keysight InfiniiVision 3000T X-series oscilloscopes (e.g. DSO-X 3014T).

Scope of this driver (deliberately small): complex triggering, resolution and
channel alignment are best done interactively at the instrument. The
application layer focuses on what you want to automate afterwards - basic
channel/timebase/trigger setup, acquisition control, saving waveforms to CSV
and taking screenshots.

Waveform scaling (manual, ``:WAVeform:PREamble``)::

    voltage = (raw - y_reference) * y_increment + y_origin
    time    = (index - x_reference) * x_increment + x_origin

Usage::

    from messknecht import KeysightDSOX3000T

    with KeysightDSOX3000T() as scope:
        scope.initialize("USB0::0x2A8D::...::INSTR", reset=False)
        scope.save_waveform_csv("waveform.csv", channels=[1, 2])
        scope.screenshot("screen.png")
"""

from __future__ import annotations

import csv
import dataclasses
import math
import re
import struct
import zlib
from pathlib import Path

import numpy as np

from messknecht.core.exceptions import InstrumentDataError
from messknecht.core.instrument import InstrumentApplication, VisaInstrument
from messknecht.core.scpi import scpi_bool, scpi_number
from messknecht.core.simulation import SimulationBackend

#: Timeout used for acquisition-dependent transfers (digitize can take a while).
TRANSFER_TIMEOUT_MS = 30000.0

_POINTS_MODES = {"NORMAL": "NORMal", "MAXIMUM": "MAXimum", "RAW": "RAW"}
_IMAGE_FORMATS = {".png": "PNG", ".bmp": "BMP"}


@dataclasses.dataclass(frozen=True)
class WaveformPreamble:
    """Decoded ``:WAVeform:PREamble?`` response."""

    format: int  #: 0 = BYTE, 1 = WORD, 4 = ASCii
    type: int  #: 0 = NORMal, 1 = PEAK, 2 = AVERage, 3 = HRESolution
    points: int
    count: int
    x_increment: float
    x_origin: float
    x_reference: int
    y_increment: float
    y_origin: float
    y_reference: int


@dataclasses.dataclass(frozen=True)
class ScopeWaveform:
    """A downloaded waveform: sample times in seconds, values in Volts."""

    source: str
    time: np.ndarray
    voltage: np.ndarray
    preamble: WaveformPreamble


def _tiny_png() -> bytes:
    """A minimal valid 1x1 PNG (simulation screenshot placeholder)."""

    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data))

    header = struct.pack(">IIBBBBB", 1, 1, 8, 0, 0, 0, 0)  # 1x1 px, 8 bit grayscale
    pixel_data = zlib.compress(b"\x00\x80")  # scanline filter 0 + one gray pixel
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", pixel_data) + chunk(b"IEND", b"")


def _tiny_bmp() -> bytes:
    """A minimal valid 1x1 24-bit BMP (simulation screenshot placeholder)."""
    pixel = b"\x80\x80\x80\x00"  # BGR + row padding
    dib = struct.pack("<IiiHHIIiiII", 40, 1, 1, 1, 24, 0, len(pixel), 2835, 2835, 0, 0)
    offset = 14 + len(dib)
    file_header = struct.pack("<2sIHHI", b"BM", offset + len(pixel), 0, 0, offset)
    return file_header + dib + pixel


class _KeysightDSOX3000TSimulation(SimulationBackend):
    """Minimal simulation: a fixed-scale sine waveform and a placeholder screenshot.

    Unlike the other drivers this backend returns synthetic *binary* data,
    because binary transfers (waveform download, screenshot) cannot fall back to
    a generic default the way numeric queries can. It models nothing else: the
    only state is the requested point count so that ``get_waveform(points=N)``
    returns ``N`` samples; all setup writes are logged and ignored. The frame is
    always WORD format (matching what :meth:`KeysightDSOX3000T.get_waveform`
    requests) with a +/-3 V, 3-cycle sine.
    """

    IDN = "KEYSIGHT TECHNOLOGIES,DSO-X 3014T,MYSIM00001,07.60.2024"

    _DEFAULT_POINTS = 1000
    _TIMEBASE = 100e-6  # s/div; the screen spans 10 divisions
    _Y_REFERENCE = 32768  # WORD-format mid scale
    _Y_INCREMENT = 8.0 / 65536  # 8 divisions of 1 V/div across the WORD range
    _AMPLITUDE_V = 3.0  # sine peak, in Volts

    def reset(self) -> None:
        self.state.clear()
        self.state["points"] = self._DEFAULT_POINTS

    def _points(self) -> int:
        value = self.state.get("points", self._DEFAULT_POINTS)
        assert isinstance(value, int)
        return value

    def handle_write(self, command: str) -> None:
        match = re.fullmatch(r":?WAV(?:EFORM)?:POIN(?:TS)?\s+(\d+)", command.strip(), flags=re.IGNORECASE)
        if match is not None:
            self.state["points"] = int(match.group(1))

    def handle_query(self, command: str) -> str | None:
        normalized = command.strip().lstrip(":").upper()
        if normalized.startswith(("WAV:PRE", "WAVEFORM:PRE")):
            points = self._points()
            x_increment = 10.0 * self._TIMEBASE / points
            x_origin = -5.0 * self._TIMEBASE
            return (
                f"1,0,{points},1,{x_increment:.6E},{x_origin:.6E},0,"
                f"{self._Y_INCREMENT:.6E},0.000000E+00,{self._Y_REFERENCE}"
            )
        if normalized.startswith(("WAV:POIN", "WAVEFORM:POIN")):
            return str(self._points())
        if normalized.startswith(("TIM:MODE", "TIMEBASE:MODE")):
            return "MAIN"
        return None

    def handle_query_binary(self, command: str) -> bytes | None:
        normalized = command.strip().lstrip(":").upper()
        if normalized.startswith(("DISP:DATA", "DISPLAY:DATA")):
            return _tiny_bmp() if "BMP" in normalized else _tiny_png()
        if normalized.startswith(("WAV:DATA", "WAVEFORM:DATA")):
            points = self._points()
            indices = np.arange(points)
            amplitude_counts = self._AMPLITUDE_V / self._Y_INCREMENT
            samples = self._Y_REFERENCE + amplitude_counts * np.sin(2.0 * math.pi * 3.0 * indices / points)
            return samples.astype("<u2").tobytes()  # get_waveform requests LSBFirst
        return None


class KeysightDSOX3000TLowLevel(VisaInstrument):
    """Low level SCPI wrapper for the InfiniiVision 3000T X-series."""

    SIMULATION_BACKEND = _KeysightDSOX3000TSimulation

    @staticmethod
    def _channel(channel: int) -> str:
        if not 1 <= channel <= KeysightDSOX3000T.CHANNEL_COUNT:
            msg = f"Channel must be 1..{KeysightDSOX3000T.CHANNEL_COUNT}, got {channel}"
            raise ValueError(msg)
        return f"CHANnel{channel}"

    # -- acquisition control ---------------------------------------------------

    def run(self) -> None:
        """``:RUN`` - continuous acquisition."""
        self.write(":RUN")

    def stop(self) -> None:
        """``:STOP`` - stop acquiring."""
        self.write(":STOP")

    def single(self) -> None:
        """``:SINGle`` - a single acquisition, then stop."""
        self.write(":SINGle")

    def digitize(self, *sources: str) -> None:
        """``:DIGitize [<source>,...]`` - acquire the sources, then stop."""
        argument = " " + ",".join(sources) if sources else ""
        self.write(f":DIGitize{argument}")

    def autoscale(self) -> None:
        """``:AUToscale`` - automatic scope setup for the connected signals."""
        self.write(":AUToscale")

    # -- vertical / horizontal / trigger -----------------------------------------

    def set_channel_display(self, channel: int, on: bool) -> None:
        """``:CHANnel<n>:DISPlay {ON|OFF}``."""
        self.write(f":{self._channel(channel)}:DISPlay {scpi_bool(on)}")

    def set_channel_scale(self, channel: int, volts_per_div: float) -> None:
        """``:CHANnel<n>:SCALe <scale>`` in Volts/division."""
        self.write(f":{self._channel(channel)}:SCALe {scpi_number(volts_per_div)}")

    def set_channel_offset(self, channel: int, volts: float) -> None:
        """``:CHANnel<n>:OFFSet <offset>`` in Volts (center screen value)."""
        self.write(f":{self._channel(channel)}:OFFSet {scpi_number(volts)}")

    def set_channel_coupling(self, channel: int, coupling: str) -> None:
        """``:CHANnel<n>:COUPling {AC|DC}``."""
        keyword = coupling.strip().upper()
        if keyword not in {"AC", "DC"}:
            msg = f"Coupling must be 'AC' or 'DC', got {coupling!r}"
            raise ValueError(msg)
        self.write(f":{self._channel(channel)}:COUPling {keyword}")

    def set_channel_probe(self, channel: int, attenuation: float) -> None:
        """``:CHANnel<n>:PROBe <attenuation>`` - probe attenuation factor (e.g. 10)."""
        self.write(f":{self._channel(channel)}:PROBe {scpi_number(attenuation)}")

    def set_timebase_scale(self, seconds_per_div: float) -> None:
        """``:TIMebase:SCALe <scale>`` in seconds/division."""
        self.write(f":TIMebase:SCALe {scpi_number(seconds_per_div)}")

    def set_timebase_position(self, seconds: float) -> None:
        """``:TIMebase:POSition <pos>`` - delay between trigger and screen center."""
        self.write(f":TIMebase:POSition {scpi_number(seconds)}")

    def get_timebase_mode(self) -> str:
        """``:TIMebase:MODE?`` - ``MAIN``, ``WIND``, ``XY`` or ``ROLL``."""
        return self.query(":TIMebase:MODE?").upper()

    def set_timebase_mode(self, mode: str) -> None:
        """``:TIMebase:MODE {MAIN|WINDow|XY|ROLL}``."""
        self.write(f":TIMebase:MODE {mode}")

    def set_trigger_mode_edge(self) -> None:
        """``:TRIGger:MODE EDGE``."""
        self.write(":TRIGger:MODE EDGE")

    def set_edge_trigger_source(self, source: str) -> None:
        """``:TRIGger:EDGE:SOURce <source>`` (e.g. ``CHANnel1``, ``EXTernal``, ``LINE``)."""
        self.write(f":TRIGger:EDGE:SOURce {source}")

    def set_edge_trigger_level(self, volts: float) -> None:
        """``:TRIGger:EDGE:LEVel <level>`` in Volts."""
        self.write(f":TRIGger:EDGE:LEVel {scpi_number(volts)}")

    def set_edge_trigger_slope(self, slope: str) -> None:
        """``:TRIGger:EDGE:SLOPe {POSitive|NEGative|EITHer|ALTernate}``."""
        allowed = {
            "POSITIVE": "POSitive",
            "POS": "POSitive",
            "NEGATIVE": "NEGative",
            "NEG": "NEGative",
            "EITHER": "EITHer",
            "EITH": "EITHer",
            "ALTERNATE": "ALTernate",
            "ALT": "ALTernate",
        }
        mnemonic = allowed.get(slope.strip().upper())
        if mnemonic is None:
            msg = f"Invalid slope {slope!r}; allowed: positive, negative, either, alternate"
            raise ValueError(msg)
        self.write(f":TRIGger:EDGE:SLOPe {mnemonic}")

    # -- waveform transfer -------------------------------------------------------

    def set_waveform_source(self, source: str) -> None:
        """``:WAVeform:SOURce <source>``."""
        self.write(f":WAVeform:SOURce {source}")

    def set_waveform_format(self, format_: str) -> None:
        """``:WAVeform:FORMat {BYTE|WORD|ASCii}``."""
        self.write(f":WAVeform:FORMat {format_}")

    def set_waveform_points_mode(self, mode: str) -> None:
        """``:WAVeform:POINts:MODE {NORMal|MAXimum|RAW}``."""
        self.write(f":WAVeform:POINts:MODE {mode}")

    def set_waveform_points(self, points: int) -> None:
        """``:WAVeform:POINts <n>`` - requested number of points (100..10M)."""
        self.write(f":WAVeform:POINts {int(points)}")

    def set_waveform_unsigned(self, unsigned: bool) -> None:
        """``:WAVeform:UNSigned {0|1}``."""
        self.write(f":WAVeform:UNSigned {scpi_bool(unsigned)}")

    def set_waveform_byte_order(self, lsb_first: bool) -> None:
        """``:WAVeform:BYTeorder {LSBFirst|MSBFirst}`` (WORD format only)."""
        self.write(f":WAVeform:BYTeorder {'LSBFirst' if lsb_first else 'MSBFirst'}")

    def get_waveform_preamble(self) -> WaveformPreamble:
        """``:WAVeform:PREamble?`` - scaling information for the selected source."""
        response = self.query(":WAVeform:PREamble?")
        fields = response.split(",")
        if len(fields) != 10:
            msg = f"Unexpected preamble response: {response!r}"
            raise InstrumentDataError(msg)
        return WaveformPreamble(
            format=int(float(fields[0])),
            type=int(float(fields[1])),
            points=int(float(fields[2])),
            count=int(float(fields[3])),
            x_increment=float(fields[4]),
            x_origin=float(fields[5]),
            x_reference=int(float(fields[6])),
            y_increment=float(fields[7]),
            y_origin=float(fields[8]),
            y_reference=int(float(fields[9])),
        )

    def read_waveform_data(self) -> bytes:
        """``:WAVeform:DATA?`` - raw binary block payload for the selected source."""
        return self.query_binary_block(":WAVeform:DATA?")

    # -- display / screenshot -------------------------------------------------------

    def set_inksaver(self, on: bool) -> None:
        """``:HARDcopy:INKSaver {ON|OFF}`` - OFF gives non-inverted screenshots."""
        self.write(f":HARDcopy:INKSaver {scpi_bool(on)}")

    def read_screen_image(self, format_: str = "PNG", palette: str = "COLor") -> bytes:
        """``:DISPlay:DATA? <format>,<palette>`` - screen image as binary block."""
        return self.query_binary_block(f":DISPlay:DATA? {format_}, {palette}")

    # -- measurements ------------------------------------------------------------------

    def measure_vpp(self, source: str) -> float:
        """``:MEASure:VPP? <source>`` - peak-to-peak voltage."""
        return self.query_float(f":MEASure:VPP? {source}")

    def measure_frequency(self, source: str) -> float:
        """``:MEASure:FREQuency? <source>``."""
        return self.query_float(f":MEASure:FREQuency? {source}", sim_value=1000.0)

    def measure_vaverage(self, source: str) -> float:
        """``:MEASure:VAVerage? <source>`` - average voltage of the display."""
        return self.query_float(f":MEASure:VAVerage? {source}")


class KeysightDSOX3000T(InstrumentApplication[KeysightDSOX3000TLowLevel]):
    """Application layer for InfiniiVision 3000T X-series oscilloscopes."""

    CHANNEL_COUNT = 4

    def __init__(self) -> None:
        super().__init__(KeysightDSOX3000TLowLevel())

    @staticmethod
    def _source_name(channel: int | str) -> str:
        if isinstance(channel, str):
            return channel
        return KeysightDSOX3000TLowLevel._channel(channel)

    # -- acquisition ------------------------------------------------------------

    def run(self) -> None:
        """Start continuous acquisition."""
        self._lowlevel.run()

    def stop(self) -> None:
        """Stop acquiring."""
        self._lowlevel.stop()

    def single(self) -> None:
        """Arm a single acquisition, then stop."""
        self._lowlevel.single()

    def digitize(self, *channels: int | str, timeout_ms: float = TRANSFER_TIMEOUT_MS) -> None:
        """Acquire the given channels (all displayed ones if empty) and stop.

        This is the recommended way to get a consistent acquisition before
        downloading waveform data. ``:DIGitize`` is rejected in Roll mode, so
        the timebase is switched to Normal (``MAIN``) mode first if needed.
        Waits until the acquisition is complete (at most ``timeout_ms``).
        """
        lowlevel = self._lowlevel
        if lowlevel.get_timebase_mode() == "ROLL":
            lowlevel.set_timebase_mode("MAIN")
        with lowlevel.temporary_timeout(timeout_ms):
            lowlevel.digitize(*(self._source_name(channel) for channel in channels))
            # The scope answers the error query only once the acquisition is done.
            self.check_errors()

    def autoscale(self) -> None:
        """Automatic setup for the connected signals (like the front panel key)."""
        self._lowlevel.autoscale()

    # -- setup -------------------------------------------------------------------

    def setup_channel(
        self,
        channel: int,
        scale: float | None = None,
        offset: float | None = None,
        coupling: str | None = None,
        probe_attenuation: float | None = None,
        display: bool | None = None,
    ) -> None:
        """Basic vertical setup of one analog channel (only given values are set)."""
        lowlevel = self._lowlevel
        if display is not None:
            lowlevel.set_channel_display(channel, display)
        if probe_attenuation is not None:
            lowlevel.set_channel_probe(channel, probe_attenuation)
        if coupling is not None:
            lowlevel.set_channel_coupling(channel, coupling)
        if scale is not None:
            lowlevel.set_channel_scale(channel, scale)
        if offset is not None:
            lowlevel.set_channel_offset(channel, offset)
        self.check_errors()

    def setup_timebase(self, scale: float | None = None, position: float | None = None) -> None:
        """Basic horizontal setup (seconds/division, trigger position offset)."""
        if scale is not None:
            self._lowlevel.set_timebase_scale(scale)
        if position is not None:
            self._lowlevel.set_timebase_position(position)
        self.check_errors()

    def setup_edge_trigger(
        self,
        source: int | str = 1,
        level: float | None = None,
        slope: str = "positive",
    ) -> None:
        """Set up a simple edge trigger.

        Anything beyond an edge trigger is intentionally out of scope - set it
        up interactively at the scope.
        """
        lowlevel = self._lowlevel
        lowlevel.set_trigger_mode_edge()
        lowlevel.set_edge_trigger_source(self._source_name(source))
        lowlevel.set_edge_trigger_slope(slope)
        if level is not None:
            lowlevel.set_edge_trigger_level(level)
        self.check_errors()

    # -- waveform download ----------------------------------------------------------

    def get_waveform(
        self,
        channel: int | str = 1,
        points: int | None = None,
        points_mode: str = "normal",
        timeout_ms: float = TRANSFER_TIMEOUT_MS,
    ) -> ScopeWaveform:
        """Download one waveform and convert it to physical units.

        The data of the *current* acquisition is read (use :meth:`digitize`
        or stop the scope first for consistent data).

        Args:
            channel: Analog channel number, or a raw source string like
                ``"FUNCtion1"``.
            points: Requested number of points (instrument may return fewer).
                ``None`` keeps the instrument setting.
            points_mode: ``"normal"`` (displayed data), ``"maximum"`` or
                ``"raw"`` (full memory, acquisition must be stopped).
            timeout_ms: VISA timeout for the transfer.

        Returns:
            :class:`ScopeWaveform` with time/voltage numpy arrays.
        """
        mode = _POINTS_MODES.get(points_mode.strip().upper())
        if mode is None:
            msg = f"Invalid points_mode {points_mode!r}; allowed: normal, maximum, raw"
            raise ValueError(msg)
        source = self._source_name(channel)
        lowlevel = self._lowlevel
        lowlevel.set_waveform_source(source)
        lowlevel.set_waveform_format("WORD")
        lowlevel.set_waveform_unsigned(True)
        lowlevel.set_waveform_byte_order(lsb_first=True)
        lowlevel.set_waveform_points_mode(mode)
        if points is not None:
            lowlevel.set_waveform_points(points)
        with lowlevel.temporary_timeout(timeout_ms):
            preamble = lowlevel.get_waveform_preamble()
            payload = lowlevel.read_waveform_data()
        dtype = "<u2" if preamble.format == 1 else "u1"
        raw = np.frombuffer(payload, dtype=dtype)
        voltage = (raw.astype(np.float64) - preamble.y_reference) * preamble.y_increment + preamble.y_origin
        time = (np.arange(raw.size, dtype=np.float64) - preamble.x_reference) * preamble.x_increment + preamble.x_origin
        self.check_errors()
        return ScopeWaveform(source=source, time=time, voltage=voltage, preamble=preamble)

    def save_waveform_csv(
        self,
        path: str | Path,
        channels: int | str | list[int | str] = 1,
        points: int | None = None,
        points_mode: str = "normal",
        acquire: bool = True,
        timeout_ms: float = TRANSFER_TIMEOUT_MS,
    ) -> Path:
        """Save one or more channel waveforms to a CSV file.

        The file has a ``time_s`` column and one voltage column per channel.

        Args:
            path: Target CSV file path.
            channels: One channel or a list of channels to save.
            points: Requested number of points per waveform.
            points_mode: See :meth:`get_waveform`.
            acquire: Run a fresh :meth:`digitize` of the channels first
                (guarantees one consistent acquisition; leaves the scope
                stopped). Set to False to read what is currently on screen.
            timeout_ms: VISA timeout for acquisition and transfer.

        Returns:
            The written path.
        """
        channel_list = channels if isinstance(channels, list) else [channels]
        if not channel_list:
            msg = "At least one channel is required"
            raise ValueError(msg)
        if acquire:
            self.digitize(*channel_list, timeout_ms=timeout_ms)
        waveforms = [
            self.get_waveform(channel, points=points, points_mode=points_mode, timeout_ms=timeout_ms)
            for channel in channel_list
        ]
        lengths = {waveform.voltage.size for waveform in waveforms}
        if len(lengths) != 1:
            msg = f"Channels returned different record lengths: {sorted(lengths)}"
            raise InstrumentDataError(msg)

        file_path = Path(path)
        with file_path.open("w", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(["time_s", *(f"{waveform.source.lower()}_V" for waveform in waveforms)])
            columns = [waveforms[0].time, *(waveform.voltage for waveform in waveforms)]
            writer.writerows(zip(*columns, strict=True))
        return file_path

    # -- screenshot ---------------------------------------------------------------------

    def screenshot(self, path: str | Path, palette: str = "color", inksaver: bool = False) -> Path:
        """Save a screenshot of the scope display to a file on this PC.

        Args:
            path: Target file; the suffix selects the format (``.png`` or ``.bmp``).
            palette: ``"color"`` or ``"grayscale"``.
            inksaver: Inverted (white background) image when True.

        Returns:
            The written path.
        """
        file_path = Path(path)
        image_format = _IMAGE_FORMATS.get(file_path.suffix.lower())
        if image_format is None:
            msg = f"Unsupported screenshot format {file_path.suffix!r}; use .png or .bmp"
            raise ValueError(msg)
        palettes = {"COLOR": "COLor", "GRAYSCALE": "GRAYscale"}
        palette_keyword = palettes.get(palette.strip().upper())
        if palette_keyword is None:
            msg = f"Invalid palette {palette!r}; allowed: color, grayscale"
            raise ValueError(msg)
        lowlevel = self._lowlevel
        lowlevel.set_inksaver(inksaver)
        with lowlevel.temporary_timeout(TRANSFER_TIMEOUT_MS):
            data = lowlevel.read_screen_image(image_format, palette_keyword)
        file_path.write_bytes(data)
        self.check_errors()
        return file_path

    # -- measurements ----------------------------------------------------------------------
    # A measurement query waits for a complete acquisition, which takes longer
    # than the default VISA timeout on slow timebases (10 divisions of 500 ms).

    def measure_vpp(self, channel: int | str = 1) -> float:
        """Peak-to-peak voltage of the displayed signal."""
        with self._lowlevel.temporary_timeout(TRANSFER_TIMEOUT_MS):
            return self._lowlevel.measure_vpp(self._source_name(channel))

    def measure_frequency(self, channel: int | str = 1) -> float:
        """Frequency of the displayed signal."""
        with self._lowlevel.temporary_timeout(TRANSFER_TIMEOUT_MS):
            return self._lowlevel.measure_frequency(self._source_name(channel))

    def measure_vaverage(self, channel: int | str = 1) -> float:
        """Average voltage of the displayed signal."""
        with self._lowlevel.temporary_timeout(TRANSFER_TIMEOUT_MS):
            return self._lowlevel.measure_vaverage(self._source_name(channel))
