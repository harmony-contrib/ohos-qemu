#pragma once
#include <cerrno>
#include <chrono>
#include <cstring>
#include <dirent.h>
#include <fcntl.h>
#include <poll.h>
#include <string>
#include <sys/file.h>
#include <sys/stat.h>
#include <unistd.h>

namespace OhosOpenvpn {
// No recursive removal: only our exact mkdtemp namespace and known session
// entries are eligible, under an exclusively held, private, owned root.
inline bool SessionName(const char *name)
{
    if (!name || strlen(name) != 14 || strncmp(name, "session-", 8)) return false;
    for (const unsigned char *p = reinterpret_cast<const unsigned char *>(name + 8); *p; ++p)
        if (!((*p >= 'a' && *p <= 'z') || (*p >= 'A' && *p <= 'Z') || (*p >= '0' && *p <= '9'))) return false;
    return true;
}
inline bool PrivateOwned(int fd, bool directory, uid_t owner)
{
    struct stat st {};
    return fstat(fd, &st) == 0 && st.st_uid == owner &&
        (st.st_mode & 0777) == (directory ? 0700 : 0600) &&
        (directory ? S_ISDIR(st.st_mode) : (S_ISREG(st.st_mode) && st.st_nlink == 1));
}
inline bool RemoveSession(int root, const char *name, uid_t owner)
{
    if (!SessionName(name)) return false;
    int fd = openat(root, name, O_RDONLY | O_DIRECTORY | O_CLOEXEC | O_NOFOLLOW);
    if (fd < 0) return errno == ENOENT;
    bool valid = PrivateOwned(fd, true, owner);
    DIR *entries = valid ? fdopendir(dup(fd)) : nullptr;
    if (!entries) valid = false;
    if (entries) {
        errno = 0;
        while (dirent *entry = readdir(entries)) {
            const std::string item(entry->d_name);
            if (item == "." || item == "..") continue;
            if (item != "client.ovpn" && item != "askpass" && item != "management" && item != "ready" && item != "dns-wire.jsonl") {
                valid = false;
                break;
            }
        }
        if (errno) valid = false;
        closedir(entries);
    }
    if (valid) {
        for (const char *item : {"client.ovpn", "askpass", "management", "ready", "dns-wire.jsonl"})
            if (unlinkat(fd, item, 0) != 0 && errno != ENOENT) valid = false;
    }
    close(fd);
    return valid && (unlinkat(root, name, AT_REMOVEDIR) == 0 || errno == ENOENT);
}
class SessionStore {
public:
    SessionStore() = default;
    SessionStore(const SessionStore &) = delete;
    SessionStore &operator=(const SessionStore &) = delete;
    ~SessionStore() { if (lock_ >= 0) close(lock_); if (root_ >= 0) close(root_); }
    bool Open(const char *path, uid_t owner)
    {
        owner_ = owner;
        root_ = open(path, O_RDONLY | O_DIRECTORY | O_CLOEXEC | O_NOFOLLOW);
        if (root_ < 0 || !PrivateOwned(root_, true, owner)) return false;
        lock_ = openat(root_, "backend.lock", O_RDWR | O_CREAT | O_CLOEXEC | O_NOFOLLOW, 0600);
        if (lock_ < 0 || !PrivateOwned(lock_, false, owner)) return false;
        const auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds(5);
        while (flock(lock_, LOCK_EX | LOCK_NB) != 0) {
            if ((errno != EWOULDBLOCK && errno != EINTR) || std::chrono::steady_clock::now() >= deadline) return false;
            poll(nullptr, 0, 25);
        }
        // The previous supervisor has exited (or was killed by init). Its
        // parent-death-bound children cannot continue using these credentials.
        DIR *entries = fdopendir(dup(root_));
        if (!entries) return false;
        bool valid = true;
        errno = 0;
        while (dirent *entry = readdir(entries)) {
            if (!strcmp(entry->d_name, ".") || !strcmp(entry->d_name, "..") || !strcmp(entry->d_name, "backend.lock")) continue;
            if (!RemoveSession(root_, entry->d_name, owner)) { valid = false; break; }
            errno = 0;
        }
        if (errno) valid = false;
        closedir(entries);
        return valid;
    }
    bool Remove(const std::string &directory)
    {
        const auto at = directory.rfind('/');
        return root_ >= 0 && at != std::string::npos && RemoveSession(root_, directory.c_str() + at + 1, owner_);
    }
    void CloseInChild()
    {
        // Closing an inherited description must not unlock the parent's flock.
        if (lock_ >= 0) close(lock_);
        if (root_ >= 0) close(root_);
        lock_ = root_ = -1;
    }
private:
    uid_t owner_ = static_cast<uid_t>(-1);
    int root_ = -1;
    int lock_ = -1;
};
} // namespace OhosOpenvpn
