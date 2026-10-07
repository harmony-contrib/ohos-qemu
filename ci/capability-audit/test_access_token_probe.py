#!/usr/bin/env python3
"""Ensure the guest probe fails on stubs; mocked syscalls are not guest evidence."""
from pathlib import Path
import json
import unittest
from test_access_token_kernel import compile_run
from verify_access_token_results import verify

PROBE = Path(__file__).parent / "probes/access_token_kernel.c"
RUN = "a" * 32

MOCK = r'''
#include <stdarg.h>
static pthread_mutex_t mock_mutex = PTHREAD_MUTEX_INITIALIZER;
static bool mock_present;
static Bitmap mock_bitmap;
static void *mock_readonly;
int probe_mprotect(void *address, size_t length, int protection) {
    (void)length; (void)protection; mock_readonly = address; return 0;
}
int probe_open(const char *name, int flags, ...) { (void)name; (void)flags; return 42; }
int probe_close(int value) { (void)value; return 0; }
uid_t probe_geteuid(void) { return MOCK_UID; }
int probe_ioctl(int descriptor, unsigned long command, ...) {
    (void)descriptor;
    va_list args;
    va_start(args, command);
    void *data = va_arg(args, void *);
    va_end(args);
    pthread_mutex_lock(&mock_mutex);
    int result = 0, error = 0;
    if (!data) error = EINVAL;
    else if ((uintptr_t)data < 4096) error = EFAULT;
    else if (command == GET_ALL && data == mock_readonly) error = EFAULT;
    else if ((command == ADD || command == REMOVE || command == SET || command == _IOW('A', 2, uint64_t))
        && MOCK_UID != 0) error = EPERM;
    else if (command == ADD) { mock_bitmap = *(Bitmap *)data; mock_present = true; }
    else if (command == REMOVE) mock_present = false;
    else if (command == GET_ALL) {
        if (!mock_present || ((Bitmap *)data)->token != mock_bitmap.token) error = ENODATA;
        else if (MOCK_STUB) memset(((Bitmap *)data)->perm, 0, sizeof(mock_bitmap.perm));
        else *(Bitmap *)data = mock_bitmap;
    } else if (command == GET || command == SET) {
        Permission *permission = data;
        if (permission->opcode >= 2048) error = EINVAL;
        else if (!mock_present || permission->token != mock_bitmap.token) error = ENODATA;
        else {
            uint32_t *word = &mock_bitmap.perm[permission->opcode / 32];
            uint32_t mask = 1u << (permission->opcode % 32);
            if (command == GET) result = !!(*word & mask);
            else if (permission->granted) *word |= mask;
            else *word &= ~mask;
        }
    } else if (command == _IOR('A', 1, uint64_t)) *(uint64_t *)data = 123;
    else error = EOPNOTSUPP;
    pthread_mutex_unlock(&mock_mutex);
    if (error) { errno = error; return -1; }
    return result;
}
int main(void) {
    char *arguments[] = {"probe", MOCK_MODE, "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", NULL};
    return guest_probe_main(3, arguments);
}
'''


class AccessTokenProbeTests(unittest.TestCase):
    def run_probe(self, uid, mode, stub=False, success=True):
        prefix = f'''#define MOCK_UID {uid}
#define MOCK_MODE "--{mode}"
#define MOCK_STUB {int(stub)}
#define ioctl probe_ioctl
#define open probe_open
#define close probe_close
#define geteuid probe_geteuid
#define mprotect probe_mprotect
#define main guest_probe_main
'''
        # Only the OS calls are replaced. The real probe's cases and threads run.
        program = prefix + PROBE.read_text() + "\n#undef main\n" + MOCK
        return compile_run(program, expect_success=success)

    def test_real_probe_privileged_cases_and_cleanup(self):
        result = self.run_probe(0, "privileged")
        rows = [json.loads(line) for line in result.stdout.splitlines()]
        arch = rows[0]["arch"]
        report = verify(rows, arch, "privileged", RUN, result.returncode)
        self.assertIn("remove_readd_reader_snapshot_consistency", report["cases"])
        self.assertIn("reserved_token_removed", report["cases"])

    def test_normal_uid_cannot_mutate_kernel_permissions(self):
        result = self.run_probe(20010001, "unprivileged")
        rows = [json.loads(line) for line in result.stdout.splitlines()]
        verify(rows, rows[0]["arch"], "unprivileged", RUN, result.returncode)

    def test_all_zero_success_stub_is_rejected(self):
        result = self.run_probe(0, "privileged", stub=True, success=False)
        self.assertEqual(result.returncode, 1)
        rows = [json.loads(line) for line in result.stdout.splitlines()]
        self.assertEqual(rows[-1]["name"], "all_64_words_match")
        self.assertIs(rows[-1]["pass"], False)

    def test_privileged_uid_cannot_impersonate_normal_app_role(self):
        for uid in (0, 3020):
            result = self.run_probe(uid, "unprivileged", success=False)
            self.assertEqual(result.returncode, 2)
            self.assertEqual(result.stdout, "")


if __name__ == "__main__":
    unittest.main()
