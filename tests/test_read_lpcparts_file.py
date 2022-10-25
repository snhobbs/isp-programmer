from isp_programmer import parts_definitions

if __name__ == "__main__":
    df = parts_definitions.ReadChipFile("../lpctools_parts.def")
    print(df)
