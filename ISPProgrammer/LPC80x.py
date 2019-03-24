from . import NXPChip 

class LPC80x(NXPChip):
    ChipName = "LPC80x"
    Family = (
        'LPC804',
    )
    CrystalFrequency = 30000#khz == 30MHz
    PartIDs = (
        0x00008040,
        0x00008041,
        0x00008042,
        0x00008043,
        0x00008044,
    )

    SectorCount = 32
