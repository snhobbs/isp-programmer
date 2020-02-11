from serial import Serial
from collections import deque
from timeout_decorator import timeout
from time import sleep

class ISPChip(object):
    NewLine = "\r\n"
    def __init__(self, port = "/dev/ttyUSB0", baudrate = 9600):
        self.uart = Serial(port, baudrate, xonxoff = False)
        self.frame = []
        self.DataBufferIn = deque()

    @property
    def BaudRate(self):
        return self.uart.baudrate

    def ChangeBaudRate(self, baudrate):
        self.SetBaudRate(baudrate)
        self.uart.baudrate = baudrate

    def WriteSerial(self, out):
        assert(type(out) == bytes)
        self.uart.write(out)

    def Wait(self, time = 0.004):
        sleep(time)

    def Flush(self):
        self.uart.flush()

    #@timeout(0.25)
    @timeout(1)
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
        self.DataBufferIn.extend(self.uart.read_all())

    def ReadFrame(self):
        '''
        Fill the recieving buffer until
        '''
        fNewFrame = False

        while(len(self.DataBufferIn)):
            ch = self.DataBufferIn.popleft()
            #print(hex(ch), chr(ch))
            self.frame.append(ch)
            if(chr(ch) == self.NewLine[-1]):
                #print("New Frame")
                fNewFrame = True
                break
        return fNewFrame

    def Check(self, *args, **kwargs):
        raise NotImplementedError

    def InitConnection(self, *args, **kwargs):
        raise NotImplementedError
