import logging
import timeout_decorator
from time import sleep
try:
    from IODevices import UartDevice
    from nxp import retry, LPC_TypeAChip, retry, BAUDRATES, FillDataToFitSector, calc_crc
    from parts_definitions import GetPartDescriptor
except ImportError as e:
    from ISPProgrammer import LPC_TypeAChip, retry, UartDevice, GetPartDescriptor, BAUDRATES, FillDataToFitSector

def SetupChip(baudrate: int, crystal_frequency: int, chip_file: str, sleep_time : float = 1) -> LPC_TypeAChip:
    #print(baudrate, device, crystal_frequency, chip_file) 
    kStartingBaudRate = baudrate

    device = "/dev/ttyUSB0"
    iodevice = UartDevice(device, baudrate=kStartingBaudRate)
    chip = LPC_TypeAChip(iodevice)
    chip.kSleepTime = sleep_time
    chip.InitConnection()

    chip.Echo(False)
    part_id = retry(chip.ReadPartID, count=100, exception=timeout_decorator.TimeoutError)()
    
    descriptor = GetPartDescriptor(chip_file, part_id)
    logging.info(f"{part_id}, {descriptor}")
    chip.CrystalFrequency = crystal_frequency#12000#khz == 30MHz
    chip.SectorCount = descriptor["SectorCount"]
    chip.RAMSize = descriptor["RAMSize"]
    chip.RAMRange = descriptor["RAMRange"]
    chip.FlashRange = descriptor["FlashRange"]
    chip.RAMStartWrite = descriptor["RAMStartWrite"]
    chip.kCheckSumLocation = 7 #0x0000001c

    if(chip.RAMRange[1]-chip.RAMRange[0] != chip.RAMSize - 1):
        raise ValueError(f"RAM size for {part_id: 0x%x} is wrong")
    print("Setting new baudrate %d"%baudrate)
    chip.ChangeBaudRate(baudrate)
    return chip

def main():
    imagein = "../blinky845.hex"
    chip = SetupChip(9600, 12000, "./lpctools_parts.def")
    # Clear chip, write, read
    success = True
    try:
        if False:
            chip.MassErase()
            # Read and check flash is blank
            image = chip.ReadImage()
            logging.info(f"image length: {len(image)} {image}")
            assert len(image) == 0  #  Test for blank chip
            logging.info("Checking Sectors are blank")
            assert chip.CheckSectorsBlank(0, chip.SectorCount-1)

        expected_data = bytes([0xff]*chip.sector_bytes)
        crc_expected = calc_crc(expected_data)

        if True:
            # Read first sector
            chip.WriteToRam(chip.RAMStartWrite, expected_data)
            sleep(1)
            chip.ResetSerialConnection()
            first_sector = retry(chip.ReadMemory, count=2, exception=(UserWarning, timeout_decorator.TimeoutError))(chip.RAMStartWrite, chip.sector_bytes)
            # first_sector = chip.ReadSector(0)
            assert first_sector == expected_data
            # crc_calculated = chip.ReadCRC(chip.FlashRange[0], chip.sector_bytes)
            crc_read = chip.ReadCRC(0, chip.sector_bytes)
            crc_calculated = calc_crc(first_sector)
            assert crc_read == crc_expected
            assert crc_expected == crc_calculated
            logging.info("RAM CRC check passed")

        if False:
            data = FillDataToFitSector(b"hello world", chip.sector_bytes)
            assert len(data) == chip.sector_bytes
            crc_expected = calc_crc(data)
            chip.WriteBinaryToFlash(data, 0)
            first_sector = chip.ReadSector(0)
            assert first_sector == data
            crc_expected = calc_crc(data)
            # crc_calculated = chip.ReadCRC(chip.FlashRange[0], chip.sector_bytes)
            crc_read = chip.ReadCRC(0, chip.sector_bytes)
            crc_calculated = calc_crc(first_sector)
            assert crc_read == crc_expected
            assert crc_expected == crc_calculated


        if False:
            image = chip.ReadImage()
            print(image)
        # chip.WriteImage(imagein)
    except UserWarning as e:
        print(e)
        success = False
    print(chip)
    assert success

logging.basicConfig()
logging.getLogger().setLevel(logging.DEBUG-2)
main()
