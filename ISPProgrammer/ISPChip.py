from collections import deque
from serial import Serial
from timeout_decorator import timeout
from typing import List, Deque
kTimeout = 1
class IODevice:
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

class MockUart(IODevice):
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
    def __init__(self, port: str = "/dev/ttyUSB0", baudrate: int = 9600):
        self.uart = Serial(port, baudrate, xonxoff=False)
    def ReadByte(self):
        return self.uart.read_all()
    def ReadAll(self):
        return self.uart.read_all()
    def Write(self, arr: bytes):
        assert(type(arr) is bytes)
        self.uart.write(arr)
    def Flush(self):
        self.uart.flush()
    def SetBaudrate(self, baudrate: int) -> None:
        self.uart.baudrate = baudrate
    def GetBaudrate(self):
        return self.uart.baudrate

class ISPChip:
    kNewLine = "\r\n"
    _echo = False

    @classmethod
    def SetEcho(self, enable):
        self._echo = enable

    @classmethod
    def GetEcho(self):
        return self._echo

    def __init__(self, iodevice: IODevice):
        self.iodevice = iodevice
        self.frame : List[int] = list()
        self.data_buffer_in : Deque[int] = deque()

    @property
    def baud_rate(self):
        return self.iodevice.GetBaudrate()

    def ChangeBaudRate(self, baudrate: int):
        self.SetBaudRate(baudrate)
        self.iodevice.SetBaudrate(baudrate)

    def WriteSerial(self, out: bytes) -> None:
        assert(type(out) is bytes)
        self.iodevice.Write(out)
        if self.GetEcho():
          print("<", out, ">")

    def Flush(self):
        self.iodevice.Flush()

    @timeout(kTimeout)
    def ReadLine(self):
        while not self.ReadFrame():
            self.Read()
        return self.GetBufferIn()

    #def Write(self, *args, **kwargs):
    #    raise NotImplementedError

    def GetBufferIn(self):
        frame = "".join([chr(ch) for ch in self.frame])
        self.frame.clear()
        return frame

    def ClearBuffer(self):
        self.data_buffer_in.clear()
        self.frame.clear()

    def Read(self):
        data_in = self.iodevice.ReadAll()
        if self.GetEcho():
          if len(data_in):
            print("[", data_in, "]")
        self.data_buffer_in.extend(data_in)

    def ReadFrame(self):
        '''
        Fill the recieving buffer until
        '''
        f_new_frame = False

        while len(self.data_buffer_in) != 0:
            ch = self.data_buffer_in.popleft()
            #print(hex(ch), chr(ch))
            self.frame.append(ch)
            if chr(ch) == self.kNewLine[-1]:
                #print("New Frame")
                f_new_frame = True
                break
        return f_new_frame

    def Check(self, *args, **kwargs):
        raise NotImplementedError

    def InitConnection(self):
        raise NotImplementedError
