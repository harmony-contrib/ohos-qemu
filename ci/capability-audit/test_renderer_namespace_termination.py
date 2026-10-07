"""Exercise the patch's actual helper. Product/guest checks are separate."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
PATCH = ROOT / "patches/common/base/startup/appspawn/render_pid_namespace/0001-enable-renderer-termination-inside-pid-namespace.patch"
PREAMBLE = r'''
#include <cassert>
#include <cerrno>
#include <string>
#include <signal.h>
#include <unistd.h>
#include <sys/wait.h>
#define APPSPAWN_LOGE(...) ((void)0)
static pid_t mockPid = 1;
static int failure = 0, calls = 0;
static pid_t RendererPid() { return mockPid; }
static int RendererSigaction(int number, const struct sigaction *action, struct sigaction *previous) {
    ++calls;
    if ((failure == 1 && !action) || (failure == 2 && action)) { errno = EPERM; return -1; }
    return sigaction(number, action, previous);
}
static int RendererSigemptyset(sigset_t *set) {
    if (failure == 3) { errno = EINVAL; return -1; }
    return sigemptyset(set);
}
#define getpid RendererPid
#define sigaction(...) RendererSigaction(__VA_ARGS__)
#undef sigemptyset
#define sigemptyset RendererSigemptyset
'''


def exercise(program):
    additions = "\n".join(line[1:] for line in PATCH.read_text().splitlines()
                          if line.startswith("+") and not line.startswith("+++"))
    helper = additions.split("static void ExitRendererOnTermination", 1)[1].split(
        "    if (!EnableRendererNamespaceTermination(processType))", 1)[0]
    compiler = shutil.which("clang++")
    if not compiler:
        raise RuntimeError("clang++ required")
    with tempfile.TemporaryDirectory(prefix="renderer-signal-test-") as directory:
        source = Path(directory) / "renderer.cpp"
        executable = Path(directory) / "renderer"
        source.write_text(PREAMBLE + "static void ExitRendererOnTermination" + helper +
                          "\n#undef getpid\n#undef sigaction\n#undef sigemptyset\n" + program)
        subprocess.run([compiler, "-std=c++17", "-Wall", "-Wextra", "-Werror",
                        "-fsanitize=address,undefined", str(source), "-o", str(executable)], check=True)
        subprocess.run([str(executable)], check=True, timeout=10)


class RendererTerminationTests(unittest.TestCase):
    def test_only_render_namespace_init_is_modified(self):
        exercise(r'''
int main() {
    for (auto type : {"", "gpu", "utility"}) assert(EnableRendererNamespaceTermination(type));
    mockPid = 123; assert(EnableRendererNamespaceTermination("render"));
    assert(calls == 0);
}
''')

    def test_default_handler_causes_real_signal_exit(self):
        exercise(r'''
int main() {
    pid_t child = fork(); assert(child >= 0);
    if (child == 0) {
        signal(SIGTERM, SIG_DFL);
        assert(EnableRendererNamespaceTermination("render"));
        kill(getpid(), SIGTERM);
        _exit(99);
    }
    int status = 0; assert(waitpid(child, &status, 0) == child);
    assert(WIFEXITED(status) && WEXITSTATUS(status) == 128 + SIGTERM);
}
''')

    def test_existing_engine_handler_is_preserved(self):
        exercise(r'''
void ExistingHandler(int) {}
int main() {
    struct sigaction before {}; before.sa_handler = ExistingHandler;
    RendererSigemptyset(&before.sa_mask); before.sa_flags = SA_RESTART;
    assert(sigaction(SIGTERM, &before, nullptr) == 0);
    assert(EnableRendererNamespaceTermination("render"));
    struct sigaction after {}; assert(sigaction(SIGTERM, nullptr, &after) == 0);
    assert(after.sa_handler == before.sa_handler && (after.sa_flags & SA_RESTART));
    assert(calls == 1);
}
''')

    def test_query_install_and_mask_failures_fail_closed(self):
        exercise(r'''
int main() {
    for (failure = 1; failure <= 3; ++failure) {
        signal(SIGTERM, SIG_DFL);
        assert(!EnableRendererNamespaceTermination("render"));
        struct sigaction after {}; assert(sigaction(SIGTERM, nullptr, &after) == 0);
        assert(after.sa_handler == SIG_DFL);
    }
}
''')

    def test_explicit_ignore_is_not_reported_as_supported(self):
        exercise(r'''
int main() {
    signal(SIGTERM, SIG_IGN);
    assert(!EnableRendererNamespaceTermination("render"));
    struct sigaction after {}; assert(sigaction(SIGTERM, nullptr, &after) == 0);
    assert(after.sa_handler == SIG_IGN);
}
''')

    def test_patch_precedes_seccomp_and_does_not_remove_isolation(self):
        additions = "\n".join(line for line in PATCH.read_text().splitlines()
                              if line.startswith("+") and not line.startswith("+++"))
        for forbidden in ("unshare(", "setns(", "SIGKILL", "setuid(", "setgid(", "prctl("):
            self.assertNotIn(forbidden, additions)
        self.assertIn("_exit(128 + signalNumber)", additions)
        tail = PATCH.read_text().split("std::string processType =", 1)[1]
        self.assertLess(tail.index("EnableRendererNamespaceTermination"), tail.index("SetSeccompPolicyForRenderer"))


if __name__ == "__main__":
    unittest.main()
