/* SPDX-License-Identifier: Apache-2.0
 * Read actual AccessToken definitions; never allocate tokens or grant rights.
 * Uses innerkit headers/library from the pinned build, not a replicated ABI.
 */
#include "accesstoken_kit.h"
#include "access_token_error.h"
#include <cctype>
#include <cstdlib>
#include <cstdio>
#include <fstream>
#include <string>
#include <unordered_set>

using OHOS::Security::AccessToken::AccessTokenKit;
using OHOS::Security::AccessToken::PermissionDef;

static void query(const char *kind, const std::string &name)
{
    PermissionDef definition = {};
    const int result = AccessTokenKit::GetDefPermission(name, definition);
    // Input names are restricted below; fixed boundary strings also
    // cannot contain JSON quoting/control characters.
    printf("{\"kind\":\"%s\",\"permissionName\":\"%s\",\"result\":%d",
           kind, name.c_str(), result);
    if (result == 0) {
        if (definition.permissionName != name) {
            fprintf(stderr, "permission query returned a different name\n");
            std::exit(1);
        }
        printf(",\"grantMode\":%d,\"availableLevel\":%d,\"availableType\":%d,"
               "\"provisionEnable\":%s,\"distributedSceneEnable\":%s,"
               "\"isKernelEffect\":%s,\"hasValue\":%s",
               definition.grantMode, definition.availableLevel, definition.availableType,
               definition.provisionEnable ? "true" : "false",
               definition.distributedSceneEnable ? "true" : "false",
               definition.isKernelEffect ? "true" : "false", definition.hasValue ? "true" : "false");
    }
    puts("}");
}

int main(int argc, char **argv)
{
    if (argc != 3) { fprintf(stderr, "usage: permission_registry SOURCE_NAMES_FILE RUN_ID\n"); return 2; }
    const std::string runId = argv[2];
    if (runId.size() != 32) { fprintf(stderr, "run ID must be 32 lowercase hex characters\n"); return 2; }
    for (const char ch : runId) {
        if (!((ch >= '0' && ch <= '9') || (ch >= 'a' && ch <= 'f'))) return 2;
    }
    std::ifstream input(argv[1]);
    if (!input) { fprintf(stderr, "cannot open permission name input\n"); return 1; }
    printf("{\"kind\":\"run\",\"runId\":\"%s\"}\n", runId.c_str());
    std::unordered_set<std::string> seen;
    std::string name;
    while (std::getline(input, name)) {
        if (name.empty() || name.size() > 256 || name.rfind("ohos.permission.", 0) != 0 ||
            !seen.insert(name).second) {
            fprintf(stderr, "invalid or duplicate source permission name\n"); return 1;
        }
        for (const unsigned char ch : name) {
            if (!std::isalnum(ch) && ch != '.' && ch != '_') {
                fprintf(stderr, "unsafe source permission name\n"); return 1;
            }
        }
        query("definition", name);
    }
    if (!input.eof() || seen.empty()) { fprintf(stderr, "empty or unreadable source name input\n"); return 1; }
    query("absent", "ohos.permission.QEMU_CAPABILITY_AUDIT_DOES_NOT_EXIST");
    // Pinned DataValidator checks length, not the spelling of a nonempty
    // name. Punctuation is an unknown name, NOT an invalid-parameter case.
    query("unknown-format", "invalid!");
    constexpr size_t MAX_PERMISSION_NAME_LENGTH = 256;
    query("invalid", std::string(MAX_PERMISSION_NAME_LENGTH + 1, 'A'));
    query("empty", "");
    printf("{\"kind\":\"complete\",\"runId\":\"%s\",\"sourcePermissionCount\":%zu}\n",
           runId.c_str(), seen.size());
    return 0;
}
