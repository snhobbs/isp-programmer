import math
import logging
from pycrc.algorithms import Crc
import functools
import zlib
import timeout_decorator

def collection_to_string(arr):
    return "".join([chr(ch) for ch in arr])


# 2s compliment of checksum
def CalculateCheckSum(frame) -> int:
    csum = 0
    for entry in frame:
        csum += entry
    return (1<<32) - (csum % (1<<32))


def Crc32(frame: bytes) -> int:
    # CRC32
    polynomial = 0x104c11db6
    crc = Crc(width=32, poly=polynomial, reflect_in=True,
              xor_in=(1<<32)-1, reflect_out=True, xor_out=0x00)
    crc_calc = crc.bit_by_bit(frame)
    return crc_calc


def calc_crc(frame: bytes):
    return zlib.crc32(frame, 0)
    # return Crc32(frame)


def retry(_func=None, *, count=2, exception=timeout_decorator.TimeoutError, raise_on_fail=True):
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            value = None
            for i in range(1, count+1):
                try:
                    assert func
                    value = func(*args, **kwargs)
                    break
                except exception as e:
                    logging.warning(f"{e}: Retry {i}/{count}")
                    if i >= count and raise_on_fail:
                        raise UserWarning(f"{_func} retry exceeded {count}")
            return value
        return wrapper
    if _func is None:
        return decorator
    return decorator(_func)


def calc_sector_count(image, sector_bytes):
    return int(math.ceil(len(image)/sector_bytes))
