import math
import zlib
from pycrc.algorithms import Crc


def collection_to_string(arr) -> str:
    """Convert a list of integer character codes to a string."""
    return "".join([chr(ch) for ch in arr])


def CalculateCheckSum(frame) -> int:
    """
    Calculate 2's complement checksum of the sum of frame entries.
    Assumes 'frame' is an iterable of integers.
    """
    csum = 0
    for entry in frame:
        csum += entry
    return (1 << 32) - (csum % (1 << 32))


def nxp_crc32(frame: bytes) -> int:
    """
    Calculate CRC32 using pycrc with standard polynomial.
    Note: polynomial here is 0x104C11DB6, which is non-standard (33 bits).
    """
    polynomial = 0x104C11DB6
    crc = Crc(
        width=32,
        poly=polynomial,
        reflect_in=True,
        xor_in=(1 << 32) - 1,
        reflect_out=True,
        xor_out=0x00,
    )
    crc_calc = crc.bit_by_bit(frame)
    return crc_calc


def calc_crc(frame: bytes):
    """Calculate CRC32 using zlib (fast, standard)."""
    #  0x04C11DB7
    return zlib.crc32(frame, 0)


def calc_sector_count(image, sector_bytes: int) -> int:
    """Calculate number of sectors needed to store the image."""
    return int(math.ceil(len(image) / sector_bytes))
