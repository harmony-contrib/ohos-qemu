#!/usr/bin/env python3
"""Execute actual probe with stateful mocked ioctls; never guest evidence."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from test_access_token_kernel import compile_run
from verify_userid_results import verify

RUN = "a" * 32
PROBE = Path(__file__).parent / "probes/access_token_userid.c"
MOCK = r'''
#include <stdarg.h>
static uint32_t mock_userid = 100;
static void *mock_readonly;
int probe_mprotect(void *address, size_t length, int protection) {
    (void)length; (void)protection; mock_readonly = address; return 0;
}
int probe_open(const char *name, int flags, ...) { (void)name; (void)flags; return 42; }
int probe_close(int fd) { (void)fd; return 0; }
uid_t probe_getuid(void) { return MOCK_UID; }
uid_t probe_geteuid(void) { return MOCK_UID; }
int probe_ioctl(int fd, unsigned long command, ...) {
    (void)fd; va_list args; va_start(args, command);
    void *data = va_arg(args, void *); va_end(args);
    int error = 0;
    if (!data) error = EINVAL;
    else if (command == SET_USERID && MOCK_UID != 0) error = EPERM;
    else if ((uintptr_t)data < 4096 || data == mock_readonly) error = EFAULT;
    else if (command == SET_USERID) { if (!MOCK_STUB) mock_userid = *(uint32_t *)data; }
    else if (command == GET_USERID) *(uint32_t *)data = mock_userid;
    else error = EOPNOTSUPP;
    if (error) { errno = error; return -1; } return 0;
}
int main(void) {
    char *args[] = {"probe", MOCK_MODE, "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", "100", NULL};
    return guest_probe_main(4, args);
}
'''


class UserIdProbeTests(unittest.TestCase):
    def run_probe(self, uid, mode, stub=False, success=True):
        prefix = f'''#define MOCK_UID {uid}
#define MOCK_MODE "--{mode}"
#define MOCK_STUB {int(stub)}
#define ioctl probe_ioctl
#define open probe_open
#define close probe_close
#define getuid probe_getuid
#define geteuid probe_geteuid
#define mprotect probe_mprotect
#define main guest_probe_main
'''
        result = compile_run(prefix + PROBE.read_text() + "\n#undef main\n" + MOCK,
                             expect_success=success)
        return result, [json.loads(line) for line in result.stdout.splitlines()]

    def test_root_roundtrip_actual_fork_isolation_boundaries_and_restoration(self):
        result, rows = self.run_probe(0, "privileged")
        report = verify(rows, rows[0]["arch"], "privileged", RUN, result.returncode)
        self.assertIn("child_userid_does_not_change_parent", report["cases"])
        self.assertIn("userid_restore_observed", report["cases"])

    def test_normal_application_account_and_privilege_boundary(self):
        result, rows = self.run_probe(20010001, "unprivileged")
        rows += [{"kind": "native_result", "run_id": RUN, "exit_code": result.returncode}]
        verify(rows, rows[0]["arch"], "unprivileged", RUN, 0, 100, app_context=True)

    def test_success_without_real_userid_storage_fails(self):
        result, rows = self.run_probe(0, "privileged", stub=True, success=False)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(rows[-1]["name"], "userid_actual_roundtrip")
        self.assertIs(rows[-1]["pass"], False)

    def test_verifier_rejects_stale_partial_failed_wrong_account_or_shell(self):
        _, full = self.run_probe(20010001, "unprivileged")
        full += [{"kind": "native_result", "run_id": RUN, "exit_code": 0}]
        bad = [full[:-1], full[:1] + full[2:], full[:-2] + [full[1]] + full[-2:]]
        for key, value in (("arch", "bogus"), ("pointer_bits", 32 if full[0]["arch"] != "armv7a" else 64),
                           ("uid", 2000), ("euid", 0), ("expected_user_id", 99)):
            row = copy.deepcopy(full)
            row[0][key] = value
            bad.append(row)
        for value in (False, 1, "true"):
            row = copy.deepcopy(full)
            row[2]["pass"] = value
            bad.append(row)
        row = copy.deepcopy(full)
        row[-1]["exit_code"] = False
        bad.append(row)
        for rows in bad:
            with self.assertRaises(ValueError):
                verify(rows, full[0]["arch"], "unprivileged", RUN, 0, 100, app_context=True)
        with self.assertRaises(ValueError):
            verify(full, full[0]["arch"], "unprivileged", "b" * 32, 0, 100, app_context=True)

    def test_root_or_atm_cannot_impersonate_app(self):
        for uid in (0, 3020):
            result, rows = self.run_probe(uid, "unprivileged", success=False)
            self.assertEqual((result.returncode, rows), (2, []))

    def test_cli_retains_failed_app_observations_hashes_and_nonzero_return(self):
        result, rows = self.run_probe(20010001, 'unprivileged')
        rows += [{'kind': 'native_result', 'run_id': RUN, 'exit_code': result.returncode}]
        # Reproduce a failed ordinary-app case instead of discarding its records.
        rows[3]['pass'] = False
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive, log, output = root / 'archive', root / 'log', root / 'result.json'
            archive.write_bytes(b'host fixture, not guest acceptance')
            log.write_text('\n'.join(json.dumps(row) for row in rows) + '\n')
            command = [sys.executable, str(PROBE.parent.parent / 'verify_userid_results.py'),
                       '--archive', str(archive), '--log', str(log), '--arch', rows[0]['arch'],
                       '--mode', 'unprivileged', '--run-id', RUN, '--probe-exit-code', '0',
                       '--expected-user-id', '100', '--app-context', '--output', str(output)]
            completed = subprocess.run(command, capture_output=True, text=True)
            report = json.loads(output.read_text())
            self.assertEqual(completed.returncode, 1)
            self.assertEqual(report['status'], 'fail')
            self.assertEqual(report['observations'], rows)
            self.assertEqual(len(report['archive_sha256']), 64)
            self.assertEqual(len(report['log_sha256']), 64)
            self.assertTrue(report['failures'])
            self.assertFalse(report['first_artifact_behavior_gate_passed'])


if __name__ == "__main__":
    unittest.main()
