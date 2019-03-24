from . import ISPChip
from timeout_decorator import TimeoutError

class NXPChip(ISPChip):
    PageSizeBytes = 64
    MaxByteTransfer = 1024
    
    NewLine = "\r\n"
    Parity = None
    DataBits = 8
    StopBits = 1
    SyncString = "Synchronized\r\n"
    SyncVerified = "OK\r\n"
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

    def InitConnection(self):
        try:
            try:
                self.SyncConnection()
            except (UserWarning, TimeoutError) as w:
                pass
                #print("Syncronization Failed, trying to connect to running ISP ({})".format(w))
            self.Wait()
            self.Flush()
            print("Connect to running ISP")
            self.ConnectToRunningISP()
            print("Reconnection Successful")

            self.CheckPartType()
            uid = self.ReadUID()
            print("Part UID: %s"%uid)
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
        self.Echo(False)
        self.Flush()
        self.Echo(False)
        try:
            while(True):
                l = self.ReadLine()
        except TimeoutError:
            pass

        self.Echo(False)
        self.Wait()
        l = self.ReadLine()
        if(int(l.strip()) != self.ReturnCodes["CMD_SUCCESS"]):
            raise UserWarning("Reconnection Failure {}".format(code))
        
        self.Flush()

    def CheckPartType(self):
        self.Echo(False)
        self.Wait()
        self.Flush()
        PartID = self.ReadPartID()
        if(PartID not in self.PartIDs):
            raise UserWarning("%s recieved %08x"%(self.ChipName, PartID))
        
        print("Part Check Successful, 0x%08x"%(PartID))

    def MassErase(self):
        self.Wait()
        self.GetBufferIn()
        self.Unlock()
        self.PrepSectorsForWrite(0, self.SectorCount)
        self.EraseSector(0, self.SectorCount)

