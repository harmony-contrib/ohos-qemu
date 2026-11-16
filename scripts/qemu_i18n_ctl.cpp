/*
 * Copyright (c) 2026 OpenHarmony QEMU contributors.
 * SPDX-License-Identifier: Apache-2.0
 *
 * System language, region, and locale controller (/system/bin/qemu-i18n-ctl).
 *
 * Acquires a native system_core access token with UPDATE_CONFIGURATION ACL and
 * invokes I18nServiceAbilityClient (SA 1602, libi18n_sa_client.z.so) so running
 * UI abilities (SceneBoard, Launcher, SystemUI, Settings, etc.) hot-reload
 * immediately via AppMgrClient::UpdateConfiguration + COMMON_EVENT_LOCALE_CHANGED
 * and persist across reboots in /data/service/el1/public/i18n/global/GlobalParamData.
 */

#include <algorithm>
#include <cctype>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <dlfcn.h>
#include <fcntl.h>
#include <pwd.h>
#include <string>
#include <sys/stat.h>
#include <sys/types.h>
#include <unistd.h>
#include <vector>

namespace {

struct NativeTokenInfoParamsC {
    int32_t dcapsNum;
    int32_t permsNum;
    int32_t aclsNum;
    const char **dcaps;
    const char **perms;
    const char **acls;
    const char *processName;
    const char *aplStr;
    int32_t uid;
};

using FnGetAccessTokenId = uint64_t (*)(NativeTokenInfoParamsC *);
using FnSetSelfTokenID = int (*)(uint64_t);
using FnGetParameter = int (*)(const char *, const char *, char *, uint32_t);
using FnSetParameter = int (*)(const char *, const char *);
using FnSetSystemString = int32_t (*)(const std::string &);
using FnAddPreferredLanguage = int32_t (*)(const std::string &, int32_t);

constexpr const char *kSymSetSystemLanguage =
    "_ZN4OHOS6Global4I18n24I18nServiceAbilityClient17SetSystemLanguageERKNSt3__h12basic_stringIcNS3_11char_traitsIcEENS3_9allocatorIcEEEE";
constexpr const char *kSymSetSystemRegion =
    "_ZN4OHOS6Global4I18n24I18nServiceAbilityClient15SetSystemRegionERKNSt3__h12basic_stringIcNS3_11char_traitsIcEENS3_9allocatorIcEEEE";
constexpr const char *kSymSetSystemLocale =
    "_ZN4OHOS6Global4I18n24I18nServiceAbilityClient15SetSystemLocaleERKNSt3__h12basic_stringIcNS3_11char_traitsIcEENS3_9allocatorIcEEEE";
constexpr const char *kSymAddPreferredLanguage =
    "_ZN4OHOS6Global4I18n24I18nServiceAbilityClient20AddPreferredLanguageERKNSt3__h12basic_stringIcNS3_11char_traitsIcEENS3_9allocatorIcEEEEi";

constexpr const char *kGlobalParamDir = "/data/service/el1/public/i18n/global";
constexpr const char *kGlobalParamPath = "/data/service/el1/public/i18n/global/GlobalParamData";
constexpr const char *kI18nParamConfigXml = "/system/etc/xml/i18n_param_config.xml";

struct ResolvedLocale {
    std::string language;
    std::string region;
    std::string locale;
    bool valid = false;
    std::string error;
};

std::string to_lower_ascii(std::string s) {
    for (char &c : s) {
        c = static_cast<char>(std::tolower(static_cast<unsigned char>(c)));
    }
    return s;
}

std::string to_upper_ascii(std::string s) {
    for (char &c : s) {
        c = static_cast<char>(std::toupper(static_cast<unsigned char>(c)));
    }
    return s;
}

std::string to_title_ascii(std::string s) {
    if (s.empty()) {
        return s;
    }
    s = to_lower_ascii(s);
    s[0] = static_cast<char>(std::toupper(static_cast<unsigned char>(s[0])));
    return s;
}

std::string trim_ascii(const std::string &s) {
    size_t b = 0;
    while (b < s.size() && std::isspace(static_cast<unsigned char>(s[b]))) {
        ++b;
    }
    size_t e = s.size();
    while (e > b && std::isspace(static_cast<unsigned char>(s[e - 1]))) {
        --e;
    }
    return s.substr(b, e - b);
}

bool is_alpha_only(const std::string &s) {
    if (s.empty()) {
        return false;
    }
    for (char c : s) {
        if (!std::isalpha(static_cast<unsigned char>(c))) {
            return false;
        }
    }
    return true;
}

bool is_valid_region_code(const std::string &s) {
    if (s.size() == 2) {
        return is_alpha_only(s);
    }
    if (s.size() == 3) {
        for (char c : s) {
            if (!std::isdigit(static_cast<unsigned char>(c))) {
                return false;
            }
        }
        return true;
    }
    return false;
}

std::vector<std::string> split_char(const std::string &s, char sep) {
    std::vector<std::string> out;
    size_t start = 0;
    while (start <= s.size()) {
        size_t pos = s.find(sep, start);
        if (pos == std::string::npos) {
            out.push_back(s.substr(start));
            break;
        }
        out.push_back(s.substr(start, pos - start));
        start = pos + 1;
    }
    return out;
}

void *dlopen_any(const char *soname) {
    void *h = dlopen(soname, RTLD_LAZY);
    if (h) {
        return h;
    }
    const char *dirs[] = {
        "/system/lib64/platformsdk/",
        "/system/lib64/chipset-pub-sdk/",
        "/system/lib64/chipset-sdk-sp/",
        "/system/lib64/",
        "/system/lib/platformsdk/",
        "/system/lib/chipset-pub-sdk/",
        "/system/lib/chipset-sdk-sp/",
        "/system/lib/",
    };
    for (const char *dir : dirs) {
        std::string full = std::string(dir) + soname;
        h = dlopen(full.c_str(), RTLD_LAZY);
        if (h) {
            return h;
        }
    }
    return nullptr;
}

std::string get_sys_param(const char *key, const char *def_val = "") {
    static void *h_beget = dlopen_any("libbegetutil.z.so");
    static FnGetParameter fn_get = h_beget ? reinterpret_cast<FnGetParameter>(dlsym(h_beget, "GetParameter")) : nullptr;
    char buf[128] = {0};
    if (fn_get && fn_get(key, def_val, buf, sizeof(buf) - 1) >= 0 && buf[0] != '\0') {
        return std::string(buf);
    }
    return std::string(def_val ? def_val : "");
}

int set_sys_param(const char *key, const std::string &val) {
    static void *h_beget = dlopen_any("libbegetutil.z.so");
    static FnSetParameter fn_set = h_beget ? reinterpret_cast<FnSetParameter>(dlsym(h_beget, "SetParameter")) : nullptr;
    if (fn_set) {
        return fn_set(key, val.c_str());
    }
    return -1;
}

std::string extract_region_from_locale(const std::string &loc) {
    std::string base = loc;
    size_t u_pos = base.find("-u-");
    if (u_pos != std::string::npos) {
        base = base.substr(0, u_pos);
    }
    size_t x_pos = base.find("-x-");
    if (x_pos != std::string::npos) {
        base = base.substr(0, x_pos);
    }
    std::vector<std::string> parts = split_char(base, '-');
    for (size_t i = 1; i < parts.size(); ++i) {
        if (is_valid_region_code(parts[i])) {
            return to_upper_ascii(parts[i]);
        }
    }
    return "";
}

std::string build_locale_tag(const std::string &language_tag, const std::string &region_tag) {
    std::vector<std::string> parts = split_char(language_tag, '-');
    if (parts.empty()) {
        return "";
    }
    std::string lang = to_lower_ascii(parts[0]);
    std::string script;
    std::string embedded_region;
    for (size_t i = 1; i < parts.size(); ++i) {
        if (parts[i].size() == 4 && is_alpha_only(parts[i])) {
            script = to_title_ascii(parts[i]);
        } else if (is_valid_region_code(parts[i])) {
            embedded_region = to_upper_ascii(parts[i]);
        }
    }
    if (script.empty()) {
        if (lang == "en") script = "Latn";
        else if (lang == "zh") script = "Hans";
        else if (lang == "bo") script = "Tibt";
        else if (lang == "ug") script = "Arab";
    }
    std::string reg = !region_tag.empty() ? to_upper_ascii(region_tag) : embedded_region;
    std::string out = lang;
    if (!script.empty()) {
        out += "-" + script;
    }
    if (!reg.empty()) {
        out += "-" + reg;
    }
    return out;
}

ResolvedLocale resolve_locale_request(const std::string &raw_spec, const std::string &raw_region) {
    ResolvedLocale res;
    std::string spec = trim_ascii(raw_spec);
    std::string explicit_region = trim_ascii(raw_region);

    if (!explicit_region.empty()) {
        if (!is_valid_region_code(explicit_region)) {
            res.error = "invalid region tag: " + explicit_region;
            return res;
        }
        explicit_region = to_upper_ascii(explicit_region);
    }

    if (spec.empty() && !explicit_region.empty()) {
        std::string cur_lang = get_sys_param("persist.global.language", "");
        if (cur_lang.empty()) {
            cur_lang = get_sys_param("const.global.language", "zh-Hans");
        }
        res.language = cur_lang;
        res.region = explicit_region;
        res.locale = build_locale_tag(cur_lang, explicit_region);
        res.valid = true;
        return res;
    }

    // Normalize '_' and '@' separators to '-'
    std::string norm = spec;
    size_t dot = norm.find('.');
    if (dot != std::string::npos) {
        norm = norm.substr(0, dot); // e.g. en_US.UTF-8 -> en_US
    }
    for (char &c : norm) {
        if (c == '_' || c == '@') {
            c = '-';
        }
    }
    std::string key = to_lower_ascii(norm);

    struct AliasEntry {
        const char *alias;
        const char *language;
        const char *default_region;
    };
    static const AliasEntry kAliases[] = {
        {"en", "en-Latn-US", "US"},
        {"eng", "en-Latn-US", "US"},
        {"english", "en-Latn-US", "US"},
        {"en-us", "en-Latn-US", "US"},
        {"en-latn", "en-Latn-US", "US"},
        {"en-latn-us", "en-Latn-US", "US"},
        {"en-gb", "en-Latn-US", "GB"},
        {"en-uk", "en-Latn-US", "GB"},
        {"en-latn-gb", "en-Latn-US", "GB"},
        {"en-au", "en-Latn-US", "AU"},
        {"en-ca", "en-Latn-US", "CA"},
        {"en-sg", "en-Latn-US", "SG"},
        {"zh", "zh-Hans", "CN"},
        {"zho", "zh-Hans", "CN"},
        {"chs", "zh-Hans", "CN"},
        {"chinese", "zh-Hans", "CN"},
        {"zh-cn", "zh-Hans", "CN"},
        {"zh-hans", "zh-Hans", "CN"},
        {"zh-hans-cn", "zh-Hans", "CN"},
        {"zh-sg", "zh-Hans", "SG"},
        {"zh-hans-sg", "zh-Hans", "SG"},
        {"zh-tw", "zh-Hant", "TW"},
        {"cht", "zh-Hant", "TW"},
        {"zh-hant", "zh-Hant", "TW"},
        {"zh-hant-tw", "zh-Hant", "TW"},
        {"zh-hk", "zh-Hant-HK", "HK"},
        {"zh-hant-hk", "zh-Hant-HK", "HK"},
        {"zh-mo", "zh-Hant", "MO"},
        {"zh-hant-mo", "zh-Hant", "MO"},
        {"ja", "ja", "JP"},
        {"jpn", "ja", "JP"},
        {"japanese", "ja", "JP"},
        {"ja-jp", "ja", "JP"},
        {"ja-jpan", "ja", "JP"},
        {"ja-jpan-jp", "ja", "JP"},
        {"ko", "ko", "KR"},
        {"kor", "ko", "KR"},
        {"korean", "ko", "KR"},
        {"ko-kr", "ko", "KR"},
        {"ko-kore", "ko", "KR"},
        {"ko-kore-kr", "ko", "KR"},
        {"fr", "fr", "FR"},
        {"fra", "fr", "FR"},
        {"french", "fr", "FR"},
        {"fr-fr", "fr", "FR"},
        {"fr-latn-fr", "fr", "FR"},
        {"de", "de", "DE"},
        {"deu", "de", "DE"},
        {"german", "de", "DE"},
        {"de-de", "de", "DE"},
        {"de-latn-de", "de", "DE"},
        {"es", "es-ES", "ES"},
        {"spa", "es-ES", "ES"},
        {"spanish", "es-ES", "ES"},
        {"es-es", "es-ES", "ES"},
        {"es-latn-es", "es-ES", "ES"},
        {"es-us", "es-US", "US"},
        {"es-419", "es-US", "US"},
        {"es-mx", "es-US", "MX"},
        {"it", "it", "IT"},
        {"ita", "it", "IT"},
        {"italian", "it", "IT"},
        {"it-it", "it", "IT"},
        {"pt", "pt", "BR"},
        {"por", "pt", "BR"},
        {"portuguese", "pt", "BR"},
        {"pt-br", "pt", "BR"},
        {"pt-pt", "pt-PT", "PT"},
        {"ru", "ru", "RU"},
        {"rus", "ru", "RU"},
        {"russian", "ru", "RU"},
        {"ru-ru", "ru", "RU"},
        {"ru-cyrl-ru", "ru", "RU"},
        {"ar", "ar", "SA"},
        {"ara", "ar", "SA"},
        {"arabic", "ar", "SA"},
        {"ar-sa", "ar", "SA"},
        {"ar-ae", "ar", "AE"},
        {"ar-eg", "ar", "EG"},
        {"ar-arab-sa", "ar", "SA"},
        {"vi", "vi", "VN"},
        {"vie", "vi", "VN"},
        {"vietnamese", "vi", "VN"},
        {"vi-vn", "vi", "VN"},
        {"bo", "bo", "CN"},
        {"tibetan", "bo", "CN"},
        {"bo-cn", "bo", "CN"},
        {"bo-tibt", "bo", "CN"},
        {"bo-tibt-cn", "bo", "CN"},
        {"ug", "ug", "CN"},
        {"uyghur", "ug", "CN"},
        {"ug-cn", "ug", "CN"},
        {"ug-arab", "ug", "CN"},
        {"ug-arab-cn", "ug", "CN"},
    };

    for (const auto &entry : kAliases) {
        if (key == entry.alias) {
            res.language = entry.language;
            res.region = !explicit_region.empty() ? explicit_region : entry.default_region;
            res.locale = build_locale_tag(res.language, res.region);
            res.valid = true;
            return res;
        }
    }

    // Generic BCP-47 validation: <lang:2..3 alpha>[-<Script:4 alpha>][-<REGION:2 alpha|3 digit>]
    std::vector<std::string> parts = split_char(norm, '-');
    if (parts.empty() || parts[0].size() < 2 || parts[0].size() > 3 || !is_alpha_only(parts[0])) {
        res.error = "invalid language/locale tag: " + raw_spec;
        return res;
    }

    std::string lang = to_lower_ascii(parts[0]);
    std::string script;
    std::string parsed_region;
    for (size_t i = 1; i < parts.size(); ++i) {
        if (parts[i].empty()) {
            res.error = "invalid empty subtag in: " + raw_spec;
            return res;
        }
        if (parts[i].size() == 4 && is_alpha_only(parts[i]) && script.empty()) {
            script = to_title_ascii(parts[i]);
        } else if (is_valid_region_code(parts[i]) && parsed_region.empty()) {
            parsed_region = to_upper_ascii(parts[i]);
        } else {
            res.error = "unsupported subtag in language/locale: " + raw_spec;
            return res;
        }
    }

    std::string cur_locale = get_sys_param("persist.global.locale", "");
    if (cur_locale.empty()) {
        cur_locale = get_sys_param("const.global.locale", "zh-Hans-CN");
    }
    std::string fallback_region = extract_region_from_locale(cur_locale);
    if (fallback_region.empty()) {
        fallback_region = get_sys_param("const.global.region", "US");
    }

    if (lang == "en") {
        res.language = "en-Latn-US";
        res.region = !explicit_region.empty() ? explicit_region : (!parsed_region.empty() ? parsed_region : "US");
    } else if (lang == "zh") {
        if (script == "Hant" || parsed_region == "TW" || parsed_region == "MO") {
            res.language = "zh-Hant";
            res.region = !explicit_region.empty() ? explicit_region : (!parsed_region.empty() ? parsed_region : "TW");
        } else if (parsed_region == "HK") {
            res.language = "zh-Hant-HK";
            res.region = !explicit_region.empty() ? explicit_region : "HK";
        } else {
            res.language = "zh-Hans";
            res.region = !explicit_region.empty() ? explicit_region : (!parsed_region.empty() ? parsed_region : "CN");
        }
    } else {
        res.language = script.empty() ? lang : (lang + "-" + script);
        res.region = !explicit_region.empty() ? explicit_region : (!parsed_region.empty() ? parsed_region : fallback_region);
    }
    res.locale = build_locale_tag(res.language, res.region);
    res.valid = true;
    return res;
}

void ensure_dir(const char *path, mode_t mode) {
    mkdir(path, mode);
    chmod(path, mode);
}

void chown_i18n_if_present(const char *path) {
    const char *names[] = {"i18n_service", "i18n"};
    for (const char *name : names) {
        struct passwd *pw = getpwnam(name);
        if (pw) {
            (void)chown(path, pw->pw_uid, pw->pw_gid);
            return;
        }
    }
}

bool write_global_param_data(const std::string &language, const std::string &locale) {
    ensure_dir("/data/service", 0771);
    ensure_dir("/data/service/el1", 0771);
    ensure_dir("/data/service/el1/public", 0775);
    ensure_dir("/data/service/el1/public/i18n", 0755);
    chown_i18n_if_present("/data/service/el1/public/i18n");
    ensure_dir(kGlobalParamDir, 0777);
    chown_i18n_if_present(kGlobalParamDir);

    std::string is24 = get_sys_param("persist.global.is24Hour", "default");
    if (is24.empty()) {
        is24 = "default";
    }
    // Single-line NativePreferences XML without whitespace text children under <preferences>.
    std::string xml =
        "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n"
        "<preferences version=\"1.0\">"
        "<bool key=\"init\" value=\"true\"/>"
        "<string key=\"is24HourData\">100:" + is24 + "</string>"
        "<string key=\"languageData\">100:" + language + "</string>"
        "<string key=\"localeData\">100:" + locale + "</string>"
        "</preferences>";

    std::string tmp_path = std::string(kGlobalParamPath) + ".tmp";
    int fd = open(tmp_path.c_str(), O_CREAT | O_WRONLY | O_TRUNC | O_CLOEXEC, 0666);
    if (fd < 0) {
        return false;
    }
    ssize_t written = write(fd, xml.data(), xml.size());
    fsync(fd);
    close(fd);
    if (written != static_cast<ssize_t>(xml.size())) {
        unlink(tmp_path.c_str());
        return false;
    }
    chmod(tmp_path.c_str(), 0666);
    chown_i18n_if_present(tmp_path.c_str());
    if (rename(tmp_path.c_str(), kGlobalParamPath) != 0) {
        unlink(tmp_path.c_str());
        return false;
    }
    chmod(kGlobalParamPath, 0666);
    chown_i18n_if_present(kGlobalParamPath);
    return true;
}

void update_preferred_languages_param(const std::string &language) {
    std::string cur = get_sys_param("persist.global.preferredLanguages", "");
    std::vector<std::string> items;
    items.push_back(language);
    for (const std::string &tok : split_char(cur, ';')) {
        if (!tok.empty() && tok != language) {
            items.push_back(tok);
        }
    }
    std::string joined;
    for (size_t i = 0; i < items.size(); ++i) {
        if (i > 0) {
            joined += ";";
        }
        joined += items[i];
    }
    (void)set_sys_param("persist.global.preferredLanguages", joined);
}

bool acquire_i18n_native_token() {
    void *h_nt = dlopen_any("libnativetoken_shared.z.so");
    void *h_sp = dlopen_any("libtokensetproc_shared.z.so");
    if (!h_nt || !h_sp) {
        return false;
    }
    auto fn_get_token = reinterpret_cast<FnGetAccessTokenId>(dlsym(h_nt, "GetAccessTokenId"));
    auto fn_set_self = reinterpret_cast<FnSetSelfTokenID>(dlsym(h_sp, "SetSelfTokenID"));
    if (!fn_get_token || !fn_set_self) {
        return false;
    }
    const char *perms[] = {
        "ohos.permission.UPDATE_CONFIGURATION",
        "ohos.permission.MANAGE_SECURE_SETTINGS",
        "ohos.permission.MANAGE_LOCAL_ACCOUNTS",
        "ohos.permission.INTERACT_ACROSS_LOCAL_ACCOUNTS",
    };
    NativeTokenInfoParamsC info = {};
    info.dcapsNum = 0;
    info.permsNum = static_cast<int32_t>(sizeof(perms) / sizeof(perms[0]));
    info.aclsNum = info.permsNum;
    info.dcaps = nullptr;
    info.perms = perms;
    info.acls = perms;
    info.processName = "qemu_i18n_ctl";
    info.aplStr = "system_core";
    info.uid = static_cast<int32_t>(getuid());

    uint64_t token_id = fn_get_token(&info);
    if (token_id == 0) {
        return false;
    }
    return fn_set_self(token_id) == 0;
}

int print_status() {
    std::string lang = get_sys_param("persist.global.language", "");
    if (lang.empty()) {
        lang = get_sys_param("const.global.language", "zh-Hans");
    }
    std::string loc = get_sys_param("persist.global.locale", "");
    if (loc.empty()) {
        loc = get_sys_param("const.global.locale", "zh-Hans-CN");
    }
    std::string reg = extract_region_from_locale(loc);
    if (reg.empty()) {
        reg = get_sys_param("const.global.region", "CN");
    }
    std::string pref = get_sys_param("persist.global.preferredLanguages", "");
    std::printf("OK LOCALE language=%s region=%s locale=%s preferred=%s\n",
                lang.c_str(), reg.c_str(), loc.c_str(), pref.empty() ? lang.c_str() : pref.c_str());
    return 0;
}

int print_supported_languages() {
    int fd = open(kI18nParamConfigXml, O_RDONLY | O_CLOEXEC);
    std::string content;
    if (fd >= 0) {
        char buf[4096];
        ssize_t n = 0;
        while ((n = read(fd, buf, sizeof(buf))) > 0) {
            content.append(buf, static_cast<size_t>(n));
        }
        close(fd);
    }
    std::string langs = "zh-Hans,en-Latn-US,zh-Hant,bo,ug";
    size_t b = content.find("<white_languages>");
    size_t e = content.find("</white_languages>");
    if (b != std::string::npos && e != std::string::npos && e > b + 17) {
        langs = trim_ascii(content.substr(b + 17, e - (b + 17)));
    }
    std::printf("OK LOCALE_LIST %s\n", langs.c_str());
    return 0;
}

void print_usage(FILE *out) {
    std::fprintf(
        out,
        "Usage: qemu-i18n-ctl [OPTIONS] [status | list | <LANG_OR_LOCALE>]\n\n"
        "Options:\n"
        "  -l, --lang, --locale TAG   Language or locale tag (e.g. en, en-US, en-GB, zh, zh-Hant, ja, ko, fr, de, es, ru, ar, vi)\n"
        "  -r, --region REGION        ISO 3166-1 region override (e.g. US, GB, CN, TW, HK, JP, KR, FR, DE)\n"
        "      --preseed-only         Pre-seed persist.global.* and GlobalParamData without invoking SA 1602\n"
        "      --list                 Print whitelisted system language tags\n"
        "      --status               Print active language, region, and locale\n"
        "  -h, --help                 Show this help\n\n"
        "Environment variables (overridden by CLI options):\n"
        "  QEMU_LOCALE / QEMU_LANG / OHOS_QEMU_LOCALE / OHOS_QEMU_LANG\n"
        "  QEMU_REGION / OHOS_QEMU_REGION\n");
}

const char *first_non_empty_env(std::initializer_list<const char *> names) {
    for (const char *name : names) {
        const char *val = std::getenv(name);
        if (val && val[0] != '\0') {
            return val;
        }
    }
    return "";
}

} // namespace

int main(int argc, char **argv) {
    std::string spec = first_non_empty_env({"QEMU_LOCALE", "QEMU_LANG", "OHOS_QEMU_LOCALE", "OHOS_QEMU_LANG"});
    std::string region = first_non_empty_env({"QEMU_REGION", "OHOS_QEMU_REGION"});
    bool preseed_only = false;
    bool explicit_status = false;
    bool explicit_list = false;

    for (int i = 1; i < argc; ++i) {
        std::string arg = argv[i];
        if (arg == "-h" || arg == "--help") {
            print_usage(stdout);
            return 0;
        }
        if (arg == "--preseed-only") {
            preseed_only = true;
            continue;
        }
        if (arg == "--status" || arg == "status" || arg == "get") {
            explicit_status = true;
            continue;
        }
        if (arg == "--list" || arg == "list") {
            explicit_list = true;
            continue;
        }
        if (arg == "-l" || arg == "--lang" || arg == "--locale") {
            if (i + 1 >= argc) {
                std::printf("ERR LOCALE missing value for %s\n", arg.c_str());
                return 2;
            }
            spec = argv[++i];
            continue;
        }
        if (arg.rfind("--lang=", 0) == 0) {
            spec = arg.substr(7);
            continue;
        }
        if (arg.rfind("--locale=", 0) == 0) {
            spec = arg.substr(9);
            continue;
        }
        if (arg == "-r" || arg == "--region") {
            if (i + 1 >= argc) {
                std::printf("ERR LOCALE missing value for %s\n", arg.c_str());
                return 2;
            }
            region = argv[++i];
            continue;
        }
        if (arg.rfind("--region=", 0) == 0) {
            region = arg.substr(9);
            continue;
        }
        if (!arg.empty() && arg[0] == '-') {
            std::printf("ERR LOCALE unknown option: %s\n", arg.c_str());
            return 2;
        }
        spec = arg;
    }

    if (explicit_list) {
        return print_supported_languages();
    }
    if (explicit_status || (spec.empty() && region.empty())) {
        return print_status();
    }

    ResolvedLocale target = resolve_locale_request(spec, region);
    if (!target.valid) {
        std::printf("ERR LOCALE %s\n", target.error.c_str());
        return 2;
    }

    // Always pre-seed persistent parameters and GlobalParamData first so early-boot
    // callers work before samgr/i18n_service starts and reboots never revert.
    (void)set_sys_param("persist.global.language", target.language);
    (void)set_sys_param("persist.global.locale", target.locale);
    update_preferred_languages_param(target.language);
    (void)write_global_param_data(target.language, target.locale);

    if (preseed_only) {
        std::printf("OK LOCALE language=%s region=%s locale=%s mode=preseed\n",
                    target.language.c_str(), target.region.c_str(), target.locale.c_str());
        return 0;
    }

    int32_t sa_rc = -1;
    if (acquire_i18n_native_token()) {
        void *h_i18n = dlopen_any("libi18n_sa_client.z.so");
        if (h_i18n) {
            auto fn_set_lang = reinterpret_cast<FnSetSystemString>(dlsym(h_i18n, kSymSetSystemLanguage));
            auto fn_set_reg = reinterpret_cast<FnSetSystemString>(dlsym(h_i18n, kSymSetSystemRegion));
            auto fn_set_loc = reinterpret_cast<FnSetSystemString>(dlsym(h_i18n, kSymSetSystemLocale));
            auto fn_add_pref = reinterpret_cast<FnAddPreferredLanguage>(dlsym(h_i18n, kSymAddPreferredLanguage));

            if (fn_set_reg && !target.region.empty()) {
                (void)fn_set_reg(target.region);
            }
            if (fn_add_pref && !target.language.empty()) {
                (void)fn_add_pref(target.language, 0);
            }
            if (fn_set_lang && !target.language.empty()) {
                sa_rc = fn_set_lang(target.language);
            } else if (fn_set_loc && !target.locale.empty()) {
                sa_rc = fn_set_loc(target.locale);
            }
        }
    }

    // Re-read final effective parameters after SA update (or keep pre-seeded values if SA not yet up).
    std::string final_lang = get_sys_param("persist.global.language", target.language.c_str());
    std::string final_loc = get_sys_param("persist.global.locale", target.locale.c_str());
    if (sa_rc != 0) {
        (void)set_sys_param("persist.global.language", target.language);
        (void)set_sys_param("persist.global.locale", target.locale);
        (void)write_global_param_data(target.language, target.locale);
        final_lang = target.language;
        final_loc = target.locale;
    }

    std::printf("OK LOCALE language=%s region=%s locale=%s sa=%d\n",
                final_lang.c_str(), target.region.c_str(), final_loc.c_str(), static_cast<int>(sa_rc));
    return 0;
}
