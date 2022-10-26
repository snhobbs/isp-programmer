import logging
from time import sleep
import struct
import timeout_decorator
from . import ISPConnection
from .tools import calc_crc
from . import tools
kTimeout = 1


###############################################################
# Check Sum
###############################################################


class ChipDescription:
    '''
    Wraps a chip description line and exposes it as a class
    '''
    kWordSize = 4  #  32 bit
    kPageSizeBytes = 64
    SectorSizePages = 16
    CRCLocation = 0x000002fc
    CRCValues = {
        "NO_ISP": 0x4e697370,
        "CRP1" : 0x12345678,
        "CRP2" : 0x87654321,
        "CRP3" : 0x43218765,
    }

    @property
    def MaxByteTransfer (self):
        return self.RAMBufferSize

    def __init__(self, descriptor: dict):
        descriptor: dict
        for name in dict(descriptor):
            self.__setattr__(name, descriptor[name])
        self.CrystalFrequency = 12000#khz == 30MHz
        self.kCheckSumLocation = 7  # 0x0000001c

    @property
    def sector_bytes(self):
        sector_bytes = self.SectorSizePages*self.kPageSizeBytes
        assert sector_bytes%self.kWordSize == 0
        assert sector_bytes <= self.MaxByteTransfer
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



'''
Script tools
'''


assert calc_crc(bytes([0xff]*1024)) == 3090874356  #  Check the software crc algorithm

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
    csum = tools.CalculateCheckSum(intvecs_list)
    intvecs_list[vector_table_loc] = csum
    vector_table_bytes = b''
    for vecval in intvecs_list:
        vector_table_bytes += struct.pack("<I", vecval)
    return vector_table_bytes


def MakeBootable(vector_table_loc: int, orig_image: bytes) -> bytes:
    vector_table_bytes = GetCheckSumedVectorTable(vector_table_loc, orig_image)

    image = vector_table_bytes + orig_image[len(vector_table_bytes):]
    return image


def CheckFlashWrite(isp: ISPConnection, data, flash_address: int) -> bool:
    '''
    Read Memory and compare it to what was written
    baud_rate'''

    data_read = isp.ReadMemory(flash_address, len(data))

    if len(data) != len(data_read):
        raise ValueError("Read Memory received incorrect amount of data")
    if isinstance(data_read, type(data)):
        raise TypeError("data written and data read are of different types")

    return data == data_read


def WriteFlashSector(isp: ISPConnection, chip: ChipDescription, sector: int, data: bytes):
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
    flash_write_sleep = 0.05
    ram_write_sleep = 0#0.1
    ram_address = chip.RAMStartWrite
    flash_address = chip.FlashRange[0] + sector*chip.sector_bytes
    logging.info("\nWriting Sector: %d\tFlash Address: %x\tRAM Address: %x", sector, flash_address, ram_address)

    assert len(data) == chip.sector_bytes
    # data += bytes(chip.sector_bytes - len(data))

    logging.debug("Calculate starting CRC")
    data_crc = calc_crc(data)
    ram_crc = isp.ReadCRC(ram_address, num_bytes=len(data))

    logging.debug("Starting CRC: %d", ram_crc)

    logging.debug("Writing RAM %d", ram_address)
    assert chip.RamRangeLegal(ram_address, len(data))
    sleep(ram_write_sleep)
    isp.WriteToRam(ram_address, data)
    sleep(ram_write_sleep)
    ram_crc = isp.ReadCRC(ram_address, num_bytes=len(data))
    if data_crc == ram_crc:
        logging.debug(f"CRC Check successful {data_crc} {ram_crc}")
    else:
        logging.error(f"RAM CRC Check failed {data_crc} {ram_crc}")

    # Check to see if sector is already equal to RAM, if so skip
    ram_equal = isp.MemoryLocationsEqual(flash_address, ram_address, chip.sector_bytes)
    if ram_equal:
        logging.info("Flash already equal to RAM, skipping write")
        return

    logging.info("Prep Sector")
    isp.PrepSectorsForWrite(sector, sector)
    logging.info("Erase Sector")
    isp.EraseSector(sector, sector)
    sleep(flash_write_sleep)
    assert isp.CheckSectorsBlank(sector, sector)

    logging.info("Prep Sector")
    sector_blank = isp.CheckSectorsBlank(sector, sector)
    assert sector_blank
    isp.PrepSectorsForWrite(sector, sector)
    logging.info("Write to Flash")

    assert chip.RamRangeLegal(ram_address, chip.sector_bytes)
    assert chip.FlashRangeLegal(flash_address, chip.sector_bytes)

    isp.CopyRAMToFlash(flash_address, ram_address, chip.sector_bytes)
    sleep(flash_write_sleep)
    flash_crc = isp.ReadCRC(flash_address, num_bytes=len(data))
    assert flash_crc == data_crc
    assert isp.MemoryLocationsEqual(flash_address, ram_address, chip.sector_bytes)


def WriteSector(isp: ISPConnection, chip: ChipDescription, sector: int, data: bytes):
    assert len(data) > 0

    if len(data) != chip.sector_bytes:  #  Fill data buffer to match write size
        data += bytes([0xff] *(chip.sector_bytes - len(data)))
    WriteFlashSector(isp, chip, sector, data)

    #assert isp.ReadSector(sector) == data_chunk


def WriteBinaryToFlash(isp: ISPConnection, chip: ChipDescription, image: bytes, start_sector: int) -> int:
    '''
    Take the image as bytes object. Break the image into sectors and write each in reverse order.
    On completion return the flash signature which cna be stored for validity checking
    '''
    assert isinstance(image, bytes)
    logging.info("Program Length: %d", len(image))

    sector_count = tools.calc_sector_count(image, chip.sector_bytes)
    if start_sector + sector_count > chip.SectorCount:
        logging.error(f"Invalid sector count\t Start: {start_sector}\tCount: {sector_count}\tEnd: {chip.SectorCount}")
        return
    isp.Unlock()
    for sector in reversed(range(start_sector, start_sector + sector_count)):
        logging.info(f"\nWriting Sector {sector}")
        data_chunk = image[(sector-start_sector) * chip.sector_bytes : (sector - start_sector + 1) * chip.sector_bytes]
        WriteSector(isp, chip, sector, data_chunk)

    assert chip.FlashAddressLegal(chip.FlashRange[0]) and chip.FlashAddressLegal(chip.FlashRange[1])
    '''  Flash signature reading is only supported for some chips and is partially impimented for others.
    sleep(0.5)
    chip_flash_sig = isp.ReadFlashSig(chip.FlashRange[0], chip.FlashRange[1])
    logging.info(f"Flash Signature: {chip_flash_sig}")
    logging.info("Programming Complete.")
    return chip_flash_sig
    '''


def WriteImage(isp: ISPConnection, chip: ChipDescription, imagein: bytes):
    '''
    1. Overwrite first sector which clears the checksum bytes making the image unbootable, preventing bricking
    2. Read the binary file into memory as a bytes object
    3. Write the checksum to the image
    4. Write the image in reverse order, the checksum will only be written once the entire valid image is written
    '''
    # make not bootable
    isp.Unlock()
    WriteSector(isp, chip, 0, bytes([0xde]*chip.sector_bytes))

    #image = RemoveBootableCheckSum(chip.kCheckSumLocation, prog)
    image = MakeBootable(chip.kCheckSumLocation, imagein)
    WriteBinaryToFlash(isp, chip, image, start_sector=0)


def FindFirstBlankSector(isp: ISPConnection, chip) -> int:
    '''
    Returns the first blank sector, returns the last sector on failure
    '''
    for sector in range(chip.SectorCount):
        if isp.CheckSectorsBlank(sector, chip.SectorCount - 1):
            return sector
    return chip.SectorCount - 1


def ReadSector(isp: ISPConnection, chip: ChipDescription, sector: int) -> bytes:

    start = sector*chip.sector_bytes
    assert chip.FlashRangeLegal(start, chip.sector_bytes)
    return isp.ReadMemory(start, chip.sector_bytes)


def ReadImage(isp: ISPConnection, chip: ChipDescription) -> bytes:
    image = bytes()
    blank_sector = FindFirstBlankSector(isp, chip)
    sectors = []
    for sector in range(blank_sector):
        logging.info("Sector %d", sector)
        sector = ReadSector(isp, chip, sector)
        sectors.append(sector)

    return image.join(sectors)


def MassErase(isp: ISPConnection, chip: ChipDescription):
    last_sector = chip.SectorCount - 1
    isp.reset()
    isp.Unlock()
    isp.PrepSectorsForWrite(0, last_sector)
    isp.EraseSector(0, last_sector)


def InitConnection(isp: ISPConnection, chip):
    isp.reset()
    try:
        try:
            isp.SyncConnection()
        except (UserWarning, timeout_decorator.TimeoutError) as e:
            logging.error(f"Sync Failed {e}")
            logging.debug("Connect to running ISP")
            # isp.Write(bytes(isp.kNewLine, encoding="utf-8"))
        # After syncronization some devices send a second OK at the first
        # command
        isp.SetEcho(False)
        isp.SetBaudRate(isp.baud_rate)
        logging.info("Baudrate set to %d", isp.baud_rate)
        isp.SetCrystalFrequency(chip.CrystalFrequency)
        isp.reset()
    except Exception as e:
        logging.error(e)
        raise
