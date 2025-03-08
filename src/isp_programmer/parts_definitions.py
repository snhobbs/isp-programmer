"""
Parser for the lpctools file, read into a data frame that is
consistent with other formats
"""

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


def read_lpcparts_string(string: str) -> dict[str, list]:
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
    df_dict: dict[str, list] = {}
    for column in lpc_tools_column_locations:
        df_dict[column] = []

    f = string.splitlines()
    for line in f:
        if not line.strip() or line.strip()[0] == "#":
            continue
        split_line = line.strip().split(",")
        for column, index in lpc_tools_column_locations.items():
            read = split_line[index].strip()
            try:
                value: int = int(read, 0)
                df_dict[column].append(value)
            except ValueError:
                df_dict[column].append(read)

    df = df_dict
    df["RAMEnd"] = [
        start + size - 1 for start, size in zip(df["RAMStart"], df["RAMSize"])
    ]
    df["FlashEnd"] = [
        start + size - 1 for start, size in zip(df["FlashStart"], df["FlashSize"])
    ]
    df["RAMStartWrite"] = [
        start + offset for start, offset in zip(df["RAMStart"], df["RAMBufferOffset"])
    ]

    df["RAMRange"] = list(zip(df["RAMStart"], df["RAMEnd"]))
    df["FlashRange"] = list(zip(df["FlashStart"], df["FlashEnd"]))
    return df


def ReadChipFile(fname: str) -> dict:
    """
    Reads an lpcparts style file to a dataframe
    """
    with open(fname, "r") as f:
        df = read_lpcparts_string(f.read())
    return df


def GetPartDescriptorLine(fname: str, partid: int) -> dict[str, str]:
    entries = ReadChipFile(fname)
    for i, line_part_id in enumerate(entries["part id"]):
        if partid == line_part_id:
            return {key: entries[key][i] for key in entries}
    raise UserWarning(f"PartId {partid} not found in {fname}")


def GetPartDescriptor(fname: str, partid: int) -> dict[str, str]:
    # FIXME redundant function
    descriptor = GetPartDescriptorLine(fname, partid)
    if descriptor is None:
        raise UserWarning("Warning chip %s not found in file %s" % (hex(partid), fname))
    return descriptor


def check_parts_definition_dataframe(df):
    """
    Takes the standard layout dataframe, check the field validity
    """
    valid = True
    for _, line in df.iterrows():
        if line["RAMRange"][1] - line["RAMRange"][0] + 1 != line["RAMSize"]:
            valid = False
    return valid
