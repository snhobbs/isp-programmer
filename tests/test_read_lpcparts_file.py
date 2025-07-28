import unittest
from pathlib import Path
from ispprogrammer import parts_definitions


def_file = Path(__file__).absolute().parent / "lpctools_parts.def"


class SmokeTest(unittest.TestCase):
    def test_smoketest(self):
        df = parts_definitions.read_chip_file(def_file)
        print(df)

        line = parts_definitions.get_part_descriptor_line(fname=def_file, partid=0x00008041)
        self.assertTrue(line is not None)

        with self.assertRaises(ValueError):
                parts_definitions.get_part_descriptor_line(fname=def_file, partid=0x0000804)

if __name__ == "__main__":
    unittest.main()
