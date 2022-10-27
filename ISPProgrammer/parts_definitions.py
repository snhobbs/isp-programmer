'''
Parser for the lpctools file, read into a data frame that is
consitant with other formats
'''
import pandas
import numpy as np

column_names = [
        "part id",
        "name",
        "FlashStart",
        "FlashEnd",
        "FlashSize",
        "SectorCount",
        "ResetVectorOffset",
        "RAMStart",
        "RAMEnd",
        "RAMSize",
        "RAMBufferOffset",
        "RAMBufferSize",
        "UU Encode",
        "RAMStartWrite",
]


def read_lpcparts_string(string: str):
    lpc_tools_column_locations = {
        "part id": 0,
        "name": 1,
        "FlashStart": 2,
        "FlashSize": 3,
        "SectorCount": 4,
        "ResetVectorOffset": 5,
        "RAMStart": 6,
        "RAMSize": 7,
        "RAMBufferOffset": 8,
        "RAMBufferSize": 9,
        "UU Encode": 10,
    }
    df_dict = {}
    for column in lpc_tools_column_locations:
        df_dict[column] = []

    f = string.splitlines()
    for line in f:
        if not line.strip() or line.strip()[0] == '#':
            continue
        split_line = line.strip().split(',')
        for column, index in lpc_tools_column_locations.items():
            value = split_line[index].strip()
            try:
                value = int(value, 0)
            except ValueError:
                pass
            df_dict[column].append(value)

    for col in df_dict:
        df_dict[col] = np.array(df_dict[col])

    df = pandas.DataFrame(df_dict)
    df["RAMEnd"] = np.array(df["RAMStart"]) + np.array(df["RAMSize"]) - 1
    df["FlashEnd"] = np.array(df["FlashStart"]) + np.array(df["FlashSize"]) - 1
    df["RAMStartWrite"] = np.array(df["RAMStart"]) + np.array(df["RAMBufferOffset"])

    df["RAMRange"] = list(zip(df["RAMStart"], df["RAMEnd"]))
    df["FlashRange"] = list(zip(df["FlashStart"], df["FlashEnd"]))
    return df


def ReadChipFile(fname: str) -> pandas.DataFrame:
    '''
    Reads an lpcparts style file to a dataframe
    '''
    with open(fname, 'r') as f:
        df = read_lpcparts_string(f.read())
    return df


def GetPartDescriptorLine(fname: str, partid: int) -> list:
    entries = ReadChipFile(fname)
    for _, entry in entries.iterrows():
        if partid == entry["part id"]:
            return entry
    raise UserWarning(f"PartId {partid : 0x%x} not found in {fname}")


def GetPartDescriptor(fname: str, partid: int) -> dict:
    descriptor = GetPartDescriptorLine(fname, partid)
    if descriptor is None:
        raise UserWarning("Warning chip %s not found in file %s"%(hex(partid), fname))
    return descriptor


def check_parts_definition_dataframe(df):
    '''
    Takes the standard layout dataframe, check the field validity
    '''
    valid = True
    for _, line in df.iterrows():
        if line["RAMRange"][1] - line["RAMRange"][0] + 1 != line["RAMSize"]:
            valid=False
    return valid
