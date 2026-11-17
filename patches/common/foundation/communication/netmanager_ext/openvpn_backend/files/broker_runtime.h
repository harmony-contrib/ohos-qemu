#pragma once
#include "broker_protocol.h"
#include "process_lifecycle.h"
#include "session_files.h"
#include <algorithm>
#include <functional>
#include <map>
#include <signal.h>
#include <sys/wait.h>
#include <vector>

namespace OhosOpenvpn {
inline void EraseSecret(std::string &text)
{
    volatile char *data = text.empty() ? nullptr : &text[0];
    for (size_t i = 0; i < text.size(); ++i) data[i] = 0;
    text.clear();
}
inline BrokerCommand BrokerMetadata(const BrokerCommand &command)
{
    BrokerCommand result;
    result.owner = command.owner; result.interfaceName = command.interfaceName;
    result.session.token = command.session.token;
    return result;
}
// The sole init broker forks before touching IPC/FFRT. Its worker owns one
// process group, one private directory and one service-generated capability.
// Stops use actual process exit; no callback is needed to acknowledge them.
class BrokerRuntime {
public:
    using Worker = std::function<int(const BrokerCommand &, const std::string &)>;
    BrokerRuntime(std::string root, uid_t owner, Worker worker) : rootPath_(std::move(root)), owner_(owner), worker_(std::move(worker)) {}
    BrokerRuntime(const BrokerRuntime &) = delete;
    BrokerRuntime &operator=(const BrokerRuntime &) = delete;
    ~BrokerRuntime() { Shutdown(); }
    bool Open()
    {
#ifdef __linux__
        if (prctl(PR_SET_CHILD_SUBREAPER, 1) != 0) return false;
#endif
        return store_.Open(rootPath_.c_str(), owner_);
    }
    int Apply(const BrokerCommand &command, int listener = -1, int connection = -1)
    {
        if (!BrokerIdentity(command)) return EINVAL;
        Reap();
        return command.start ? Start(command, listener, connection) : Stop(command);
    }
    bool Identity(const std::string &generation, pid_t &worker, std::string &start) const
    {
        const auto found = jobs_.find(generation);
        if (found == jobs_.end() || found->second.killSent) return false;
        start = ProcessStart(found->second.pid);
        if (start.empty()) return false;
        worker = found->second.pid; return true;
    }
    size_t Count() const { return jobs_.size(); }
    void Reap()
    {
        for (auto it = jobs_.begin(); it != jobs_.end();) {
            siginfo_t state {};
            if (waitid(P_PID, it->second.pid, &state, WEXITED | WNOHANG | WNOWAIT) == 0 && !state.si_pid) { ++it; continue; }
            if (!Finish(it->second, 0)) { ++it; continue; }
            it = jobs_.erase(it);
        }
    }
    bool Shutdown()
    {
        for (auto &item : jobs_) SignalStop(item.second);
        const auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds(5);
        for (auto it = jobs_.begin(); it != jobs_.end();) {
            const auto left = std::chrono::duration_cast<std::chrono::milliseconds>(deadline - std::chrono::steady_clock::now()).count();
            if (Finish(it->second, static_cast<int>(std::max<int64_t>(0, std::min<int64_t>(500, left)))))
                it = jobs_.erase(it);
            else ++it;
        }
        return jobs_.empty();
    }
private:
    struct Job {
        BrokerCommand metadata;
        pid_t pid;
        std::string directory;
        bool killSent = false;
        bool processesReaped = false;
    };
    std::string rootPath_;
    uid_t owner_;
    Worker worker_;
    SessionStore store_;
    std::map<std::string, Job> jobs_;
    // Retired capabilities are never reusable within this broker lifetime.
    // Reaching this bound rejects new starts instead of evicting replay guards.
    std::map<std::string, BrokerCommand> used_;
    static bool Same(const BrokerCommand &a, const BrokerCommand &b)
    { return a.owner == b.owner && a.interfaceName == b.interfaceName && a.session.token == b.session.token; }
    static bool SignalStop(const Job &job)
    {
        if (job.killSent) return true;
        siginfo_t state {};
        int observed;
        do { observed = waitid(P_PID, job.pid, &state, WEXITED | WNOHANG | WNOWAIT); }
        while (observed < 0 && errno == EINTR);
        // The unreaped leader reserves the group ID. Never signal a PID/group
        // after losing that ownership, including cleanup-only retries.
        if (observed < 0) return false;
        kill(-job.pid, SIGTERM);
        return true; // actual exit/reaping, not signal delivery, proves STOP
    }
    bool Finish(Job &job, int grace)
    {
        if (!job.killSent) {
            if (!SignalStop(job)) return false;
            const auto deadline = std::chrono::steady_clock::now() + std::chrono::milliseconds(grace);
            for (;;) {
                siginfo_t state {};
                const int observed = waitid(P_PID, job.pid, &state, WEXITED | WNOHANG | WNOWAIT);
                if (observed < 0 && errno == EINTR) continue;
                if (observed < 0) return false;
                if (state.si_pid || std::chrono::steady_clock::now() >= deadline) break;
                poll(nullptr, 0, 10);
            }
            // Keep the unreaped worker's PID reserved until its whole group
            // has received SIGKILL, including a bridge blocked in an RPC.
            kill(-job.pid, SIGKILL);
            job.killSent = true;
        }
        const auto reapedBy = std::chrono::steady_clock::now() + std::chrono::seconds(2);
        while (!job.processesReaped) {
            int status = 0;
            const pid_t reaped = waitpid(-job.pid, &status, WNOHANG);
            if (reaped > 0 || (reaped < 0 && errno == EINTR)) continue;
            if (reaped < 0 && errno == ECHILD) { job.processesReaped = true; break; }
            if (reaped < 0 || std::chrono::steady_clock::now() >= reapedBy) return false;
            poll(nullptr, 0, 10);
        }
        // Removal may fail independently of exit (permissions, unknown files,
        // transient I/O). Retain the owner/interface reservation and retry only
        // removal; the retired group number must never receive another signal.
        return store_.Remove(job.directory);
    }
    int Start(const BrokerCommand &command, int listener, int connection)
    {
        if (!ValidSession(command.session)) return EINVAL;
        if (used_.count(command.session.token)) return EALREADY;
        if (jobs_.size() >= MAX_BROKER_SESSIONS || used_.size() >= 1024) return ENOSPC;
        for (const auto &item : jobs_)
            if (item.second.metadata.owner == command.owner || item.second.metadata.interfaceName == command.interfaceName) return EEXIST;
        std::string pattern = rootPath_ + "/session-XXXXXX";
        std::vector<char> path(pattern.begin(), pattern.end()); path.push_back('\0');
        if (!mkdtemp(path.data())) return errno ? errno : EIO;
        const std::string directory(path.data());
        const pid_t broker = getpid();
        const pid_t pid = fork();
        if (pid < 0) { const int failure = errno; store_.Remove(directory); return failure; }
        if (pid == 0) {
            if (listener >= 0) close(listener);
            if (connection >= 0 && connection != listener) close(connection);
            store_.CloseInChild();
            if (!BindToParent(broker) || setpgid(0, 0) != 0) _exit(126);
            const int status = worker_(command, directory);
            _exit(status);
        }
        if (setpgid(pid, pid) != 0 && errno != EACCES) {
            kill(pid, SIGKILL); int status = 0; while (waitpid(pid, &status, 0) < 0 && errno == EINTR) {}
            store_.Remove(directory); return EIO;
        }
        const auto metadata = BrokerMetadata(command);
        used_.emplace(command.session.token, metadata);
        jobs_.emplace(command.session.token, Job {metadata, pid, directory});
        return 0;
    }
    int Stop(const BrokerCommand &command)
    {
        const auto used = used_.find(command.session.token);
        if (used == used_.end()) return ENOENT;
        if (!Same(used->second, command)) return EPERM;
        auto job = jobs_.find(command.session.token);
        if (job == jobs_.end()) return 0; // already exited, exact owner only
        if (!Finish(job->second, 500)) return EIO;
        jobs_.erase(job); return 0;
    }
};
} // namespace OhosOpenvpn
