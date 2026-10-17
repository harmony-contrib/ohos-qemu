#pragma once
#include <chrono>
#include <string>
#include <cerrno>
#include <cstring>
#include <climits>
namespace OHOS { namespace AudioStandard {
struct Trace { template<class... T> explicit Trace(T&&...) {} void End() {} template<class... T> static void Count(T&&...) {} };
struct ClockTime { static int64_t GetCurNano() { return std::chrono::duration_cast<std::chrono::nanoseconds>(std::chrono::steady_clock::now().time_since_epoch()).count(); } };
} }
