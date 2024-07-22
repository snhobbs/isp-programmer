import logging
from serial import Serial

kTimeout = 1

_log = logging.getLogger("isp_programmer")


class IODevice:
    """Generic for a byte IO device"""

    def read_byte(self):
        pass

    def read_all(self):
        pass

    def write(self, arr: bytes):
        pass

    def flush(self):
        pass

    def SetBaudrate(self, baudrate: int) -> None:
        pass

    def GetBaudrate(self):
        pass

    def ReadLine(self):
        pass

    def disconnect(self):
        pass


class MockUart(IODevice):
    """Mock IO device for testing"""

    def __init__(self, port: str = "/dev/ttyUSB0", baudrate: int = 9600):
        self.baudrate = baudrate
        self.port = port

    def disconnect(self):
        pass

    def read_byte(self):
        return 0x00

    def read_all(self):
        return bytes(0x00)

    def SetBaudrate(self, baudrate: int) -> None:
        self.baudrate = baudrate

    def GetBaudrate(self):
        return self.baudrate


class UartDevice(IODevice):
    """Serial IO device wrapper around pyserial"""

    def __init__(
        self,
        port: str = "/dev/ttyUSB0",
        baudrate: int = 9600,
        timeout: float = kTimeout,
    ):
        _log.debug("connect serial")
        self.uart = Serial(port, baudrate, xonxoff=False, timeout=timeout)

    def disconnect(self):
        _log.debug("disconnect serial")
        try:
            self.uart.close()
            del self.uart
        except AttributeError:
            pass

    def __del__(self):
        self.disconnect()

    def read(self, *args, **kwargs):
        return self.uart.read(*args, **kwargs)

    def flush(self, *args, **kwargs):
        return self.uart.flush(*args, **kwargs)

    def read_byte(self, *args, **kwargs):
        return self.uart.read_byte(*args, **kwargs)

    def read_all(self, *args, **kwargs):
        return self.uart.read_all(*args, **kwargs)

    def write(self, arr: bytes):
        assert isinstance(arr, bytes)
        self.uart.write(arr)

    def SetBaudrate(self, baudrate: int) -> None:
        self.uart.baudrate = baudrate

    def GetBaudrate(self) -> int:
        return self.uart.baudrate

    def ReadLine(self):
        line = self.uart.readline()
        try:
            return bytes(line).decode("utf-8")
        except UnicodeDecodeError:
            raise TimeoutError
