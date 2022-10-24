'''
Parser for the lpctools file, read into a data frame that is consitant with other formats
'''
import pandas

column_names = [
    "SectorCount",
    "RAMSize",
    "RAMStart",
    "RAMRange",
    "FlashStart",
    "FlashSize",
    "FlashRange",
    "RAMBufferOffset",
    "RAMStartWrite",
]


def ReadChipFile(fname: str) -> pandas.DataFrame:
    lpc_tools_column_locations = {
        "part id": 0,
        "name": 1
        "FlashStart": 2,
        "FlashSize": 3,
        "SectorCount": 4,
        "ResetVectorOffset": 5
        "RAMStart": 6,
        "RAMSize": 7,
        "RAMBufferOffset": 8,
        "RAMBufferSize": 9,
        "UU Encode": 10,
    }
    df_dict = {}
    for column in column_names:
        df_dict[column] = []

    with open(fname, 'r') as f:
        for line in f:
            if not line.strip() or line.strip()[0] == '#':
                continue
            split_line = line.strip().split(',')
            for column in lpc_tools_column_locations:
                df_dict[column].append(split_line[lpc_tools_column_locations[column]])

        df = pandas.DataFrame(df_dict)
        df["RAMRange"] = (df["RAMStart"], df["RAMStart"] + df["RAMSize"] - 1)
        df["FlashRange"] = (df["FlashStart"], df["FlashStart"] + df["FlashSize"] - 1)
        df["RAMStartWrite"] = df["RAMStart"] + df["RAMBufferOffset"]
    return df


def GetPartDescriptorLine(fname: str, partid: int) -> list:
    entries = ReadChipFile(fname)
    for _, entry in entries.iterrows():
        if partid == int(entry["part id"], 0):
            return entry
    raise UserWarning(f"PartId {partid : 0x%x} not found in {fname}")


def GetPartDescriptor(fname: str, partid: int) -> dict:
    descriptor = GetPartDescriptorLine(fname, partid)
    if descriptor is None:
        raise UserWarning("Warning chip %s not found in file %s"%(hex(partid), fname))
    return line
