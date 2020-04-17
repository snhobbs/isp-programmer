from serial import Serial
from collections import deque
import typing
from timeout_decorator import timeout
from time import sleep

class IODevice(object):
    pass

class MockUart(object):
    def __init__(self, port : str = "/dev/ttyUSB0", baudrate : int = 9600):
        self.baudrate = baudrate
        self.port = port
    def ReadByte(self):
        return 0x00
    def ReadAll(self):
        return bytes(0x00)
    def Write(self, arr : bytes):
        pass
    def Flush(self):
        pass
    def SetBaudrate(self, baudrate : int) -> None:
        self.baudrate = baudrate
    def GetBaudrate(self):
        return self.baudrate

class UartDevice(IODevice):
    def __init__(self, port : str = "/dev/ttyUSB0", baudrate: int = 9600):
        self.uart = Serial(port, baudrate, xonxoff = False)
    def ReadByte(self):
        return self.uart.read_all()
    def ReadAll(self):
        return self.uart.read_all()
    def Write(self, arr : bytes):
        self.uart.write(arr)
    def Flush(self):
        self.uart.flush()
    def SetBaudrate(self, baudrate : int) -> None:
        self.uart.baudrate = baudrate
    def GetBaudrate(self):
        return self.uart.baudrate

class ISPChip(object):
    kNewLine = "\r\n"
    def __init__(self, iodevice : IODevice):
        self.iodevice = iodevice
        self.frame = []
        self.DataBufferIn = deque()

    @property
    def BaudRate(self):
        return self.iodevice.GetBaudrate()

    def ChangeBaudRate(self, baudrate : int):
        self.SetBaudRate(baudrate)
        self.iodevice.SetBaudrate(baudrate)

    def WriteSerial(self, out : bytes) -> None:
        self.iodevice.Write(out)

    def Flush(self):
        self.iodevice.Flush()

    @timeout(0.25)
    def ReadLine(self):
        while(not self.ReadFrame()):
            self.Read()
        return self.GetBufferIn()

    def Write(self, *args, **kwargs):
        raise NotImplementedError

    def GetBufferIn(self):
        frame = "".join([chr(ch) for ch in self.frame])
        self.frame.clear()
        return frame

    def ClearBuffer(self):
        self.DataBufferIn.clear()
        self.frame.clear()

    def Read(self):
        data_in = self.iodevice.ReadAll()
        #if len(data_in):
        #    print(data_in.decode("utf-8"))
        self.DataBufferIn.extend(data_in)

    def ReadFrame(self):
        '''
        Fill the recieving buffer until
        '''
        fNewFrame = False

        while(len(self.DataBufferIn)):
            ch = self.DataBufferIn.popleft()
            #print(hex(ch), chr(ch))
            self.frame.append(ch)
            if(chr(ch) == self.kNewLine[-1]):
                #print("New Frame")
                fNewFrame = True
                break
        return fNewFrame

    def Check(self, *args, **kwargs):
        raise NotImplementedError

    def InitConnection(self, *args, **kwargs):
        raise NotImplementedError

