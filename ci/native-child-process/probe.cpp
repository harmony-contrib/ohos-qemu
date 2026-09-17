// Direct SDK C API regression coverage: no Rust bindings and no private offsets.
#include <AbilityKit/native_child_process.h>
#include <napi/native_api.h>
#include <hilog/log.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <signal.h>
#include <poll.h>
#include <unistd.h>
#include <fcntl.h>
#include <cerrno>
#include <cstdarg>
#include <cstdlib>
#include <cstdio>
#include <cstring>
#include <string>
#include <thread>
#include <vector>

namespace {
constexpr size_t LIMIT = 150 * 1024;
constexpr const char* RESULT = "/data/storage/el2/base/files/native-child-process-results.log";
struct Report {
    uint64_t bytes;
    uint64_t hash;
    uint32_t fdCount;
    uint32_t entryMatches;
    uint32_t threadMatches;
    uint32_t validFds;
};
void Log(const char* fmt, ...)
{
    char text[1024];
    va_list args;
    va_start(args, fmt);
    vsnprintf(text, sizeof(text), fmt, args);
    va_end(args);
    OH_LOG_Print(LOG_APP, LOG_INFO, 0x1234, "NativeChildRegression", "%{public}s", text);
    FILE* file = fopen(RESULT, "a");
    if (file) { fprintf(file, "%s\n", text); fclose(file); }
}
uint64_t Hash(const char* text)
{
    uint64_t hash = 14695981039346656037ULL;
    if (text) for (const unsigned char* p = reinterpret_cast<const unsigned char*>(text); *p; ++p) {
        hash = (hash ^ *p) * 1099511628211ULL;
    }
    return hash;
}
bool Matches(const NativeChildProcess_Args& entry)
{
    auto* current = OH_Ability_GetCurrentChildProcessArgs();
    if (!current || !current->entryParams || !entry.entryParams ||
        strcmp(current->entryParams, entry.entryParams)) return false;
    auto* a = current->fdList.head;
    auto* b = entry.fdList.head;
    for (; a && b; a = a->next, b = b->next) {
        if (!a->fdName || !b->fdName || strcmp(a->fdName, b->fdName) || a->fd != b->fd) return false;
    }
    return !a && !b;
}
bool ReadAll(int fd, void* data, size_t size)
{
    auto* p = static_cast<char*>(data);
    while (size) {
        pollfd event{fd, POLLIN, 0};
        if (poll(&event, 1, 30000) <= 0) return false;
        ssize_t n = read(fd, p, size);
        if (n < 0 && errno == EINTR) continue;
        if (n <= 0) return false;
        p += n; size -= n;
    }
    return true;
}
bool WriteAll(int fd, const void* data, size_t size)
{
    const auto* p = static_cast<const char*>(data);
    while (size) {
        ssize_t n = send(fd, p, size, MSG_NOSIGNAL);
        if (n < 0 && errno == EINTR) continue;
        if (n <= 0) return false;
        p += n; size -= n;
    }
    return true;
}
}

extern "C" __attribute__((visibility("default"))) void Main(NativeChildProcess_Args args)
{
    Report report{};
    report.bytes = args.entryParams ? strlen(args.entryParams) : 0;
    report.hash = Hash(args.entryParams);
    report.entryMatches = Matches(args);
    std::thread other([&] { report.threadMatches = Matches(args); });
    other.join();
    report.validFds = 1;
    for (auto* fd = args.fdList.head; fd; fd = fd->next) {
        ++report.fdCount;
        if (!fd->fdName || strlen(fd->fdName) != 20 || fcntl(fd->fd, F_GETFD) < 0) report.validFds = 0;
    }
    if (!args.fdList.head) return;
    if (!WriteAll(args.fdList.head->fd, &report, sizeof(report))) return;
    uint8_t index = 0;
    for (auto* fd = args.fdList.head; fd; fd = fd->next) {
        WriteAll(fd->fd, &index, sizeof(index));
        ++index;
    }
}

namespace {
bool Case(const char* name, const std::string& params, int count, bool configured, bool reject = false)
{
    int pair[2];
    if (socketpair(AF_UNIX, SOCK_STREAM, 0, pair)) return false;
    std::vector<std::string> names(count);
    std::vector<NativeChildProcess_Fd> descriptors(count);
    for (int i = 0; i < count; ++i) {
        char nameBuffer[21];
        snprintf(nameBuffer, sizeof(nameBuffer), "fd_%017d", i);
        names[i] = nameBuffer;
        descriptors[i].fdName = names[i].data();
        descriptors[i].fd = pair[1];
        descriptors[i].next = i + 1 < count ? &descriptors[i + 1] : nullptr;
    }
    NativeChildProcess_Args args{};
    args.entryParams = const_cast<char*>(params.c_str());
    args.fdList.head = descriptors.data();
    int32_t pid = -1;
    int code;
    Log("BEGIN case=%s api=%s bytes=%zu fds=%d", name, configured ? "configs" : "start", params.size(), count);
    if (configured) {
        auto* configs = OH_Ability_CreateChildProcessConfigs();
        if (!configs) { close(pair[0]); close(pair[1]); return false; }
        code = OH_Ability_StartNativeChildProcessWithConfigs("libprobe.so:Main", args, configs, &pid);
        OH_Ability_DestroyChildProcessConfigs(configs);
    } else {
        NativeChildProcess_Options options{};
        code = OH_Ability_StartNativeChildProcess("libprobe.so:Main", args, options, &pid);
    }
    Log("RETURN case=%s api=%s code=%d pid=%d", name, configured ? "configs" : "start", code, pid);
    bool retained = fcntl(pair[1], F_GETFD) >= 0;
    close(pair[1]);
    Report report{};
    bool passed = false;
    if (reject) {
        passed = code == NCP_ERR_INVALID_PARAM && pid == -1 && retained;
    } else if (code == NCP_NO_ERROR && pid > 0 && ReadAll(pair[0], &report, sizeof(report))) {
        passed = report.bytes == params.size() && report.hash == Hash(params.c_str()) &&
            report.fdCount == static_cast<uint32_t>(count) && report.entryMatches && report.threadMatches && report.validFds;
        for (int i = 0; i < count && passed; ++i) {
            uint8_t marker = 255;
            passed = ReadAll(pair[0], &marker, sizeof(marker)) && marker == i;
        }
    }
    close(pair[0]);
    Log("%s case=%s api=%s bytes=%zu fds=%d code=%d pid=%d received=%llu entry=%u thread=%u fd_valid=%u",
        passed ? "PASS" : "FAIL", name, configured ? "configs" : "start", params.size(), count, code, pid,
        static_cast<unsigned long long>(report.bytes), report.entryMatches, report.threadMatches, report.validFds);
    usleep(300000);
    return passed;
}
void RunCases()
{
    unlink(RESULT);
    unsigned failures = 0, total = 0;
    auto check = [&](bool ok) { ++total; if (!ok) ++failures; };
    bool parent = OH_Ability_GetCurrentChildProcessArgs() == nullptr;
    Log("%s parent_getter_null", parent ? "PASS" : "FAIL");
    check(parent);
#ifdef NATIVE_CHILD_SINGLE_CASE
    if (NATIVE_CHILD_SINGLE_CASE == 1) check(Case("150KiB-ascii", std::string(LIMIT, 'p'), 2, false));
    if (NATIVE_CHILD_SINGLE_CASE == 2) check(Case("empty", "", 2, false));
    if (NATIVE_CHILD_SINGLE_CASE == 3) {
        check(Case("empty", "", 2, false));
        check(Case("150KiB-ascii", std::string(LIMIT, 'p'), 2, false));
    }
    Log("SUMMARY total=%u failures=%u", total, failures);
    return;
#endif
    std::string unicode;
    for (size_t i = 0; i < LIMIT / 3; ++i) unicode += u8"中";
    for (bool configured : {false, true}) {
        check(Case("empty", "", 2, configured));
        check(Case("small", "native-child-arguments", 2, configured));
        check(Case("99KiB", std::string(99 * 1024, 'p'), 2, configured));
        check(Case("100KiB", std::string(100 * 1024, 'p'), 2, configured));
        check(Case("limit-minus-one", std::string(LIMIT - 1, 'p'), 2, configured));
        check(Case("150KiB-ascii", std::string(LIMIT, 'p'), 2, configured));
        check(Case("150KiB-unicode", unicode, 2, configured));
        check(Case("150KiB-16-fds", std::string(LIMIT, 'p'), 16, configured));
        check(Case("over-limit", std::string(LIMIT + 1, 'p'), 16, configured, true));
        check(Case("after-rejection", "still-working", 2, configured));
    }
    Log("SUMMARY total=%u failures=%u", total, failures);
}
void RunSelected(int index)
{
    if (index < 0 || index >= 21) {
        Log("CASE_DONE index=%d pass=0 invalid-index", index);
        return;
    }
    bool passed = false;
    if (index == 0) {
        passed = OH_Ability_GetCurrentChildProcessArgs() == nullptr;
        Log("%s parent_getter_null", passed ? "PASS" : "FAIL");
    } else {
        const bool configured = index > 10;
        const int which = (index - 1) % 10;
        std::string unicode;
        switch (which) {
            case 0: passed = Case("empty", "", 2, configured); break;
            case 1: passed = Case("small", "native-child-arguments", 2, configured); break;
            case 2: passed = Case("99KiB", std::string(99 * 1024, 'p'), 2, configured); break;
            case 3: passed = Case("100KiB", std::string(100 * 1024, 'p'), 2, configured); break;
            case 4: passed = Case("limit-minus-one", std::string(LIMIT - 1, 'p'), 2, configured); break;
            case 5: passed = Case("150KiB-ascii", std::string(LIMIT, 'p'), 2, configured); break;
            case 6:
                for (size_t i = 0; i < LIMIT / 3; ++i) unicode += u8"中";
                passed = Case("150KiB-unicode", unicode, 2, configured);
                break;
            case 7: passed = Case("150KiB-16-fds", std::string(LIMIT, 'p'), 16, configured); break;
            case 8:
                passed = Case("over-limit", std::string(LIMIT + 1, 'p'), 16, configured, true) &&
                    Case("after-rejection", "still-working", 2, configured);
                break;
            case 9: passed = Case("after-rejection", "still-working", 2, configured); break;
        }
    }
    Log("CASE_DONE index=%d pass=%d", index, passed ? 1 : 0);
}
napi_value Run(napi_env env, napi_callback_info)
{
    auto mark = [](int sig) {
        int fd = open(RESULT, O_WRONLY | O_APPEND | O_CREAT, 0600);
        if (fd >= 0) {
            char line[80];
            int size = snprintf(line, sizeof(line), "SIGNAL parent=%d number=%d\n", getpid(), sig);
            if (size > 0) write(fd, line, static_cast<size_t>(size));
            close(fd);
        }
        _exit(128 + sig);
    };
    for (int sig : {SIGSEGV, SIGABRT, SIGBUS, SIGILL, SIGPIPE}) signal(sig, mark);
    atexit([] { Log("EXIT parent=%d", getpid()); });
    std::thread(RunCases).detach();
    napi_value result;
    napi_get_undefined(env, &result);
    return result;
}
napi_value RunCase(napi_env env, napi_callback_info info)
{
    size_t count = 1;
    napi_value argument;
    int32_t index = -1;
    if (napi_get_cb_info(env, info, &count, &argument, nullptr, nullptr) != napi_ok ||
        count != 1 || napi_get_value_int32(env, argument, &index) != napi_ok) {
        index = -1;
    }
    std::thread(RunSelected, index).detach();
    napi_value result;
    napi_get_undefined(env, &result);
    return result;
}
napi_value Init(napi_env env, napi_value exports)
{
    napi_property_descriptor methods[] = {
        {"run", nullptr, Run, nullptr, nullptr, nullptr, napi_default, nullptr},
        {"runCase", nullptr, RunCase, nullptr, nullptr, nullptr, napi_default, nullptr},
    };
    napi_define_properties(env, exports, 2, methods);
    return exports;
}
napi_module module{1, 0, nullptr, Init, "probe", nullptr, {0}};
}
extern "C" __attribute__((constructor)) void RegisterProbe() { napi_module_register(&module); }
