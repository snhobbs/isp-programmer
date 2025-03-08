from isp_programmer import parts_definitions

def_file = "lpctools_parts.def"

if __name__ == "__main__":
    df = parts_definitions.ReadChipFile(def_file)
    print(df)

    line = parts_definitions.GetPartDescriptorLine(fname=def_file, partid=0x00008041)
    print(line)

    line = parts_definitions.GetPartDescriptorLine(fname=def_file, partid=0x0000804)
    print(line)
