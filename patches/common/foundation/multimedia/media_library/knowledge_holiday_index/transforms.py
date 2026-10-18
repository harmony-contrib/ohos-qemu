"""Exact hooks into the previously installed KnowledgeContent and fixed media service."""
PROJECT='foundation/multimedia/media_library'
HOOKS={
 'interfaces/kits/js/BUILD.gn':None,
 'frameworks/innerkitsimpl/media_library_helper/src/media_asset_rdbstore.cpp':(
    '    return store == nullptr ? nullptr : store->QueryByStep(sql, args);',
    '    return store == nullptr ? nullptr : store->QueryByStep(sql, args, false);'),
 'frameworks/innerkitsimpl/medialibrary_data_extension/BUILD.gn':(
    '    "${MEDIALIB_NEW_SERVICES_PATH}/media_rdbstore/src/rdbstore/medialibrary_rdbstore.cpp",',
    '    "${MEDIALIB_NEW_SERVICES_PATH}/media_rdbstore/src/rdbstore/medialibrary_rdbstore.cpp",\n'
    '    "${MEDIALIB_NEW_SERVICES_PATH}/media_rdbstore/src/rdbstore/knowledge_holiday_index.cpp",'),
}
SERVICE_QUERY = '    // Fixed internal Knowledge route. The HAP never opens the service database\n    // and cannot send SQL. Check the actual IPC caller before decoding input.\n    if (uri.ToString() == std::string(MEDIALIBRARY_DATA_URI) + "/knowledge-content") {\n        if (!PermissionUtils::IsSystemApp()) {\n            businessError.SetCode(202); return nullptr;\n        }\n        if (!PermissionUtils::CheckCallerPermission("ohos.permission.READ_IMAGEVIDEO")) {\n            businessError.SetCode(201); return nullptr;\n        }\n        Knowledge::Query query;\n        if (!predicates.GetOperationList().empty() || !predicates.GetWhereClause().empty() ||\n            !predicates.GetWhereArgs().empty() || !Knowledge::DecodeServiceWire(columns, query)) {\n            businessError.SetCode(13900020); return nullptr;\n        }\n        auto store = MediaLibraryRdbStore::GetRaw();\n        if (store == nullptr) {\n            MEDIA_ERR_LOG("Knowledge phase=service-rdb-open result=null; underlying_rc=unavailable");\n            businessError.SetCode(23800301); return nullptr;\n        }\n        std::vector<NativeRdb::ValueObject> args;\n        for (const auto &value : query.args) {\n            if (std::holds_alternative<int64_t>(value)) args.emplace_back(std::get<int64_t>(value));\n            else args.emplace_back(std::get<std::string>(value));\n        }\n        // DataShare\'s own GoToRow pre-counts; cap work by the existing 8MiB\n        // response budget. The sentinel count is rejected, never truncated to success.\n        const auto sql = query.sql + " LIMIT " + std::to_string(Knowledge::SERVICE_ROW_LIMIT + 1);\n        auto result = store->QueryByStep(sql, args, false);\n        if (result == nullptr) {\n            MEDIA_ERR_LOG("Knowledge phase=service-query result=null; underlying_rc=unavailable");\n            businessError.SetCode(23800301); return nullptr;\n        }\n        // Reuse the same real RDB/DataShare bridge as MediaLibraryDataManager.\n        // No explicit service pre-count or preload; the client checks the bounded count.\n        auto bridge = OHOS::RdbDataShareAdapter::RdbUtils::ToResultSetBridge(result);\n        if (bridge == nullptr) {\n            result->Close(); businessError.SetCode(23800301); return nullptr;\n        }\n        businessError.SetCode(0);\n        return std::make_shared<DataShareResultSet>(bridge);\n    }\n'

def repair(name,data):
    crlf=b'\r\n' in data
    text=data.decode().replace('\r\n','\n')
    if name=='frameworks/innerkitsimpl/medialibrary_data_extension/src/media_datashare_ext_ability.cpp':
        # Exact complete parent/final vectors are checked by apply.py first.
        # Upgrade the existing service block without replaying include/query hooks.
        legacy = SERVICE_QUERY.replace('OHOS::RdbDataShareAdapter::RdbUtils::', 'RdbUtils::', 1)
        if SERVICE_QUERY in text or legacy in text:
            if text.count(SERVICE_QUERY) + text.count(legacy) != 1:
                raise ValueError('mixed or repeated Knowledge service query blocks')
            text = text.replace(legacy, SERVICE_QUERY)
            return text.replace('\n','\r\n').encode() if crlf else text.encode()
        before='#include "media_datashare_ext_ability.h"'
        if text.count(before)!=1:raise ValueError('unknown Knowledge service include hook')
        text=text.replace(before,before+'\n#include "knowledge_content_query.h"\n#include "medialibrary_rdbstore.h"\n#include "rdb_utils.h"')
        before='shared_ptr<DataShareResultSet> MediaDataShareExtAbility::Query(const Uri &uri,\n    const DataSharePredicates &predicates, vector<string> &columns, DatashareBusinessError &businessError)\n{\n'
        if text.count(before)!=1:raise ValueError('unknown fixed Knowledge service query hook')
        text=text.replace(before,before+SERVICE_QUERY)
    elif name=='interfaces/kits/js/BUILD.gn':
        start=text.index('ohos_shared_library("photoaccesshelpernative") {')
        end=text.index('\n}',start)+2
        block=text[start:end]
        before='    "bundle_framework:appexecfwk_core",'
        if block.count(before)!=1:raise ValueError('unknown direct KnowledgeContent AccessToken dependency hook')
        if '"access_token:libaccesstoken_sdk"' not in block:
            block=block.replace(before,'    "access_token:libaccesstoken_sdk",\n'+before)
        before='    "ipc:ipc_napi",'
        if block.count(before)!=1:raise ValueError('unknown direct KnowledgeContent IPC dependency hook')
        if '"ipc:ipc_core"' not in block:
            block=block.replace(before,'    "ipc:ipc_core",\n'+before)
        before='    "relational_store:native_rdb",'
        if block.count(before)!=1:raise ValueError('unknown direct KnowledgeContent RDB adapter dependency hook')
        if '"relational_store:rdb_data_share_adapter"' not in block:
            block=block.replace(before,before+'\n    "relational_store:rdb_data_share_adapter",')
        if '"samgr:samgr_proxy"' not in block:
            block=block.replace(before,before+'\n    "samgr:samgr_proxy",')
        text=text[:start]+block+text[end:]
    elif name in HOOKS:
        before,after=HOOKS[name]
        if after not in text:
            if text.count(before)!=1:raise ValueError('unknown exact knowledge calendar hook: '+name)
            text=text.replace(before,after)
        if name.endswith('BUILD.gn'):
            before='    "relational_store:native_dataability",'
            if text.count(before)!=1:raise ValueError('unknown knowledge calendar library dependency hook')
            if '"openssl:libcrypto_shared"' not in text:
                text=text.replace(before,'    "openssl:libcrypto_shared",\n'+before)
            before='    "${MEDIALIB_NEW_SERVICES_PATH}/media_rdbstore/src/rdbstore/knowledge_holiday_index.cpp",'
            if text.count(before)!=1:raise ValueError('unknown service-owned Knowledge generator source hook')
            text=text.replace(before,before+'\n    "${MEDIALIB_JS_PATH}/src/knowledge_content_query.cpp",')
            before='    "${MEDIALIB_NEW_SERVICES_PATH}/media_rdbstore/include/rdbstore",'
            if text.count(before)!=1:raise ValueError('unknown service Knowledge include hook')
            text=text.replace(before,before+'\n    "${MEDIALIB_INTERFACES_PATH}/kits/js/include",')
    elif name=='services/media_rdbstore/src/rdbstore/medialibrary_rdbstore.cpp':
        before='#include "medialibrary_rdbstore.h"'
        if text.count(before)!=1:raise ValueError('unknown knowledge calendar include hook')
        text=text.replace(before,before+'\n#include "knowledge_holiday_index.h"')
        # The static DB can outlive individual wrapper instances. Cancel and
        # join its observer before actual Stop/reopen, never on a wrapper dtor.
        for before in [
            '    int32_t errCode = 0;\n    MediaLibraryDataCallBack rdbDataCallBack;',
            '    int32_t errCode = 0;\n    MediaLibraryTracer tracer;\n    tracer.Start("MediaLibraryRdbStore::Init GetRdbStore with config");',
        ]:
            if text.count(before)!=1:raise ValueError('unknown calendar reopen hook')
            text=text.replace(before,'    KnowledgeHolidayIndex::StopObserver();\n'+before)
        for before in [
            '    MEDIA_INFO_LOG("MediaLibraryRdbStore::Init(), SUCCESS");',
            '    MEDIA_INFO_LOG("MediaLibraryRdbStore::Init with config, SUCCESS");',
        ]:
            if text.count(before)!=1:raise ValueError('unknown knowledge calendar service-open hook')
            text=text.replace(before,'''    // New/legacy database imports the fixed trusted resource before queries.
    // Failure preserves the last complete index and is logged without disabling
    // unrelated media storage. Polling observes later configuration versions.
    const int calendarResult = KnowledgeHolidayIndex::Refresh(*rdbStore_);
    CHECK_AND_PRINT_LOG(calendarResult == NativeRdb::E_OK,
        "Knowledge holiday initialization failed: %{public}d", calendarResult);
    const int calendarObserver = KnowledgeHolidayIndex::Observe(rdbStore_);
    CHECK_AND_PRINT_LOG(calendarObserver == NativeRdb::E_OK,
        "Knowledge holiday configuration observer failed: %{public}d", calendarObserver);
'''+before)
        before='void MediaLibraryRdbStore::Stop()\n{\n    rdbStore_ = nullptr;\n}'
        if text.count(before)!=1:raise ValueError('unknown calendar close hook')
        text=text.replace(before,'''void MediaLibraryRdbStore::Stop()
{
    // Wait outside observer locks for any in-flight import before releasing DB.
    // Reentrant worker Stop cancels; its local shared RDB keeps that call alive.
    const int calendarStop = KnowledgeHolidayIndex::StopObserver();
    CHECK_AND_PRINT_LOG(calendarStop == NativeRdb::E_OK,
        "Knowledge holiday observer join deferred: %{public}d", calendarStop);
    rdbStore_ = nullptr;
}''')
    else:raise ValueError('unlisted knowledge calendar hook: '+name)
    return text.replace('\n','\r\n').encode() if crlf else text.encode()
