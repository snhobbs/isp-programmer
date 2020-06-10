import math
import zlib
from time import sleep
import struct
from timeout_decorator import timeout
from timeout_decorator.timeout_decorator import TimeoutError
from pycrc.algorithms import Crc
from .ISPChip import ISPChip

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
    return "Not Found"

def RaiseReturnCodeError(code: int, call_name: str) -> None:
    if int(code) != NXPReturnCodes["CMD_SUCCESS"]:
        raise UserWarning(
            "Return Code Failure in {} {} {}".format(call_name, GetErrorCodeName(code), code))

def RemoveBootableCheckSum(vector_table_loc: int, image: bytes):
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

class NXPChip(ISPChip):
    kWordSize = 4
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
        self.kCheckSumLocation = 7 #0x0000001c

    def FlashAddressLegal(self, address):
        return address >= self.FlashRange[0] and address <= self.FlashRange[1];

    def FlashRangeLegal(self, address, length):
        print(self.FlashRange, address, length)
        return self.FlashAddressLegal(address) and self.FlashAddressLegal(address + length - 1) and length <= self.FlashRange[1] - self.FlashRange[0] and address%self.kPageSizeBytes == 0

    def RamAddressLegal(self, address):
        return address >= self.RAMRange[0] and address <= self.RAMRange[1]

    def RamRangeLegal(self, address, length):
        return self.RamAddressLegal(address) and self.RamAddressLegal(address + length) and length <= self.RAMRange[1] - self.RAMRange[0] and address%self.kWordSize == 0

    def GetReturnCode(self) -> int:
        for _ in range(10):
            #sleep(.1)
            try:
                resp = self.ReadLine().strip()
                return int(resp)
            except ValueError:
                pass
        return self.ReturnCodes["NoStatusResponse"]

    def AssertReturnCode(self, call_name: str) -> None:
        '''
        Get a return code with no response
        '''
        code = self.GetReturnCode()
        RaiseReturnCodeError(code, call_name)

    def Write(self, string : bytes) -> None:
        #print(out)
        assert(type(string) is bytes)
        self.WriteSerial(string)
        #self.WriteSerial(bytes(self.kNewLine, encoding = "utf-8"))

    '''
    Takes the command string, return the response code
    '''
    def WriteCommand(self, command_string: str) -> int:
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
        response_code = self.WriteCommand("B {} {}".format(baud_rate, stop_bits))
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
        print("Write to RAM %d bytes"%len(data))
        #while i < len(data):
        #    self.Write("W %d %d"%(start + i, kWordSize))
        #    self.AssertReturnCode("Write to RAM")#get confirmation
        #    self.Write(data[i:i+kWordSize])#Stream data after confirmation
        #    i+=kWordSize

        #when transfer is complete the handler sends OK<CR><LF>
        response_code = self.WriteCommand("W %d %d"%(start, len(data)))
        RaiseReturnCodeError(response_code, "Write to RAM")
        self.Write(data)#Stream data after confirmation
        #self.Write("OK"+self.kNewLine)
        try:
            print(self.ReadLine())
        except TimeoutError:
            return

    @timeout(4)
    def ReadMemory(self, start: int, num_bytes: int):
        assert num_bytes%self.kWordSize == 0
        assert self.RamRangeLegal(start, num_bytes)
        print("ReadMemory")

        #self.Flush()
        #self.Read()
        #self.ClearBuffer()
        #self.Flush()

        print("R %d %d"%(start, num_bytes))
        response_code = self.WriteCommand("R %d %d"%(start, num_bytes))
        RaiseReturnCodeError(response_code, "Read Memory")

        while len(self.data_buffer_in) < (num_bytes):
            self.Read()
        # Command success is sent at the end of the transferr
        data = []
        while self.data_buffer_in:
            ch = self.data_buffer_in.popleft()
            data.append(ch)

        if len(data) != num_bytes:
            print(data, len(data), num_bytes)
        assert len(data) == num_bytes
        return bytes(data)

    def PrepSectorsForWrite(self, start: int, end: int):
        try:
            response_code = self.WriteCommand("P %d %d"%(start, end))
        except Exception:
            response_code = self.WriteCommand("P %d %d"%(start, end))
        RaiseReturnCodeError(response_code, "Prep Sectors")

    def CopyRAMToFlash(self, flash_address: int, ram_address: int, num_bytes: int):
        assert self.RamRangeLegal(ram_address, num_bytes)
        assert self.FlashRangeLegal(flash_address, num_bytes)

        response_code = self.WriteCommand("C %d %d %d"%(flash_address, ram_address, num_bytes))
        RaiseReturnCodeError(response_code, "Copy RAM To Flash")
        #sleep(.2)

    def Go(self, address: int, thumb_mode: bool = False):
        '''
        Start executing code at the specified spot
        '''
        mode = ""
        if thumb_mode:
            mode = 'T'
        response_code = self.WriteCommand("G %d %s"%(address, mode))
        RaiseReturnCodeError(response_code, "Go")

    def EraseSector(self, start: int, end: int):
        response_code = self.WriteCommand("E %d %d"%(start, end))
        RaiseReturnCodeError(response_code, "Erase Sectors")

    def ErasePages(self, start: int, end: int):
        response_code = self.WriteCommand("X %d %d"%(start, end))
        RaiseReturnCodeError(response_code, "Erase Pages")

    def CheckSectorsBlank(self, start: int, end: int) -> bool:
        assert start <= end
        response_code = self.WriteCommand("I %d %d"%(start, end))
        try:
            self.ReadLine()
            response = self.ReadLine().strip()
            print("Check Sectors Blank response", response)
        except TimeoutError:
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
        return "%d.%d"%(int(major), int(minor))


    '''
    Checks to see if two sections in the memory map are equal
    '''
    def MemoryLocationsEqual(self, address1: int, address2: int, num_bytes: int):
        self.Write(bytes(("M %d %d %d"%(address1, address2, num_bytes) + self.kNewLine), encoding="utf-8"))
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
        try:
            response_code = self.WriteCommand("S %d %d"%(address, num_bytes))
        except TimeoutError:
            response_code = self.WriteCommand("S %d %d"%(address, num_bytes))

        RaiseReturnCodeError(response_code, "Read CRC")
        return int(self.ReadLine().strip())

    def ReadFlashSig(self, start: int, end: int, wait_states: int = 2, mode: int = 0) -> str:
        assert start < end
        assert(self.FlashAddressLegal(start) and self.FlashAddressLegal(end))
        response_code = self.WriteCommand("Z %d %d %d %d"%(start, end, wait_states, mode))
        RaiseReturnCodeError(response_code, "Read Flash Signature")
        sig = []
        for i in range(4):
            sig.append(self.ReadLine().strip())
        return sig

    def ReadWriteFAIM(self):
        response_code = self.WriteCommand("O")
        RaiseReturnCodeError(response_code, "Read Write FAIM")

    def ResetSerialConnection(self):
        self.Flush()
        self.Write(bytes(self.kNewLine, encoding="utf-8"))
        try:
            self.ReadLine()
        except TimeoutError:
            pass

    def InitConnection(self):
        self.ResetSerialConnection()
        try:
            try:
                self.SyncConnection()
                self.SetCrystalFrequency(self.CrystalFrequency)
            except (UserWarning, TimeoutError) as w:
                print("Sync Failed", w)
                print("Connect to running ISP")
                self.ClearSerialConnection()
            self.Echo(False)
            try:
                self.ReadLine()
                self.Flush()
                self.ClearBuffer()
            except TimeoutError:
                pass
            uid = self.ReadUID()
            print("Part UID: %s"%uid)
            boot_code_version = self.ReadBootCodeVersion()
            print("Boot Code Version: %s"%boot_code_version)
            self.SetBaudRate(self.baud_rate)
            print("Baudrate set to %d"%self.baud_rate)
        except Exception as e:
            print(e, type(e))
            raise

    def SyncConnection(self):
        synced = False
        self.ClearSerialConnection()
        self.Flush()
        for i in range(5):
            self.Write(bytes('?'*15, encoding="utf-8"))
            #self.Write('?' + self.kNewLine)
            try:
                frame_in = self.ReadLine()
                if self.SyncString.strip() in frame_in.strip():
                    synced = True
                    break
            except TimeoutError:
                pass

        if not synced:
            #Check for SyncString
            raise UserWarning("Syncronization Failure")

        #self.Flush()
        self.Write(self.SyncStringBytes)#echo SyncString
        try:
            frame_in = self.ReadLine()#discard echo
        except TimeoutError:
            pass

        verified = False
        for i in range(3):
            try:
                frame_in = self.ReadLine()#Should be OK\r\n
                if self.SyncVerified.strip() in frame_in:
                    verified = True
                    break
            except TimeoutError:
                pass
        if not verified:
            raise UserWarning("Verification Failure")
        print("Syncronization Successful")

    def ClearSerialConnection(self):
        self.Write(bytes(self.kNewLine, encoding="utf-8"))
        self.ClearBuffer()
        self.Flush()
        self.Read()
        self.ClearBuffer()
        self.Flush()
        for _ in range(2):
            try:
                self.ReadLine()
            except TimeoutError:
                pass

    def SetCrystalFrequency(self, frequency_khz: int):
        self.Write((bytes("%d"%frequency_khz + self.kNewLine, encoding="utf-8")))
        verified = False
        for i in range(3):
            try:
                frame_in = self.ReadLine()#Should be OK\r\n
                if self.SyncVerified.strip() in frame_in:
                    verified = True
                    break
            except TimeoutError:
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
        if isinstance(type(data), data_read):
            raise TypeError("data written and data read are of different types")

        return data == data_read

    def WriteFlashSector(self, sector: int, data: bytes):
        ram_address = self.RAMStartWrite
        sector_size_bytes = self.kPageSizeBytes*self.SectorSizePages
        flash_address = self.FlashRange[0] + sector*sector_size_bytes
        print("\nWriting Sector: %d\nFlash Address: %x\nRAM Address: %x\n"%(sector, flash_address, ram_address))

        assert len(data) == sector_size_bytes
        #data += bytes(sector_size_bytes - len(data))

        data_crc = zlib.crc32(data, 0)

        try:
            ram_crc = self.ReadCRC(ram_address, num_bytes=len(data))
        except Exception:
            ram_crc = self.ReadCRC(ram_address, num_bytes=len(data))
        while ram_crc != data_crc:
            sleep(self.kSleepTime)
            self.WriteToRam(ram_address, data)
            sleep(self.kSleepTime)
            ram_crc = self.ReadCRC(ram_address, num_bytes=len(data))
            if data_crc != ram_crc:
                print("CRC Check failed", data_crc, ram_crc)
            else:
                break

        # Check to see if sector is already equal to RAM, if so skip

        try:
            self.MemoryLocationsEqual(flash_address, ram_address, sector_size_bytes)
            print("Flash already equal to RAM, skipping write")
            return
        except:
            pass

        print("Prep Sector")
        self.PrepSectorsForWrite(sector, sector)
        sleep(self.kSleepTime)
        print("Erase Sector")
        self.EraseSector(sector, sector)
        sleep(self.kSleepTime)
        assert self.CheckSectorsBlank(sector, sector)
        sleep(self.kSleepTime)

        print("Prep Sector")
        sector_blank = self.CheckSectorsBlank(sector, sector)
        assert sector_blank
        sleep(self.kSleepTime)
        self.PrepSectorsForWrite(sector, sector)
        sleep(self.kSleepTime)
        print("Write to Flash")
        self.CopyRAMToFlash(flash_address, ram_address, sector_size_bytes)
        sleep(self.kSleepTime)
        flash_crc = self.ReadCRC(flash_address, num_bytes=len(data))
        assert flash_crc == data_crc
        assert self.MemoryLocationsEqual(flash_address, ram_address, sector_size_bytes)

    def WriteSector(self, sector: int, data: bytes):
        #assert data

        sector_bytes = self.SectorSizePages*self.kPageSizeBytes
        assert(len(data) > 0)
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
            print("Program Length:", len(prog))

            sector_count = int(math.ceil(len(prog)/sector_bytes))
            assert start_sector + sector_count <= self.SectorCount
            self.Unlock()
            for sector in reversed(range(start_sector, start_sector + sector_count)):
                print("\nWriting Sector %d"%sector)
                data_chunk = image[(sector-start_sector) * sector_bytes : (sector - start_sector + 1) * sector_bytes]
                self.WriteSector(sector, data_chunk)

        sleep(1)
        chip_flash_sig = self.ReadFlashSig(self.FlashRange[0], self.FlashRange[1])
        print("Flash Signature: %s"%chip_flash_sig)
        print("Programming Complete.")

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
            print("Program Length:", len(prog))

            sector_count = int(math.ceil(len(prog)/sector_bytes))
            assert sector_count <= self.SectorCount
            for sector in reversed(range(sector_count)):
                print("\nWriting Sector %d"%sector)
                data_chunk = image[sector * sector_bytes : (sector + 1) * sector_bytes]
                self.WriteSector(sector, data_chunk)

        chip_flash_sig = self.ReadFlashSig(self.FlashRange[0], self.FlashRange[1])
        print("Flash Signature: %s"%chip_flash_sig)
        print("Programming Complete.")

    def FindFirstBlankSector(self) -> int:
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
                print("Sector ", sector)
                f.write(self.ReadSector(sector))

    def MassErase(self):
        last_sector = self.SectorCount - 1
        sleep(1)
        self.ClearBuffer()
        self.Unlock()
        self.PrepSectorsForWrite(0, last_sector)
        self.EraseSector(0, last_sector)
        print("Checking Sectors are blank")
        assert self.CheckSectorsBlank(0, last_sector)
