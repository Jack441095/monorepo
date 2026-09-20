import unittest


class CliDialogueParseTests(unittest.TestCase):
    def test_parse_on_off(self):
        from utils.cli_dialogue import parse_on_off

        self.assertIs(parse_on_off("on"), True)
        self.assertIs(parse_on_off("OFF"), False)
        self.assertIs(parse_on_off("1"), True)
        self.assertIs(parse_on_off("0"), False)
        self.assertIsNone(parse_on_off("maybe"))


if __name__ == "__main__":
    unittest.main()
