from serial import Serial

kTimeout = 1


class IODevice:
    ''' Generic for a byte IO device'''
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


class MockUart(IODevice):
    '''Mock IO device for testing'''
    def __init__(self, port: str = "/dev/ttyUSB0", baudrate: int = 9600):
        self.baudrate = baudrate
        self.port = port

    def read_byte(self):
        return 0x00

    def read_all(self):
        return bytes(0x00)

    def SetBaudrate(self, baudrate: int) -> None:
        self.baudrate = baudrate

    def GetBaudrate(self):
        return self.baudrate


class UartDevice(IODevice):
    '''Serial IO device wrapper around pyserial'''
    def __init__(self, port: str = "/dev/ttyUSB0", baudrate: int = 9600):
        self.uart = Serial(port, baudrate, xonxoff=False)
        self.read = self.uart.read
        self.read_all = self.uart.read_all
        self.read_byte = self.uart.read
        self.flush = self.uart.flush

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
