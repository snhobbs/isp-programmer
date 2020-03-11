from . import ISPChip
from time import sleep
from timeout_decorator import TimeoutError, timeout
import zlib

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
        "NoStatusResponse"                          : 0xff,
    }

class NXPChip(ISPChip):
    kWordSize = 4
    kPageSizeBytes = 64
    SectorSizePages = 16
    MaxByteTransfer = 1024
    NewLine = "\r\n"
    StatusRespLength = len(NewLine) + 1
    Parity = None
    DataBits = 8
    StopBits = 1
    SyncString = "Synchronized"+NewLine
    SyncVerified = "OK"+NewLine
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

    def GetReturnCode(self):
        for i in range(10):
            self.Wait()
            try:
                resp = self.ReadLine().strip()
                return int(resp)
            except ValueError:
                pass
        return self.ReturnCodes["NoStatusResponse"]

    def AssertReturnCode(self, CallLoc = ""):
        '''
        Get a return code with no response
        '''
        code = self.GetReturnCode()
        if(code != self.ReturnCodes["CMD_SUCCESS"]):
            raise UserWarning("Return Code Failure in {} {} {}".format(CallLoc, self.GetErrorCodeName(code), code))

    def Write(self, string):
        if type(string) != bytes:
            out = bytes(string, encoding = "utf-8")
        else:
            out = string
        self.WriteSerial(out)
        self.WriteSerial(bytes(self.NewLine, encoding = "utf-8"))

    def Unlock(self):
        '''
        Enables Flash Write, Erase, & Go
        '''
        #self.Wait()
        self.ClearBuffer()
        self.Write("U 23130")
        self.AssertReturnCode("Unlock")

    def SetBaudRate(self, baudRate, stopBits = 1):
        '''
        Baud Depends of FAIM config, stopbit is 1 or 2
        '''
        self.Write("B {} {}".format(baudRate, stopBits))
        self.AssertReturnCode("Set Baudrate")

    def Echo(self, on=True):
        '''
        ISP echos host when enabled
        '''
        if on:
            self.Write("A 1")
        else:
            self.Write("A 0")
        try:
            self.AssertReturnCode("Set Echo")
        except UserWarning as e:
            try:
                self.AssertReturnCode("Set Echo")
            except TimeoutError:
                raise e

    def WriteToRam(self, StartLoc, Data):
        assert(len(Data)%self.kWordSize == 0)
        assert(StartLoc+len(Data) < self.RAMRange[1] and StartLoc >= self.RAMRange[0])

        print("Write to RAM %d bytes"%len(Data))
        i = 0
        #while i < len(Data):
        #    self.Write("W %d %d"%(StartLoc + i, kWordSize))
        #    self.AssertReturnCode("Write to RAM")#get confirmation
        #    self.Write(Data[i:i+kWordSize])#Stream data after confirmation
        #    i+=kWordSize

        self.Write("W %d %d"%(StartLoc, len(Data)))
        self.AssertReturnCode("Write to RAM")#get confirmation
        self.Write(Data)#Stream data after confirmation

        self.Write(self.NewLine)
        self.Read()
        self.ClearBuffer()

    @timeout(4)
    def ReadMemory(self, StartLoc, NumBytes):
        assert(NumBytes%self.kWordSize == 0)
        #assert(StartLoc+NumBytes < self.RAMRange[1] and StartLoc >= self.RAMRange[0])
        print("ReadMemory")

        i = 0
        out = []
        self.Flush()
        self.Read()
        self.ClearBuffer()
        self.Flush()

        print("R %d %d"%(StartLoc, NumBytes))
        self.Write("R %d %d"%(StartLoc, NumBytes))

        while(len(self.DataBufferIn) < NumBytes + self.StatusRespLength):
            self.Read()
        #self.Wait()
        self.AssertReturnCode("Read Memory")

        data = []
        while(len(self.DataBufferIn)):
            ch = self.DataBufferIn.popleft()
            data.append(ch)

        assert(len(data) == NumBytes)
        return bytes(data)

    def PrepSectorsForWrite(self, StartSector, EndSector):
        self.Write("P %d %d"%(StartSector, EndSector))
        self.AssertReturnCode("Prep Sectors")

    def CopyRAMToFlash(self, FlashAddress, RAMAddress, NumBytes):
        assert(RAMAddress+NumBytes < self.RAMRange[1] and RAMAddress >= self.RAMRange[0])
        assert(FlashAddress + NumBytes < self.FlashRange[1] and FlashAddress >= self.FlashRange[0])

        assert(FlashAddress%self.kPageSizeBytes == 0)
        assert(RAMAddress%self.kWordSize == 0)

        self.Write("C %d %d %d"%(FlashAddress, RAMAddress, NumBytes))
        #self.Wait(2)
        self.AssertReturnCode("Copy RAM To Flash")

    def Go(self, Address, ThumbMode = False):
        '''
        Start executing code at the specified spot
        '''
        mode = ""
        if ThumbMode:
            mode = 'T'
        self.Write("G %d %s"%(Address, mode))
        while(True):
            try:
                self.AssertReturnCode("Go")
            except TimeoutError:
                pass
            break

    def EraseSector(self, StartSector, EndSector):
        self.Write("E %d %d"%(StartSector, EndSector))
        self.AssertReturnCode("Erase Sectors")

    def ErasePages(self, StartPage, ErasePage):
        self.Write("X %d %d"%(StartPage, EndPage))
        self.AssertReturnCode("Erase Pages")

    def AreSectorsBlank(self, StartSector, EndSector):
        try:
            self.BlankCheckSectors(StartSector, EndSector)
        except UserWarning:
            return False
        return True

    def BlankCheckSectors(self, StartSector, EndSector):
        '''
        Checks to see if the sector is blank
        '''
        self.Write("I %d %d"%(StartSector, EndSector))
        self.AssertReturnCode("Blank Check Sectors")

    def ReadPartID(self):
        self.Flush()
        self.ClearBuffer()
        self.Write("J")
        self.AssertReturnCode("Blank Check Sectors")
        resp = self.ReadLine()
        return int(resp)

    def ReadBootCodeVersion(self):
        '''
        LPC84x sends a 0x1a first for some reason. Also the boot version seems to be Minor then Major not like the docs say
        '''
        self.Flush()

        self.Write("K")
        self.AssertReturnCode("Read Bootcode Version")
        Minor = self.ReadLine().strip()
        Major = self.ReadLine().strip()
        return "%d.%d"%(int(Major), int(Minor))

    def AssertEqual(self, Address1, Address2, NumBytes):
        '''
        Returns if two sections are equal
        '''
        self.Write("M %d %d %d"%(Address1, Address2, NumBytes))
        self.AssertReturnCode("Compare")

    def ReadUID(self):
        self.ClearBuffer()
        self.Write("N")
        self.AssertReturnCode("Read UID")
        UID0 = self.ReadLine().strip()
        UID1 = self.ReadLine().strip()
        UID2 = self.ReadLine().strip()
        UID3 = self.ReadLine().strip()
        return " ".join(["0x%08x"%int(uid) for uid in [UID0, UID1, UID2, UID3]])

    def ReadCRC(self, Address, NumBytes):
        self.ClearBuffer()
        self.Write("S %d %d"%(Address, NumBytes))
        self.AssertReturnCode("Read CRC")
        return self.ReadLine()

    def ReadFlashSig(self, StartAddress, EndAddress, WaitStates = 2, Mode = 0):
        assert(StartAddress < EndAddress)
        assert(StartAddress >= self.FlashRange[0])
        assert(EndAddress <= self.FlashRange[1])
        self.Write("Z %d %d %d %d"%(StartAddress, EndAddress, WaitStates, Mode))
        self.AssertReturnCode("Read Flash Sig")
        return self.ReadLine()

    def ReadWriteFAIM(self):
        self.Write("O")
        self.AssertReturnCode("Read Write FAIM")

    def ResetSerialConnection(self):
        self.Flush()
        self.Write(self.NewLine)
        try:
            pass
            self.ReadLine()
        except TimeoutError:
            pass

    def InitConnection(self):
        #self.ResetSerialConnection()
        try:
            try:
                self.SyncConnection()
                self.SetCrystalFrequency(self.CrystalFrequency)
            except (UserWarning, TimeoutError) as w:
                print("Sync Failed", w)
                print("Connect to running ISP")
                self.ConnectToRunningISP()
                print("Reconnection Successful")

            self.CheckPartType()
            uid = self.ReadUID()
            print("Part UID: %s"%uid)
            bootCodeVersion = self.ReadBootCodeVersion()
            print("Boot Code Version: %s"%bootCodeVersion)
            self.SetBaudRate(self.BaudRate)
            print("Baudrate set to %d"%self.BaudRate)
        except Exception as e:
            print(e, type(e))
            raise

    def SyncConnection(self):
        synced = False
        self.ClearSerialConnection()
        self.Flush()
        for i in range(5):
            self.Write('?'*15)
            #self.Write('?' + self.NewLine)
            try:
                FrameIn = self.ReadLine()
                if(self.SyncString.strip() in FrameIn.strip()):
                    synced = True
                    break
            except TimeoutError:
                pass

        if(not synced):
            #Check for SyncString
            raise UserWarning("Syncronization Failure")

        #self.Flush()
        self.Write(self.SyncString)#echo SyncString
        try:
            FrameIn = self.ReadLine()#discard echo
        except TimeoutError:
            pass

        verified = False
        for i in range(3):
            try:
                FrameIn = self.ReadLine()#Should be OK\r\n
                if(self.SyncVerified.strip() in FrameIn):
                    verified = True
                    break
            except TimeoutError:
                pass
        if not verified:
            raise UserWarning("Verification Failure")
        print("Syncronization Successful")

    def ClearSerialConnection(self):
        self.Write("")
        self.ClearBuffer()
        self.Flush()
        self.Read()
        self.ClearBuffer()
        self.Flush()
        for i in range(2):
            try:
                self.ReadLine()
            except TimeoutError:
                pass

    def SetCrystalFrequency(self, frequency_khz):
        self.Write("%d"%frequency_khz)
        verified = False
        for i in range(3):
            try:
                FrameIn = self.ReadLine()#Should be OK\r\n
                if(self.SyncVerified.strip() in FrameIn):
                    verified = True
                    break
            except TimeoutError:
                pass
        if not verified:
            raise UserWarning("Verification Failure")

    def ConnectToRunningISP(self):
        self.ClearSerialConnection()
        self.Echo(False)

    def CheckPartType(self):
        PartID = self.ReadPartID()
        if(PartID not in self.PartIDs):
            raise UserWarning("%s recieved 0x%08x"%(self.ChipName, PartID))
        print("Part Check Successful, 0x%08x"%(PartID))

    def CheckFlashWrite(Data, FlashAddress):
        '''
        Read Memory and compare it to what was written
        '''

        DataRead = self.ReadMemory(FlashAddress, len(Data))

        assert(len(Data) == len(DataRead))
        assert(type(Data) == type(DataRead))
        if(Data != DataRead):
            return False
        else:
            return True


    def WriteFlashSector(self, sector, Data):
        RAMAddress = self.RAMStartWrite
        sectorSizeBytes = self.kPageSizeBytes*self.SectorSizePages
        FlashAddress = self.FlashRange[0] + sector*sectorSizeBytes
        print("Writing Sector: %d\nFlash Address: %x\nRAM Address: %x\n"%(sector, FlashAddress, RAMAddress))

        self.BlankCheckSectors(sector, sector)
        Data += bytes(sectorSizeBytes - len(Data))

        self.WriteToRam(RAMAddress, Data)


        print("Prep Sector")
        self.PrepSectorsForWrite(sector, sector)
        print("Write to Flash")
        self.CopyRAMToFlash(FlashAddress, RAMAddress, sectorSizeBytes)
        self.AssertEqual(FlashAddress, RAMAddress, sectorSizeBytes)
        print("Compare Sucessful")

        #if(not CheckFlashWrite(Data, FlashAddress)):
        #    raise UserWarning("Flash Read Check Failed")
        #print("Flash Read Successful")


        crcCalc = zlib.crc32(Data)
        crcChip = self.ReadCRC(FlashAddress, NumBytes = len(Data))
        if(crcCalc != int(crcChip)):
            raise UserWarning("CRC Check Failed for sector %d".format(sector))
        else:
            print("CRC Check Passed")

    def WriteImage(self, ImageFile):
        self.Unlock()
        sector = 0
        writeCount = 0

        SectorBytes = self.SectorSizePages*self.kPageSizeBytes
        assert(SectorBytes%self.kWordSize == 0)

        with open(ImageFile, 'rb') as f:
            prog = f.read()
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

        chip_flash_sig = self.ReadFlashSig(self.FlashRange[0], self.FlashRange[1])
        print("Flash Signature: %s"%chip_flash_sig)
        print("Programming Complete.")

    def ReadImage(self, ImageFile):
        sector = 0
        writeCount = 0
        SectorBytes = self.SectorSizePages*self.kPageSizeBytes
        assert(SectorBytes%self.kWordSize == 0)

        with open(ImageFile, 'wb') as f:
            for sector in range(self.SectorCount):
                print("Sector ", sector)
                #if not self.AreSectorsBlank(sector, sector+1):
                #    self.Flush()
                #    self.Flush()
                #    print("Sector Not Blank")
                #else:
                #    break#should be finished

                DataChunk = self.ReadMemory(sector*SectorBytes, SectorBytes)
                f.write(DataChunk)

    def MassErase(self):
        self.Wait()
        self.ClearBuffer()
        self.Unlock()
        self.PrepSectorsForWrite(0, self.SectorCount - 1)
        self.EraseSector(0, self.SectorCount - 1)
        print("Checking Sectors are blank")
        self.BlankCheckSectors(0, self.SectorCount -1)

