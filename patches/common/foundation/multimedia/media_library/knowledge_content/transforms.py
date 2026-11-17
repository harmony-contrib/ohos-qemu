"""Known fixed source insertions; full-byte manifest gates guard each complete state."""
PROJECT = 'foundation/multimedia/media_library'
FILES = {
    'frameworks/js/src/knowledge_content_napi.cpp': 'knowledge_content_napi.cpp',
    'frameworks/js/src/knowledge_content_query.cpp': 'knowledge_content_query.cpp',
    'interfaces/kits/js/include/knowledge_content_napi.h': 'knowledge_content_napi.h',
    'interfaces/kits/js/include/knowledge_content_query.h': 'knowledge_content_query.h',
}
HOOKS = {
'interfaces/kits/js/BUILD.gn': (
    '    "${MEDIALIB_JS_PATH}/src/media_library_napi.cpp",\n',
    '    "${MEDIALIB_JS_PATH}/src/media_library_napi.cpp",\n'
    '    "${MEDIALIB_JS_PATH}/src/knowledge_content_napi.cpp",\n'
    '    "${MEDIALIB_JS_PATH}/src/knowledge_content_query.cpp",\n'),
'frameworks/js/src/native_module_ohos_photoaccess_helper.cpp': (
    '#include "result_set_napi.h"\n',
    '#include "result_set_napi.h"\n#include "knowledge_content_napi.h"\n'),
'frameworks/js/src/photoaccesshelperinf.js': (
    '  TaskSignal: photoAccessHelper.TaskSignal,\n',
    '  TaskSignal: photoAccessHelper.TaskSignal,\n  KnowledgeContent: photoAccessHelper.KnowledgeContent,\n'),
'frameworks/innerkitsimpl/media_library_helper/include/media_asset_rdbstore.h': (
    '    EXPORT std::shared_ptr<NativeRdb::ResultSet> QueryByStep(const std::string &sql);\n',
    '    EXPORT std::shared_ptr<NativeRdb::ResultSet> QueryByStep(const std::string &sql);\n'
    '    EXPORT std::shared_ptr<NativeRdb::ResultSet> QueryByStep(const std::string &sql,\n'
    '        const std::vector<NativeRdb::ValueObject> &args);\n'),
}
STORE = 'frameworks/innerkitsimpl/media_library_helper/src/media_asset_rdbstore.cpp'
OLD_STORE = '''std::shared_ptr<NativeRdb::ResultSet> MediaAssetRdbStore::QueryByStep(const std::string &sql)
{
    if (rdbStore_ == nullptr) {
        if (TryGetRdbStore(false) != NativeRdb::E_OK) {
            return nullptr;
        }
    }
    return rdbStore_->QueryByStep(sql);
}
'''
NEW_STORE = OLD_STORE + '''
std::shared_ptr<NativeRdb::ResultSet> MediaAssetRdbStore::QueryByStep(const std::string &sql,
    const std::vector<NativeRdb::ValueObject> &args)
{
    std::shared_ptr<NativeRdb::RdbStore> store;
    {
        std::lock_guard<std::mutex> lock(mutex_);
        store = rdbStore_;
    }
    if (store == nullptr) {
        if (TryGetRdbStore(false) != NativeRdb::E_OK) {
            return nullptr;
        }
        std::lock_guard<std::mutex> lock(mutex_);
        store = rdbStore_;
    }
    return store == nullptr ? nullptr : store->QueryByStep(sql, args);
}
'''
HOOKS[STORE] = (OLD_STORE, NEW_STORE)


def repair(name, data):
    crlf = b'\r\n' in data
    source = data.decode().replace('\r\n', '\n')
    old, new = HOOKS[name]
    if source.count(old) != 1:
        raise ValueError('unknown pinned KnowledgeContent hook: ' + name)
    source = source.replace(old, new)
    if name == 'frameworks/js/src/native_module_ohos_photoaccess_helper.cpp':
        old = '    ResultSetNapi::Init(env, exports);\n'
        if source.count(old) != 1:
            raise ValueError('unknown pinned photo access native registration')
        source = source.replace(old, old + '    if (KnowledgeContentNapi::Init(env, exports) == nullptr) {\n'
            '        return nullptr;\n    }\n')
    return (source.replace('\n', '\r\n') if crlf else source).encode()
