import csv
from typing import List, Dict, Any
from pathlib import Path
from pydantic import BaseModel, Field, validator


class LPCPart(BaseModel):
    part_id: int = Field(alias="part id")
    name: str
    FlashStart: int
    FlashSize: int
    SectorCount: int
    ResetVectorOffset: int
    RAMStart: int
    RAMSize: int
    RAMBufferOffset: int
    RAMBufferSize: int
    UU_Encode: str = Field(alias="UU Encode")

    @property
    def RAMEnd(self) -> int:
        return self.RAMStart + self.RAMSize - 1

    @property
    def FlashEnd(self) -> int:
        return self.FlashStart + self.FlashSize - 1

    @property
    def RAMStartWrite(self) -> int:
        return self.RAMStart + self.RAMBufferOffset

    @property
    def RAMRange(self) -> tuple[int, int]:
        return (self.RAMStart, self.RAMEnd)

    @property
    def FlashRange(self) -> tuple[int, int]:
        return (self.FlashStart, self.FlashEnd)

    @validator("name", pre=True)
    @classmethod
    def strip_name(cls, v):
        return v.strip()


def parse_lpcparts_string(s: str) -> List[LPCPart]:
    parts = []
    reader = csv.reader(s.splitlines())
    for row in reader:
        if not row or row[0].strip().startswith("#"):
            continue
        fields = {
            "part id": int(row[0], 0),
            "name": row[1].strip(),
            "FlashStart": int(row[2], 0),
            "FlashSize": int(row[3], 0),
            "SectorCount": int(row[4], 0),
            "ResetVectorOffset": int(row[5], 0),
            "RAMStart": int(row[6], 0),
            "RAMSize": int(row[7], 0),
            "RAMBufferOffset": int(row[8], 0),
            "RAMBufferSize": int(row[9], 0),
            "UU Encode": row[10].strip(),
        }
        parts.append(LPCPart(**fields))
    return parts


def read_chip_file(fname: str) -> List[LPCPart]:
    return parse_lpcparts_string(Path(fname).read_text())


def get_part_descriptor_line(fname: str, partid: int) -> LPCPart:
    parts = read_chip_file(fname)
    for part in parts:
        if part.part_id == partid:
            return part
    raise ValueError(f"PartId {hex(partid)} not found in {fname}")


def get_part_descriptor(fname: str, partid: int) -> Dict[str, Any]:
    return get_part_descriptor_line(fname, partid).dict()


def check_parts_definition(parts: List[LPCPart]) -> bool:
    return all(p.RAMEnd - p.RAMStart + 1 == p.RAMSize for p in parts)
