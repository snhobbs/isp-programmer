import logging
import math
import zlib
from time import sleep
import struct
from typing import List, Deque
from collections import deque
from timeout_decorator import timeout, timeout_decorator
from pycrc.algorithms import Crc
import functools
try:
    from ISPChip import IODevice
except ImportError:
    from . import IODevice
kTimeout = 1

def retry(_func=None, *, count=2, exception=timeout_decorator.TimeoutError, raise_on_fail=True):
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            value = None
            for i in range(1, count+1):    
                try:
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


def RaiseReturnCodeError(code: int, call_name: str) -> None:
    '''
    Each command returns a code, check if the code is a success, throws a UserWarning if not
    '''
    if int(code) != NXPReturnCodes["CMD_SUCCESS"]:
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


def Crc32(frame) -> int:
    #CRC32
    polynomial = 0x104c11db6
    crc = Crc(width=32, poly=polynomial, reflect_in=True,
              xor_in=(1<<32)-1, reflect_out=True, xor_out=0x00)
    crc_calc = crc.bit_by_bit(frame)
    return crc_calc


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
        sleep(10e-3)
        assert isinstance(out, bytes)
        self.iodevice.Write(out)
        sleep(10e-3)
        if self.GetEcho():
            logging.info(f"Write: [{out}]")
        else:
            logging.debug(f"Write: [{out}]")

    def Flush(self):
        self.iodevice.Flush()

    @timeout(kTimeout)
    def ReadLine(self) -> str:
        '''
        Read until a new line is found.
        Timesout if no data pulled
        '''
        while not self.ReadFrame():
            self.Read()
        line = collection_to_string(self.frame)
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
                logging.debug(f"Read: <{dstr}>")
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
    SyncString = "Synchronized"+ISPChip.kNewLine
    SyncStringBytes = bytes(SyncString, encoding="utf-8")
    SyncVerified = bytes("OK"+ISPChip.kNewLine, encoding="utf-8")
    ReturnCodes = NXPReturnCodes
    CRCLocation = 0x000002fc

    CRCValues = {
        "NO_ISP": 0x4e697370,
        "CRP1" : 0x12345678,
        "CRP2" : 0x87654321,
        "CRP3" : 0x43218765,
    }
    kSleepTime = 1

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.CrystalFrequency = 12000#khz == 30MHz
        self.SectorCount = 0
        self.RAMSize = 0
        self.RAMRange = [0, 0]
        self.FlashRange = [0, 0]
        self.RAMStartWrite = 0
        self.kCheckSumLocation = 7  # 0x0000001c

    def FlashAddressLegal(self, address):
        return (self.FlashRange[0] <= address <= self.FlashRange[1])

    def FlashRangeLegal(self, address, length):
        logging.info(self.FlashRange, address, length)
        return self.FlashAddressLegal(address) and\
            self.FlashAddressLegal(address + length - 1) and\
            length <= self.FlashRange[1] - self.FlashRange[0] and\
            address%self.kPageSizeBytes == 0

    def RamAddressLegal(self, address):
        return self.RAMRange[0] <= address <= self.RAMRange[1]

    def RamRangeLegal(self, address, length):
        return self.RamAddressLegal(address) and\
            self.RamAddressLegal(address + length) and\
            length <= self.RAMRange[1] - self.RAMRange[0] and\
            address%self.kWordSize == 0

    @retry(count=5)
    def GetReturnCode(self) -> int:
        for _ in range(10):
            sleep(5e-3)
            try:
                self.Write(bytes(self.kNewLine, encoding="utf-8"))
                resp = self.ReadLine().strip()
                return int(resp)
            except ValueError:
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
        self.ClearBuffer()
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
        assert len(data)%self.kWordSize == 0
        assert self.RamRangeLegal(start, len(data))
        function_name = "Write to RAM"
        logging.info(f"{function_name} {len(data)} bytes")

        #when transfer is complete the handler sends OK<CR><LF>
        response_code = self.WriteCommand(f"W {start} {len(data)}")
        RaiseReturnCodeError(response_code, function_name)
        self.Write(data)  # Stream data after confirmation
        # self.Write("OK"+self.kNewLine)
        try:
            logging.debug(self.ReadLine())
        except timeout_decorator.TimeoutError:
            return

    @timeout(4)
    def ReadMemory(self, start: int, num_bytes: int):
        assert num_bytes%self.kWordSize == 0
        assert self.RamRangeLegal(start, num_bytes)
        logging.info("ReadMemory")

        # self.Flush()
        # self.Read()
        # self.ClearBuffer()
        # self.Flush()

        command = "R {start} {num_bytes}"
        logging.info(command)
        response_code = self.WriteCommand(command)
        RaiseReturnCodeError(response_code, "Read Memory")

        while len(self.data_buffer_in) < (num_bytes):
            self.Read()
        # Command success is sent at the end of the transferr
        data = []
        while self.data_buffer_in:
            ch = self.data_buffer_in.popleft()
            data.append(ch)

        if len(data) != num_bytes:
            logging.debug(data, len(data), num_bytes)
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
        Start executing code at the specified spot
        '''
        mode = ""
        if thumb_mode:
            mode = 'T'
        response_code = self.WriteCommand(f"G {address} {mode}")
        RaiseReturnCodeError(response_code, "Go")

    def EraseSector(self, start: int, end: int):
        response_code = self.WriteCommand(f"E {start} {end}")
        RaiseReturnCodeError(response_code, "Erase Sectors")

    def ErasePages(self, start: int, end: int):
        response_code = self.WriteCommand(f"X {start} {end}")
        RaiseReturnCodeError(response_code, "Erase Pages")

    def CheckSectorsBlank(self, start: int, end: int) -> bool:
        assert start <= end
        response_code = self.WriteCommand(f"I {start} {end}")
        try:
            self.ReadLine()
            response = self.ReadLine().strip()
            logging.info("Check Sectors Blank response", response)
        except timeout_decorator.TimeoutError:
            pass

        if response_code not in (NXPReturnCodes["CMD_SUCCESS"], NXPReturnCodes["SECTOR_NOT_BLANK"]):
            RaiseReturnCodeError(response_code, "Blank Check Sectors")
        return response_code == NXPReturnCodes["CMD_SUCCESS"]

    def ReadPartID(self):
        response_code = self.WriteCommand("J")
        RaiseReturnCodeError(response_code, "Read Part ID")
        resp = self.ReadLine()
        return int(resp)

    def ReadBootCodeVersion(self):
        '''
        LPC84x sends a 0x1a first for some reason.
        Also the boot version seems to be Minor then Major not like the docs say
        '''
        response_code = self.WriteCommand("K")
        RaiseReturnCodeError(response_code, "Read Bootcode Version")
        minor = self.ReadLine().strip()
        major = self.ReadLine().strip()
        return f"{major}.{minor}"

    def MemoryLocationsEqual(self, address1: int, address2: int, num_bytes: int):
        '''
        Checks to see if two sections in the memory map are equal.
        Raises a timeout error or a user warning
        '''
        command = f"M {address1} {address2} {num_bytes} {self.kNewLine}"
        self.Write(bytes(command, encoding="utf-8"))
        response = self.ReadLine()
        response_code = int(response[0])
        if response_code not in (NXPReturnCodes["CMD_SUCCESS"], NXPReturnCodes["COMPARE_ERROR"]):
            RaiseReturnCodeError(response_code, "Compare")
        return response_code == NXPReturnCodes["CMD_SUCCESS"]

    def ReadUID(self):
        response_code = self.WriteCommand("N")
        RaiseReturnCodeError(response_code, "Read UID")
        uuids = [
            self.ReadLine().strip(),
            self.ReadLine().strip(),
            self.ReadLine().strip(),
            self.ReadLine().strip()]
        return " ".join(["0x%08x"%int(uid) for uid in uuids])

    def ReadCRC(self, address: int, num_bytes: int) -> int:
        function = "Read CRC"
        command = f"S {address} {num_bytes}"

        response_code = retry(self.WriteCommand, count=5)(command)
        sleep(0.25)
        RaiseReturnCodeError(response_code, function)
        return int(self.ReadLine().strip())

    def ReadFlashSig(self, start: int, end: int, wait_states: int = 2, mode: int = 0) -> str:
        assert start < end
        assert self.FlashAddressLegal(start) and self.FlashAddressLegal(end)
        response_code = self.WriteCommand(f"Z {start} {end} {wait_states} {mode}")
        RaiseReturnCodeError(response_code, "Read Flash Signature")
        sig = []
        nlines = 4
        for _ in range(nlines):
            sig.append(self.ReadLine().strip())
        return sig

    def ReadWriteFAIM(self):
        response_code = self.WriteCommand("O")
        RaiseReturnCodeError(response_code, "Read Write FAIM")

    def ResetSerialConnection(self):
        self.ClearSerialConnection()

    def InitConnection(self):
        self.ResetSerialConnection()
        try:
            try:
                self.SyncConnection()
                self.SetCrystalFrequency(self.CrystalFrequency)
            except (UserWarning, timeout_decorator.TimeoutError) as w:
                logging.error("Sync Failed", w)
                logging.debug("Connect to running ISP")
                self.Write(bytes(self.kNewLine, encoding="utf-8"))
                self.ClearSerialConnection()
            self.Echo(False)
            try:
                self.ReadLine()
                self.Flush()
                self.ClearBuffer()
            except timeout_decorator.TimeoutError:
                pass
            uid = self.ReadUID()
            logging.info("Part UID: %s"%uid)
            boot_code_version = self.ReadBootCodeVersion()
            logging.info("Boot Code Version: %s"%boot_code_version)
            self.SetBaudRate(self.baud_rate)
            logging.info("Baudrate set to %d"%self.baud_rate)
        except Exception as e:
            logging.error(e)
            raise

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
        self.ClearSerialConnection()
        self.Flush()
        sync_char = '?'
        for _ in range(64):
            self.Write(bytes(sync_char, "utf-8"))
            sleep(0.1)

            frame_in = ""
            try:
                frame_in = self.ReadLine().strip()
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
        if self.SyncVerified.decode("utf-8") in frame_in:
            verified = True
            logging.info("Syncronization Successful")
        else:
            raise UserWarning("Verification Failure")
        return verified

    def ClearSerialConnection(self):
        self.ClearBuffer()
        self.Flush()
        self.Read()
        self.ClearBuffer()
        self.Flush()
        retry(self.ReadLine, count=2, exception=timeout_decorator.TimeoutError, raise_on_fail=False)()

    def SetCrystalFrequency(self, frequency_khz: int):
        self.Write((bytes("%d"%frequency_khz + self.kNewLine, encoding="utf-8")))
        verified = False
        for _ in range(3):
            try:
                frame_in = self.ReadLine()#Should be OK\r\n
                if self.SyncVerified.decode("utf-8") in frame_in:
                    verified = True
                    break
            except timeout_decorator.TimeoutError:
                pass
        if not verified:
            raise UserWarning("Verification Failure")

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
        ram_address = self.RAMStartWrite
        sector_size_bytes = self.kPageSizeBytes*self.SectorSizePages
        flash_address = self.FlashRange[0] + sector*sector_size_bytes
        logging.info("\nWriting Sector: %d\nFlash Address: %x\nRAM Address: %x\n", sector, flash_address, ram_address)

        assert len(data) == sector_size_bytes
        # data += bytes(sector_size_bytes - len(data))

        data_crc = zlib.crc32(data, 0)
        ram_crc = retry(self.ReadCRC, count=2, exception=(UserWarning, timeout_decorator.TimeoutError))(ram_address, num_bytes=len(data))

        while ram_crc != data_crc:
            sleep(self.kSleepTime)
            self.WriteToRam(ram_address, data)
            sleep(self.kSleepTime)
            ram_crc = self.ReadCRC(ram_address, num_bytes=len(data))
            if data_crc != ram_crc:
                logging.error(f"CRC Check failed {data_crc} {ram_crc}")
            else:
                break

        # Check to see if sector is already equal to RAM, if so skip
        ram_equal = retry(self.MemoryLocationsEqual, count=5, exception=(UserWarning, timeout_decorator.TimeoutError))(flash_address, ram_address, sector_size_bytes)
        if ram_equal:
            logging.info("Flash already equal to RAM, skipping write")
            return
     
        logging.info("Prep Sector")
        self.PrepSectorsForWrite(sector, sector)
        sleep(self.kSleepTime)
        logging.info("Erase Sector")
        self.EraseSector(sector, sector)
        sleep(self.kSleepTime)
        assert self.CheckSectorsBlank(sector, sector)
        sleep(self.kSleepTime)

        logging.info("Prep Sector")
        sector_blank = self.CheckSectorsBlank(sector, sector)
        assert sector_blank
        sleep(self.kSleepTime)
        self.PrepSectorsForWrite(sector, sector)
        sleep(self.kSleepTime)
        logging.info("Write to Flash")
        self.CopyRAMToFlash(flash_address, ram_address, sector_size_bytes)
        sleep(self.kSleepTime)
        flash_crc = self.ReadCRC(flash_address, num_bytes=len(data))
        assert flash_crc == data_crc
        assert self.MemoryLocationsEqual(flash_address, ram_address, sector_size_bytes)

    def WriteSector(self, sector: int, data: bytes):
        #assert data

        sector_bytes = self.SectorSizePages*self.kPageSizeBytes
        assert len(data) > 0
        filled_data = FillDataToFitSector(data, sector_bytes)

        self.WriteFlashSector(sector, filled_data)
        sleep(self.kSleepTime)
        #assert self.ReadSector(sector) == data_chunk

    def WriteBinaryToFlash(self, image_file: str, start_sector: int):
        sector_bytes = self.SectorSizePages*self.kPageSizeBytes
        assert sector_bytes%self.kWordSize == 0

        with open(image_file, 'rb') as f:
            prog = f.read()
            image = prog
            logging.info("Program Length:", len(prog))

            sector_count = int(math.ceil(len(prog)/sector_bytes))
            assert start_sector + sector_count <= self.SectorCount
            self.Unlock()
            for sector in reversed(range(start_sector, start_sector + sector_count)):
                logging.info(f"\nWriting Sector {sector}")
                data_chunk = image[(sector-start_sector) * sector_bytes : (sector - start_sector + 1) * sector_bytes]
                self.WriteSector(sector, data_chunk)

        sleep(1)
        chip_flash_sig = self.ReadFlashSig(self.FlashRange[0], self.FlashRange[1])
        logging.info(f"Flash Signature: {chip_flash_sig}")
        logging.info("Programming Complete.")

    def WriteImage(self, image_file: str):
        sector_bytes = self.SectorSizePages*self.kPageSizeBytes
        assert sector_bytes%self.kWordSize == 0

        #make not bootable
        self.Unlock()
        self.WriteSector(0, bytes([0xde]*sector_bytes))

        with open(image_file, 'rb') as f:
            prog = f.read()
            #image = RemoveBootableCheckSum(self.kCheckSumLocation, prog)
            image = MakeBootable(self.kCheckSumLocation, prog)
            logging.info("Program Length: %d", len(prog))

            sector_count = int(math.ceil(len(prog)/sector_bytes))
            assert sector_count <= self.SectorCount
            for sector in reversed(range(sector_count)):
                logging.info("\nWriting Sector %d"%sector)
                data_chunk = image[sector * sector_bytes : (sector + 1) * sector_bytes]
                self.WriteSector(sector, data_chunk)

        chip_flash_sig = self.ReadFlashSig(self.FlashRange[0], self.FlashRange[1])
        logging.info("Flash Signature: %s"%chip_flash_sig)
        logging.info("Programming Complete.")

    def FindFirstBlankSector(self) -> int:
        '''
        Returns the first blank sector, returns the last sector on failure
        '''
        for sector in range(self.SectorCount):
            if self.CheckSectorsBlank(sector, self.SectorCount - 1):
                return sector
        return self.SectorCount - 1

    def ReadSector(self, sector: int) -> bytes:
        sector_bytes = self.SectorSizePages*self.kPageSizeBytes
        assert sector_bytes%self.kWordSize == 0
        return self.ReadMemory(sector*sector_bytes, sector_bytes)

    def ReadImage(self, image_file: str):
        blank_sector = self.FindFirstBlankSector()
        with open(image_file, 'wb') as f:
            for sector in range(blank_sector):
                logging.info("Sector ", sector)
                f.write(self.ReadSector(sector))

    def MassErase(self):
        last_sector = self.SectorCount - 1
        sleep(1)
        self.ClearBuffer()
        self.Unlock()
        self.PrepSectorsForWrite(0, last_sector)
        self.EraseSector(0, last_sector)
        logging.info("Checking Sectors are blank")
        assert self.CheckSectorsBlank(0, last_sector)
