from . import NXPChip 
from timeout_decorator import TimeoutError

class LPC804(NXPChip):
    ChipName = "LPC804"
    CRCLocation = 0x000002fc
    CRCValues = {
        "NO_ISP": 0x4e697370,
        "CRP1" : 0x12345678,       
        "CRP2" : 0x87654321,       
        "CRP3" : 0x43218765,       
    }
    CrystalFrequency = 30000#khz == 30MHz
    PartIDs = (
        0x00008441,
        0x00008442,
        0x00008444,
        0x00008451,
        0x00008452,
        0x00008454,
        0x00008454,
    )

    SectorCount = 32# or 16 for 16KB flash FIXME

    def Unlock(self):
        '''
        Enables Flash Write, Erase, & Go
        '''
        print("Unlock")
        self.Flush()
        self.GetBufferIn()
        self.Write("U 23130")
        self.Wait()
        resp = self.ReadLine().strip().split('\n')
        code = int(resp[-1])
        if(code != self.ReturnCodes["CMD_SUCCESS"]):
            raise UserWarning("Return Code Failure in Unlock %d"%code)

    def SetBaudRate(self, baudRate, stopBits = 1):
        '''
        Baud Depends of FAIM config, stopbit is 1 or 2
        '''
        self.Write("B {} {}".format(baudRate, stopBits))

    def Echo(self, on=True):
        '''
        ISP echos host when enabled
        '''
        self.Write("A %d"%(on))

    def WriteToRam(self, StartLoc, NumBytes):
        assert(NumBytes%4 == 0)
        self.Write("W %d %d"%(StartLoc, NumBytes))

    def ReadMemory(self, StartLoc, NumBytes):
        self.Write("R %d %d"%(StartLoc, NumBytes))

    def PrepSectorsForWrite(self, StartSector, EndSector):
        self.Write("P %d %d"%(StartSector, EndSector))
        self.Wait()
        resp = self.ReadLine().strip().split('\n')
        code = int(resp[-1])
        if(code != self.ReturnCodes["CMD_SUCCESS"]):
            raise UserWarning("Return Code Failure in Unlock %d"%code)


    def CopyRAMToFlash(self, FlashAddress, RAMAddress, NumBytes):
        self.Write("C %d %d %d"%(FlashAddress, RAMAddress, NumBytes))

    def Go(self, Address, ThumbMode = False):
        '''
        Start executing code at the specified spot
        '''
        mode = ""
        if ThumbMode:
            mode = 'T'
        self.Write("G %d %s"%(Address, mode))

    def EraseSector(self, StartSector, EndSector):
        self.Write("E %d %d"%(StartSector, EndSector))

    def ErasePages(self, StartPage, ErasePage):
        self.Write("X %d %d"%(StartPage, EndPage))

    def BlankCheckSectors(self, StartSector, EndSector):
        '''
        Checks to see if the sector is blank
        '''
        self.Write("I %d %d"%(StartSector, EndSector))

    def ReadPartID(self):
        self.Wait()
        self.Flush()
        self.GetBufferIn()
        self.Write("J")
        self.Wait()
        frame = self.ReadLine().strip()
        code, resp = frame.strip().split("\n")[-2:]
        code = int(code.strip()) 
        if(code != self.ReturnCodes["CMD_SUCCESS"]):
            raise UserWarning("Read Part ID Failure %d"%code)
        return int(resp.strip())

    def ReadBootCodeVersion(self):
        self.Flush()
        self.Write("K")
        self.Wait()
        frame = self.ReadLine().strip()
        resp, code = frame.split("\n")[-2:]
        if(int(resp.strip()) != self.ReturnCodes["CMD_SUCCESS"]):
            raise UserWarning("Failed Reading Boot Code Version")

    def Compare(self, Address1, Address2, NumBytes):
        '''
        Returns if two sections are equal
        '''
        self.Write("M %d %d %d"%(Address1, Address2, NumBytes))

    def ReadUID(self):
        self.GetBufferIn()
        self.Wait()
        self.Write("N")
        self.Wait()
        self.Wait()
        frame = self.ReadLine().strip().split("\n")
        code = int(frame[0].strip())
        if(code != self.ReturnCodes["CMD_SUCCESS"]):
            raise UserWarning("Read UID Failure")
        return " ".join(["0x%08x"%int(n) for n in frame[1:]]) 

    def ReadCRC(self, Address, NumBytes):
        self.Write("S %d %d"%(Address, NumBytes))

    def ReadFlashSig(self):
        self.Write("Z")

    def ReadWriteFAIM(self):
        self.Write("O")

