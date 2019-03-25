from . import NXPChip 

class LPC84x(NXPChip):
    ChipName = "LPC84x"
    Family = (
        'LPC845', 
        'LPC844',         
    )
    CrystalFrequency = 30000#khz == 30MHz
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
