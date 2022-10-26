import logging
from time import sleep
import timeout_decorator
from isp_programmer import tools, UartDevice, GetPartDescriptor, MassErase, \
    InitConnection, ISPConnection, ReadImage, WriteBinaryToFlash, \
    ChipDescription, ReadSector

retry = tools.retry
calc_crc = tools.calc_crc


def SetupChip(baudrate: int, crystal_frequency: int, chip_file: str, sleep_time: float = 1):
    device = "/dev/ttyUSB0"
    kStartingBaudRate = baudrate
    iodevice = UartDevice(device, baudrate=kStartingBaudRate)
    isp = ISPConnection(iodevice)
    #print(baudrate, device, crystal_frequency, chip_file)

    InitConnection(isp)
    part_id = retry(isp.ReadPartID, count=100, exception=timeout_decorator.TimeoutError)()

    descriptor = GetPartDescriptor(chip_file, part_id)
    logging.info(f"{part_id}, {descriptor}")
    chip = ChipDescription(descriptor)
    chip.CrystalFrequency = crystal_frequency#12000#khz == 30MHz

    print("Setting new baudrate %d"%baudrate)
    isp.baud_rate = baudrate
    return isp, chip

def main(imagein):
    isp, chip = SetupChip(9600, 12000, "./lpctools_parts.def")
    # Clear chip, write, read

    MassErase(isp, chip)
    # Read and check flash is blank
    image = ReadImage(isp, chip)
    logging.info(f"image length: {len(image)} {image}")
    assert len(image) == 0  #  Test for blank chip
    logging.info("Checking Sectors are blank")
    assert isp.CheckSectorsBlank(0, chip.SectorCount-1)

    expected_data = bytes([0xff]*chip.sector_bytes)
    crc_expected = calc_crc(expected_data)

    # Read first sector
    sleep(0.1)
    isp.WriteToRam(chip.RAMStartWrite, expected_data)
    sleep(0.1)
    isp.reset()
    first_sector = retry(isp.ReadMemory, count=2, exception=(UserWarning, timeout_decorator.TimeoutError))(chip.RAMStartWrite, chip.sector_bytes)
    # first_sector = chip.ReadSector(0)
    assert first_sector == expected_data
    # crc_calculated = chip.ReadCRC(chip.FlashRange[0], chip.sector_bytes)
    crc_read = isp.ReadCRC(0, chip.sector_bytes)
    crc_calculated = calc_crc(first_sector)
    assert crc_expected == crc_calculated
    assert crc_read == crc_expected
    logging.info("RAM CRC check passed")

    data = b"hello world"
    data += bytes([0xff] *(chip.sector_bytes - len(data)))
    assert len(data) == chip.sector_bytes
    crc_expected = calc_crc(data)
    WriteBinaryToFlash(isp, chip, data, 0)
    first_sector = ReadSector(isp, chip, 0)
    assert first_sector == data
    crc_expected = calc_crc(data)
    # crc_calculated = chip.ReadCRC(chip.FlashRange[0], chip.sector_bytes)
    crc_read = isp.ReadCRC(0, chip.sector_bytes)
    crc_calculated = calc_crc(first_sector)
    assert crc_read == crc_expected
    assert crc_expected == crc_calculated

    image = ReadImage(isp, chip)
    print(image)
    # chip.WriteImage(imagein)
    print(chip)


if __name__ == "__main__":
    logging.basicConfig()
    logging.getLogger().setLevel(logging.DEBUG-2)
    # imagein = "../blinky845.hex"
    imagein = "../blinky845MAX.hex"
    main(imagein)
