import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from b import label  # noqa: E402


class LabelTest(unittest.TestCase):
    def test_prefix(self) -> None:
        self.assertEqual(label("x"), "b:x")
