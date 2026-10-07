#!/usr/bin/env python3
"""Patch and sanitizer regressions, not proof of a booted kernel/provider."""
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
KERNEL = ROOT / "patches/common/kernel/linux/linux_6_6/access_token_abi"
SPM = ROOT / "patches/common/base/security/access_token/kernel_spm_handshake"
PATCH = KERNEL / "0001-query-real-permission-bitmap-under-lock.patch"
SPM_PATCH = SPM / "0001-require-successful-supported-spm-version.patch"
APPSPAWN = ROOT / "patches/common/base/startup/appspawn/kernel_user_id"
APPSPAWN_PATCH = APPSPAWN / "0001-store-account-identity-before-dropping-root.patch"
APPSPAWN_IMPL_PATCH = APPSPAWN / "0002-store-user-id-without-custom-sandbox.patch"


def patch_sections(path):
    """Exact hunk bodies with verified counts; sparse fixtures test plumbing."""
    files = {}
    for section in path.read_text().split("diff --git ")[1:]:
        name = section.split("+++ b/", 1)[1].splitlines()[0]
        hunks = []
        for part in re.split(r"(?m)^@@ ", section)[1:]:
            header, *body = part.splitlines()
            match = re.match(r"-(\d+),(\d+) \+(\d+),(\d+) @@", header)
            if not match:
                raise ValueError(header)
            old, new = [line[1:] for line in body if line.startswith((" ", "-"))], [
                line[1:] for line in body if line.startswith((" ", "+"))]
            if (len(old), len(new)) != (int(match[2]), int(match[4])):
                raise ValueError(f"incorrect hunk counts: {header}")
            hunks.append((int(match[1]), old, new))
        files[name] = hunks
    return files


def write_preimages(root, patch):
    combined = {}
    for item in patch if isinstance(patch, tuple) else (patch,):
        for name, hunks in patch_sections(item).items():
            combined.setdefault(name, []).extend(hunks)
    for name, hunks in combined.items():
        lines = []
        for line, old, _ in sorted(hunks):
            if len(lines) >= line:
                raise ValueError("overlapping fixture preimages")
            lines += [f"// fixture filler {index}" for index in range(len(lines), line - 1)]
            lines += old
        file = root / name
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text("\n".join(lines) + "\n")


def compile_run(source, language="c", expect_success=True):
    compiler = shutil.which("clang++" if language == "c++" else "clang")
    if compiler is None:
        raise RuntimeError("clang is required for sanitizer regressions")
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / ("probe.cpp" if language == "c++" else "probe.c")
        path.write_text(source)
        binary = Path(directory) / "probe"
        subprocess.run([compiler, "-std=c++17" if language == "c++" else "-std=gnu11",
                        "-Wall", "-Wextra", "-Werror", "-Wno-unused-parameter",
                        "-fsanitize=address,undefined", "-g", str(path), "-o", str(binary)], check=True)
        result = subprocess.run([str(binary)], capture_output=True, text=True)
        if expect_success and result.returncode != 0:
            raise AssertionError(result.stderr)
        return result


MOCK = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>
#define __user
#define MAX_PERM_GROUP_NUM 64
#define UINT32_T_BITS 32
#define pr_err(...) ((void)0)
struct file { int unused; };
typedef struct { uint32_t token, op_code; bool is_granted; } ioctl_set_get_perm_data;
typedef struct { uint32_t token, perm[64]; } ioctl_get_all_perm_data;
struct token_perm_node { ioctl_get_all_perm_data perm_data; };
_Static_assert(sizeof(ioctl_get_all_perm_data) == 260, "bitmap ABI size");
static struct token_perm_node *g_token_perm_root;
static int token_rwlock, locked, delete_on_unlock, fail_in, fail_out;
static void read_lock(int *lock) { (void)lock; assert(!locked); locked = 1; }
static void read_unlock(int *lock) {
    (void)lock; assert(locked); locked = 0;
    if (delete_on_unlock) { free(g_token_perm_root); g_token_perm_root = NULL; }
}
static size_t copy_from_user(void *out, const void *in, size_t size) {
    assert(!locked); if (!in || fail_in) return size; memcpy(out, in, size); return 0;
}
static size_t copy_to_user(void *out, const void *in, size_t size) {
    assert(!locked); if (!out || fail_out) return size; memcpy(out, in, size); return 0;
}
static void find_node_by_token(struct token_perm_node *root, uint32_t token,
    struct token_perm_node **target, struct token_perm_node **parent) {
    assert(locked); *parent = NULL;
    *target = root && root->perm_data.token == token ? root : NULL;
}
int access_tokenid_get_permission(struct file *file, void __user *uarg) {
    ioctl_set_get_perm_data get_perm_data;
    if (copy_from_user(&get_perm_data, uarg, sizeof(get_perm_data))) return -EFAULT;
    uint32_t idx = get_perm_data.op_code / UINT32_T_BITS;
    if (idx >= MAX_PERM_GROUP_NUM) return -EINVAL;
'''

MAIN = r'''
int main(void) {
    g_token_perm_root = calloc(1, sizeof(*g_token_perm_root));
    assert(g_token_perm_root);
    g_token_perm_root->perm_data.token = 123;
    for (unsigned i = 0; i < 64; ++i) g_token_perm_root->perm_data.perm[i] = 0x80000001u;
    ioctl_set_get_perm_data one = {.token = 123};
    ioctl_get_all_perm_data all = {.token = 123};
    assert(access_tokenid_get_all_permissions(NULL, &all) == 0);
    for (unsigned i = 0; i < 2048; ++i) {
        one.op_code = i;
        assert(access_tokenid_get_permission(NULL, &one) == (int)((all.perm[i / 32] >> (i % 32)) & 1));
    }
    // Changes must be reflected; never return an all-zero/all-granted stub.
    g_token_perm_root->perm_data.perm[0] = 2;
    assert(access_tokenid_get_all_permissions(NULL, &all) == 0 && all.perm[0] == 2);
    one.op_code = 0; assert(access_tokenid_get_permission(NULL, &one) == 0);
    one.op_code = 1; assert(access_tokenid_get_permission(NULL, &one) == 1);
    one.op_code = 2048; assert(access_tokenid_get_permission(NULL, &one) == -EINVAL);
    one.op_code = UINT32_MAX; assert(access_tokenid_get_permission(NULL, &one) == -EINVAL);
    one.op_code = 0; one.token = 124; all.token = 124;
    assert(access_tokenid_get_permission(NULL, &one) == -ENODATA && !locked);
    assert(access_tokenid_get_all_permissions(NULL, &all) == -ENODATA && !locked);
    one.token = all.token = 123;
    assert(access_tokenid_get_permission(NULL, NULL) == -EFAULT);
    assert(access_tokenid_get_all_permissions(NULL, NULL) == -EFAULT);
    fail_in = 1;
    assert(access_tokenid_get_permission(NULL, &one) == -EFAULT);
    assert(access_tokenid_get_all_permissions(NULL, &all) == -EFAULT);
    fail_in = 0; fail_out = 1;
    assert(access_tokenid_get_all_permissions(NULL, &all) == -EFAULT && !locked);
    fail_out = 0;
    // Force removal at the first unlock. Old code dereferences freed memory;
    // patched functions return the atomic snapshot and never touch the node.
    delete_on_unlock = 1;
    one.op_code = 1;
    assert(access_tokenid_get_permission(NULL, &one) == 1 && !g_token_perm_root);
    g_token_perm_root = calloc(1, sizeof(*g_token_perm_root));
    assert(g_token_perm_root);
    g_token_perm_root->perm_data.token = 123;
    g_token_perm_root->perm_data.perm[63] = 0x80000000u;
    assert(access_tokenid_get_all_permissions(NULL, &all) == 0);
    assert(!g_token_perm_root && all.perm[63] == 0x80000000u);
    assert(access_tokenid_get_all_permissions(NULL, &all) == -ENODATA);
    return 0;
}
'''


class AccessTokenKernelTests(unittest.TestCase):
    def test_real_bitmap_boundaries_and_delete_at_unlock(self):
        hunks = next(v for name, v in patch_sections(PATCH).items() if name.endswith(".c"))
        code = "\n".join(next(new for _, _, new in hunks if any("int granted;" in line for line in new)))
        code = code.split("\nstatic long access_tokenid_ioctl", 1)[0]
        compile_run(MOCK + code + "\n" + MAIN)

    def test_sanitizer_regression_detects_original_use_after_unlock(self):
        hunks = next(v for name, v in patch_sections(PATCH).items() if name.endswith(".c"))
        code = "\n".join(next(old for _, old, new in hunks if any("int granted;" in line for line in new)))
        code = code.split("\nstatic long access_tokenid_ioctl", 1)[0]
        main = r'''
int main(void) {
    g_token_perm_root = calloc(1, sizeof(*g_token_perm_root));
    g_token_perm_root->perm_data.token = 123;
    delete_on_unlock = 1;
    ioctl_set_get_perm_data one = {.token = 123};
    return access_tokenid_get_permission(NULL, &one);
}
'''
        # The old implementation has no all-bitmap function, hence no copy out.
        mock = MOCK.replace("static size_t copy_to_user", "__attribute__((unused)) static size_t copy_to_user")
        result = compile_run(mock + code + "\n" + main, expect_success=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("heap-use-after-free", result.stderr)

    def test_spm_handshake_errors_and_versions(self):
        hunk = next(iter(patch_sections(SPM_PATCH).values()))[0][2]
        code = "\n".join(hunk)
        program = r'''
#include <cassert>
#include <cstdint>
#include <cerrno>
#define ATM_TEST_ENABLE
#define LOGI(...) ((void)0)
static int result;
static uint32_t reported;
static int SpmGetVersion(uint32_t *version) { *version = reported; return result; }
bool supported() {
''' + code + r'''
int main() {
    for (int error : {ENOTSUP, EACCES, ENODEV, EINVAL, EIO, 1, -1}) {
        result = error;
        for (uint32_t version : {0u, 1u, 2u}) { reported = version; assert(!supported()); }
    }
    result = 0;
    for (uint32_t version : {0u, 2u, UINT32_MAX}) { reported = version; assert(!supported()); }
    reported = 1; assert(supported());
}
'''
        compile_run("#include <initializer_list>\n" + program, language="c++")

    def test_component_apply_and_idempotence(self):
        for component, patch in ((KERNEL, PATCH), (SPM, SPM_PATCH), (APPSPAWN, APPSPAWN_PATCH)):
            with self.subTest(component=component), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                write_preimages(root, (patch, APPSPAWN_IMPL_PATCH) if component == APPSPAWN else patch)
                command = ["bash", str(component / "apply.sh"), "--source-root", str(root)]
                subprocess.run(command, capture_output=True, check=True)
                subprocess.run(command, capture_output=True, check=True)
                subprocess.run(["git", "-C", str(root), "apply", "--check", "--reverse", str(patch)], check=True)

    def test_known_cached_header_migration_and_marker_drift(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_preimages(root, PATCH)
            header = root / "kernel/linux/linux-6.6/drivers/accesstokenid/access_tokenid.h"
            shutil.copyfile(Path(__file__).parent / "fixtures/access_tokenid_linux_6_6.h", header)
            subprocess.run(["git", "-C", str(root), "apply", str(KERNEL / "migration-old-header.patch")], check=True)
            command = ["bash", str(KERNEL / "apply.sh"), "--source-root", str(root)]
            subprocess.run(command, capture_output=True, check=True)
            subprocess.run(command, capture_output=True, check=True)
            self.assertNotIn("ACCESS_TOKENID_GET_SPM_VERSION", header.read_text())
            self.assertIn("ACCESS_TOKENID_GET_ALL_PERMISSIONS", header.read_text())
            # A marker must not accept a driver that was reset behind its back.
            subprocess.run(["git", "-C", str(root), "apply", "--reverse", str(PATCH)], check=True)
            self.assertNotEqual(subprocess.run(command, capture_output=True).returncode, 0)

    def test_user_id_storage_and_write_authorization(self):
        hunks = next(v for name, v in patch_sections(PATCH).items() if name.endswith(".c"))
        code = "\n".join(next(new for _, _, new in hunks if any("int access_tokenid_set_userid" in line for line in new)))
        code = code.split("\nstatic void add_node_to_left_tree_tail", 1)[0]
        program = r'''
#include <assert.h>
#include <stdint.h>
#include <stdbool.h>
#include <string.h>
#include <errno.h>
#define __user
typedef uint32_t kuid_t;
#define ACCESS_TOKEN_UID 3020
#define GLOBAL_ROOT_UID 0
#define NWEBSPAWN_UID 3081
struct file { int unused; };
static struct { uint32_t user_id; } task;
#define current (&task)
static uint32_t uid;
static kuid_t current_uid(void) { return uid; }
static bool uid_eq(kuid_t a, kuid_t b) { return a == b; }
static int fail_in, fail_out;
static size_t copy_from_user(void *out, const void *in, size_t count) {
    if (!in || fail_in) return count; memcpy(out, in, count); return 0;
}
static size_t copy_to_user(void *out, const void *in, size_t count) {
    if (!out || fail_out) return count; memcpy(out, in, count); return 0;
}
static bool check_permission_for_set_token_permission(void) {
''' + code + r'''
int main(void) {
    uint32_t value = 100, result = 0;
    assert(access_tokenid_set_userid(NULL, &value) == 0);
    assert(access_tokenid_get_userid(NULL, &result) == 0 && result == 100);
    uid = 20010001;
    value = 101;
    assert(access_tokenid_set_userid(NULL, &value) == -EPERM && task.user_id == 100);
    assert(access_tokenid_get_userid(NULL, &result) == 0 && result == 100);
    uid = ACCESS_TOKEN_UID;
    assert(access_tokenid_set_userid(NULL, &value) == 0 && task.user_id == 101);
    uid = NWEBSPAWN_UID;
    value = 102;
    assert(access_tokenid_set_userid(NULL, &value) == 0 && task.user_id == 102);
    assert(!check_permission_for_set_token_permission());
    uid = 20110001; // The final renderer cannot inherit the spawner exception.
    value = 103;
    assert(access_tokenid_set_userid(NULL, &value) == -EPERM && task.user_id == 102);
    uid = NWEBSPAWN_UID;
    fail_in = 1;
    assert(access_tokenid_set_userid(NULL, &value) == -EFAULT && task.user_id == 102);
    fail_in = 0;
    assert(access_tokenid_set_userid(NULL, NULL) == -EFAULT);
    assert(access_tokenid_get_userid(NULL, NULL) == -EFAULT);
    fail_out = 1;
    assert(access_tokenid_get_userid(NULL, &result) == -EFAULT);
}
'''
        compile_run(program)

    def test_appspawn_sets_account_before_dropping_uid_and_propagates_failure(self):
        new = "\n".join(next(iter(patch_sections(APPSPAWN_PATCH).values()))[0][2])
        # Execute the actual reordered hunk, including its failure return.
        program = r'''
#include <assert.h>
#include <stdint.h>
#include <errno.h>
#include <stddef.h>
#define MSG_EXT_NAME_USERID 1
#define APPSPAWN_LOGV(...) ((void)0)
#define APPSPAWN_CHECK(condition, action, ...) do { if (!(condition)) { action; } } while (0)
static int privileged = 1, failed;
static char account[] = "100";
static void *GetAppSpawnMsgExtInfo(void *message, int name, void *length) {
    (void)message; (void)name; (void)length; return account;
}
static const char *GetProcessName(void *property) { (void)property; return "probe"; }
static int SetUserId(const char *value) { assert(privileged); assert(value == account); return failed; }
static int setresuid(uint32_t a, uint32_t b, uint32_t c) { (void)a; (void)b; (void)c; privileged = 0; return 0; }
static int spawn(void) {
    int ret = 0;
    struct { void *message; } instance = {0}, *property = &instance;
    struct { uint32_t uid; } dac = {20010001}, *dacInfo = &dac;
''' + new.split("\n    /* The setenv operation", 1)[0] + r'''
    return 0;
}
int main(void) {
    assert(spawn() == 0 && !privileged);
    privileged = 1; failed = -EPERM;
    assert(spawn() == -EPERM && privileged);
}
'''
        # Logging is deliberately a no-op in this isolated harness.
        program = program.replace("static const char *GetProcessName", "__attribute__((unused)) static const char *GetProcessName")
        compile_run(program)

    def test_real_set_userid_is_unconditional_and_never_weak_success(self):
        sections = patch_sections(APPSPAWN_IMPL_PATCH)
        common = next(hunks for name, hunks in sections.items() if name.endswith("appspawn_common.c"))
        function = "\n".join(common[0][2])
        self.assertNotIn("weak", function)
        custom = next(hunks for name, hunks in sections.items() if name.endswith("appspawn_custom_config.cpp"))
        self.assertNotIn("SetUserId", "\n".join(custom[0][2]))
        program = r'''
#include <assert.h>
#include <stdint.h>
#include <errno.h>
#include <stdlib.h>
#include <string.h>
#include <fcntl.h>
#include <sys/ioctl.h>
#define APPSPAWN_CHECK(condition, action, ...) do { if (!(condition)) { action; } } while (0)
#define APPSPAWN_LOGE(...) ((void)0)
static int opened, closed, called, fail_open, fail_ioctl;
static uint32_t stored;
static int test_open(const char *path, int flags) {
    assert(!strcmp(path, "/dev/access_token_id"));
    assert(flags == (O_WRONLY | O_CLOEXEC)); opened++;
    if (fail_open) { errno = ENODEV; return -1; } return 42;
}
static int test_close(int fd) { assert(fd == 42); closed++; errno = EIO; return 0; }
static int test_ioctl(int fd, unsigned long command, uint32_t *value) {
    assert(fd == 42 && command == _IOW('A', 12, uint32_t)); called++;
    if (fail_ioctl) { errno = EPERM; return -1; } stored = *value; return 0;
}
#define open test_open
#define close test_close
#define ioctl test_ioctl
''' + function + r'''
int main(void) {
    assert(SetUserId("100") == 0 && stored == 100 && opened == 1 && closed == 1 && called == 1);
    assert(SetUserId("4294967295") == 0 && stored == UINT32_MAX && called == 2);
    const char *invalid[] = {"", "no", "100x", "-1", "4294967296", "9999999999999999999999999"};
    for (unsigned int i = 0; i < sizeof(invalid) / sizeof(invalid[0]); i++)
        assert(SetUserId((char *)invalid[i]) == -1 && called == 2 && stored == UINT32_MAX);
    assert(SetUserId(NULL) == -1 && called == 2);
    fail_open = 1; assert(SetUserId("100") == -1 && closed == 2 && called == 2);
    fail_open = 0; fail_ioctl = 1;
    assert(SetUserId("100") == -1 && closed == 3 && called == 3 && errno == EPERM && stored == UINT32_MAX);
}
'''
        compile_run(program)


if __name__ == "__main__":
    unittest.main()
