from . import ISPChip
from timeout_decorator import TimeoutError
from pprint import pprint
NXPReturnCodes = {
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

class NXPChip(ISPChip):
    PageSizeBytes = 64
    SectorSizePages = 16
    MaxByteTransfer = 1024
    
    NewLine = "\r\n"
    Parity = None
    DataBits = 8
    StopBits = 1
    SyncString = "Synchronized\r\n"
    SyncVerified = "OK\r\n"
    ReturnCodes = NXPReturnCodes 
    CRCLocation = 0x000002fc

    CRCValues = {
        "NO_ISP": 0x4e697370,
        "CRP1" : 0x12345678,       
        "CRP2" : 0x87654321,       
        "CRP3" : 0x43218765,       
    }

    @classmethod
    def GetErrorCodeName(cls, code):
        code = int(code)
        for item in cls.ReturnCodes.items():
            if code == item[1]:
                return item[0]
        return "Not Found"

    def GetReturnCode(self, CallLoc = ""):
        '''
        Get a return code with no response
        '''
        self.Wait()
        resp = self.ReadLine().strip().split('\n')
        assert(len(resp) == 1)
        code = int(resp[0])
        if(code != self.ReturnCodes["CMD_SUCCESS"]):
            raise UserWarning("Return Code Failure in {} {}".format(CallLoc, self.GetErrorCodeName(code)))

    def Write(self, string):
        if type(string) != bytes:
            out = bytes(string, encoding = "utf-8")
        else:
            out = string
        self.WriteSerial(out)
        #print("Write:", out, bytes(self.NewLine, encoding = "utf-8"))
        self.WriteSerial(bytes(self.NewLine, encoding = "utf-8"))

    def Unlock(self):
        '''
        Enables Flash Write, Erase, & Go
        '''
        self.ClearBuffer()
        self.Write("U 23130")
        self.GetReturnCode("Unlock")

    def SetBaudRate(self, baudRate, stopBits = 1):
        '''
        Baud Depends of FAIM config, stopbit is 1 or 2
        '''
        self.Write("B {} {}".format(baudRate, stopBits))
        self.GetReturnCode("Set Baudrate")

    def Echo(self, on=True):
        '''
        ISP echos host when enabled
        '''
        self.Write("A %d"%(on))
        self.GetReturnCode("Set Echo")

    def WriteToRam(self, StartLoc, Data):
        WordSize = 4
        assert(len(Data)%4 == 0)
        assert(StartLoc+len(Data) < self.RAMRange[1] and StartLoc >= self.RAMRange[0])
        
        print("Write to RAM %d bytes"%len(Data))
        i = 0
        while i < len(Data):
            self.Write("W %d %d"%(StartLoc + i, WordSize))
            self.GetReturnCode("Write to RAM")#get confirmation
            self.Write(Data[i:i+WordSize])#Stream data after confirmation
            i+=WordSize
        self.Write("\r\n")
        self.Read()
        self.ClearBuffer()

    def ReadMemory(self, StartLoc, NumBytes):
        assert(NumBytes%4 == 0)
        #assert(StartLoc+NumBytes < self.RAMRange[1] and StartLoc >= self.RAMRange[0])
        WordSize = 4
        print("ReadMemory")
        
        i = 0
        out = []
        self.Flush()
        self.Read()
        self.ClearBuffer()
        self.Flush()

        while i < NumBytes:
            self.Write("R %d %d"%(StartLoc + i, WordSize))
            #self.GetReturnCode("Read Memory")
            self.Wait()
            self.Read()
            #self.Flush()
            i+=WordSize
            assert(i%4 == 0)
        try:
            i = 0
            while(True):
                i+=1
                resp = self.ReadLine().strip()
                respBytes = bytes(resp, encoding = "utf-8")
                print(i, "Response", (respBytes), len(respBytes), ":", *respBytes)
                out.extend(respBytes)#get confirmation
        except TimeoutError:
            pass
        print(len(list(out)), NumBytes)
        pprint(list(out))
        assert(len(out) == NumBytes)
        return out

    def PrepSectorsForWrite(self, StartSector, EndSector):
        self.Write("P %d %d"%(StartSector, EndSector))
        self.GetReturnCode("Prep Sectors")

    def CopyRAMToFlash(self, FlashAddress, RAMAddress, NumBytes):
        assert(RAMAddress+NumBytes < self.RAMRange[1] and RAMAddress >= self.RAMRange[0])
        assert(FlashAddress + NumBytes < self.FlashRange[1] and FlashAddress >= self.FlashRange[0])

        assert(FlashAddress%64 == 0)
        assert(RAMAddress%4 == 0)

        self.Write("C %d %d %d"%(FlashAddress, RAMAddress, NumBytes))
        #self.Wait(2)
        self.GetReturnCode("Copy RAM To Flash")

    def Go(self, Address, ThumbMode = False):
        '''
        Start executing code at the specified spot
        '''
        mode = ""
        if ThumbMode:
            mode = 'T'
        self.Write("G %d %s"%(Address, mode))
        self.GetReturnCode("Go")

    def EraseSector(self, StartSector, EndSector):
        self.Write("E %d %d"%(StartSector, EndSector))
        self.GetReturnCode("Erase Sectors")

    def ErasePages(self, StartPage, ErasePage):
        self.Write("X %d %d"%(StartPage, EndPage))
        self.GetReturnCode("Erase Pages")

    def BlankCheckSectors(self, StartSector, EndSector):
        '''
        Checks to see if the sector is blank
        '''
        self.Write("I %d %d"%(StartSector, EndSector))
        #self.Wait()
        self.GetReturnCode("Blank Check Sectors")

    def ReadPartID(self):
        #self.Wait()
        self.Flush()
        self.ClearBuffer()
        self.Write("J")
        self.GetReturnCode("Blank Check Sectors")
        resp = self.ReadLine()
        return int(resp)

    def ReadBootCodeVersion(self):
        '''
        LPC84x sends a 0x1a first for some reason. Also the boot version seems to be Minor then Major not like the docs say
        '''
        #self.Wait()
        self.Flush()

        self.Write("K")
        #self.Wait()
        self.GetReturnCode("Read Bootcode Version")
        Minor = self.ReadLine().strip()
        Major = self.ReadLine().strip()
        return "%d.%d"%(int(Major), int(Minor))

    def Compare(self, Address1, Address2, NumBytes):
        '''
        Returns if two sections are equal
        '''
        self.Write("M %d %d %d"%(Address1, Address2, NumBytes))
        self.GetReturnCode("Compare")

    def ReadUID(self):
        self.ClearBuffer()
        #self.Wait()
        self.Write("N")
        self.GetReturnCode("Read UID")
        UID0 = self.ReadLine().strip()
        UID1 = self.ReadLine().strip()
        UID2 = self.ReadLine().strip()
        UID3 = self.ReadLine().strip()
        return " ".join(["0x%08x"%int(uid) for uid in [UID0, UID1, UID2, UID3]]) 

    def ReadCRC(self, Address, NumBytes):
        self.Write("S %d %d"%(Address, NumBytes))
        self.GetReturnCode("Read CRC")
        return self.ReadLine()

    def ReadFlashSig(self, StartAddress = 0, EndAddress = 0xffff, WaitStates = 2, Mode = 0):
        assert(StartAddress < EndAddress)
        self.Write("Z %d %d %d %d"%(StartAddress, EndAddress, WaitStates, Mode))
        self.GetReturnCode("Read Flash Sig")
        return self.ReadLine()

    def ReadWriteFAIM(self):
        self.Write("O")
        self.GetReturnCode("Read Write FAIM")

    def InitConnection(self):
        try:
            try:
                self.SyncConnection()
            except (UserWarning, TimeoutError) as w:
                pass

            self.Wait()
            self.Flush()
            print("Connect to running ISP")
            self.ConnectToRunningISP()
            print("Reconnection Successful")

            self.CheckPartType()
            uid = self.ReadUID()
            print("Part UID: %s"%uid)
            bootCodeVersion = self.ReadBootCodeVersion()
            print("Boot Code Version: %s"%bootCodeVersion)
            self.SetBaudRate(self.BaudRate)
            print("Buadrate set to %d"%self.BaudRate)
            flashSig = self.ReadFlashSig()
            print("Flash Signiture: %s"%flashSig)
        except Exception as e:
            print(e, type(e))
            raise
        
    def SyncConnection(self):
        self.Wait()
        self.Flush()
        self.Write("?")
        FrameIn = self.ReadLine()

        #print(FrameIn)
        if(FrameIn.strip() != self.SyncString.strip()):
            #Check for SyncString
            raise UserWarning("Syncronization Failure")

        self.Flush()
        self.Write(self.SyncString)#echo SyncString
        FrameIn = self.ReadLine()#discard echo

        self.Flush()
        self.Write("%d"%self.CrystalFrequency)
        self.ReadLine()#discard echo
        FrameIn = self.ReadLine()#Should be OK\r\n
        
        if(FrameIn.strip() != self.SyncVerified.strip()):
            raise UserWarning("Syncronization Verification Failure")

        print("Syncronization Successful")
        self.Echo(False)

    def ConnectToRunningISP(self):
        self.Wait()
        self.Flush()
        self.ClearBuffer()
        try:
            self.ReadLine()
        except TimeoutError:
            pass
        try:
            self.Write(self.NewLine)
            self.Read()
            #self.ReadLine()
            self.Echo(False)
        except ValueError:
            pass

    def CheckPartType(self):
        self.Echo(False)
        self.Wait()
        self.Flush()
        PartID = self.ReadPartID()
        if(PartID not in self.PartIDs):
            raise UserWarning("%s recieved 0x%08x"%(self.ChipName, PartID))
        
        print("Part Check Successful, 0x%08x"%(PartID))

    def WriteFlashSector(self, sector, Data):
        RAMAddress = self.RAMStartWrite
        sectorSizeBytes = self.PageSizeBytes*self.SectorSizePages
        FlashAddress = self.FlashRange[0] + sector*sectorSizeBytes
        print("Writing Sector: %d\nFlash Address: %d\nRAM Address: %d\n"%(sector, FlashAddress, RAMAddress))

        self.BlankCheckSectors(sector, sector)
        self.WriteToRam(RAMAddress, Data)

        self.PrepSectorsForWrite(sector, sector)
        self.CopyRAMToFlash(FlashAddress, RAMAddress, sectorSizeBytes)
        self.Compare(FlashAddress, RAMAddress, sectorSizeBytes)
        print("Compare Sucessful")

        '''
        Read Memory and compare it to what was written
        '''
        #resp = self.ReadMemory(FlashAddress, len(Data))

        #DataRead = bytes(resp[0], encoding = "utf-8")
        #print(Data, DataRead)
        #if(Data != DataRead):
        #    raise UserWarning("RAM Write/Read Check Failed")

        #self.ReadFlashSig(StartAddress = 0, EndAddress = 0xffff, WaitStates = 2, Mode = 0)


    def WriteImage(self, ImageFile = None):
        self.Unlock()
        sector = 0
        writeCount = 0

        SectorBytes = self.SectorSizePages*self.PageSizeBytes
        with open(ImageFile, 'rb') as f:
            prog = f.read()
            assert(SectorBytes%4 == 0)
            print("Program Length: ", len(prog))
            while(True):
                print("Sector ", sector)
                DataChunk = prog[writeCount : writeCount + SectorBytes]
                if(not len(DataChunk)):
                    break
                assert(sector < self.SectorCount)
                self.PrepSectorsForWrite(sector, sector)
                self.EraseSector(sector, sector)
                self.BlankCheckSectors(sector, sector)

                print("Write Flash")
                self.WriteFlashSector(sector, DataChunk)
                print("Flash Written")

                writeCount += SectorBytes
                sector += 1

    def MassErase(self):
        self.Wait()
        self.ClearBuffer()
        self.Unlock()
        self.PrepSectorsForWrite(0, self.SectorCount - 1)
        self.EraseSector(0, self.SectorCount - 1)
        print("Checking Sectors are blank")
        self.BlankCheckSectors(0, self.SectorCount -1)

