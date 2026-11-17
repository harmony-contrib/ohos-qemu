# `netmanager_ext` NetFirewall 32-Bit HiLog Timestamp Cast

Uses `%{public}llu` with `static_cast<unsigned long long>(record->time)` in `netfirewall_intercept_recorder.cpp` for 32-bit `armv7a_virt` HiLog format portability.
