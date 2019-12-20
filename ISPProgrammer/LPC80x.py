from . import NXPChip 
KILOBYTE = 1024

class LPC80x(NXPChip):
    ChipName = "LPC80x"
    Family = (
        'LPC804',
    )
    #MAXBAUDRATE = 57600
    MAXBAUDRATE = 9600
    CrystalFrequency = 30000#khz == 30MHz
    PartIDs = (
        0x00008040,
        0x00008041,
        0x00008042,
        0x00008043,
        0x00008044,
    )

    SectorCount = 32
    RAMSize = 4*KILOBYTE
    RAMRange = (0x10000000, 0x10001000)
    FlashRange = (0x0, SectorCount*NXPChip.PageSizeBytes*NXPChip.SectorSizePages-1)
    RAMStartWrite = 0x100003A8#the ISP stack starts 
    #assert(FlashRange[1] == 0x00008000-2)
    def ReadFlashSig(*args, **kwargs):
        raise NotImplementedError("804 does not fully support read flash signature")
