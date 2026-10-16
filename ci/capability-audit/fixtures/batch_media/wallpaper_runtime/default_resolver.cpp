/* Read-only test helper. Root must compile/link against the actual product.
 * Mirrors pinned WallpaperService GetDefaultResDir/GetWallpaperPathInJson.
 * Never calls a wallpaper mutation API or writes a resource/database. */
#include <cctype>
#include <cstdio>
#include <fstream>
#include <iterator>
#include <string>
#include <sys/stat.h>
#include "cJSON.h"
#include "config_policy_utils.h"

namespace {
bool Regular(const std::string &path)
{
    struct stat status {};
    return lstat(path.c_str(), &status) == 0 && S_ISREG(status.st_mode) && status.st_size > 0;
}

std::string ReadManifest(const std::string &path)
{
    struct stat status {};
    if (lstat(path.c_str(), &status) != 0 || !S_ISREG(status.st_mode) || status.st_size <= 0 || status.st_size > 65536) {
        return "";
    }
    std::ifstream file(path);
    return file ? std::string(std::istreambuf_iterator<char>(file), std::istreambuf_iterator<char>()) : "";
}

std::string Resolve(const std::string &root, const char *section, const char *fallback, cJSON *description)
{
    const auto manifest = root.empty() ? "" : root + section + "/manifest.json";
    const auto text = ReadManifest(manifest);
    cJSON *parsed = text.empty() ? nullptr : cJSON_Parse(text.c_str());
    const cJSON *image = parsed == nullptr ? nullptr : cJSON_GetObjectItemCaseSensitive(parsed, "image");
    const cJSON *src = image == nullptr ? nullptr : cJSON_GetObjectItemCaseSensitive(image, "src");
    std::string resolved;
    if (cJSON_IsObject(image) && cJSON_IsString(src) && src->valuestring != nullptr) {
        const auto candidate = root + section + "/base/resources/" + src->valuestring;
        if (Regular(candidate)) { resolved = candidate; }
    }
    cJSON_AddStringToObject(description, "manifest_remote", manifest.c_str());
    cJSON_AddStringToObject(description, "manifest_state", resolved.empty() ? "fallback" : "resolved");
    cJSON_Delete(parsed);
    if (resolved.empty() && Regular(fallback)) { resolved = fallback; }
    return resolved;
}
}

int main(int argc, char **argv)
{
    if (argc != 2 || std::string(argv[1]).size() != 32) { return 2; }
    for (const char *cursor = argv[1]; *cursor; ++cursor) {
        if (!std::isxdigit(static_cast<unsigned char>(*cursor))) { return 2; }
    }
    std::ifstream bootFile("/proc/sys/kernel/random/boot_id");
    std::string boot;
    if (!std::getline(bootFile, boot) || boot.size() != 36) { return 3; }
    cJSON *document = cJSON_CreateObject();
    cJSON *paths = cJSON_CreateArray();
    cJSON *resolved = cJSON_CreateObject();
    cJSON *descriptions = cJSON_CreateObject();
    if (!document || !paths || !resolved || !descriptions) { return 4; }
    cJSON_AddStringToObject(document, "run_id", argv[1]);
    cJSON_AddStringToObject(document, "boot_id", boot.c_str());
    cJSON_AddStringToObject(document, "resource_path", "resource/themes/theme/");
    cJSON_AddItemToObject(document, "paths", paths);
    cJSON_AddItemToObject(document, "resolved", resolved);
    cJSON_AddItemToObject(document, "descriptions", descriptions);
    std::string root;
    CfgFiles *files = GetCfgFiles("resource/themes/theme/");
    if (files != nullptr) {
        bool first = true;
        for (auto &path : files->paths) {
            if (path != nullptr) {
                cJSON_AddItemToArray(paths, cJSON_CreateString(path));
                if (first) { root = std::string(path) + "default/"; first = false; }
            }
        }
        FreeCfgFiles(files);
    }
    const char *names[] = {"desktop", "lock"};
    const char *sections[] = {"home", "lock"};
    const char *fallbacks[] = {"/system/etc/wallpaperdefault.jpeg", "/system/etc/wallpaperlockdefault.jpeg"};
    for (int i = 0; i < 2; ++i) {
        cJSON *description = cJSON_CreateObject();
        if (!description) { cJSON_Delete(document); return 4; }
        cJSON_AddItemToObject(descriptions, names[i], description);
        const auto value = Resolve(root, sections[i], fallbacks[i], description);
        if (value.empty() || !cJSON_AddStringToObject(resolved, names[i], value.c_str())) {
            cJSON_Delete(document); return 5;
        }
    }
    char *text = cJSON_PrintUnformatted(document);
    if (!text) { cJSON_Delete(document); return 4; }
    const int result = std::puts(text);
    cJSON_free(text); cJSON_Delete(document);
    return result < 0 ? 6 : 0;
}
