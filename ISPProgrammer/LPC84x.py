from . import NXPChip 
KILOBYTE = 1024
class LPC84x(NXPChip):
    ChipName = "LPC84x"
    Family = (
        'LPC845', 
        'LPC844',         
    )
    #MAXBAUDRATE = 460800
    #MAXBAUDRATE = 115200
    MAXBAUDRATE = 230400

    #MAXBAUDRATE = 57600
    CrystalFrequency = 30000#khz == 30MHz
    #CrystalFrequency = 12000#khz == 30MHz
    #CrystalFrequency = 15000#khz == 30MHz
    PartIDs = (
        0x00008441,
        0x00008442,
        0x00008444,
        0x00008451,
        0x00008452,
        0x00008454,
        0x00008454,
    )

    SectorCount = 64
    RAMSize = 16*KILOBYTE
    RAMRange = (0x10000000, 0x10004000)
    FlashRange = (0x0, SectorCount*NXPChip.PageSizeBytes*NXPChip.SectorSizePages-1)
    RAMStartWrite = 0x10000800#the ISP stack starts 
    #StartExecution = 0x0F000000

    assert(FlashRange[1] == 0x00010000-1)
    assert(RAMRange[1]-RAMRange[0] == RAMSize)

