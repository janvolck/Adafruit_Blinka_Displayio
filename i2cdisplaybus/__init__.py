# SPDX-FileCopyrightText: 2020 Melissa LeBlanc-Williams for Adafruit Industries
# SPDX-FileCopyrightText: 2020 Erik Tollerud
# SPDX-FileCopyrightText: 2021 Jim Morris
# SPDX-FileCopyrightText: 2021 James Carr
#
# SPDX-License-Identifier: MIT

"""
`i2cdisplaybus`
================================================================================

i2cdisplaybus for Blinka

**Software and Dependencies:**

* Adafruit Blinka:
  https://github.com/adafruit/Adafruit_Blinka/releases

* Author(s): Melissa LeBlanc-Williams, Erik Tollerud, James Carr

"""

import time
from typing import Optional

import busio
import digitalio
from circuitpython_typing import ReadableBuffer
from displayio._constants import CHIP_SELECT_UNTOUCHED, DISPLAY_COMMAND

__version__ = "0.0.0+auto.0"
__repo__ = "https://github.com/adafruit/Adafruit_Blinka_displayio.git"


class I2CDisplayBus:
    """Manage updating a display over I2C in the background while Python code runs.
    It doesn’t handle display initialization.
    """

    def __init__(self, i2c_bus: busio.I2C, *, device_address: int, reset=None):
        """Create a I2CDisplayBus object associated with the given I2C bus and reset pin.

        The I2C bus and pins are then in use by the display until displayio.release_displays() is
        called even after a reload. (It does this so CircuitPython can use the display after your
        code is done.) So, the first time you initialize a display bus in code.py you should call
        :py:func`displayio.release_displays` first, otherwise it will error after the first
        code.py run.
        """

        if reset is not None:
            self._reset = digitalio.DigitalInOut(reset)
            self._reset.switch_to_output(value=True)
        else:
            self._reset = None
        self._i2c = i2c_bus
        self._dev_addr = device_address

    def __new__(cls, *args, **kwargs):
        from displayio import (  # pylint: disable=import-outside-toplevel, cyclic-import
            allocate_display_bus,
        )

        display_bus_instance = super().__new__(cls)
        allocate_display_bus(display_bus_instance)
        return display_bus_instance

    def _release(self):
        self.reset()
        self._i2c.deinit()
        if self._reset is not None:
            self._reset.deinit()

    def reset(self) -> None:
        """
        Performs a hardware reset via the reset pin if one is present.
        """

        if self._reset is None:
            return

        self._reset.value = False
        time.sleep(0.0001)
        self._reset.value = True

    def send(self, command: int, data: ReadableBuffer) -> None:
        """
        Sends the given command value followed by the full set of data. Display state,
        such as vertical scroll, set via ``send`` may or may not be reset once the code is
        done.
        """
        self._begin_transaction()
        self._send(DISPLAY_COMMAND, CHIP_SELECT_UNTOUCHED, data, command)
        self._end_transaction()

    def _send(
        self,
        data_type: int,
        _chip_select: int,  # Chip select behavior
        data: ReadableBuffer,
        command: Optional[int] = None,
    ):
        # pylint: disable=too-many-branches
        if data_type == DISPLAY_COMMAND:
            n = len(data)
            if command is not None:
                n += 1
            if n > 0:
                command_bytes = bytearray(n * 2)
                for i in range(n):
                    command_bytes[2 * i] = 0x80
                    if command is not None:
                        if i > 0:
                            command_bytes[2 * i + 1] = data[i]
                        else:
                            command_bytes[2 * i + 1] = command
                    else:
                        command_bytes[2 * i + 1] = data[i]

            try:
                self._i2c.writeto(self._dev_addr, buffer=command_bytes)
            except OSError as error:
                if error.errno == 121:
                    raise RuntimeError(
                        f"I2C write error to 0x{self._dev_addr:02x}"
                    ) from error
                raise error
        else:
            size = len(data) + 1
            if command is not None:
                size += 1
            data_bytes = bytearray(size)
            data_bytes[0] = 0x40
            if command is not None:
                data_bytes[1] = command
                data_bytes[2:] = data
            else:
                data_bytes[1:] = data
            try:
                self._i2c.writeto(self._dev_addr, buffer=data_bytes)
            except OSError as error:
                if error.errno == 121:
                    raise RuntimeError(
                        f"I2C write error to 0x{self._dev_addr:02x}"
                    ) from error
                raise error

    def _free(self) -> bool:
        """Attempt to free the bus and return False if busy"""
        if not self._i2c.try_lock():
            return False
        self._i2c.unlock()
        return True

    def _begin_transaction(self) -> bool:
        """Lock the bus before sending data."""
        return self._i2c.try_lock()

    def _end_transaction(self) -> None:
        """Release the bus after sending data."""
        self._i2c.unlock()
