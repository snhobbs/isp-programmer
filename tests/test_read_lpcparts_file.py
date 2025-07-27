import unittest
from pathlib import Path
from isp_programmer import parts_definitions


def_file = Path(__file__).absolute().parent / "lpctools_parts.def"


class SmokeTest(unittest.TestCase):
    def test_smoketest(self):
        df = parts_definitions.ReadChipFile(def_file)
        print(df)

        line = parts_definitions.GetPartDescriptorLine(fname=def_file, partid=0x00008041)
        self.assertTrue(line is not None)

        with self.assertRaises(ValueError):
                parts_definitions.GetPartDescriptorLine(fname=def_file, partid=0x0000804)

if __name__ == "__main__":
    unittest.main()
