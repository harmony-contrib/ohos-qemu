#pragma once
#include <cstddef>
#include <cstring>
#define EOK 0
static inline int memset_s(void *dst, size_t capacity, int value, size_t count) {
    if (count > capacity || (count && dst == nullptr)) return 22;
    if (count) std::memset(dst, value, count);
    return EOK;
}
static inline int memcpy_s(void *dst, size_t capacity, const void *src, size_t count) {
    if (count > capacity || (count && (dst == nullptr || src == nullptr))) return 22;
    if (count) std::memcpy(dst, src, count);
    return EOK;
}
