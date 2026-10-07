import unittest
from build_library_exit_probes import CASES
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from run_library_exit_probes import candidate_inputs, verify, verify_candidate_maps


class LibraryExitTests(unittest.TestCase):
    def rows(self):
        return [{"case": case, "repeat": repeat, "guest_exit_code": 0}
                for case in CASES for repeat in range(3)]

    def test_all_orders_and_boundaries(self):
        self.assertEqual(verify(self.rows(), 3)["status"], "pass")
        self.assertEqual(CASES["avplayer-udmf"], ("avplayer", "udmf"))
        self.assertEqual(CASES["udmf-pasteboard"], ("udmf", "pasteboard"))
        self.assertFalse(verify(self.rows(), 3)["first_artifact_behavior_gate_passed"])

    def test_signal_is_failure(self):
        rows = self.rows()
        rows[-1]["guest_exit_code"] = 139
        result = verify(rows, 3)
        self.assertEqual(result["status"], "fail")
        self.assertEqual(result["failures"], [rows[-1]])

    def test_missing_and_duplicate_are_not_success(self):
        rows = self.rows()
        for invalid in (rows[:-1], rows + [rows[-1]], rows[:-1] + [rows[0]]):
            with self.assertRaises(ValueError):
                verify(invalid, 3)

    def test_candidate_is_explicit_and_all_or_nothing(self):
        self.assertIsNone(candidate_inputs(SimpleNamespace()))
        for name in ("candidate_surface", "candidate_fence", "candidate_mapping_probe"):
            with self.assertRaises(ValueError):
                candidate_inputs(SimpleNamespace(**{name: Path("/tmp/input")}))

    def test_candidate_requires_verified_pair_and_expected_mapping_graph(self):
        args = SimpleNamespace(arch="arm64", candidate_surface=Path("/tmp/surface"),
                               candidate_fence=Path("/tmp/fence"), candidate_mapping_probe=Path("/tmp/probe"))
        pair = {key: {"sha256": key} for key in ("surface", "fence")}
        with patch("run_library_exit_probes.verify_pair", return_value=pair) as ownership, \
                patch("run_library_exit_probes.validate_elf"), \
                patch("run_library_exit_probes.digest", return_value="probe"), \
                patch("run_library_exit_probes.needed_libraries", return_value={"libavplayer.so", "libudmf.so"}):
            self.assertEqual(candidate_inputs(args)["mapping_probe"]["sha256"], "probe")
            ownership.assert_called_once_with(args.candidate_surface, args.candidate_fence, "arm64")
        with patch("run_library_exit_probes.verify_pair", return_value=pair), \
                patch("run_library_exit_probes.validate_elf"), \
                patch("run_library_exit_probes.needed_libraries", return_value={"libudmf.so"}):
            with self.assertRaises(ValueError):
                candidate_inputs(args)

    def test_candidate_maps_reject_fallback_duplicate_deleted_or_missing(self):
        remote = "/data/local/tmp/ohos-library-exit-nonce"
        maps = [f"1000-2000 r-xp 0 00:00 1 {remote}/candidate/{name}"
                for name in ("libsurface.z.so", "libsync_fence.z.so")]
        self.assertEqual(len(verify_candidate_maps("\n".join(maps + maps), remote)), 2)
        invalid = (maps[:1], maps + [maps[0].replace(remote + "/candidate", "/system/lib64")],
                   [maps[0] + " (deleted)", maps[1]],
                   [line.replace(remote + "/candidate", "/system/lib64") for line in maps])
        for lines in invalid:
            with self.assertRaises(ValueError):
                verify_candidate_maps("\n".join(lines), remote)


if __name__ == "__main__":
    unittest.main()
