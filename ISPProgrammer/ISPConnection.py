import time
import logging
from typing import List, Deque
from collections import deque
import timeout_decorator
from timeout_decorator import timeout
from . import IODevice
from .tools import retry
from . import tools

kTimeout = 5

BAUDRATES = (
    9600,
    19200,
    38400,
    57600,
    115200,
    230400,
    460800
)

NXPReturnCodes = {
    "CMD_SUCCESS"                               : 0x0,
    "INVALID_COMMAND"                           : 0x1,
    "SRC_ADDR_ERROR"                            : 0x2,
    "DST_ADDR_ERROR"                            : 0x3,
    "SRC_ADDR_NOT_MAPPED"                       : 0x4,
    "DST_ADDR_NOT_MAPPED"                       : 0x5,
    "COUNT_ERROR"                               : 0x6,
    "INVALID_SECTOR/INVALID_PAGE"               : 0x7,
    "SECTOR_NOT_BLANK"                          : 0x8,
    "SECTOR_NOT_PREPARED_FOR_WRITE_OPERATION"   : 0x9,
    "COMPARE_ERROR"                             : 0xa,
    "BUSY"                                      : 0xb,
    "PARAM_ERROR"                               : 0xc,
    "ADDR_ERROR"                                : 0xd,
    "ADDR_NOT_MAPPED"                           : 0xe,
    "CMD_LOCKED"                                : 0xf,
    "INVALID_CODE"                              : 0x10,
    "INVALID_BAUD_RATE"                         : 0x11,
    "INVALID_STOP_BIT"                          : 0x12,
    "CODE_READ_PROTECTION_ENABLED"              : 0x13,
    "Unused 1"                                  : 0x14,
    "USER_CODE_CHECKSUM"                        : 0x15,
    "Unused 2"                                  : 0x16,
    "EFRO_NO_POWER"                             : 0x17,
    "FLASH_NO_POWER"                            : 0x18,
    "Unused 3"                                  : 0x19,
    "Unused 4"                                  : 0x1a,
    "FLASH_NO_CLOCK"                            : 0x1b,
    "REINVOKE_ISP_CONFIG"                       : 0x1c,
    "NO_VALID_IMAGE"                            : 0x1d,
    "FAIM_NO_POWER"                             : 0x1e,
    "FAIM_NO_CLOCK"                             : 0x1f,
    "NoStatusResponse"                          : 0xff,
}


def GetErrorCodeName(code: int) -> str:
    code = int(code)
    for item in NXPReturnCodes.items():
        if code == item[1]:
            return item[0]
    return f"Not Found: {code}"

def return_code_success(code: int) -> bool:
    return int(code) == NXPReturnCodes["CMD_SUCCESS"]

def RaiseReturnCodeError(code: int, call_name: str) -> None:
    '''
    Each command returns a code, check if the code is a success, throws a UserWarning if not
    '''
    if not return_code_success(code):
        raise UserWarning(
            f"Return Code Failure in {call_name} {GetErrorCodeName(code)} {code}")



class ISPConnection:
    '''
    ISPConnection abstracts the interface to the chip, wrapping all responses and ensuring a reliable connection
    '''
    kNewLine = "\r\n"
    _serial_sleep = 10e-3
    _return_code_sleep = 0.05
    StatusRespLength = len(kNewLine) + 1
    kWordSize = 4  #  32 bit device
    #Parity = None
    #DataBits = 8
    #StopBits = 1
    SyncString = f"Synchronized{kNewLine}"
    SyncStringBytes = bytes(SyncString, encoding="utf-8")
    SyncVerifiedString = f"OK{kNewLine}"
    # SyncVerifiedBytes = bytes(SyncVerifiedString, encoding="utf-8")
    ReturnCodes = NXPReturnCodes

    def __init__(self, iodevice: IODevice):
        self.iodevice = iodevice
        self.data_buffer_in : Deque[int] = deque()
        self.echo_on = True

    @property
    def baud_rate(self):
        return self.iodevice.GetBaudrate()

    @baud_rate.setter
    def baud_rate(self, baudrate: int):
        self.iodevice.SetBaudrate(baudrate)

    def _write_serial(self, out: bytes) -> None:
        time.sleep(self._serial_sleep)
        assert isinstance(out, bytes)
        self.iodevice.Write(out)
        time.sleep(self._serial_sleep)
        logging.log(logging.DEBUG-1, f"Write: [{out}]")

    def _flush(self):
        self.iodevice.Flush()

    @timeout(kTimeout)
    def _read_line(self) -> str:
        '''
        Read until a new line is found.
        Timesout if no data pulled
        '''
        line = self.iodevice.ReadLine()
        return line

    def _get_data_buffer_contents(self):
        return list(self.data_buffer_in)

    def _clear_buffer(self):
        self.data_buffer_in.clear()

    def _read(self):
        '''
        Reads input buffer and stores in buffer
        '''
        data_in = self.iodevice.ReadAll()
        dstr = bytes("".join([chr(ch) for ch in data_in]), "utf-8")
        if data_in:
            logging.log(logging.DEBUG-1, f"_read: <{dstr}>")
        self.data_buffer_in.extend(data_in)

    def _clear_serial(self):
        for _ in range(2):
            retry(self._read, count=10, exception=timeout_decorator.TimeoutError, raise_on_fail=False)()
            self._clear_buffer()
            self._flush()

    def reset(self):
        self._clear_serial()

    def _get_return_code(self) -> int:
        '''
        No exceptions are thrown.
        '''
        time.sleep(self._return_code_sleep)
        try:
            resp = self._read_line()
            if self.echo_on:  # discard echo
                resp = self._read_line()
        except timeout_decorator.TimeoutError:
            self._write(bytes(self.kNewLine, encoding="utf-8"))
            return self.ReturnCodes["NoStatusResponse"]
        return int(resp.strip())

    def _write(self, string : bytes) -> None:
        logging.debug(string)
        assert isinstance(string, bytes)
        self._write_serial(string)
        # self._write_serial(bytes(self.kNewLine, encoding = "utf-8"))

    def _write_command(self, command_string: str) -> int:
        '''
        Takes the command string, return the response code
        '''
        self._write(bytes(command_string + self.kNewLine, encoding="utf-8"))
        return self._get_return_code()

    def Unlock(self):
        '''
        Enables Flash Write, Erase, & Go
        '''
        response_code = self._write_command("U 23130")
        RaiseReturnCodeError(response_code, "Unlock")

    def SetBaudRate(self, baud_rate: int, stop_bits: int = 1):
        '''
        Baud Depends of FAIM config, stopbit is 1 or 2
        '''
        response_code = self._write_command(f"B {baud_rate} {stop_bits}")
        RaiseReturnCodeError(response_code, "Set Baudrate")

    def SetEcho(self, on: bool = True):
        '''
        ISP echos host when enabled
        '''
        command = f"A {on : d}"
        response_code = self._write_command(command)
        RaiseReturnCodeError(response_code, "Set Echo")
        self.echo_on = on

    def WriteToRam(self, start: int, data: bytes):
        '''
        Send command
        Receive command success
        The data sheet claims a verification string is sent at the end
        of a transfer but it does not.
        '''
        assert len(data)%self.kWordSize == 0
        function_name = "Write to RAM"
        logging.info(f"{function_name} {len(data)} bytes")

        #when transfer is complete the handler sends OK<CR><LF>
        response_code = self._write_command(f"W {start} {len(data)}")
        RaiseReturnCodeError(response_code, function_name)
        self._write(data)  # Stream data after confirmation
        # Ignore response, it's not reliable
        # self._write(bytes(self.kNewLine, "utf-8"))  # end the data stream with normal line termination
        # response = self._read_line()
        # logging.debug(response)
        # if self.SyncVerifiedString.strip() not in response:
        #     logging.error(f"Expected {self.SyncVerifiedString}, received {response}. No confirmation from {function_name}")

    @timeout(10)
    def ReadMemory(self, start: int, num_bytes: int):
        '''
        Send command with newline, receive response code\r\n<data>
        '''
        assert num_bytes%self.kWordSize == 0  #  On a word boundary
        function = "ReadMemory"
        logging.info(function)

        command = f"R {start} {num_bytes}"
        logging.info(command)
        response_code = self._write_command(command)
        RaiseReturnCodeError(response_code, function)

        while len(self.data_buffer_in) < num_bytes:
            logging.debug(f"{function}: bytes in {len(self.data_buffer_in)}/{num_bytes}")
            time.sleep(0.1)
            self._read()
        # Command success is sent at the end of the transferr
        data = []
        while self.data_buffer_in:
            ch = self.data_buffer_in.popleft()
            data.append(ch)

        if len(data) != num_bytes:
            logging.debug(f"{data}, {len(data)}, {num_bytes}")
        assert len(data) == num_bytes
        return bytes(data)

    def PrepSectorsForWrite(self, start: int, end: int):
        command = f"P {start} {end}"
        response_code = retry(self._write_command, count=5)(command)
        RaiseReturnCodeError(response_code, "Prep Sectors")

    def CopyRAMToFlash(self, flash_address: int, ram_address: int, num_bytes: int):
        response_code = self._write_command(f"C {flash_address} {ram_address} {num_bytes}")
        RaiseReturnCodeError(response_code, "Copy RAM To Flash")
        # time.sleep(.2)

    def Go(self, address: int, thumb_mode: bool = False):
        '''
        Start executing code at the specified spot. Should not
        expect a response back.
        '''
        mode = ""
        if thumb_mode:
            mode = 'T'
        response_code = self._write_command(f"G {address} {mode}")
        if response_code != self.ReturnCodes["NoStatusResponse"]:  #  Don't expect a response code from this
            RaiseReturnCodeError(response_code, "Go")

    def EraseSector(self, start: int, end: int):
        response_code = self._write_command(f"E {start} {end}")
        RaiseReturnCodeError(response_code, "Erase Sectors")

    def ErasePages(self, start: int, end: int):
        response_code = self._write_command(f"X {start} {end}")
        RaiseReturnCodeError(response_code, "Erase Pages")

    def CheckSectorsBlank(self, start: int, end: int) -> bool:
        '''
        Raises user warning if the command fails
        '''
        assert start <= end
        response_code = self._write_command(f"I {start} {end}")
        try:
            #self._read_line()  #  throw away echo ?
            response = self._read_line()
            logging.info(f"Check Sectors Blank response: {response}")
        except timeout_decorator.TimeoutError:
            pass

        if response_code not in (NXPReturnCodes["CMD_SUCCESS"], NXPReturnCodes["SECTOR_NOT_BLANK"]):
            RaiseReturnCodeError(response_code, "Blank Check Sectors")
        return return_code_success(response_code)

    def ReadPartID(self) -> str:
        '''
        Throws no exception
        '''
        response_code = self._write_command("J")
        RaiseReturnCodeError(response_code, "Read Part ID")

        resp = retry(self._read_line, count=1, exception=timeout_decorator.TimeoutError, raise_on_fail=False)()
        try:
            return int(resp) # handle none type passed
        except ValueError:
            pass
        return resp

    def ReadBootCodeVersion(self):
        '''
        LPC84x sends a 0x1a first for some reason.
        Also the boot version seems to be Minor then Major not like the docs say
        '''
        response_code = self._write_command("K")
        RaiseReturnCodeError(response_code, "Read Bootcode Version")
        minor = 0
        major = 0

        try:
            minor = self._read_line()
            major = self._read_line()
        except timeout_decorator.TimeoutError:
            pass
        return f"{major}.{minor}"

    def MemoryLocationsEqual(self, address1: int, address2: int, num_bytes: int) -> bool:
        '''
        Checks to see if two sections in the memory map are equal.
        Raises a user warning if the command fails
        '''
        command = f"M {address1} {address2} {num_bytes} {self.kNewLine}"
        self._write(bytes(command, encoding="utf-8"))
        response_code = self._get_return_code()
        if response_code not in (NXPReturnCodes["CMD_SUCCESS"], NXPReturnCodes["COMPARE_ERROR"]):
            RaiseReturnCodeError(response_code, "Compare")

        if response_code == NXPReturnCodes["COMPARE_ERROR"]:
        # Will return first location of mismatched location if the response is COMPARE_ERROR
            try:
                _ = self._read_line()
                # discard the comparison
            except timeout_decorator.TimeoutError:
                pass
        return return_code_success(response_code)

    def ReadUID(self):
        '''
        Raises timeout exception
        '''
        response_code = self._write_command("N")
        RaiseReturnCodeError(response_code, "Read UID")
        uuids = []
        for _ in range(4):
            uuids.append(self._read_line())
        return " ".join(["0x%08x"%int(uid) for uid in uuids])

    def ReadCRC(self, address: int, num_bytes: int) -> int:
        '''
        Command echos the response then the value of the CRC
        '''
        function = "Read CRC"
        command = f"S {address} {num_bytes}"

        crc_sleep = 0.01
        response_code = self._write_command(command)
        RaiseReturnCodeError(response_code, function)
        return int(self._read_line())

    def ReadFlashSig(self, start: int, end: int, wait_states: int = 2, mode: int = 0) -> str:
        assert start < end
        response_code = self._write_command(f"Z {start} {end} {wait_states} {mode}")
        RaiseReturnCodeError(response_code, "Read Flash Signature")
        sig = []
        nlines = 4
        for _ in range(nlines):
            sig.append(self._read_line())
        return sig

    def ReadWriteFAIM(self):
        response_code = self._write_command("O")
        RaiseReturnCodeError(response_code, "Read Write FAIM")

    def SetCrystalFrequency(self, frequency_khz: int):
        self._write(bytes(f"{frequency_khz} {self.kNewLine}" , encoding="utf-8"))
        verified = False
        for _ in range(3):
            try:
                frame_in = self._read_line()#Should be OK\r\n
                if self.SyncVerifiedString in frame_in:
                    verified = True
                    break
            except timeout_decorator.TimeoutError:
                pass
        if not verified:
            raise UserWarning("Verification Failure")

    def SyncConnection(self):
        '''
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
        '''
        synced = False
        self.reset()
        sync_char = '?'
        # > ?\n
        self._write(bytes(sync_char, "utf-8"))
        frame_in = ""
        time.sleep(0.1)
        try:
            frame_in = self._read_line()
        except timeout_decorator.TimeoutError:
            frame_in = tools.collection_to_string(self._get_data_buffer_contents())

        valid_response = self.SyncString.strip() in frame_in
        # < Synchronized\n
        logging.debug(f"{frame_in}, {self.SyncString.strip()}, {valid_response}")

        if not valid_response:
            if len(frame_in) > 0 and (frame_in[0] == sync_char):  #  Already synced
                pass
            else:
                raise UserWarning("Syncronization Failure")

        #self._flush()
        frame_in = ""
        self._write(self.SyncStringBytes)#echo SyncString
        # > Synchronized\n
        try:
            time.sleep(0.1)
            frame_in = self._read_line()
        except timeout_decorator.TimeoutError:
            pass

        # Discard an additional OK sent by device

        self._write(bytes(self.kNewLine, encoding="utf-8"))
        try:
            frame_in = self._read_line()
        except timeout_decorator.TimeoutError:
            pass

        if not(self.SyncVerifiedString.strip() in frame_in):
            raise UserWarning("Verification Failure")
        logging.info("Syncronization Successful")

        time.sleep(0.1)
        self._write(bytes("A 1"+self.kNewLine, encoding="utf-8"))
        time.sleep(0.1)

        try:
            frame_in = self._read_line()
            print(frame_in)
            frame_in = self._read_line()
            print(frame_in)
        except timeout_decorator.TimeoutError:
            pass
