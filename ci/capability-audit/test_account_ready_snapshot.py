"""Validate AccountMgr gate parsing, not an account in a running guest."""
import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location(
    "account_snapshot", Path(__file__).resolve().parents[1] / "qemu-smoke/account_state.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
parse = module.parse_snapshot


class AccountSnapshotTests(unittest.TestCase):
    def test_same_current_record_must_show_user_100_foreground(self):
        for ready in ("true", '"true"'):
            text = f"bootevent.account.ready={ready}\r\nID: 0\r\n  isForeground: 0\r\n"
            text += "ID: 100\r\n\tisForeground: 1\r\nID: 101\r\n\tisForeground: 0\r\n"
            self.assertEqual(parse(text), {"param_ready": True, "user_100": True, "foreground": True})

    def test_other_foreground_account_cannot_impersonate_user_100(self):
        for text in ("ID: 0\nisForeground: 1\nID: 100\nisForeground: 0\n",
                     "ID: 100\nisForeground: 0\nID: 101\nisForeground: true\n",
                     "isForeground: true\nID: 100\n"):
            state = parse("bootevent.account.ready=true\n" + text)
            self.assertTrue(state["user_100"])
            self.assertFalse(state["foreground"])

    def test_missing_duplicate_conflicting_or_malformed_records_fail_closed(self):
        for text in ("", "ID: 1000\nisForeground: 1\n", "ID: 100\n",
                     "ID: 100\nisForeground: 1\nisForeground: 0\n",
                     "ID: 100\nisForeground: 1\nID: 100\nisForeground: 1\n",
                     "ID: 100\nID: garbage\nisForeground: 1\n",
                     "ID: 100\nisForeground: 1 extra\n", "ID: 100\nisForeground: 10\n"):
            with self.subTest(text=text):
                self.assertFalse(parse(text)["foreground"])
        self.assertFalse(parse("bootevent.account.ready=true\nbootevent.account.ready=false\n")["param_ready"])

    def test_success_factors_from_separate_snapshots_must_not_be_combined(self):
        first = parse("bootevent.account.ready=false\nID: 100\nisForeground: true\n")
        second = parse("bootevent.account.ready=true\nID: 0\nisForeground: 1\nID: 100\nisForeground: 0\n")
        self.assertFalse(all(first.values()))
        self.assertFalse(all(second.values()))
        self.assertEqual(parse("[Fail][E001005] Device disconnected\n"),
                         {"param_ready": False, "user_100": False, "foreground": False})


if __name__ == "__main__":
    unittest.main()
