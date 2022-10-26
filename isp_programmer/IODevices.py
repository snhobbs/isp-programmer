from serial import Serial

kTimeout = 1


class IODevice:
    ''' Generic for a byte IO device'''
    def ReadByte(self):
        pass

    def ReadAll(self):
        pass

    def Write(self, arr: bytes):
        pass

    def Flush(self):
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

    def ReadByte(self):
        return 0x00

    def ReadAll(self):
        return bytes(0x00)

    def SetBaudrate(self, baudrate: int) -> None:
        self.baudrate = baudrate

    def GetBaudrate(self):
        return self.baudrate


class UartDevice(IODevice):
    '''Serial IO device wrapper around pyserial'''
    def __init__(self, port: str = "/dev/ttyUSB0", baudrate: int = 9600):
        self.uart = Serial(port, baudrate, xonxoff=False)

    def ReadByte(self):
        return self.uart.read()

    def ReadAll(self) -> bytes:
        return self.uart.read_all()

    def Write(self, arr: bytes):
        assert isinstance(arr, bytes)
        self.uart.write(arr)

    def Flush(self):
        self.uart.flush()

    def SetBaudrate(self, baudrate: int) -> None:
        self.uart.baudrate = baudrate

    def GetBaudrate(self) -> int:
        return self.uart.baudrate

    def ReadLine(self):
        return bytes(self.uart.readline()).decode("utf-8")
