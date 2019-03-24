from . import ISPChip
from timeout_decorator import TimeoutError

class LPC804(ISPChip):
    PageSize = 64
    CRCLocation = 0x000002fc
    CRCValues = {
        "NO_ISP": 0x4e697370,
        "CRP1" : 0x12345678,       
        "CRP2" : 0x87654321,       
        "CRP3" : 0x43218765,       
    }
    NewLine = "\r\n"
    Parity = None
    DataBits = 8
    StopBits = 1
    SyncString = "Synchronized\r\n"
    SyncVerified = "OK\r\n"
    CrystalFrequency = 30000#khz == 30MHz
    PartID = "0x00008454"
    ChipName = "LPC804"

    ReturnCodes = {
        "CMD_SUCCESS"                               : 0x0,
        "INVALID_COMMAND"                           : 0x1,
        "SRC_ADDR_ERROR"                            : 0x2,
        "DST_ADDR_ERROR"                            : 0x3,
        "SRC_ADDR_NOT_MAPPED"                       : 0x4,
        "DST_ADDR_NOT_MAPPED"                       : 0x5,
        "COUNT_ERROR"                               : 0x6,
        "INVALID_SECTOR/INVALID_PAGE"               : 0x7,
        "SECTOR_NOT_BLANK"                          : 0x8,
        "SECTOR_NOT_PREPARED_FOR_WRITE_OPERATION"   : 0x9,
        "COMPARE_ERROR"                             : 0xa,
        "BUSY"                                      : 0xb,
        "PARAM_ERROR"                               : 0xc,
        "ADDR_ERROR"                                : 0xd,
        "ADDR_NOT_MAPPED"                           : 0xe,
        "CMD_LOCKED"                                : 0xf,
        "INVALID_CODE"                              : 0x10,
        "INVALID_BAUD_RATE"                         : 0x11,
        "INVALID_STOP_BIT"                          : 0x12,
        "CODE_READ_PROTECTION_ENABLED"              : 0x13,
        "Unused 1"                                  : 0x14, 
        "USER_CODE_CHECKSUM"                        : 0x15,
        "Unused 2"                                  : 0x16,
        "EFRO_NO_POWER"                             : 0x17,
        "FLASH_NO_POWER"                            : 0x18,
        "Unused 3"                                  : 0x19,
        "Unused 4"                                  : 0x1a,
        "FLASH_NO_CLOCK"                            : 0x1b,
        "REINVOKE_ISP_CONFIG"                       : 0x1c,
        "NO_VALID_IMAGE"                            : 0x1d,
        "FAIM_NO_POWER"                             : 0x1e,
        "FAIM_NO_CLOCK"                             : 0x1f,
    }

    def Write(self, string):
        self.WriteSerial(string + self.NewLine)

    def Unlock(self):
        '''
        Enables Flash Write, Erase, & Go
        '''
        code = 23130
        self.Write("U %d"%(code))

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
        self.Write("J")

    def ReadBootCodeVersion(self):
        self.Write("K")

    def Compare(self, Address1, Address2, NumBytes):
        '''
        Returns if two sections are equal
        '''
        self.Write("M %d %d %d"%(Address1, Address2, NumBytes))

    def ReadUID(self):
        self.Write("N")

    def ReadCRC(self, Address, NumBytes):
        self.Write("S %d %d"%(Address, NumBytes))

    def ReadFlashSig(self):
        self.Write("Z")

    def ReadWriteFAIM(self):
        self.Write("O")

    def InitConnection(self):
        try:
            try:
                self.SyncConnection()
            except (UserWarning, TimeoutError) as w:
                print("Syncronization Failed, trying to connect to running ISP ({})".format(w))
                self.ConnectToRunningISP()
            self.CheckPartType()
        except Exception as e:
            print(e, type(e))
        

    def SyncConnection(self):
        self.Flush()
        self.Write("?")
        FrameIn = self.ReadLine()
        if(FrameIn != self.SyncString):
            #Check for SyncString
            raise UserWarning("Syncronization Failure")

        self.Flush()
        self.Write(self.SyncString)#echo SyncString
        FrameIn = self.ReadLine()#discard echo

        self.Flush()
        self.Write("%d"%self.CrystalFrequency)
        self.ReadLine()#discard echo
        FrameIn = self.ReadLine()#Should be OK\r\n
        
        if(FrameIn != self.SyncVerified):
            raise UserWarning("Syncronization Verification Failure")

        print("Syncronization Successful")
        self.Echo(False)


    def ConnectToRunningISP(self):
        self.Flush()
        self.Echo(False)
        self.Flush()
        self.Echo(False)
        if(self.ReadLine() != self.Return_Codes["CMD_SUCCESS"]):
            raise UserWarning("Reconnection Failure")
        
        self.Flush()

        print("Reconnection Successful")

    def CheckPartType(self):
        self.Flush()
        self.Echo(False)
        self.ReadLine()
        self.Flush()

        self.ReadPartID()
        if(self.ReadLine() != self.Return_Codes["CMD_SUCCESS"]):
            raise UserWarning("Read Part ID Failure")
        PartID = self.ReadLine()

        if(PartID != self.PartID):
            raise UserWarning("{} Expected PartID {}, recieved {}".format(self.ChipName, self.PartID, PartID))

