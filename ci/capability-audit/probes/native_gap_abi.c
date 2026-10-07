/* SPDX-License-Identifier: Apache-2.0
 * Actual system DSO loading/public symbol ownership. No API/backend claim.
 * SPEC_HEADER is generated from the final package's complete ABI evidence.
 */
#define _GNU_SOURCE
#include <dlfcn.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

struct AbiContract {
    const char *id;
    const char *library;
    const char *path;
    bool required;
    size_t count;
    const char *const *functions;
};
#include "native_gap_abi_contracts.h"

static void json_string(const char *text)
{
    putchar('"');
    for (const unsigned char *p = (const unsigned char *)text; *p; ++p) {
        if (*p == '"' || *p == '\\') {
            putchar('\\');
            putchar(*p);
        } else if (*p < 32 || *p >= 127) {
            printf("\\u%04x", *p);
        } else {
            putchar(*p);
        }
    }
    putchar('"');
}

int main(int argc, char **argv)
{
    if (argc != 2 || strlen(argv[1]) != 32 || strspn(argv[1], "0123456789abcdef") != 32) return 2;
    const char *run = argv[1];
    size_t functions = 0, loaded_count = 0, optional_count = 0;
    bool failed = false;
    for (size_t index = 0; index < sizeof(CONTRACTS) / sizeof(CONTRACTS[0]); ++index) {
        const struct AbiContract *spec = &CONTRACTS[index];
        void *library = spec->required ? dlopen(spec->path, RTLD_NOW | RTLD_LOCAL) : NULL;
        printf("{\"kind\":\"library\",\"id\":"); json_string(spec->id);
        printf(",\"runId\":"); json_string(run);
        printf(",\"required\":%s,\"loaded\":%s,\"path\":", spec->required ? "true" : "false",
               library ? "true" : "false"); json_string(spec->path);
        printf("}\n");
        if (!spec->required) {
            ++optional_count;
            continue;
        }
        if (!library) {
            const char *error = dlerror();
            fprintf(stderr, "%s: %s\n", spec->library, error ? error : "dlopen failed");
            failed = true;
        } else {
            ++loaded_count;
        }
        for (size_t member = 0; member < spec->count; ++member) {
            Dl_info info = {0};
            void *address = library ? dlsym(library, spec->functions[member]) : NULL;
            const bool resolved = address != NULL;
            const char *origin = resolved && dladdr(address, &info) != 0 && info.dli_fname ? info.dli_fname : "";
            const bool owner = strcmp(origin, spec->path) == 0;
            printf("{\"kind\":\"symbol\",\"id\":"); json_string(spec->id);
            printf(",\"runId\":"); json_string(run);
            printf(",\"name\":"); json_string(spec->functions[member]);
            printf(",\"resolved\":%s,\"origin\":", resolved ? "true" : "false"); json_string(origin);
            printf("}\n");
            failed = failed || !resolved || !owner;
            ++functions;
        }
        /* Keep actual system DSOs alive until exit; no substitute library or
         * standalone dlclose lifecycle is part of this ABI-only test. */
    }
    printf("{\"kind\":\"summary\",\"runId\":"); json_string(run);
    printf(",\"loaded_libraries\":%zu,\"optional_undeclared\":%zu,\"checked_symbols\":%zu,\"pass\":%s}\n",
           loaded_count, optional_count, functions, failed ? "false" : "true");
    return failed ? 1 : 0;
}
