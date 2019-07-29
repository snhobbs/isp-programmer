from . import NXPChip 

class LPC175_6x(NXPChip):
    ChipName = "LPC175_6x"
    Family = (
        'LPC1769',
        'LPC1768',
        'LPC1767',
        'LPC1766',
        'LPC1765', 
        'LPC1764',
        'LPC1763',
        'LPC1759',
        'LPC1758',
        'LPC1757',
        'LPC1756',
        'LPC1755',
        'LPC1754',
        'LPC1753',        
    )
    CrystalFrequency = 12000#khz == 12MHz
    PartIDs = (
        0x26113F37,
        0x26013F37,
        0x26012837,
        0x26013F33,
        0x26013733,
        0x26011922,
        0x26012033,
        0x25113737,
        0x25013F37,
        0x25011723,
        0x25011722,
        0x25001121,
        0x25001118,
        0x25001110,
    )
    MAXBAUDRATE = 9600
    SectorCount = 512
 
