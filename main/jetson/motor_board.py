"""
Serial client for the robot's motor-controller board (STM32, USB CDC at
1 Mbaud, usually /dev/ttyACM0).

Frame format, both directions:

    0xAA 0x55 | function:u8 | length:u8 | data[length] | crc8(function, length, data)

crc8 is CRC-8/MAXIM (reflected polynomial 0x8C, init 0).  Little-endian
payloads.  Only what GHOST needs is implemented:

    motors   function 3: [0x01, n, n × (motor_index:u8 (id−1), speed:f32 rev/s)]
    battery  function 0 report: [0x04, millivolts:u16]
    imu      function 7 report: 6 × f32 (ax, ay, az m/s², gx, gy, gz rad/s)

Pure Python + pyserial; no ROS needed, so it can be bench-tested alone.
"""
from __future__ import annotations

import struct
import threading
import time

START = b"\xAA\x55"
FUNC_SYS, FUNC_MOTOR, FUNC_IMU = 0, 3, 7
FUNC_MAX = 10                       # functions >= this are invalid


def _crc8_table() -> list[int]:
    table = []
    for i in range(256):
        c = i
        for _ in range(8):
            c = (c >> 1) ^ 0x8C if c & 1 else c >> 1
        table.append(c)
    return table


_CRC = _crc8_table()


def crc8(data: bytes) -> int:
    c = 0
    for b in data:
        c = _CRC[c ^ b]
    return c


def frame(func: int, data: bytes) -> bytes:
    body = bytes([func, len(data)]) + data
    return START + body + bytes([crc8(body)])


def motor_payload(speeds: dict[int, float]) -> bytes:
    """{motor_id (1-based): rev/s} → motor command payload."""
    out = bytearray([0x01, len(speeds)])
    for mid, rps in speeds.items():
        out += struct.pack("<Bf", int(mid) - 1, float(rps))
    return bytes(out)


class FrameParser:
    """Byte-at-a-time parser; yields (function, data) for valid frames."""

    def __init__(self) -> None:
        self._buf = bytearray()

    def feed(self, chunk: bytes):
        self._buf += chunk
        while True:
            i = self._buf.find(START)
            if i < 0:
                del self._buf[:-1]          # keep a possible trailing 0xAA
                return
            del self._buf[:i]
            if len(self._buf) < 4:
                return
            func, n = self._buf[2], self._buf[3]
            if func >= FUNC_MAX:
                del self._buf[:2]
                continue
            if len(self._buf) < 5 + n:
                return
            body, crc = bytes(self._buf[2:4 + n]), self._buf[4 + n]
            del self._buf[:5 + n]
            if crc8(body) == crc:
                yield func, body[2:]


class MotorBoard:
    """Open the board, send wheel speeds, read battery / IMU reports."""

    def __init__(self, port: str = "/dev/ttyACM0", baud: int = 1_000_000) -> None:
        import serial                                  # late: tests need no pyserial
        self._ser = serial.Serial(port, baud, timeout=0.05)
        self._lock = threading.Lock()
        self._parser = FrameParser()
        self.battery_mv: int | None = None
        self.imu: tuple[float, ...] | None = None
        self.last_report = 0.0
        self._running = True
        threading.Thread(target=self._rx, daemon=True).start()

    def set_speeds(self, speeds: dict[int, float]) -> None:
        with self._lock:
            self._ser.write(frame(FUNC_MOTOR, motor_payload(speeds)))

    def stop(self, ids=(1, 2, 3, 4)) -> None:
        self.set_speeds({i: 0.0 for i in ids})

    def close(self) -> None:
        try:
            self.stop()
        finally:
            self._running = False
            time.sleep(0.06)
            self._ser.close()

    def _rx(self) -> None:
        # Draining reports also keeps the board's USB buffer from filling.
        while self._running:
            try:
                chunk = self._ser.read(256)
            except Exception:
                return
            for func, data in self._parser.feed(chunk):
                self.last_report = time.monotonic()
                if func == FUNC_SYS and len(data) == 3 and data[0] == 0x04:
                    self.battery_mv = struct.unpack("<H", data[1:])[0]
                elif func == FUNC_IMU and len(data) == 24:
                    self.imu = struct.unpack("<6f", data)
