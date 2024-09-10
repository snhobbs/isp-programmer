import math
import zlib
from pycrc.algorithms import Crc


def collection_to_string(arr):
    return "".join([chr(ch) for ch in arr])


# 2s compliment of checksum
def CalculateCheckSum(frame) -> int:
    csum = 0
    for entry in frame:
        csum += entry
    return (1 << 32) - (csum % (1 << 32))


def Crc32(frame: bytes) -> int:
    # CRC32
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
    return zlib.crc32(frame, 0)
    # return Crc32(frame)


def calc_sector_count(image, sector_bytes):
    return int(math.ceil(len(image) / sector_bytes))
