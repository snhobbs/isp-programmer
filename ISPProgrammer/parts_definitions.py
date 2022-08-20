def ReadChipFile(fname: str) -> list:
    data = []
    with open(fname, 'r') as f:
        for line in f:
            if not line.strip() or line.strip()[0] == '#':
                continue
            data.append(line.split(","))
    return data


def GetPartDescriptorLine(fname: str, partid: int) -> list:
    entries = ReadChipFile(fname)
    for entry in entries:
        if partid == int(entry[0], 0):
            return entry
    raise UserWarning(f"PartId {partid : 0x%x} not found in {fname}")


def GetPartDescriptor(fname: str, partid: int) -> dict:
    descriptor = GetPartDescriptorLine(fname, partid)
    if descriptor is None:
        raise UserWarning("Warning chip %s not found in file %s"%(hex(partid), fname))

    line = dict()
    line["SectorCount"] = int(descriptor[4])
    line["RAMSize"] = int(descriptor[7], 0)
    line["RAMStart"] = int(descriptor[6], 0)
    line["RAMRange"] = (line["RAMStart"], line["RAMStart"] + line["RAMSize"] - 1)
    line["FlashStart"] = int(descriptor[2], 0)
    line["FlashSize"] = int(descriptor[3], 0)
    line["FlashRange"] = (line["FlashStart"], line["FlashStart"] + line["FlashSize"] - 1)
    line["RAMBufferOffset"] = int(descriptor[8], 0)
    line["RAMStartWrite"] = line["RAMStart"] + line["RAMBufferOffset"]
    return line