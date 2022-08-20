import logging
import math
import zlib
from time import sleep
import struct
from typing import List, Deque
from collections import deque
import timeout_decorator
from timeout_decorator import timeout
from pycrc.algorithms import Crc
import functools
try:
    from IODevices import IODevice
except ImportError:
    try:
        from . import IODevice
    except ImportError:
        pass
kTimeout = 1

def retry(_func=None, *, count=2, exception=timeout_decorator.TimeoutError, raise_on_fail=True):
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            value = None
            for i in range(1, count+1):    
                try:
                    assert func
                    value = func(*args, **kwargs)
                    break
                except exception as e:
                    logging.warning(f"{e}: Retry {i}/{count}")
                    if i >= count and raise_on_fail:
                        raise UserWarning(f"{_func} retry exceeded {count}")
            return value
        return wrapper
    if _func is None:
        return decorator
    return decorator(_func) 

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


def RemoveBootableCheckSum(vector_table_loc: int, image: bytes) -> bytes:
    '''
    Erases only the checksum, making the image invalid. The chip will reset into the ISP now.
    '''
    kuint32_t_size = 4
    MakeBootable(vector_table_loc, image)
    image_list = list(image)
    for byte in range(kuint32_t_size):
        image_list[vector_table_loc * kuint32_t_size + byte] = 0
    return bytes(image_list)


# 2s compliment of checksum
def CalculateCheckSum(frame) -> int:
    csum = 0
    for entry in frame:
        csum += entry
    return (1<<32) - (csum % (1<<32))


def Crc32(frame: bytes) -> int:
    #CRC32
    polynomial = 0x104c11db6
    crc = Crc(width=32, poly=polynomial, reflect_in=True,
              xor_in=(1<<32)-1, reflect_out=True, xor_out=0x00)
    crc_calc = crc.bit_by_bit(frame)
    return crc_calc

def calc_crc(frame: bytes):
    return zlib.crc32(frame, 0)
    #return Crc32(frame)

def GetCheckSumedVectorTable(vector_table_loc: int, orig_image: bytes) -> bytes:
    # make this a valid image by inserting a checksum in the correct place
    vector_table_size = 8
    kuint32_t_size = 4

    # Make byte array into list of little endian 32 bit words
    intvecs = struct.unpack("<%dI"%vector_table_size,
                            orig_image[:vector_table_size * kuint32_t_size])

    # calculate the checksum over the interrupt vectors
    intvecs_list = list(intvecs[:vector_table_size])
    intvecs_list[vector_table_loc] = 0 # clear csum value
    csum = CalculateCheckSum(intvecs_list)
    intvecs_list[vector_table_loc] = csum
    vector_table_bytes = b''
    for vecval in intvecs_list:
        vector_table_bytes += struct.pack("<I", vecval)
    return vector_table_bytes


def MakeBootable(vector_table_loc: int, orig_image: bytes) -> bytes:
    vector_table_bytes = GetCheckSumedVectorTable(vector_table_loc, orig_image)

    image = vector_table_bytes + orig_image[len(vector_table_bytes):]
    return image


def FillDataToFitSector(data: bytes, size: int) -> bytes:
    if len(data) != size:
        data += bytes([0xff] *(size - len(data)))
    return data

def collection_to_string(arr):
    return "".join([chr(ch) for ch in arr])

class ISPChip:
    '''Generic ISP chip'''
    kNewLine = "\r\n"
    _echo = False
    _serial_sleep = 10e-3
    _return_code_sleep = 0.05

    @classmethod
    def SetEcho(cls, enable):
        cls._echo = enable

    @classmethod
    def GetEcho(cls):
        return cls._echo

    def __init__(self, iodevice: IODevice):
        self.iodevice = iodevice
        self.frame : List[int] = []
        self.data_buffer_in : Deque[int] = deque()

    @property
    def baud_rate(self):
        return self.iodevice.GetBaudrate()

    def ChangeBaudRate(self, baudrate: int):
        self.iodevice.SetBaudrate(baudrate)

    def WriteSerial(self, out: bytes) -> None:
        sleep(self._serial_sleep)
        assert isinstance(out, bytes)
        self.iodevice.Write(out)
        sleep(self._serial_sleep)
        if self.GetEcho():
            logging.info(f"Write: [{out}]")
        else:
            logging.log(logging.DEBUG-1, f"Write: [{out}]")

    def Flush(self):
        self.iodevice.Flush()

    @timeout(kTimeout)
    def ReadLine(self) -> str:
        '''
        Read until a new line is found.
        Timesout if no data pulled
        '''
        cnt = 0
        while not self.ReadFrame():
            self.Read()
        line = collection_to_string(self.frame).strip()
        logging.debug(f"ReadLine: [{line}]")
        self.frame.clear()
        assert isinstance(line, str)
        return line

    #def Write(self, *args, **kwargs):
    #    raise NotImplementedError

    def get_data_buffer_contents(self):
        return list(self.data_buffer_in)

    def ClearBuffer(self):
        self.data_buffer_in.clear()
        self.frame.clear()

    def Read(self):
        '''
        Reads input buffer and stores in buffer
        '''
        data_in = self.iodevice.ReadAll()
        dstr = bytes("".join([chr(ch) for ch in data_in]), "utf-8")
        if data_in:
            if self.GetEcho():
                logging.info(f"Read: <{dstr}>")
            else:
                logging.log(logging.DEBUG-1, f"Read: <{dstr}>")
        self.data_buffer_in.extend(data_in)

    def ReadFrame(self):
        '''
        Reads from the stored character buffer, pushing characters to a list
        searching for a delimiting character.
        Pushes the list of characters to a buffer.
        Exits when a frame object is created
        '''
        f_new_frame = False

        while len(self.data_buffer_in) != 0:
            ch = self.data_buffer_in.popleft()
            #logging.debug(hex(ch), chr(ch))
            self.frame.append(ch)
            if chr(ch) == self.kNewLine[-1]:
                #logging.debug("New Frame")
                f_new_frame = True
                break
        return f_new_frame

    def Check(self, *args, **kwargs):
        raise NotImplementedError

    def InitConnection(self):
        raise NotImplementedError


class NXPChip(ISPChip):
    kWordSize = 4  #  32 bit
    kPageSizeBytes = 64
    SectorSizePages = 16
    MaxByteTransfer = 1024
    StatusRespLength = len(ISPChip.kNewLine) + 1
    #Parity = None
    #DataBits = 8
    #StopBits = 1
    SyncString = f"Synchronized{ISPChip.kNewLine}"
    SyncStringBytes = bytes(SyncString, encoding="utf-8")
    SyncVerifiedString = f"OK{ISPChip.kNewLine}"
    # SyncVerifiedBytes = bytes(SyncVerifiedString, encoding="utf-8")
    ReturnCodes = NXPReturnCodes
    CRCLocation = 0x000002fc
    
    _crc_sleep = 0.1

    CRCValues = {
        "NO_ISP": 0x4e697370,
        "CRP1" : 0x12345678,
        "CRP2" : 0x87654321,
        "CRP3" : 0x43218765,
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.CrystalFrequency = 12000#khz == 30MHz
        self.SectorCount = 0
        self.RAMSize = 0
        self.RAMRange = [0, 0]
        self.FlashRange = [0, 0]
        self.RAMStartWrite = 0
        self.kCheckSumLocation = 7  # 0x0000001c
        assert calc_crc(bytes([0xff]*1024)) == 3090874356  #  Check the software crc algorithm

    @property
    def sector_bytes(self):
        sector_bytes = self.SectorSizePages*self.kPageSizeBytes
        assert sector_bytes%self.kWordSize == 0
        return sector_bytes

    def FlashAddressLegal(self, address):
        return (self.FlashRange[0] <= address <= self.FlashRange[1])

    def FlashRangeLegal(self, address, length):
        logging.info(f"Flash range {self.FlashRange} {address} {length}")
        return self.FlashAddressLegal(address) and\
            self.FlashAddressLegal(address + length - 1) and\
            length <= self.FlashRange[1] - self.FlashRange[0] and\
            address%self.kPageSizeBytes == 0

    def RamAddressLegal(self, address):
        return self.RAMRange[0] <= address <= self.RAMRange[1]

    def RamRangeLegal(self, address, length):
        return self.RamAddressLegal(address) and\
            self.RamAddressLegal(address + length - 1) and\
            length <= self.RAMRange[1] - self.RAMRange[0] and\
            address%self.kWordSize == 0

    @retry(count=5)
    def GetReturnCode(self) -> int:
        '''
        No exceptions are thrown.
        '''
        for _ in range(3):
            sleep(self._return_code_sleep)
            try:
                resp = retry(self.ReadLine, count=2, exception=timeout_decorator.TimeoutError, raise_on_fail=False)()
                return int(resp)
            except (TypeError, ValueError):
                self.Write(bytes(self.kNewLine, encoding="utf-8"))
                pass
        return self.ReturnCodes["NoStatusResponse"]

    def Write(self, string : bytes) -> None:
        logging.debug(string)
        assert isinstance(string, bytes)
        self.WriteSerial(string)
        # self.WriteSerial(bytes(self.kNewLine, encoding = "utf-8"))


    def WriteCommand(self, command_string: str) -> int:
        '''
        Takes the command string, return the response code
        '''
        self.Write(bytes(command_string + self.kNewLine, encoding="utf-8"))
        return self.GetReturnCode()

    def Unlock(self):
        '''
        Enables Flash Write, Erase, & Go
        '''
        response_code = self.WriteCommand("U 23130")
        RaiseReturnCodeError(response_code, "Unlock")

    def SetBaudRate(self, baud_rate: int, stop_bits: int = 1):
        '''
        Baud Depends of FAIM config, stopbit is 1 or 2
        '''
        response_code = self.WriteCommand(f"B {baud_rate} {stop_bits}")
        RaiseReturnCodeError(response_code, "Set Baudrate")

    def Echo(self, on: bool = True):
        '''
        ISP echos host when enabled
        '''
        if on:
            command = "A 1"
        else:
            command = "A 0"
        response_code = self.WriteCommand(command)
        RaiseReturnCodeError(response_code, "Set Echo")

    def WriteToRam(self, start: int, data: bytes):
        '''
        Send command
        Receive command success
        The data sheet claims a verification string is sent at the end
        of a transfer but it does not.
        '''
        assert len(data)%self.kWordSize == 0
        assert self.RamRangeLegal(start, len(data))
        function_name = "Write to RAM"
        logging.info(f"{function_name} {len(data)} bytes")

        #when transfer is complete the handler sends OK<CR><LF>
        response_code = self.WriteCommand(f"W {start} {len(data)}")
        RaiseReturnCodeError(response_code, function_name)
        self.Write(data)  # Stream data after confirmation
        self.Write(bytes(self.kNewLine, "utf-8"))  # end the data stream with normal line termination
        response = retry(self.ReadLine, count=1, exception=timeout_decorator.TimeoutError, raise_on_fail=False)()
        logging.debug(response)
        # if self.SyncVerifiedString.strip() not in response:
        #     logging.error(f"Expected {self.SyncVerifiedString}, received {response}. No confirmation from {function_name}")

    @timeout(10)
    def ReadMemory(self, start: int, num_bytes: int):
        '''
        Send command with newline, receive response code\r\n<data>
        '''
        assert num_bytes%self.kWordSize == 0  #  On a word boundary
        assert self.RamRangeLegal(start, num_bytes) or self.FlashRangeLegal(start, num_bytes)
        function = "ReadMemory"
        logging.info(function)

        command = f"R {start} {num_bytes}"
        logging.info(command)
        response_code = self.WriteCommand(command)
        RaiseReturnCodeError(response_code, function)

        while len(self.data_buffer_in) < num_bytes:
            logging.debug(f"{function}: bytes in {len(self.data_buffer_in)}/{num_bytes}")
            self.Read()
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
        response_code = retry(self.WriteCommand, count=5)(command)
        RaiseReturnCodeError(response_code, "Prep Sectors")

    def CopyRAMToFlash(self, flash_address: int, ram_address: int, num_bytes: int):
        assert self.RamRangeLegal(ram_address, num_bytes)
        assert self.FlashRangeLegal(flash_address, num_bytes)

        response_code = self.WriteCommand(f"C {flash_address} {ram_address} {num_bytes}")
        RaiseReturnCodeError(response_code, "Copy RAM To Flash")
        # sleep(.2)

    def Go(self, address: int, thumb_mode: bool = False):
        '''
        Start executing code at the specified spot. Should not
        expect a response back.
        '''
        mode = ""
        if thumb_mode:
            mode = 'T'
        response_code = self.WriteCommand(f"G {address} {mode}")
        if response_code != self.ReturnCodes["NoStatusResponse"]:  #  Don't expect a response code from this
            RaiseReturnCodeError(response_code, "Go")

    def EraseSector(self, start: int, end: int):
        response_code = self.WriteCommand(f"E {start} {end}")
        RaiseReturnCodeError(response_code, "Erase Sectors")

    def ErasePages(self, start: int, end: int):
        response_code = self.WriteCommand(f"X {start} {end}")
        RaiseReturnCodeError(response_code, "Erase Pages")

    def CheckSectorsBlank(self, start: int, end: int) -> bool:
        '''
        Raises user warning if the command fails
        '''
        assert start <= end
        response_code = self.WriteCommand(f"I {start} {end}")
        try:
            self.ReadLine()  #  throw away echo ?
            response = self.ReadLine()
            logging.info("Check Sectors Blank response", response)
        except timeout_decorator.TimeoutError:
            pass

        if response_code not in (NXPReturnCodes["CMD_SUCCESS"], NXPReturnCodes["SECTOR_NOT_BLANK"]):
            RaiseReturnCodeError(response_code, "Blank Check Sectors")
        return return_code_success(response_code)

    def ReadPartID(self) -> str:
        '''
        Throws no exception
        '''
        response_code = self.WriteCommand("J")
        RaiseReturnCodeError(response_code, "Read Part ID")
        
        resp = retry(self.ReadLine, count=1, exception=timeout_decorator.TimeoutError, raise_on_fail=False)()
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
        response_code = self.WriteCommand("K")
        RaiseReturnCodeError(response_code, "Read Bootcode Version")
        minor = 0
        major = 0

        try:
            minor = self.ReadLine()
            major = self.ReadLine()
        except timeout_decorator.TimeoutError:
            pass
        return f"{major}.{minor}"

    def MemoryLocationsEqual(self, address1: int, address2: int, num_bytes: int) -> bool:
        '''
        Checks to see if two sections in the memory map are equal.
        Raises a user warning if the command fails
        '''
        command = f"M {address1} {address2} {num_bytes} {self.kNewLine}"
        self.Write(bytes(command, encoding="utf-8"))
        response_code = self.GetReturnCode()
        if response_code not in (NXPReturnCodes["CMD_SUCCESS"], NXPReturnCodes["COMPARE_ERROR"]):
            RaiseReturnCodeError(response_code, "Compare")
        return return_code_success(response_code)

    def ReadUID(self):
        '''
        Raises timeout exception
        '''
        response_code = self.WriteCommand("N")
        RaiseReturnCodeError(response_code, "Read UID")
        uuids = []
        for _ in range(4):
            uuids.append(self.ReadLine())
        return " ".join(["0x%08x"%int(uid) for uid in uuids])

    def ReadCRC(self, address: int, num_bytes: int) -> int:
        '''
        Command echos the response then the value of the CRC
        '''
        function = "Read CRC"
        command = f"S {address} {num_bytes}"

        retries = 16
        for i in range(retries):
            response_code = retry(self.WriteCommand, count=5, raise_on_fail=False)(command)
            sleep(self._crc_sleep)
            if return_code_success(response_code):
                break
            logging.debug("ReadCRC failed: %d/%d", i, retries)

        RaiseReturnCodeError(response_code, function)
        return int(self.ReadLine())

    def ReadFlashSig(self, start: int, end: int, wait_states: int = 2, mode: int = 0) -> str:
        assert start < end
        assert self.FlashAddressLegal(start) and self.FlashAddressLegal(end)
        response_code = self.WriteCommand(f"Z {start} {end} {wait_states} {mode}")
        RaiseReturnCodeError(response_code, "Read Flash Signature")
        sig = []
        nlines = 4
        for _ in range(nlines):
            sig.append(self.ReadLine())
        return sig

    def ReadWriteFAIM(self):
        response_code = self.WriteCommand("O")
        RaiseReturnCodeError(response_code, "Read Write FAIM")

    def SetCrystalFrequency(self, frequency_khz: int):
        self.Write(bytes(f"{frequency_khz} {self.kNewLine}" , encoding="utf-8"))
        verified = False
        for _ in range(3):
            try:
                frame_in = self.ReadLine()#Should be OK\r\n
                if self.SyncVerifiedString in frame_in:
                    verified = True
                    break
            except timeout_decorator.TimeoutError:
                pass
        if not verified:
            raise UserWarning("Verification Failure")


class LPC_TypeAChip(NXPChip):
    '''
    Built up functions ontop of the base NXP chip functions
    '''
    _flash_write_sleep = 0.25
    def calc_sector_count(self, image):
        return int(math.ceil(len(image)/self.sector_bytes))

    def ClearSerialConnection(self):
        for _ in range(2):
            retry(self.Read, count=10, exception=timeout_decorator.TimeoutError, raise_on_fail=False)()
            self.ClearBuffer()
            self.Flush()

    def ResetSerialConnection(self):
        self.ClearSerialConnection()

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
        self.ResetSerialConnection()
        sync_char = '?'
        for _ in range(64):
            self.Write(bytes(sync_char, "utf-8"))
            frame_in = ""
            try:
                frame_in = self.ReadLine()
            except timeout_decorator.TimeoutError:
                frame_in = collection_to_string(self.get_data_buffer_contents())

            logging.debug(f"{frame_in}, {self.SyncString.strip()}, {self.SyncString.strip()==frame_in}")
            if self.SyncString.strip() in frame_in:
                synced = True
                break
            elif len(frame_in) and (frame_in[0] == sync_char):  #  Already synced
                synced = True
                break
            #self.Write(bytes('?'*15, encoding="utf-8"))

        if not synced:
            #Check for SyncString
            raise UserWarning("Syncronization Failure")

        #self.Flush()
        self.Write(self.SyncStringBytes)#echo SyncString
        try:
            frame_in = self.ReadLine() # discard echo
        except timeout_decorator.TimeoutError:
            pass

        verified = False
        frame_in = retry(self.ReadLine, count=3)()  #  Should be OK\r\n
        if self.SyncVerifiedString in frame_in:
            verified = True
            logging.info("Syncronization Successful")
        else:
            raise UserWarning("Verification Failure")
        return verified

    def InitConnection(self):
        self.ResetSerialConnection()
        try:
            try:
                self.SyncConnection()
                self.SetCrystalFrequency(self.CrystalFrequency)
            except (UserWarning, timeout_decorator.TimeoutError) as e:
                logging.error(f"Sync Failed {e}")
                logging.debug("Connect to running ISP")
                self.Write(bytes(self.kNewLine, encoding="utf-8"))
                self.ClearSerialConnection()
            self.Echo(False)
            self.ResetSerialConnection()

            uid = self.ReadUID()
            logging.info("Part UID: %s", uid)
            boot_code_version = self.ReadBootCodeVersion()
            logging.info("Boot Code Version: %s", boot_code_version)
            self.SetBaudRate(self.baud_rate)
            logging.info("Baudrate set to %d", self.baud_rate)
        except Exception as e:
            logging.error(e)
            raise

    def CheckFlashWrite(self, data, flash_address: int) -> bool:
        '''
        Read Memory and compare it to what was written
        '''

        data_read = self.ReadMemory(flash_address, len(data))

        if len(data) != len(data_read):
            raise ValueError("Read Memory received incorrect amount of data")
        if isinstance(data_read, type(data)):
            raise TypeError("data written and data read are of different types")

        return data == data_read

    def WriteFlashSector(self, sector: int, data: bytes):
        '''
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
        '''
        ram_address = self.RAMStartWrite
        flash_address = self.FlashRange[0] + sector*self.sector_bytes
        logging.info("\nWriting Sector: %d\tFlash Address: %x\tRAM Address: %x", sector, flash_address, ram_address)

        assert len(data) == self.sector_bytes
        # data += bytes(self.sector_bytes - len(data))

        logging.debug("Calculate starting CRC")
        data_crc = calc_crc(data)
        ram_crc = retry(self.ReadCRC, count=2, exception=(UserWarning, timeout_decorator.TimeoutError))(ram_address, num_bytes=len(data))

        logging.debug("Starting CRC: %d", ram_crc)
        retries = 16
        for i in range(retries):
            logging.debug("Writing RAM %d: %d/%d", ram_address, i, retries)
            self.WriteToRam(ram_address, data)
            sleep(1)
            ram_crc = retry(self.ReadCRC, count=1, raise_on_fail=False, exception=UserWarning)(ram_address, num_bytes=len(data))
            if data_crc == ram_crc:
                logging.debug(f"CRC Check successful {data_crc} {ram_crc}")
                break
            else:
                logging.error(f"RAM CRC Check failed {data_crc} {ram_crc}")

        # Check to see if sector is already equal to RAM, if so skip
        ram_equal = retry(self.MemoryLocationsEqual, count=5, exception=(UserWarning, timeout_decorator.TimeoutError))(flash_address, ram_address, self.sector_bytes)
        if ram_equal:
            logging.info("Flash already equal to RAM, skipping write")
            return
     
        logging.info("Prep Sector")
        self.PrepSectorsForWrite(sector, sector)
        logging.info("Erase Sector")
        self.EraseSector(sector, sector)
        sleep(self._flash_write_sleep)
        assert self.CheckSectorsBlank(sector, sector)

        logging.info("Prep Sector")
        sector_blank = self.CheckSectorsBlank(sector, sector)
        assert sector_blank
        self.PrepSectorsForWrite(sector, sector)
        logging.info("Write to Flash")
        self.CopyRAMToFlash(flash_address, ram_address, self.sector_bytes)
        sleep(self._flash_write_sleep)
        flash_crc = self.ReadCRC(flash_address, num_bytes=len(data))
        assert flash_crc == data_crc
        assert self.MemoryLocationsEqual(flash_address, ram_address, self.sector_bytes)

    def WriteSector(self, sector: int, data: bytes):
        assert len(data) > 0
        filled_data = FillDataToFitSector(data, self.sector_bytes)

        self.WriteFlashSector(sector, filled_data)

        #assert self.ReadSector(sector) == data_chunk

    def WriteBinaryToFlash(self, image: bytes, start_sector: int) -> int:
        '''
        Take the image as bytes object. Break the image into sectors and write each in reverse order.
        On completion return the flash signature which cna be stored for validity checking
        '''
        assert isinstance(image, bytes)
        logging.info("Program Length:", len(image))

        sector_count = self.calc_sector_count(image)
        assert start_sector + sector_count <= self.SectorCount
        self.Unlock()
        for sector in reversed(range(start_sector, start_sector + sector_count)):
            logging.info(f"\nWriting Sector {sector}")
            data_chunk = image[(sector-start_sector) * self.sector_bytes : (sector - start_sector + 1) * self.sector_bytes]
            self.WriteSector(sector, data_chunk)

        chip_flash_sig = self.ReadFlashSig(self.FlashRange[0], self.FlashRange[1])
        logging.info(f"Flash Signature: {chip_flash_sig}")
        logging.info("Programming Complete.")
        return chip_flash_sig
    
    def WriteImage(self, image_file: str):
        '''
        1. Overwrite first sector which clears the checksum bytes making the image unbootable, preventing bricking
        2. Read the binary file into memory as a bytes object
        3. Write the checksum to the image
        4. Write the image in reverse order, the checksum will only be written once the entire valid image is written 
        '''
        #make not bootable
        self.Unlock()
        self.WriteSector(0, bytes([0xde]*self.sector_bytes))

        with open(image_file, 'rb') as f:
            prog = f.read()
            #image = RemoveBootableCheckSum(self.kCheckSumLocation, prog)
            image = MakeBootable(self.kCheckSumLocation, prog)
        self.WriteBinaryToFlash(image, start_sector=0)

    def FindFirstBlankSector(self) -> int:
        '''
        Returns the first blank sector, returns the last sector on failure
        '''
        for sector in range(self.SectorCount):
            if self.CheckSectorsBlank(sector, self.SectorCount - 1):
                return sector
        return self.SectorCount - 1

    def ReadSector(self, sector: int) -> bytes:
        return self.ReadMemory(sector*self.sector_bytes, self.sector_bytes)

    def ReadImage(self) -> bytes:
        image = bytes()
        blank_sector = self.FindFirstBlankSector()
        for sector in range(blank_sector):
            logging.info("Sector ", sector)
            image.join(self.ReadSector(sector))
        return image

    def MassErase(self):
        last_sector = self.SectorCount - 1
        self.ClearBuffer()
        self.Unlock()
        self.PrepSectorsForWrite(0, last_sector)
        self.EraseSector(0, last_sector)
