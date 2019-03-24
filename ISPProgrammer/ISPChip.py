from serial import Serial
from collections import deque
from timeout_decorator import timeout
from time import sleep
'''
class Serial(object):
    
    def read_all(self):
        return self.uart.read_all()

    def run(self):
        while True:
            try:
                frame = self.sock.recv(MAX_SEND_SIZE)
                self.uart.write(frame)
            except (BlockingIOError):
                pass
            try:
                self.sock.send(self.read_all())
            except (BlockingIOError):
                pass
'''
            


class ISPChip(object):
    NewLine = "\r\n"
    def __init__(self, port = "/dev/ttyUSB0", baudrate = 9600):
        self.uart = Serial(port, baudrate, xonxoff = False)
        self.bufferIn = deque()

    def WriteSerial(self, string):
        out = bytes(string, encoding="utf-8")
        self.uart.write(out)

    def Wait(self):
        sleep(0.05)

    def Flush(self):
        self.uart.flush()

    @timeout(0.25)
    def ReadLine(self):
        while(not self.Read()):
            continue
        return self.GetBufferIn()

    def Write(self, *args, **kwargs):
        raise NotImplementedError

    def GetBufferIn(self):
        frame = []
        while(len(self.bufferIn)):
            frame.append(self.bufferIn.popleft())
        return "".join([chr(p) for p in frame])

    def Read(self):
        '''
        Fill the recieving buffer until 
        '''
        fNewFrame = False

        chIn = self.uart.read_all()
        for ch in chIn:
            #print(hex(ch))
            self.bufferIn.append(ch)
            if(chr(ch) == self.NewLine[-1]):
                fNewFrame = True
        return fNewFrame
         
    def Check(self, *args, **kwargs):
        raise NotImplementedError

    def InitConnection(self, *args, **kwargs):
        raise NotImplementedError
