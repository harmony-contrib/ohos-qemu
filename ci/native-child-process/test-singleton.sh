#!/usr/bin/env bash
# Compile the real patched manager with hidden symbols in separate Linux DSOs.
set -euo pipefail
SOURCE="${1:?usage: test-singleton.sh OHOS_SOURCE_ROOT WORK_DIR}"
WORK="${2:?missing work directory}"
mkdir -p "$WORK"
WORK="$(cd "$WORK" && pwd)"
ABILITY="$SOURCE/foundation/ability/ability_runtime"
INCLUDES=(-I"$ABILITY/interfaces/inner_api/child_process_manager/include"
  -I"$ABILITY/interfaces/kits/c/ability/ability_runtime/child_process"
  -I"$SOURCE/commonlibrary/c_utils/base/include"
  -I"$SOURCE/foundation/communication/ipc/interfaces/innerkits/c_api/include")
cat > "$WORK/set.cpp" <<'CPP'
#include "child_process_args_manager.h"
using OHOS::AbilityRuntime::ChildProcessArgsManager;
extern "C" __attribute__((visibility("default"))) void Set(NativeChildProcess_Args args)
{
    ChildProcessArgsManager::GetInstance().SetChildProcessArgs(args);
}
CPP
cat > "$WORK/get.cpp" <<'CPP'
#include "child_process_args_manager.h"
using OHOS::AbilityRuntime::ChildProcessArgsManager;
extern "C" __attribute__((visibility("default"))) NativeChildProcess_Args* Get()
{
    return ChildProcessArgsManager::GetInstance().GetChildProcessArgs();
}
CPP
cat > "$WORK/main.cpp" <<'CPP'
#include "native_child_process.h"
#include <cassert>
#include <dlfcn.h>
#include <thread>
#include <cstdio>
int main()
{
    auto loader = dlopen("./libsetter.so", RTLD_NOW | RTLD_LOCAL);
    auto api = dlopen("./libgetter.so", RTLD_NOW | RTLD_LOCAL);
    if (!loader || !api) { fprintf(stderr, "%s\n", dlerror()); return 1; }
    auto set = reinterpret_cast<void (*)(NativeChildProcess_Args)>(dlsym(loader, "Set"));
    auto get = reinterpret_cast<NativeChildProcess_Args* (*)()>(dlsym(api, "Get"));
    assert(set && get && get() == nullptr);
    char text[] = "shared across hidden DSOs";
    NativeChildProcess_Args args{};
    args.entryParams = text;
    set(args);
    assert(get() && get()->entryParams == text);
    std::thread other([&] { assert(get() && get()->entryParams == text); });
    other.join();
    puts("PASS: actual manager singleton shared across two hidden DSOs and threads");
}
CPP
CXX="${CXX:-c++}"
"$CXX" -std=c++17 -shared -fPIC -fvisibility=hidden "${INCLUDES[@]}" \
  "$ABILITY/frameworks/native/ability/native/child_process_manager/child_process_args_manager.cpp" \
  -pthread -o "$WORK/libmanager.so"
for unit in set get; do
  case "$unit" in set) library=setter ;; get) library=getter ;; esac
  "$CXX" -std=c++17 -shared -fPIC -fvisibility=hidden "${INCLUDES[@]}" \
    "$WORK/$unit.cpp" -L"$WORK" -lmanager -Wl,-rpath,'$ORIGIN' \
    -pthread -o "$WORK/lib$library.so"
done
"$CXX" -std=c++17 "${INCLUDES[@]}" "$WORK/main.cpp" -ldl -pthread -o "$WORK/test"
(cd "$WORK" && ./test)
