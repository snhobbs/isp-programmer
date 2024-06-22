import contextlib
import os
import time
import logging
import struct
from typing import Deque
from collections import deque
import timeout_decorator
from timeout_decorator import timeout
from intelhex import IntelHex
from .IODevices import IODevice, UartDevice
from .parts_definitions import GetPartDescriptor
from . import tools


_log = logging.getLogger("isp_programmer")

kTimeout = 1


BAUDRATES = (9600, 19200, 38400, 57600, 115200, 230400, 460800)


NXPReturnCodes = {
    "CMD_SUCCESS": 0x0,
    "INVALID_COMMAND": 0x1,
    "SRC_ADDR_ERROR": 0x2,
    "DST_ADDR_ERROR": 0x3,
    "SRC_ADDR_NOT_MAPPED": 0x4,
    "DST_ADDR_NOT_MAPPED": 0x5,
    "COUNT_ERROR": 0x6,
    "INVALID_SECTOR/INVALID_PAGE": 0x7,
    "SECTOR_NOT_BLANK": 0x8,
    "SECTOR_NOT_PREPARED_FOR_WRITE_OPERATION": 0x9,
    "COMPARE_ERROR": 0xA,
    "BUSY": 0xB,
    "PARAM_ERROR": 0xC,
    "ADDR_ERROR": 0xD,
    "ADDR_NOT_MAPPED": 0xE,
    "CMD_LOCKED": 0xF,
    "INVALID_CODE": 0x10,
    "INVALID_BAUD_RATE": 0x11,
    "INVALID_STOP_BIT": 0x12,
    "CODE_READ_PROTECTION_ENABLED": 0x13,
    "Unused 1": 0x14,
    "USER_CODE_CHECKSUM": 0x15,
    "Unused 2": 0x16,
    "EFRO_NO_POWER": 0x17,
    "FLASH_NO_POWER": 0x18,
    "Unused 3": 0x19,
    "Unused 4": 0x1A,
    "FLASH_NO_CLOCK": 0x1B,
    "REINVOKE_ISP_CONFIG": 0x1C,
    "NO_VALID_IMAGE": 0x1D,
    "FAIM_NO_POWER": 0x1E,
    "FAIM_NO_CLOCK": 0x1F,
    "NoStatusResponse": 0xFF,
}


def _get_error_code_name(code: int) -> str:
    code = int(code)
    for item in NXPReturnCodes.items():
        if code == item[1]:
            return item[0]
    return f"Not Found: {code}"


def _return_code_success(code: int) -> bool:
    return int(code) == NXPReturnCodes["CMD_SUCCESS"]


def _raise_return_code_error(code: int, call_name: str) -> None:
    """
    Each command returns a code, check if the code is a success, throws a UserWarning if not
    """
    if not _return_code_success(code):
        raise UserWarning(
            f"Return Code Failure in {call_name} {_get_error_code_name(code)} {code}"
        )


class ISPConnection:
    """
    ISPConnection abstracts the interface to the chip, wrapping all responses and ensuring a reliable connection
    """

    kNewLine = "\r\n"
    StatusRespLength = len(kNewLine) + 1
    kWordSize = 4  #  32 bit device
    # Parity = None
    # DataBits = 8
    # StopBits = 1
    SyncString = f"Synchronized{kNewLine}"
    SyncStringBytes = bytes(SyncString, encoding="utf-8")
    SyncVerifiedString = f"OK{kNewLine}"
    # SyncVerifiedBytes = bytes(SyncVerifiedString, encoding="utf-8")
    ReturnCodes = NXPReturnCodes

    def __init__(self, iodevice: IODevice):
        self._return_code_sleep = 0.05
        self._serial_sleep = 10e-3
        self.iodevice = iodevice
        self.data_buffer_in: Deque[int] = deque()
        self.echo_on = True

    @property
    def serial_sleep(self):
        return self._serial_sleep

    @serial_sleep.setter
    def serial_sleep(self, value):
        _log.debug("Setting sleep value %E", value)
        self._serial_sleep = value

    @property
    def return_code_sleep(self):
        return self._return_code_sleep

    @return_code_sleep.setter
    def return_code_sleep(self, value):
        self._return_code_sleep = value

    @property
    def baud_rate(self):
        return self.iodevice.GetBaudrate()

    @baud_rate.setter
    def baud_rate(self, baudrate: int):
        self.iodevice.SetBaudrate(baudrate)

    def _delay_write_serial(self, out: bytes) -> None:
        for byte in out:
            self.iodevice.write(bytes([byte]))
            time.sleep(self.serial_sleep)

    def _write_serial(self, out: bytes) -> None:
        assert isinstance(out, bytes)
        if self.serial_sleep != 0:
            self._delay_write_serial(out)
        else:
            self.iodevice.write(out)
        _log.log(logging.DEBUG - 1, f"Write: [{out}]")

    def _flush(self):
        self.iodevice.flush()

    @timeout(kTimeout)
    def _read_line(self) -> str:
        """
        Read until a new line is found.
        Timesout if no data pulled
        """
        line = self.iodevice.ReadLine()
        return line

    def _get_data_buffer_contents(self):
        return list(self.data_buffer_in)

    def _clear_buffer(self):
        self.data_buffer_in.clear()

    def _read(self):
        """
        Reads input buffer and stores in buffer
        """
        data_in = self.iodevice.read_all()
        dstr = bytes("".join([chr(ch) for ch in data_in]), "utf-8")
        if data_in:
            _log.log(logging.DEBUG - 1, f"_read: <{dstr}>")
        self.data_buffer_in.extend(data_in)

    def _clear_serial(self):
        for _ in range(2):
            tools.retry(
                self._read,
                count=10,
                exception=timeout_decorator.TimeoutError,
                raise_on_fail=False,
            )()
            self._clear_buffer()
            self._flush()

    def _get_return_code(self, command_string: str) -> int:
        """
        No exceptions are thrown.
        """
        time.sleep(self._return_code_sleep)
        try:
            resp = self._read_line()
            if resp.strip() == command_string.strip():
                _log.debug(
                    "Command was echoed, Discarding line: %s", resp
                )
                resp = self._read_line()
            # if self.echo_on:  # discard echo
            #    _log.debug("ECHO ON, Discarding line: %s", resp)
            #    resp = self._read_line()
        except (timeout_decorator.TimeoutError, TimeoutError):
            self._write(bytes(self.kNewLine, encoding="utf-8"))
            return self.ReturnCodes["NoStatusResponse"]
        if len(resp) == 0:
            return self.ReturnCodes["NoStatusResponse"]

        _log.debug("%s: %s", command_string, resp)
        return int(resp.strip())

    def _write(self, string: bytes) -> None:
        _log.debug(string)
        assert isinstance(string, bytes)
        self._write_serial(string)
        # self._write_serial(bytes(self.kNewLine, encoding = "utf-8"))

    def _write_command(self, command_string: str) -> int:
        """
        Takes the command string, return the response code
        """
        new_line = self.kNewLine
        self._write(bytes(f"{command_string}{new_line}", encoding="utf-8"))
        return self._get_return_code(command_string)

    def reset(self):
        self._clear_serial()

    def write_newline(self):
        self._write(bytes(self.kNewLine, encoding="utf-8"))

    def Unlock(self):
        """
        Enables Flash Write, Erase, & Go
        """
        response_code = self._write_command("U 23130")
        _raise_return_code_error(response_code, "Unlock")

    def SetBaudRate(self, baud_rate: int, stop_bits: int = 1):
        """
        Baud Depends of FAIM config, stopbit is 1 or 2
        """
        response_code = self._write_command(f"B {baud_rate} {stop_bits}")
        _raise_return_code_error(response_code, "Set Baudrate")

    def SetEcho(self, on: bool = True):
        """
        ISP echos host when enabled
        """
        command = f"A {on : d}"
        response_code = self._write_command(command)
        _raise_return_code_error(response_code, "Set Echo")
        self.echo_on = on

    def WriteToRam(self, start: int, data: bytes):
        """
        Send command
        Receive command success
        The data sheet claims a verification string is sent at the end
        of a transfer but it does not.
        """
        assert len(data) % self.kWordSize == 0
        function_name = "Write to RAM"
        _log.debug("%s %d bytes", function_name, len(data))

        # when transfer is complete the handler sends OK<CR><LF>
        response_code = self._write_command(f"W {start} {len(data)}")
        _raise_return_code_error(response_code, function_name)
        self._write(data)  # Stream data after confirmation
        # Ignore response, it's not reliable
        # self._write(bytes(self.kNewLine, "utf-8"))  # end the data stream with normal line termination
        # response = self._read_line()
        # _log.debug(response)
        # if self.SyncVerifiedString.strip() not in response:
        #     _log.error(f"Expected {self.SyncVerifiedString}, received {response}. No confirmation from {function_name}")

    @timeout(10)
    def ReadMemory(self, start: int, num_bytes: int):
        """
        Send command with newline, receive response code\r\n<data>
        """
        assert num_bytes % self.kWordSize == 0  #  On a word boundary
        function = "ReadMemory"
        command = f"R {start} {num_bytes}"

        msg = f"{function} {command}"
        _log.info(msg)

        response_code = self._write_command(command)
        _raise_return_code_error(response_code, function)

        while len(self.data_buffer_in) < num_bytes:
            _log.debug(
                f"{function}: bytes in {len(self.data_buffer_in)}/{num_bytes}"
            )
            time.sleep(0.1)
            self._read()
        # Command success is sent at the end of the transferr
        data = []
        while self.data_buffer_in:
            ch = self.data_buffer_in.popleft()
            data.append(ch)

        if len(data) != num_bytes:
            _log.error(f"{data}, {len(data)}, {num_bytes}")
        assert len(data) == num_bytes
        return bytes(data)

    def PrepSectorsForWrite(self, start: int, end: int):
        command = f"P {start} {end}"
        response_code = tools.retry(self._write_command, count=5)(command)
        _raise_return_code_error(response_code, "Prep Sectors")

    def CopyRAMToFlash(self, flash_address: int, ram_address: int, num_bytes: int):
        response_code = self._write_command(
            f"C {flash_address} {ram_address} {num_bytes}"
        )
        _raise_return_code_error(response_code, "Copy RAM To Flash")
        # time.sleep(.2)

    def Go(self, address: int, thumb_mode: bool = False):
        """
        Start executing code at the specified spot. Should not
        expect a response back.
        """
        mode = ""
        if thumb_mode:
            mode = "T"
        response_code = self._write_command(f"G {address} {mode}")
        if (
            response_code != self.ReturnCodes["NoStatusResponse"]
        ):  #  Don't expect a response code from this
            _raise_return_code_error(response_code, "Go")

    def EraseSector(self, start: int, end: int):
        response_code = self._write_command(f"E {start} {end}")
        _raise_return_code_error(response_code, "Erase Sectors")

    def ErasePages(self, start: int, end: int):
        response_code = self._write_command(f"X {start} {end}")
        _raise_return_code_error(response_code, "Erase Pages")

    def CheckSectorsBlank(self, start: int, end: int) -> bool:
        """
        Raises user warning if the command fails
        """
        assert start <= end
        response_code = self._write_command(f"I {start} {end}")
        if response_code == 8:
            try:
                response = self._read_line()
                response = self._read_line()
                _log.debug(f"Check Sectors Blank response: {response}")
            except timeout_decorator.TimeoutError:
                pass

        if response_code not in (
            NXPReturnCodes["CMD_SUCCESS"],
            NXPReturnCodes["SECTOR_NOT_BLANK"],
        ):
            _raise_return_code_error(response_code, "Blank Check Sectors")
        return _return_code_success(response_code)

    def ReadPartID(self) -> int:
        """
        Throws no exception
        """
        response_code = self._write_command("J")
        _raise_return_code_error(response_code, "Read Part ID")

        resp = tools.retry(
            self._read_line,
            count=1,
            exception=timeout_decorator.TimeoutError,
            raise_on_fail=False,
        )()
        with contextlib.suppress(TypeError):
            return int(resp)
        return 0

    def ReadBootCodeVersion(self):
        """
        LPC84x sends a 0x1a first for some reason.
        Also the boot version seems to be Minor then Major not like the docs say
        """
        response_code = self._write_command("K")
        _raise_return_code_error(response_code, "Read Bootcode Version")
        minor = 0
        major = 0

        try:
            minor = self._read_line().strip()
            major = self._read_line().strip()
        except timeout_decorator.TimeoutError:
            pass
        return f"{major}.{minor}"

    def MemoryLocationsEqual(
        self, address1: int, address2: int, num_bytes: int
    ) -> bool:
        """
        Checks to see if two sections in the memory map are equal.
        Raises a user warning if the command fails
        """
        command = f"M {address1} {address2} {num_bytes} {self.kNewLine}"
        self._write(bytes(command, encoding="utf-8"))
        response_code = self._get_return_code(command)
        if response_code not in (
            NXPReturnCodes["CMD_SUCCESS"],
            NXPReturnCodes["COMPARE_ERROR"],
        ):
            _raise_return_code_error(response_code, "Compare")

        if response_code == NXPReturnCodes["COMPARE_ERROR"]:
            # Will return first location of mismatched location if the response is COMPARE_ERROR
            try:
                _ = self._read_line()
                # discard the comparison
            except timeout_decorator.TimeoutError:
                pass
        return _return_code_success(response_code)

    def ReadUID(self):
        """
        Raises timeout exception
        """
        response_code = self._write_command("N")
        _raise_return_code_error(response_code, "Read UID")
        uuids = []
        for _ in range(4):
            uuids.append(self._read_line())
        return " ".join(["0x%08x" % int(uid) for uid in uuids])

    def ReadCRC(self, address: int, num_bytes: int) -> int:
        """
        Command echos the response then the value of the CRC
        """
        function = "Read CRC"
        command = f"S {address} {num_bytes}"

        self.reset()
        response_code = self._write_command(command)
        _raise_return_code_error(response_code, function)
        return int(self._read_line())

    def ReadFlashSig(
        self, start: int, end: int, wait_states: int = 2, mode: int = 0
    ) -> list[str]:
        assert start < end
        response_code = self._write_command(f"Z {start} {end} {wait_states} {mode}")
        _raise_return_code_error(response_code, "Read Flash Signature")
        sig = []
        nlines = 4
        for _ in range(nlines):
            sig.append(self._read_line())
        return sig

    def ReadWriteFAIM(self):
        response_code = self._write_command("O")
        _raise_return_code_error(response_code, "Read Write FAIM")

    def SetCrystalFrequency(self, frequency_khz: int):
        self._write(bytes(f"{frequency_khz} {self.kNewLine}", encoding="utf-8"))
        verified = False
        for _ in range(3):
            try:
                frame_in = self._read_line()  # Should be OK\r\n
                if self.SyncVerifiedString in frame_in:
                    verified = True
                    break
            except timeout_decorator.TimeoutError:
                pass
        if not verified:
            raise UserWarning("Verification Failure")

    def SyncConnection(self):
        """
        - A ? synchronizes the autobaud
        1. Send a ?
        2. Receive "Synchronized"
        3. Return "Synchronized"
        4. Recieve "OK"

        If the chip is started from reset this will work.
        If too many characters that are not a ? are received then the chip will need to be
        reset. If a couple garbage characters are picked then the chip will still sychronize if the
        serial buffer is overflowed. Therefore try sending a single '?' and checking for the response.
        Otherwise send another '?' at a time until a response comes back or n number of characters have
        been sent.
        """
        _log.info("Synchronizing")
        self.reset()
        sync_char = "?"
        # > ?\n
        self._write(bytes(sync_char, "utf-8"))
        byte_in = self.iodevice.read()
        if byte_in == sync_char:
            # already syncronized
            _log.info("Already synchronized")
            return

        try:
            frame_in = self._read_line()
        except timeout_decorator.TimeoutError:
            frame_in = tools.collection_to_string(self._get_data_buffer_contents())

        valid_response = self.SyncString.strip()[1:] in frame_in
        # < Synchronized\n
        _log.debug(
            f"Sync string comparison {repr(frame_in)}, {self.SyncString.strip()}, {valid_response}"
        )

        if not valid_response:
            _log.error("Syncronization Failure")
            raise UserWarning("Syncronization Failure")

        # self._flush()
        _log.debug(f"Echoing sync string, {repr(self.SyncStringBytes)}")
        time.sleep(0.1)
        self._write(self.SyncStringBytes)  # echo SyncString
        self.write_newline()
        self.write_newline()
        # > Synchronized\n
        frame_in = ""
        try:
            time.sleep(0.1)
            frame_in = self._read_line()
        except timeout_decorator.TimeoutError:
            frame_in = tools.collection_to_string(self._get_data_buffer_contents())

        _log.debug(f"{frame_in}")

        # Discard an additional OK sent by device

        self._write(bytes(self.kNewLine, encoding="utf-8"))
        time.sleep(0.1)
        try:
            frame_in = self._read_line()
        except timeout_decorator.TimeoutError:
            frame_in = tools.collection_to_string(self._get_data_buffer_contents())

        _log.debug(f"{frame_in}")

        if self.SyncVerifiedString.strip() not in frame_in:
            _log.error("Verification Failure")
            raise UserWarning("Verification Failure")
        _log.info("Syncronization Successful")

        self._write(bytes(self.kNewLine, encoding="utf-8"))
        self.reset()
        time.sleep(0.1)
        self._write(bytes("A 1" + self.kNewLine, encoding="utf-8"))
        # time.sleep(0.1)

        try:
            frame_in = self._read_line()
            _log.debug(frame_in)
            frame_in = self._read_line()
            _log.debug(frame_in)
        except timeout_decorator.TimeoutError:
            pass


class ChipDescription:
    """
    Wraps a chip description line and exposes it as a class
    """

    kWordSize = 4  #  32 bit
    kPageSizeBytes = 64
    SectorSizePages = 16
    CRCLocation = 0x000002FC
    CRCValues = {
        "NO_ISP": 0x4E697370,
        "CRP1": 0x12345678,
        "CRP2": 0x87654321,
        "CRP3": 0x43218765,
    }

    def __init__(self, descriptor: dict[str, str]):
        # for name in dict(descriptor):
        #    self.__setattr__(name, descriptor[name])

        self.RAMRange = descriptor.pop("RAMRange")
        self.FlashRange = descriptor.pop("FlashRange")
        self.RAMBufferSize = int(descriptor.pop("RAMBufferSize"))
        self.SectorCount: int = int(descriptor.pop("SectorCount"))
        self.RAMStartWrite: int = int(descriptor.pop("RAMStartWrite"))
        self.CrystalFrequency = 12000  # khz == 30MHz
        self.kCheckSumLocation = 7  # 0x0000001c

        assert self.RAMRange[0] > 0
        assert self.RAMRange[1] > self.RAMRange[0]

        assert self.FlashRange[1] > self.FlashRange[0]

        assert self.SectorCount > 0

    @property
    def MaxByteTransfer(self) -> int:
        return self.RAMBufferSize

    @property
    def sector_bytes(self):
        sector_bytes = self.SectorSizePages * self.kPageSizeBytes
        assert sector_bytes % self.kWordSize == 0
        if sector_bytes > self.MaxByteTransfer:
            raise UserWarning(f"Sector Bytes: {sector_bytes} / {self.MaxByteTransfer}")
        assert sector_bytes <= self.MaxByteTransfer
        return sector_bytes

    def FlashAddressLegal(self, address):
        return self.FlashRange[0] <= address <= self.FlashRange[1]

    def FlashRangeLegal(self, address, length):
        _log.debug(f"Flash range {self.FlashRange} {address} {length}")
        return (
            self.FlashAddressLegal(address)
            and self.FlashAddressLegal(address + length - 1)
            and length <= self.FlashRange[1] - self.FlashRange[0]
            and address % self.kPageSizeBytes == 0
        )

    def RamAddressLegal(self, address):
        return self.RAMRange[0] <= address <= self.RAMRange[1]

    def RamRangeLegal(self, address, length):
        return (
            self.RamAddressLegal(address)
            and self.RamAddressLegal(address + length - 1)
            and length <= self.RAMRange[1] - self.RAMRange[0]
            and address % self.kWordSize == 0
        )


# Script tools

assert (
    tools.calc_crc(bytes([0xFF] * 1024)) == 3090874356
)  #  Check the software crc algorithm


def RemoveBootableCheckSum(vector_table_loc: int, image: bytes) -> bytes:
    """
    Erases only the checksum, making the image invalid. The chip will reset into the ISP now.
    """
    kuint32_t_size = 4
    MakeBootable(vector_table_loc, image)
    image_list = list(image)
    for byte in range(kuint32_t_size):
        image_list[vector_table_loc * kuint32_t_size + byte] = 0
    return bytes(image_list)


def GetCheckSumedVectorTable(vector_table_loc: int, orig_image: bytes) -> bytes:
    # make this a valid image by inserting a checksum in the correct place
    vector_table_size = 8
    kuint32_t_size = 4

    # Make byte array into list of little endian 32 bit words
    intvecs = struct.unpack(
        "<%dI" % vector_table_size, orig_image[: vector_table_size * kuint32_t_size]
    )

    # calculate the checksum over the interrupt vectors
    intvecs_list = list(intvecs[:vector_table_size])
    intvecs_list[vector_table_loc] = 0  # clear csum value
    csum = tools.CalculateCheckSum(intvecs_list)
    intvecs_list[vector_table_loc] = csum
    vector_table_bytes = b""
    for vecval in intvecs_list:
        vector_table_bytes += struct.pack("<I", vecval)
    return vector_table_bytes


def MakeBootable(vector_table_loc: int, orig_image: bytes) -> bytes:
    vector_table_bytes = GetCheckSumedVectorTable(vector_table_loc, orig_image)

    image = vector_table_bytes + orig_image[len(vector_table_bytes) :]
    return image


def CheckFlashWrite(isp: ISPConnection, data, flash_address: int) -> bool:
    """
    Read Memory and compare it to what was written
    baud_rate"""

    data_read = isp.ReadMemory(flash_address, len(data))

    if len(data) != len(data_read):
        raise ValueError("Read Memory received incorrect amount of data")
    if isinstance(data_read, type(data)):
        raise TypeError("data written and data read are of different types")

    return data == data_read


def WriteFlashSector(
    isp: ISPConnection, chip: ChipDescription, sector: int, data: bytes
):
    """
    Safe way to write to flash sector.
    Basic approach:
    1. Write bytes to ram
    2. Prep sectors for writing
    3. Erase sector
    4. Prep sector again
    5. Copy RAM to flash

    To make this more robust we check that each step has completed successfully.
    After writing RAM check that the CRC matches the data in.
    After writing the Flash repeat the test
    """
    flash_write_sleep = 0.01
    ram_write_sleep = 0.01
    ram_address = chip.RAMStartWrite
    flash_address = chip.FlashRange[0] + sector * chip.sector_bytes
    _log.info(
        "\nWriting Sector: %d\tFlash Address: %x\tRAM Address: %x",
        sector,
        flash_address,
        ram_address,
    )

    assert len(data) == chip.sector_bytes
    # data += bytes(chip.sector_bytes - len(data))

    _log.debug("Calculate starting CRC")
    data_crc = tools.calc_crc(data)

    ram_crc_initial = isp.ReadCRC(ram_address, num_bytes=len(data))
    _log.debug("Starting CRC: %d", ram_crc_initial)

    _log.debug("Writing RAM %d", ram_address)
    assert chip.RamRangeLegal(ram_address, len(data))
    time.sleep(ram_write_sleep)
    isp.WriteToRam(ram_address, data)
    time.sleep(ram_write_sleep)
    isp.reset()
    time.sleep(ram_write_sleep)
    ram_crc = tools.retry(isp.ReadCRC, count=5, exception=(UserWarning, ValueError))(
        ram_address, num_bytes=len(data)
    )

    # ram_crc = isp.ReadCRC(ram_address, num_bytes=len(data))
    isp.reset()
    if data_crc == ram_crc:
        _log.debug(f"CRC Check successful {data_crc} {ram_crc}")
    else:
        _log.error(f"RAM CRC Check failed {data_crc} {ram_crc}")

    # Check to see if sector is already equal to RAM, if so skip
    ram_equal = isp.MemoryLocationsEqual(flash_address, ram_address, chip.sector_bytes)
    if ram_equal:
        _log.debug("Flash already equal to RAM, skipping write")
        return

    _log.debug("Prep Sector")
    isp.PrepSectorsForWrite(sector, sector)
    _log.debug("Erase Sector")
    isp.EraseSector(sector, sector)
    time.sleep(flash_write_sleep)
    assert isp.CheckSectorsBlank(sector, sector)

    _log.debug("Prep Sector")
    isp.PrepSectorsForWrite(sector, sector)

    _log.debug("Write to Flash")
    assert chip.RamRangeLegal(ram_address, chip.sector_bytes)
    assert chip.FlashRangeLegal(flash_address, chip.sector_bytes)

    isp.CopyRAMToFlash(flash_address, ram_address, chip.sector_bytes)
    time.sleep(flash_write_sleep)
    flash_crc = tools.retry(isp.ReadCRC, count=5, exception=[UserWarning])(
        flash_address, num_bytes=len(data)
    )
    # flash_crc = isp.ReadCRC()
    assert flash_crc == data_crc
    assert isp.MemoryLocationsEqual(flash_address, ram_address, chip.sector_bytes)


def WriteSector(isp: ISPConnection, chip: ChipDescription, sector: int, data: bytes):
    assert len(data) > 0

    if len(data) != chip.sector_bytes:  #  Fill data buffer to match write size
        data += bytes([0xFF] * (chip.sector_bytes - len(data)))
    WriteFlashSector(isp, chip, sector, data)

    # assert isp.ReadSector(sector) == data_chunk


def WriteBinaryToFlash(
    isp: ISPConnection,
    chip: ChipDescription,
    image: bytes,
    start_sector: int,
    flash_write_sleep: float = 0.05,
) -> int:
    """
    Take the image as bytes object. Break the image into sectors and write each in reverse order.
    On completion return the flash signature which cna be stored for validity checking
    """
    flash_write_sleep = 0.05
    assert isinstance(image, bytes)
    _log.info("Program Length: %d", len(image))

    sector_count = tools.calc_sector_count(image, chip.sector_bytes)
    if start_sector + sector_count > chip.SectorCount:
        _log.error(
            f"Invalid sector count\t Start: {start_sector}\tCount: {sector_count}\tEnd: {chip.SectorCount}"
        )
        return 1
    isp.Unlock()
    for sector in reversed(range(start_sector, start_sector + sector_count)):
        _log.info(f"\nWriting Sector {sector} / {sector_count}")
        data_chunk = image[
            (sector - start_sector) * chip.sector_bytes : (sector - start_sector + 1)
            * chip.sector_bytes
        ]
        WriteSector(isp, chip, sector, data_chunk)
        time.sleep(flash_write_sleep)

    assert chip.FlashAddressLegal(chip.FlashRange[0]) and chip.FlashAddressLegal(
        chip.FlashRange[1]
    )
    """  Flash signature reading is only supported for some chips and is partially impimented for others.
    time.sleep(0.5)
    chip_flash_sig = isp.ReadFlashSig(chip.FlashRange[0], chip.FlashRange[1])
    _log.info(f"Flash Signature: {chip_flash_sig}")
    _log.info("Programming Complete.")
    return chip_flash_sig
    """
    return 0


def WriteImage(
    isp: ISPConnection,
    chip: ChipDescription,
    imagein: bytes,
    flash_write_sleep: float = 0.05,
):
    """
    1. Overwrite first sector which clears the checksum bytes making the image unbootable, preventing bricking
    2. Read the binary file into memory as a bytes object
    3. Write the checksum to the image
    4. Write the image in reverse order, the checksum will only be written once the entire valid image is written
    """
    # make not bootable
    isp.Unlock()
    WriteSector(isp, chip, 0, bytes([0xDE] * chip.sector_bytes))

    # image = RemoveBootableCheckSum(chip.kCheckSumLocation, prog)
    image = MakeBootable(chip.kCheckSumLocation, imagein)
    WriteBinaryToFlash(
        isp, chip, image, start_sector=0, flash_write_sleep=flash_write_sleep
    )


def FindFirstBlankSector(isp: ISPConnection, chip) -> int:
    """
    Returns the first blank sector, returns the last sector on failure
    """
    for sector in range(chip.SectorCount):
        sector_blank = isp.CheckSectorsBlank(sector, chip.SectorCount - 1)
        _log.debug("Sector %d Blank: %d", sector, sector_blank)
        if sector_blank:
            return sector
    return chip.SectorCount - 1


def ReadSector(isp: ISPConnection, chip: ChipDescription, sector: int) -> bytes:
    start = sector * chip.sector_bytes
    assert chip.FlashRangeLegal(start, chip.sector_bytes)
    return isp.ReadMemory(start, chip.sector_bytes)


def ReadImage(isp: ISPConnection, chip: ChipDescription) -> bytes:
    image = bytes()
    blank_sector = FindFirstBlankSector(isp, chip)
    _log.debug("First Blank Sector %d", blank_sector)
    sectors: list[bytes] = []
    for nsector in range(blank_sector):
        _log.debug("Sector %d", nsector)
        sector: bytes = ReadSector(isp, chip, nsector)
        sectors.append(sector)

    return image.join(sectors)


def MassErase(isp: ISPConnection, chip: ChipDescription):
    last_sector = chip.SectorCount - 1
    isp.reset()
    isp.Unlock()
    isp.PrepSectorsForWrite(0, last_sector)
    isp.EraseSector(0, last_sector)


def SetupChip(
    baudrate: int,
    device: str,
    crystal_frequency: int,
    chip_file: str,
    no_sync: bool = False,
    sleep_time: float = 1,
    serial_sleep: float = 0,
):
    """
    :param int baudrate: The baudrate to set or use. If no_sync is True this baudrate is assumed to already be set
    :param str device: Serial port
    :param float crystal_frequency: On board oscillator
    :param str chip_file: Alternate file to find chip settings
    :param bool no_sync: Whether or not to synchronize the channel on start
    :param float sleep_time: Time between operations
    :param float serial_sleep: Time between serial commands
    :return ISPConnection isp: an already opened link to an isp device
    :return ChipDescription chip: object describing the targets characteristics

    + Opens UART
    + Makes an ISPConnection instance
    + Tries to sync the connection
    + Sets the baudrate
    + Reads the chip ID and returns the matching chip description
    """

    if no_sync:
        kStartingBaudRate = baudrate
    else:
        kStartingBaudRate = BAUDRATES[0]

    _log.debug("Using baud rate %d", kStartingBaudRate)
    iodevice: UartDevice = UartDevice(device, baudrate=kStartingBaudRate)
    isp = ISPConnection(iodevice)
    isp.serial_sleep = serial_sleep
    isp.return_code_sleep = sleep_time
    isp.reset()
    # print(baudrate, device, crystal_frequency, chip_file)

    if not no_sync:
        isp.SyncConnection()

    isp.SetBaudRate(baudrate)
    isp.baud_rate = baudrate
    time.sleep(max(0.1, sleep_time))
    time.sleep(max(0.1, sleep_time))
    isp.reset()
    part_id = isp.ReadPartID()

    descriptor: dict[str, str] = GetPartDescriptor(chip_file, part_id)
    _log.debug(f"{part_id}, {descriptor}")
    chip = ChipDescription(descriptor)
    chip.CrystalFrequency = crystal_frequency

    _log.debug("Setting new baudrate %d" % baudrate)
    isp.SetBaudRate(baudrate)  # set the chips baudrate
    isp.baud_rate = baudrate  # change the driver baudrate
    return isp, chip


def read_image_file_to_bin(image_file: str):
    extension = os.path.splitext(image_file)[-1].lstrip(".").lower()
    ih = IntelHex()
    ih.fromfile(image_file, format=extension)
    return ih.tobinarray()
