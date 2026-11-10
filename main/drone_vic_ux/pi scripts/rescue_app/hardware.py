"""
hardware.py — everything that touches the physical PiTFT 2.2" HAT.

    DisplayProfile  the fixed facts about this HAT (size, rotation, pins)
    Screen          sends a finished picture to the glass over SPI
    ButtonPanel     reads the 4 buttons and turns presses into ButtonEvents

Nothing outside this file knows about pins, SPI, or the screen chip.
"""

import time
from dataclasses import dataclass

import lgpio
import spidev

from events import HOLD, TAP, ButtonEvent


@dataclass(frozen=True)
class DisplayProfile:
    """
    Facts about the Adafruit PiTFT 2.2" (240x320, ILI9340 chip), confirmed by smoke_test.py.
    frozen=True means these values can't be changed by accident while the app runs.
    """
    width: int = 320                      # landscape: buttons along the bottom
    height: int = 240
    rotation: int = 1                     # 1 or 3 — whichever showed TOP opposite the buttons
    dc_pin: int = 25                      # data/command pin
    spi_bus: int = 0
    spi_device: int = 0                   # CE0
    spi_speed_hz: int = 32_000_000
    button_pins: tuple = (17, 22, 23, 27)  # left to right


# ---------------------------------------------------------------------------
# Screen
# ---------------------------------------------------------------------------

class Screen:
    """
    Talks to the ILI9340 chip. Every message is either a COMMAND or DATA;
    the DC pin tells the chip which (low = command, high = data).
    """

    ROTATION_SETTINGS = {0: 0x48, 1: 0x28, 2: 0x88, 3: 0xE8}   # chip's MADCTL values per rotation

    STARTUP_SEQUENCE = [                                      # (command, data, wait ms)
        (0x01, [], 150),
        (0xEF, [0x03, 0x80, 0x02], 0), (0xCF, [0x00, 0xC1, 0x30], 0),
        (0xED, [0x64, 0x03, 0x12, 0x81], 0), (0xE8, [0x85, 0x00, 0x78], 0),
        (0xCB, [0x39, 0x2C, 0x00, 0x34, 0x02], 0), (0xF7, [0x20], 0), (0xEA, [0x00, 0x00], 0),
        (0xC0, [0x23], 0), (0xC1, [0x10], 0), (0xC5, [0x3E, 0x28], 0), (0xC7, [0x86], 0),
        (0x37, [0x00], 0), (0x3A, [0x55], 0), (0xB1, [0x00, 0x18], 0),
        (0xB6, [0x08, 0x82, 0x27], 0), (0xF2, [0x00], 0), (0x26, [0x01], 0),
        (0xE0, [0x0F, 0x31, 0x2B, 0x0C, 0x0E, 0x08, 0x4E, 0xF1, 0x37, 0x07, 0x10, 0x03, 0x0E, 0x09, 0x00], 0),
        (0xE1, [0x00, 0x0E, 0x14, 0x03, 0x11, 0x07, 0x31, 0xC1, 0x48, 0x08, 0x0F, 0x0C, 0x31, 0x36, 0x0F], 0),
        (0x11, [], 150),
        (0x29, [], 150),
    ]

    def __init__(self, profile, gpio_chip):
        self.profile = profile
        self.gpio_chip = gpio_chip
        lgpio.gpio_claim_output(gpio_chip, profile.dc_pin, 0)

        self.spi_link = spidev.SpiDev()
        self.spi_link.open(profile.spi_bus, profile.spi_device)
        self.spi_link.max_speed_hz = profile.spi_speed_hz
        self.spi_link.mode = 0

        for command, data_bytes, wait_ms in self.STARTUP_SEQUENCE:
            self._send_command(command, data_bytes)
            time.sleep(wait_ms / 1000)
        self._send_command(0x36, [self.ROTATION_SETTINGS[profile.rotation]])

    def _send_command(self, command, data_bytes=()):
        lgpio.gpio_write(self.gpio_chip, self.profile.dc_pin, 0)
        self.spi_link.writebytes([command])
        if data_bytes:
            lgpio.gpio_write(self.gpio_chip, self.profile.dc_pin, 1)
            self.spi_link.writebytes2(bytes(data_bytes))

    def show(self, picture):
        """Send one full picture. It must be exactly profile.width x profile.height."""
        expected_size = (self.profile.width, self.profile.height)
        if picture.size != expected_size:
            raise ValueError(f"picture is {picture.size}, screen is {expected_size}")
        last_x, last_y = self.profile.width - 1, self.profile.height - 1
        self._send_command(0x2A, [0, 0, last_x >> 8, last_x & 0xFF])   # column range
        self._send_command(0x2B, [0, 0, last_y >> 8, last_y & 0xFF])   # row range
        self._send_command(0x2C)                                       # pixels follow
        lgpio.gpio_write(self.gpio_chip, self.profile.dc_pin, 1)
        self.spi_link.writebytes2(to_rgb565(picture))

    def close(self):
        self.spi_link.close()
        lgpio.gpio_free(self.gpio_chip, self.profile.dc_pin)


# RGB565: the chip's 2-bytes-per-pixel color format (5 bits red, 6 green, 5 blue).
RED_TABLE = bytes(value & 0xF8 for value in range(256))
GREEN_HIGH_TABLE = bytes(value >> 5 for value in range(256))
GREEN_LOW_TABLE = bytes((value << 3) & 0xE0 for value in range(256))
BLUE_TABLE = bytes(value >> 3 for value in range(256))


def to_rgb565(picture):
    """Convert a whole PIL picture at once (byte translate + big-integer OR), not pixel by pixel."""
    red, green, blue = (channel.tobytes() for channel in picture.convert("RGB").split())
    pixel_count = len(red)
    high_bytes = (int.from_bytes(red.translate(RED_TABLE), "big")
                  | int.from_bytes(green.translate(GREEN_HIGH_TABLE), "big")).to_bytes(pixel_count, "big")
    low_bytes = (int.from_bytes(green.translate(GREEN_LOW_TABLE), "big")
                 | int.from_bytes(blue.translate(BLUE_TABLE), "big")).to_bytes(pixel_count, "big")
    pixel_bytes = bytearray(pixel_count * 2)
    pixel_bytes[0::2] = high_bytes
    pixel_bytes[1::2] = low_bytes
    return pixel_bytes


# ---------------------------------------------------------------------------
# Buttons
# ---------------------------------------------------------------------------

class ButtonPanel:
    """
    Each button rests HIGH (pull-up) and reads LOW while pressed.
    A TAP is reported when a short press is released (only then do we know it was short).
    A HOLD is reported the moment a press passes hold_seconds, so you don't have to let go.
    """

    def __init__(self, profile, gpio_chip, hold_seconds=0.8, tap_min_seconds=0.03):
        self.gpio_chip = gpio_chip
        self.pins = profile.button_pins
        self.hold_seconds = hold_seconds
        self.tap_min_seconds = tap_min_seconds
        self.pressed_since = [None] * len(self.pins)
        self.hold_reported = [False] * len(self.pins)
        for pin in self.pins:
            lgpio.gpio_claim_input(gpio_chip, pin, lgpio.SET_PULL_UP)

    def poll(self):
        """Return the ButtonEvents that happened since the last call (often an empty list)."""
        events = []
        now = time.monotonic()
        for button_index, pin in enumerate(self.pins):
            is_pressed = lgpio.gpio_read(self.gpio_chip, pin) == 0
            started = self.pressed_since[button_index]
            if is_pressed and started is None:
                self.pressed_since[button_index] = now
                self.hold_reported[button_index] = False
            elif is_pressed and not self.hold_reported[button_index] and now - started >= self.hold_seconds:
                events.append(ButtonEvent(button_index, HOLD))
                self.hold_reported[button_index] = True
            elif not is_pressed and started is not None:
                if not self.hold_reported[button_index] and now - started >= self.tap_min_seconds:
                    events.append(ButtonEvent(button_index, TAP))
                self.pressed_since[button_index] = None
        return events

    def close(self):
        for pin in self.pins:
            lgpio.gpio_free(self.gpio_chip, pin)
