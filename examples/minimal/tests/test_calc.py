import unittest

from src.calc import add, divide


class CalcTest(unittest.TestCase):
    def test_add(self) -> None:
        self.assertEqual(add(2, 3), 5)

    def test_divide(self) -> None:
        self.assertEqual(divide(10, 2), 5)

    def test_divide_by_zero(self) -> None:
        with self.assertRaises(ValueError):
            divide(1, 0)


if __name__ == "__main__":
    unittest.main()
