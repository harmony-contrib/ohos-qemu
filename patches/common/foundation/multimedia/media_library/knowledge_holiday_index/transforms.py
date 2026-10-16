"""Exact hooks into the previously installed KnowledgeContent and fixed media service."""
PROJECT='foundation/multimedia/media_library'
HOOKS={
 'frameworks/innerkitsimpl/media_library_helper/src/media_asset_rdbstore.cpp':(
    '    return store == nullptr ? nullptr : store->QueryByStep(sql, args);',
    '    return store == nullptr ? nullptr : store->QueryByStep(sql, args, false);'),
 'frameworks/innerkitsimpl/medialibrary_data_extension/BUILD.gn':(
    '    "${MEDIALIB_NEW_SERVICES_PATH}/media_rdbstore/src/rdbstore/medialibrary_rdbstore.cpp",',
    '    "${MEDIALIB_NEW_SERVICES_PATH}/media_rdbstore/src/rdbstore/medialibrary_rdbstore.cpp",\n'
    '    "${MEDIALIB_NEW_SERVICES_PATH}/media_rdbstore/src/rdbstore/knowledge_holiday_index.cpp",'),
}
def repair(name,data):
    crlf=b'\r\n' in data
    text=data.decode().replace('\r\n','\n')
    if name in HOOKS:
        before,after=HOOKS[name]
        if text.count(before)!=1:raise ValueError('unknown exact knowledge calendar hook: '+name)
        text=text.replace(before,after)
        if name.endswith('BUILD.gn'):
            before='    "relational_store:native_dataability",'
            if text.count(before)!=1:raise ValueError('unknown knowledge calendar library dependency hook')
            text=text.replace(before,'    "openssl:libcrypto_shared",\n'+before)
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
