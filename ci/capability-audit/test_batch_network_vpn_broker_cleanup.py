"""Use real child exit and filesystem failures to verify broker cleanup retries.

Signals are counted and forwarded to the host kernel. macOS doubles only prctl;
Linux exercises the actual subreaper and parent-death implementation.
"""
from pathlib import Path
import sys
import tempfile
import unittest

from test_batch_network_openvpn_lifecycle import compile_run


SOURCE = r'''
#include <signal.h>
#include <sys/types.h>
int signalCalls = 0;
int TracedKill(pid_t pid, int signal) { ++signalCalls; return kill(pid, signal); }
#define kill TracedKill
#include "broker_runtime.h"
#undef kill
#include <cassert>
#include <filesystem>

int main(int argc, char **argv)
{
    assert(argc == 3);
    using namespace OhosOpenvpn;
    const std::string root = argv[1];
    const bool shutdown = std::string(argv[2]) == "shutdown";
    assert(mkdir(root.c_str(), 0700) == 0);
    int ready[2];
    assert(pipe(ready) == 0);
    BrokerRuntime broker(root, getuid(), [&](const BrokerCommand &, const std::string &directory) {
        alarm(10);
        close(ready[0]);
        for (const auto *name : {"askpass", "foreign-entry"}) {
            const int fd = open((directory + "/" + name).c_str(), O_WRONLY | O_CREAT | O_EXCL, 0600);
            assert(fd >= 0 && write(fd, "private", 7) == 7);
            close(fd);
        }
        const pid_t worker = getpid();
        assert(write(ready[1], &worker, sizeof(worker)) == sizeof(worker));
        for (;;) pause();
        return 0;
    });
    assert(broker.Open());
    BrokerCommand command;
    command.start = true;
    command.owner = {123, 100, "actual.owner", "cleanup-retry"};
    command.interfaceName = "multitun-vpn1";
    command.session = {std::string(32, 'a'), "client\nactual-profile\n", "secret"};
    assert(broker.Apply(command) == 0);
    close(ready[1]);
    pollfd readable {ready[0], POLLIN, 0};
    assert(poll(&readable, 1, 3000) == 1);
    pid_t worker = -1;
    assert(read(ready[0], &worker, sizeof(worker)) == sizeof(worker) && worker > 1);
    close(ready[0]);
    std::string session;
    for (const auto &entry : std::filesystem::directory_iterator(root))
        if (entry.is_directory()) session = entry.path();
    assert(!session.empty());
    std::string start;
#ifdef __linux__
    assert(broker.Identity(command.session.token, worker, start));
#endif
    const auto stop = BrokerMetadata(command);
    if (shutdown) assert(!broker.Shutdown());
    else assert(broker.Apply(stop) == EIO);
    // The process really exited; directory cleanup truthfully remains pending.
    assert(broker.Count() == 1);
    assert(kill(worker, 0) == -1 && errno == ESRCH);
    assert(std::filesystem::exists(session + "/askpass"));
    assert(std::filesystem::exists(session + "/foreign-entry"));
    const int afterExit = signalCalls;
    // Retrying a blocked cleanup must retain the reservation and must never
    // signal the retired process-group number, even when no PID was recycled.
    broker.Reap();
    assert(broker.Count() == 1 && signalCalls == afterExit);
    assert(!broker.Identity(command.session.token, worker, start));
    auto replacement = command;
    replacement.session.token = std::string(32, 'b');
    replacement.interfaceName = "multitun-vpn2";
    assert(broker.Apply(replacement) == EEXIST); // same owner remains reserved
    replacement.owner.bundle = "foreign.owner";
    replacement.owner.vpnId = "other";
    replacement.interfaceName = command.interfaceName;
    assert(broker.Apply(replacement) == EEXIST); // same interface remains reserved
    auto foreignStop = stop;
    foreignStop.owner = replacement.owner;
    assert(broker.Apply(foreignStop) == EPERM);
    assert(broker.Count() == 1 && signalCalls == afterExit);
    assert(std::filesystem::remove(session + "/foreign-entry"));
    if (shutdown) assert(broker.Shutdown());
    else assert(broker.Apply(stop) == 0);
    assert(broker.Count() == 0 && signalCalls == afterExit);
    assert(!std::filesystem::exists(session));
    assert(broker.Apply(stop) == 0 && broker.Apply(command) == EALREADY);
    for (const auto &entry : std::filesystem::directory_iterator(root))
        assert(entry.path().filename() == "backend.lock");
}
'''


class BrokerCleanupTests(unittest.TestCase):
    def run_case(self, action):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            extra = []
            if not sys.platform.startswith("linux"):
                stub = root / "sys"
                stub.mkdir()
                (stub / "prctl.h").write_text(
                    "#pragma once\n#define PR_SET_PDEATHSIG 1\n"
                    "inline int prctl(int,int,int,int,int){return 0;}\n")
                extra = ["-I", str(root)]
            compile_run(SOURCE, root, arguments=[str(root / "sessions"), action], extra=extra)

    def test_stop_cleanup_retries_without_signalling_retired_group(self):
        self.run_case("stop")

    def test_shutdown_retains_cleanup_until_retry_succeeds(self):
        self.run_case("shutdown")


if __name__ == "__main__":
    unittest.main()
