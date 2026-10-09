/*
 * Copyright (C) 2023 Huawei Device Co., Ltd.
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */
#define MLOG_TAG "PhotoAlbumNapi"

#include "photo_album_napi.h"
#include <nlohmann/json.hpp>

#include "fetch_file_result_napi.h"
#include "file_asset_napi.h"
#include "media_file_utils.h"
#include "medialibrary_client_errno.h"
#include "medialibrary_napi_log.h"
#include "medialibrary_napi_utils_ext.h"
#include "medialibrary_tracer.h"
#include "photo_map_column.h"
#include "userfile_manager_types.h"
#include "result_set_utils.h"
#include "userfile_client.h"
#include "album_operation_uri.h"
#include "user_define_ipc_client.h"
#include "medialibrary_business_code.h"
#include "delete_photos_vo.h"
#include "album_commit_modify_vo.h"
#include "album_add_assets_vo.h"
#include "album_remove_assets_vo.h"
#include "album_recover_assets_vo.h"
#include "album_photo_query_vo.h"
#include "album_get_assets_vo.h"
#include "album_get_selected_assets_vo.h"
#include "get_face_id_vo.h"
#include "shooting_mode_column.h"
#include "get_fussion_assets_vo.h"
#include "js_interface_helper.h"
#include "analysis_album_attribute_request_utils.h"
#include "analysis_album_get_attribute_vo.h"
#include "permission_utils.h"
#include "accesstoken_kit.h"

using namespace std;
using namespace OHOS::DataShare;
using namespace OHOS::Security::AccessToken;

namespace OHOS::Media {
thread_local PhotoAlbum *PhotoAlbumNapi::pAlbumData_ = nullptr;
thread_local napi_ref PhotoAlbumNapi::constructor_ = nullptr;
thread_local napi_ref PhotoAlbumNapi::photoAccessConstructor_ = nullptr;
static const string PHOTO_ALBUM_CLASS = "UserFileMgrPhotoAlbum";
static const string PHOTOACCESS_PHOTO_ALBUM_CLASS = "PhotoAccessPhotoAlbum";
static const string COUNT_GROUP_BY = "count(*) AS count";
std::mutex PhotoAlbumNapi::mutex_;
static const int32_t NAPI_INVALID_PARAMETER_ERROR = 23800151;
static const int32_t MEDIA_LIBRARY_INTERNAL_SYSTEM_ERROR = 23800301;
static const int32_t GET_ATTRIBUTE_MAX_COUNT = 20;

struct TrashAlbumExecuteOpt {
    napi_env env;
    void *data;
    string tracerLabel;
    string uri;
};

using CompleteCallback = napi_async_complete_callback;

PhotoAlbumNapi::PhotoAlbumNapi() : env_(nullptr) {}

PhotoAlbumNapi::~PhotoAlbumNapi() = default;

napi_value PhotoAlbumNapi::Init(napi_env env, napi_value exports)
{
    NapiClassInfo info = {
        .name = PHOTO_ALBUM_CLASS,
        .ref = &constructor_,
        .constructor = PhotoAlbumNapiConstructor,
        .props = {
            DECLARE_NAPI_GETTER_SETTER("albumName", JSGetAlbumName, JSSetAlbumName),
            DECLARE_NAPI_GETTER("albumUri", JSGetAlbumUri),
            DECLARE_NAPI_GETTER("count", JSGetAlbumCount),
            DECLARE_NAPI_GETTER("albumType", JSGetPhotoAlbumType),
            DECLARE_NAPI_GETTER("albumSubType", JSGetPhotoAlbumSubType),
            DECLARE_NAPI_GETTER_SETTER("coverUri", JSGetCoverUri, JSSetCoverUri),
            DECLARE_NAPI_GETTER("dateModified", JSGetDateModified),
            DECLARE_NAPI_FUNCTION("commitModify", JSCommitModify),
            DECLARE_NAPI_FUNCTION("addPhotoAssets", JSPhotoAlbumAddAssets),
            DECLARE_NAPI_FUNCTION("removePhotoAssets", JSPhotoAlbumRemoveAssets),
            DECLARE_NAPI_FUNCTION("getPhotoAssets", JSGetPhotoAssets),
            DECLARE_NAPI_FUNCTION("recoverPhotoAssets", JSRecoverPhotos),
            DECLARE_NAPI_FUNCTION("deletePhotoAssets", JSDeletePhotos),
            // PrivateAlbum.recover
            DECLARE_NAPI_FUNCTION("recover", PrivateAlbumRecoverPhotos),
            // PrivateAlbum.delete
            DECLARE_NAPI_FUNCTION("delete", PrivateAlbumDeletePhotos),
        }
    };

    MediaLibraryNapiUtils::NapiDefineClass(env, exports, info);
    return exports;
}

napi_value PhotoAlbumNapi::PhotoAccessInit(napi_env env, napi_value exports)
{
    NapiClassInfo info = {
        .name = PHOTOACCESS_PHOTO_ALBUM_CLASS,
        .ref = &photoAccessConstructor_,
        .constructor = PhotoAlbumNapiConstructor,
        .props = {
            DECLARE_NAPI_GETTER_SETTER("albumName", JSPhotoAccessGetAlbumName, JSPhotoAccessSetAlbumName),
            DECLARE_NAPI_GETTER("albumUri", JSPhotoAccessGetAlbumUri),
            DECLARE_NAPI_GETTER("count", JSPhotoAccessGetAlbumCount),
            DECLARE_NAPI_GETTER("imageCount", JSPhotoAccessGetAlbumImageCount),
            DECLARE_NAPI_GETTER("videoCount", JSPhotoAccessGetAlbumVideoCount),
            DECLARE_NAPI_GETTER("albumType", JSGetPhotoAlbumType),
            DECLARE_NAPI_GETTER("albumSubtype", JSGetPhotoAlbumSubType),
            DECLARE_NAPI_GETTER("coverUri", JSGetCoverUri),
            DECLARE_NAPI_GETTER("latitude", JSGetLatitude),
            DECLARE_NAPI_GETTER("longitude", JSGetLongitude),
            DECLARE_NAPI_GETTER("lpath", JSGetAlbumLPath),
            DECLARE_NAPI_GETTER("dateModified", JSGetDateModifiedSystem),
            DECLARE_NAPI_GETTER("dateAdded", JSGetDateAdded),
            DECLARE_NAPI_GETTER("coverUriSource", JSGetCoverUriSource),
            DECLARE_NAPI_GETTER("changeTime", JSGetChangeTime),
            DECLARE_NAPI_GETTER("uploadStatus", JSGetUploadStatus),
            DECLARE_NAPI_GETTER("hidden", JSPhotoAccessGetPhotoAlbumtHidden),
            DECLARE_NAPI_FUNCTION("commitModify", PhotoAccessHelperCommitModify),
            DECLARE_NAPI_FUNCTION("addAssets", PhotoAccessHelperAddAssets),
            DECLARE_NAPI_FUNCTION("removeAssets", PhotoAccessHelperRemoveAssets),
            DECLARE_NAPI_FUNCTION("getAssets", JSPhotoAccessGetPhotoAssets),
            DECLARE_NAPI_FUNCTION("recoverAssets", PhotoAccessHelperRecoverPhotos),
            DECLARE_NAPI_FUNCTION("deleteAssets", PhotoAccessHelperDeletePhotos),
            DECLARE_NAPI_FUNCTION("setCoverUri", PhotoAccessHelperSetCoverUri),
            DECLARE_NAPI_FUNCTION("getAssetsSync", JSPhotoAccessGetPhotoAssetsSync),
            DECLARE_NAPI_FUNCTION("getSharedPhotoAssets", JSPhotoAccessGetSharedPhotoAssets),
            DECLARE_NAPI_FUNCTION("getFaceId", PhotoAccessHelperGetFaceId),
            DECLARE_NAPI_FUNCTION("getSelectedAssets", JSPhotoAccessGetSelectedPhotoAssets),
            DECLARE_NAPI_FUNCTION("getFusionAssetsInfo", PhotoAccessGetFusionAssetsInfo),
            DECLARE_NAPI_FUNCTION("getAttribute", JSAnalysisAlbumGetAttribute),
        }
    };

    MediaLibraryNapiUtils::NapiDefineClass(env, exports, info);
    return exports;
}

napi_value PhotoAlbumNapi::CreatePhotoAlbumNapi(napi_env env, unique_ptr<PhotoAlbum> &albumData)
{
    if (albumData == nullptr) {
        return nullptr;
    }

    napi_value constructor;
    napi_ref constructorRef;
    if (albumData->GetResultNapiType() == ResultNapiType::TYPE_PHOTOACCESS_HELPER) {
        constructorRef = photoAccessConstructor_;
    } else {
        constructorRef = constructor_;
    }
    CHECK_ARGS(env, napi_get_reference_value(env, constructorRef, &constructor), JS_INNER_FAIL);

    napi_value result = nullptr;
    pAlbumData_ = albumData.release();
    CHECK_ARGS(env, napi_new_instance(env, constructor, 0, nullptr, &result), JS_INNER_FAIL);
    pAlbumData_ = nullptr;
    return result;
}

napi_value PhotoAlbumNapi::CreatePhotoAlbumNapi(napi_env env, shared_ptr<PhotoAlbum>& albumData)
{
    if (albumData == nullptr || albumData->GetResultNapiType() != ResultNapiType::TYPE_PHOTOACCESS_HELPER) {
        NAPI_ERR_LOG("Unsupported photo album data");
        return nullptr;
    }

    napi_value constructor = nullptr;
    napi_value result = nullptr;
    CHECK_ARGS(env, napi_get_reference_value(env, photoAccessConstructor_, &constructor), JS_INNER_FAIL);
    CHECK_ARGS(env, napi_new_instance(env, constructor, 0, nullptr, &result), JS_INNER_FAIL);
    CHECK_COND(env, result != nullptr, JS_INNER_FAIL);

    PhotoAlbumNapi* photoAlbumNapi = nullptr;
    CHECK_ARGS(env, napi_unwrap(env, result, reinterpret_cast<void**>(&photoAlbumNapi)), JS_INNER_FAIL);
    CHECK_COND(env, photoAlbumNapi != nullptr, JS_INNER_FAIL);
    photoAlbumNapi->photoAlbumPtr = albumData;
    return result;
}

int32_t PhotoAlbumNapi::GetAlbumId() const
{
    return photoAlbumPtr->GetAlbumId();
}

int32_t PhotoAlbumNapi::GetCount() const
{
    return photoAlbumPtr->GetCount();
}

void PhotoAlbumNapi::SetCount(int32_t count)
{
    return photoAlbumPtr->SetCount(count);
}

int32_t PhotoAlbumNapi::GetImageCount() const
{
    return photoAlbumPtr->GetImageCount();
}

void PhotoAlbumNapi::SetImageCount(int32_t count)
{
    return photoAlbumPtr->SetImageCount(count);
}

int32_t PhotoAlbumNapi::GetVideoCount() const
{
    return photoAlbumPtr->GetVideoCount();
}

void PhotoAlbumNapi::SetVideoCount(int32_t count)
{
    return photoAlbumPtr->SetVideoCount(count);
}

const string& PhotoAlbumNapi::GetAlbumUri() const
{
    return photoAlbumPtr->GetAlbumUri();
}

const string& PhotoAlbumNapi::GetCoverUri() const
{
    return photoAlbumPtr->GetCoverUri();
}

int64_t PhotoAlbumNapi::GetDateModified() const
{
    return photoAlbumPtr->GetDateModified();
}

int64_t PhotoAlbumNapi::GetDateAdded() const
{
    return photoAlbumPtr->GetDateAdded();
}

int32_t PhotoAlbumNapi::GetCoverUriSource() const
{
    return photoAlbumPtr->GetCoverUriSource();
}

const string& PhotoAlbumNapi::GetAlbumName() const
{
    return photoAlbumPtr->GetAlbumName();
}

PhotoAlbumType PhotoAlbumNapi::GetPhotoAlbumType() const
{
    return photoAlbumPtr->GetPhotoAlbumType();
}

PhotoAlbumSubType PhotoAlbumNapi::GetPhotoAlbumSubType() const
{
    return photoAlbumPtr->GetPhotoAlbumSubType();
}

double PhotoAlbumNapi::GetLatitude() const
{
    return photoAlbumPtr->GetLatitude();
}

double PhotoAlbumNapi::GetLongitude() const
{
    return photoAlbumPtr->GetLongitude();
}

const string& PhotoAlbumNapi::GetLPath() const
{
    return photoAlbumPtr->GetLPath();
}

shared_ptr<PhotoAlbum> PhotoAlbumNapi::GetPhotoAlbumInstance() const
{
    return photoAlbumPtr;
}

bool PhotoAlbumNapi::GetHiddenOnly() const
{
    return photoAlbumPtr->GetHiddenOnly();
}

void PhotoAlbumNapi::SetHiddenOnly(const bool hiddenOnly_)
{
    return photoAlbumPtr->SetHiddenOnly(hiddenOnly_);
}

int64_t PhotoAlbumNapi::GetChangeTime() const
{
    return photoAlbumPtr->GetChangeTime();
}

int32_t PhotoAlbumNapi::GetUploadStatus() const
{
    return photoAlbumPtr->GetUploadStatus();
}

int32_t PhotoAlbumNapi::GetHidden() const
{
    return photoAlbumPtr->GetHidden();
}

void PhotoAlbumNapi::SetPhotoAlbumNapiProperties()
{
    photoAlbumPtr = shared_ptr<PhotoAlbum>(pAlbumData_);
}

// Constructor callback
napi_value PhotoAlbumNapi::PhotoAlbumNapiConstructor(napi_env env, napi_callback_info info)
{
    napi_value result = nullptr;
    CHECK_ARGS(env, napi_get_undefined(env, &result), JS_INNER_FAIL);

    napi_value thisVar = nullptr;
    CHECK_ARGS(env, napi_get_cb_info(env, info, nullptr, nullptr, &thisVar, nullptr), JS_INNER_FAIL);
    if (thisVar == nullptr) {
        NapiError::ThrowError(env, JS_ERR_PARAMETER_INVALID);
        return result;
    }

    unique_ptr<PhotoAlbumNapi> obj = make_unique<PhotoAlbumNapi>();
    obj->env_ = env;
    if (pAlbumData_ != nullptr) {
        obj->SetPhotoAlbumNapiProperties();
    }
    CHECK_ARGS(env, napi_wrap(env, thisVar, reinterpret_cast<void *>(obj.get()),
        PhotoAlbumNapi::PhotoAlbumNapiDestructor, nullptr, nullptr), JS_INNER_FAIL);
    obj.release();
    return thisVar;
}

void PhotoAlbumNapi::PhotoAlbumNapiDestructor(napi_env env, void *nativeObject, void *finalizeHint)
{
    auto *album = reinterpret_cast<PhotoAlbumNapi*>(nativeObject);
    lock_guard<mutex> lockGuard(mutex_);
    if (album != nullptr) {
        delete album;
        album = nullptr;
    }
}

napi_value UnwrapPhotoAlbumObject(napi_env env, napi_callback_info info, PhotoAlbumNapi** obj)
{
    napi_value result = nullptr;
    CHECK_ARGS(env, napi_get_undefined(env, &result), JS_INNER_FAIL);

    napi_value thisVar = nullptr;
    CHECK_ARGS(env, napi_get_cb_info(env, info, nullptr, nullptr, &thisVar, nullptr), JS_INNER_FAIL);
    if (thisVar == nullptr) {
        NapiError::ThrowError(env, JS_ERR_PARAMETER_INVALID);
        return result;
    }

    CHECK_ARGS(env, napi_unwrap(env, thisVar, reinterpret_cast<void **>(obj)), JS_INNER_FAIL);
    if (obj == nullptr) {
        NapiError::ThrowError(env, JS_ERR_PARAMETER_INVALID);
        return result;
    }

    CHECK_ARGS(env, napi_get_boolean(env, true, &result), JS_INNER_FAIL);
    return result;
}

napi_value PhotoAlbumNapi::JSGetAlbumName(napi_env env, napi_callback_info info)
{
    PhotoAlbumNapi *obj = nullptr;
    CHECK_NULLPTR_RET(UnwrapPhotoAlbumObject(env, info, &obj));

    napi_value jsResult = nullptr;
    CHECK_ARGS(env, napi_create_string_utf8(env, obj->GetAlbumName().c_str(), NAPI_AUTO_LENGTH, &jsResult),
        JS_INNER_FAIL);
    return jsResult;
}

napi_value PhotoAlbumNapi::JSPhotoAccessGetAlbumName(napi_env env, napi_callback_info info)
{
    PhotoAlbumNapi *obj = nullptr;
    CHECK_NULLPTR_RET(UnwrapPhotoAlbumObject(env, info, &obj));

    napi_value jsResult = nullptr;
    CHECK_ARGS(env, napi_create_string_utf8(env, obj->GetAlbumName().c_str(), NAPI_AUTO_LENGTH, &jsResult),
        JS_INNER_FAIL);
    return jsResult;
}

napi_value PhotoAlbumNapi::JSGetAlbumUri(napi_env env, napi_callback_info info)
{
    PhotoAlbumNapi *obj = nullptr;
    CHECK_NULLPTR_RET(UnwrapPhotoAlbumObject(env, info, &obj));

    napi_value jsResult = nullptr;
    CHECK_ARGS(env, napi_create_string_utf8(env, obj->GetAlbumUri().c_str(), NAPI_AUTO_LENGTH, &jsResult),
        JS_INNER_FAIL);
    return jsResult;
}

napi_value PhotoAlbumNapi::JSPhotoAccessGetAlbumUri(napi_env env, napi_callback_info info)
{
    PhotoAlbumNapi *obj = nullptr;
    CHECK_NULLPTR_RET(UnwrapPhotoAlbumObject(env, info, &obj));

    napi_value jsResult = nullptr;
    CHECK_ARGS(env, napi_create_string_utf8(env, obj->GetAlbumUri().c_str(), NAPI_AUTO_LENGTH, &jsResult),
        JS_INNER_FAIL);
    return jsResult;
}

napi_value PhotoAlbumNapi::JSGetAlbumCount(napi_env env, napi_callback_info info)
{
    PhotoAlbumNapi *obj = nullptr;
    CHECK_NULLPTR_RET(UnwrapPhotoAlbumObject(env, info, &obj));

    napi_value jsResult = nullptr;
    CHECK_ARGS(env, napi_create_int32(env, obj->GetCount(), &jsResult), JS_INNER_FAIL);
    return jsResult;
}

napi_value PhotoAlbumNapi::JSPhotoAccessGetAlbumCount(napi_env env, napi_callback_info info)
{
    PhotoAlbumNapi *obj = nullptr;
    CHECK_NULLPTR_RET(UnwrapPhotoAlbumObject(env, info, &obj));

    napi_value jsResult = nullptr;
    CHECK_ARGS(env, napi_create_int32(env, obj->GetCount(), &jsResult), JS_INNER_FAIL);
    return jsResult;
}

napi_value PhotoAlbumNapi::JSPhotoAccessGetAlbumImageCount(napi_env env, napi_callback_info info)
{
    PhotoAlbumNapi *obj = nullptr;
    CHECK_NULLPTR_RET(UnwrapPhotoAlbumObject(env, info, &obj));

    napi_value jsResult = nullptr;
    CHECK_ARGS(env, napi_create_int32(env, obj->GetImageCount(), &jsResult), JS_INNER_FAIL);
    return jsResult;
}

napi_value PhotoAlbumNapi::JSPhotoAccessGetAlbumVideoCount(napi_env env, napi_callback_info info)
{
    PhotoAlbumNapi *obj = nullptr;
    CHECK_NULLPTR_RET(UnwrapPhotoAlbumObject(env, info, &obj));

    napi_value jsResult = nullptr;
    CHECK_ARGS(env, napi_create_int32(env, obj->GetVideoCount(), &jsResult), JS_INNER_FAIL);
    return jsResult;
}

napi_value PhotoAlbumNapi::JSGetPhotoAlbumType(napi_env env, napi_callback_info info)
{
    PhotoAlbumNapi *obj = nullptr;
    CHECK_NULLPTR_RET(UnwrapPhotoAlbumObject(env, info, &obj));

    napi_value jsResult = nullptr;
    CHECK_ARGS(env, napi_create_int32(env, obj->GetPhotoAlbumType(), &jsResult), JS_INNER_FAIL);
    return jsResult;
}

napi_value PhotoAlbumNapi::JSGetPhotoAlbumSubType(napi_env env, napi_callback_info info)
{
    PhotoAlbumNapi *obj = nullptr;
    CHECK_NULLPTR_RET(UnwrapPhotoAlbumObject(env, info, &obj));

    napi_value jsResult = nullptr;
    CHECK_ARGS(env, napi_create_int32(env, obj->GetPhotoAlbumSubType(), &jsResult), JS_INNER_FAIL);
    return jsResult;
}

napi_value PhotoAlbumNapi::JSPhotoAccessGetPhotoAlbumtHidden(napi_env env, napi_callback_info info)
{
    PhotoAlbumNapi *obj = nullptr;
    CHECK_NULLPTR_RET(UnwrapPhotoAlbumObject(env, info, &obj));

    napi_value jsResult = nullptr;
    CHECK_ARGS(env, napi_get_boolean(env, static_cast<bool>(obj->GetHidden()), &jsResult), JS_INNER_FAIL);
    return jsResult;
}

napi_value PhotoAlbumNapi::JSGetCoverUri(napi_env env, napi_callback_info info)
{
    PhotoAlbumNapi *obj = nullptr;
    CHECK_NULLPTR_RET(UnwrapPhotoAlbumObject(env, info, &obj));

    napi_value jsResult = nullptr;
    CHECK_ARGS(env, napi_create_string_utf8(env, obj->GetCoverUri().c_str(), NAPI_AUTO_LENGTH, &jsResult),
        JS_INNER_FAIL);
    return jsResult;
}

napi_value PhotoAlbumNapi::JSGetLatitude(napi_env env, napi_callback_info info)
{
    PhotoAlbumNapi *obj = nullptr;
    CHECK_NULLPTR_RET(UnwrapPhotoAlbumObject(env, info, &obj));

    napi_value jsResult = nullptr;
    CHECK_ARGS(env, napi_create_double(env, obj->GetLatitude(), &jsResult), JS_INNER_FAIL);
    return jsResult;
}

napi_value PhotoAlbumNapi::JSGetLongitude(napi_env env, napi_callback_info info)
{
    PhotoAlbumNapi *obj = nullptr;
    CHECK_NULLPTR_RET(UnwrapPhotoAlbumObject(env, info, &obj));

    napi_value jsResult = nullptr;
    CHECK_ARGS(env, napi_create_double(env, obj->GetLongitude(), &jsResult), JS_INNER_FAIL);
    return jsResult;
}

napi_value PhotoAlbumNapi::JSGetAlbumLPath(napi_env env, napi_callback_info info)
{
    PhotoAlbumNapi *obj = nullptr;
    CHECK_NULLPTR_RET(UnwrapPhotoAlbumObject(env, info, &obj));

    napi_value jsResult = nullptr;
    CHECK_ARGS(env, napi_create_string_utf8(env, obj->GetLPath().c_str(), NAPI_AUTO_LENGTH, &jsResult), JS_INNER_FAIL);
    return jsResult;
}

napi_value GetStringArg(napi_env env, napi_callback_info info, PhotoAlbumNapi **obj, string &output)
{
    size_t argc = ARGS_ONE;
    napi_value argv[ARGS_ONE];
    napi_value thisVar = nullptr;
    CHECK_ARGS(env, napi_get_cb_info(env, info, &argc, argv, &thisVar, nullptr), JS_INNER_FAIL);
    CHECK_COND(env, argc == ARGS_ONE, JS_ERR_PARAMETER_INVALID);

    napi_value result = nullptr;
    CHECK_ARGS(env, napi_get_undefined(env, &result), JS_INNER_FAIL);
    napi_valuetype valueType = napi_undefined;
    if ((thisVar == nullptr) || (napi_typeof(env, argv[PARAM0], &valueType) != napi_ok) || (valueType != napi_string)) {
        NapiError::ThrowError(env, JS_ERR_PARAMETER_INVALID);
        return result;
    }

    size_t res = 0;
    char buffer[FILENAME_MAX];
    CHECK_ARGS(env, napi_get_value_string_utf8(env, argv[PARAM0], buffer, FILENAME_MAX, &res), JS_INNER_FAIL);
    output = string(buffer);

    CHECK_ARGS(env, napi_unwrap(env, thisVar, reinterpret_cast<void **>(obj)), JS_INNER_FAIL);
    if (obj == nullptr) {
        NapiError::ThrowError(env, JS_ERR_PARAMETER_INVALID);
        return result;
    }

    CHECK_ARGS(env, napi_get_boolean(env, true, &result), JS_INNER_FAIL);
    return result;
}

napi_value PhotoAlbumNapi::JSSetAlbumName(napi_env env, napi_callback_info info)
{
    PhotoAlbumNapi *obj = nullptr;
    string albumName;
    CHECK_NULLPTR_RET(GetStringArg(env, info, &obj, albumName));
    obj->photoAlbumPtr->SetAlbumName(albumName);

    napi_value result = nullptr;
    CHECK_ARGS(env, napi_get_undefined(env, &result), JS_INNER_FAIL);
    return result;
}

napi_value PhotoAlbumNapi::JSPhotoAccessSetAlbumName(napi_env env, napi_callback_info info)
{
    PhotoAlbumNapi *obj = nullptr;
    string albumName;
    CHECK_NULLPTR_RET(GetStringArg(env, info, &obj, albumName));
    obj->photoAlbumPtr->SetAlbumName(albumName);

    napi_value result = nullptr;
    CHECK_ARGS(env, napi_get_undefined(env, &result), JS_INNER_FAIL);
    return result;
}

napi_value PhotoAlbumNapi::JSSetCoverUri(napi_env env, napi_callback_info info)
{
    PhotoAlbumNapi *obj = nullptr;
    string coverUri;
    CHECK_NULLPTR_RET(GetStringArg(env, info, &obj, coverUri));
    obj->photoAlbumPtr->SetCoverUri(coverUri);

    napi_value result = nullptr;
    CHECK_ARGS(env, napi_get_undefined(env, &result), JS_INNER_FAIL);
    return result;
}

napi_value PhotoAlbumNapi::JSGetDateModified(napi_env env, napi_callback_info info)
{
    PhotoAlbumNapi *obj = nullptr;
    CHECK_NULLPTR_RET(UnwrapPhotoAlbumObject(env, info, &obj));

    napi_value jsResult = nullptr;
    CHECK_ARGS(env, napi_create_int64(env, obj->GetDateModified(), &jsResult),
        JS_INNER_FAIL);
    return jsResult;
}

napi_value PhotoAlbumNapi::JSGetDateModifiedSystem(napi_env env, napi_callback_info info)
{
    CHECK_COND_LOG_THROW_RETURN_RET(env, MediaLibraryNapiUtils::IsSystemApp(), JS_ERR_PERMISSION_DENIED,
        "Get dateModified permission denied: not a system app", nullptr,
        "Get album dateModified failed: not a system app");
    PhotoAlbumNapi *obj = nullptr;
    CHECK_NULLPTR_RET(UnwrapPhotoAlbumObject(env, info, &obj));

    napi_value jsResult = nullptr;
    CHECK_ARGS(env, napi_create_int64(env, obj->GetDateModified(), &jsResult),
        JS_INNER_FAIL);
    return jsResult;
}


napi_value PhotoAlbumNapi::JSGetDateAdded(napi_env env, napi_callback_info info)
{
    CHECK_COND_LOG_THROW_RETURN_RET(env, MediaLibraryNapiUtils::IsSystemApp(), JS_ERR_PERMISSION_DENIED,
        "Get dateAdded permission denied: not a system app", nullptr, "Get album dateAdded failed: not a system app");
    PhotoAlbumNapi *obj = nullptr;
    CHECK_NULLPTR_RET(UnwrapPhotoAlbumObject(env, info, &obj));

    napi_value jsResult = nullptr;
    CHECK_ARGS(env, napi_create_int64(env, obj->GetDateAdded(), &jsResult),
        JS_INNER_FAIL);
    return jsResult;
}

static int32_t PublicCoverUriSource(int32_t source)
{
    // Native storage distinguishes local, cloud and pending manual covers.
    // API 26 exposes a single MANUAL_COVER value; do not rewrite native storage.
    switch (source) {
        case CoverUriSource::MANUAL_CLOUD_COVER:
        case CoverUriSource::MANUAL_LOCAL_COVER:
        case CoverUriSource::MANUAL_WAIT_PULL_COVER:
            return CoverUriSource::MANUAL_CLOUD_COVER;
        default:
            return source;
    }
}

napi_value PhotoAlbumNapi::JSGetCoverUriSource(napi_env env, napi_callback_info info)
{
    CHECK_COND_LOG_THROW_RETURN_RET(env, MediaLibraryNapiUtils::IsSystemApp(), JS_ERR_PERMISSION_DENIED,
        "GetCoverUriSource permission denied: not a system app", nullptr, "GetCoverUriSource failed: not a system app");
    PhotoAlbumNapi *obj = nullptr;
    CHECK_NULLPTR_RET(UnwrapPhotoAlbumObject(env, info, &obj));

    napi_value jsResult = nullptr;
    CHECK_ARGS(env, napi_create_int32(env, PublicCoverUriSource(obj->GetCoverUriSource()), &jsResult),
        JS_INNER_FAIL);
    return jsResult;
}

napi_value PhotoAlbumNapi::JSGetUploadStatus(napi_env env, napi_callback_info info)
{
    CHECK_COND_LOG_THROW_RETURN_RET(env, MediaLibraryNapiUtils::IsSystemApp(), JS_ERR_PERMISSION_DENIED,
        "GetUploadStatus permission denied: not a system app", nullptr, "GetUploadStatus failed: not a system app");
    PhotoAlbumNapi *obj = nullptr;
    CHECK_NULLPTR_RET(UnwrapPhotoAlbumObject(env, info, &obj));

    napi_value jsResult = nullptr;
    CHECK_ARGS(env, napi_create_int32(env, obj->GetUploadStatus(), &jsResult), JS_INNER_FAIL);
    return jsResult;
}

napi_value PhotoAlbumNapi::JSGetChangeTime(napi_env env, napi_callback_info info)
{
    PhotoAlbumNapi *obj = nullptr;
    CHECK_NULLPTR_RET(UnwrapPhotoAlbumObject(env, info, &obj));

    napi_value jsResult = nullptr;
    CHECK_ARGS(env, napi_create_int64(env, obj->GetChangeTime(), &jsResult), JS_INNER_FAIL);
    return jsResult;
}

static napi_value ParseArgsCommitModify(napi_env env, napi_callback_info info,
    unique_ptr<PhotoAlbumNapiAsyncContext> &context)
{
    constexpr size_t minArgs = ARGS_ZERO;
    constexpr size_t maxArgs = ARGS_ONE;
    CHECK_ARGS(env, MediaLibraryNapiUtils::AsyncContextSetObjectInfo(env, info, context, minArgs, maxArgs),
        JS_ERR_PARAMETER_INVALID);

    auto photoAlbum = context->objectInfo->GetPhotoAlbumInstance();
    if (photoAlbum == nullptr) {
        NapiError::ThrowError(env, JS_ERR_PARAMETER_INVALID);
        return nullptr;
    }
    if (!PhotoAlbum::IsUserPhotoAlbum(photoAlbum->GetPhotoAlbumType(), photoAlbum->GetPhotoAlbumSubType())) {
        NapiError::ThrowError(env, JS_ERR_PARAMETER_INVALID);
        return nullptr;
    }

    if (MediaFileUtils::CheckAlbumName(photoAlbum->GetAlbumName()) < 0) {
        NapiError::ThrowError(env, JS_ERR_PARAMETER_INVALID);
        return nullptr;
    }
    context->predicates.EqualTo(PhotoAlbumColumns::ALBUM_ID, to_string(photoAlbum->GetAlbumId()));
    context->valuesBucket.Put(PhotoAlbumColumns::ALBUM_NAME, photoAlbum->GetAlbumName());
    context->valuesBucket.Put(PhotoAlbumColumns::ALBUM_COVER_URI, photoAlbum->GetCoverUri());
    context->businessCode = static_cast<uint32_t>(MediaLibraryBusinessCode::PAH_COMMIT_MODIFY);

    napi_value result = nullptr;
    CHECK_ARGS(env, napi_get_boolean(env, true, &result), JS_INNER_FAIL);
    return result;
}

static void JSCommitModifyIPCExecute(PhotoAlbumNapiAsyncContext *context)
{
    int32_t changedRows = 0;
    auto objectInfo = context->objectInfo;
    if (objectInfo == nullptr) {
        NAPI_ERR_LOG("objectInfo is nullptr");
        return;
    }
    auto photoAlbum = objectInfo->GetPhotoAlbumInstance();
    AlbumCommitModifyReqBody reqBody;
    reqBody.businessCode = context->businessCode;
    if (reqBody.businessCode == static_cast<uint32_t>(MediaLibraryBusinessCode::PAH_COMMIT_MODIFY)) {
        reqBody.albumName = photoAlbum->GetAlbumName();
        reqBody.albumType = photoAlbum->GetPhotoAlbumType();
        reqBody.albumSubType = photoAlbum->GetPhotoAlbumSubType();
    }

    bool isValid = false;
    string coverUri = context->valuesBucket.Get(PhotoAlbumColumns::ALBUM_COVER_URI, isValid);
    reqBody.coverUri = coverUri;
    if (!isValid) {
        NAPI_ERR_LOG("CommitModify get coveruri fail.");
        context->SaveError(changedRows);
        return;
    }

    reqBody.albumId = photoAlbum->GetAlbumId();
    changedRows = IPC::UserDefineIPCClient().Call(context->businessCode, reqBody);
    context->SaveError(changedRows);
    context->changedRows = changedRows;
}

static void JSCommitModifyExecute(napi_env env, void *data)
{
    MediaLibraryTracer tracer;
    tracer.Start("JSCommitModifyExecute");

    auto *context = static_cast<PhotoAlbumNapiAsyncContext*>(data);
    if (context->resultNapiType != ResultNapiType::TYPE_USERFILE_MGR) {
        JSCommitModifyIPCExecute(context);
        return;
    }

    Uri uri(CONST_UFM_UPDATE_PHOTO_ALBUM);
    int changedRows = UserFileClient::Update(uri, context->predicates, context->valuesBucket);
    context->SaveError(changedRows);
    context->changedRows = changedRows;
}

static void JSCommitModifyCompleteCallback(napi_env env, napi_status status, void *data)
{
    MediaLibraryTracer tracer;
    tracer.Start("JSCommitModifyCompleteCallback");

    auto *context = static_cast<PhotoAlbumNapiAsyncContext*>(data);
    auto jsContext = make_unique<JSAsyncContextOutput>();
    jsContext->status = false;
    CHECK_ARGS_RET_VOID(env, napi_get_undefined(env, &jsContext->data), JS_INNER_FAIL);
    if (context->error == ERR_DEFAULT) {
        CHECK_ARGS_RET_VOID(env, napi_get_undefined(env, &jsContext->error), JS_INNER_FAIL);
        jsContext->status = true;
    } else {
        context->HandleError(env, jsContext->error);
    }

    tracer.Finish();
    if (context->work != nullptr) {
        MediaLibraryNapiUtils::InvokeJSAsyncMethod(env, context->deferred, context->callbackRef,
                                                   context->work, *jsContext);
    }
    MediaLibraryNapiUtils::DeleteAsyncContextWithRef(env, context);
    delete context;
}

napi_value PhotoAlbumNapi::JSCommitModify(napi_env env, napi_callback_info info)
{
    auto asyncContext = make_unique<PhotoAlbumNapiAsyncContext>();
    CHECK_NULLPTR_RET(ParseArgsCommitModify(env, info, asyncContext));
    asyncContext->resultNapiType = ResultNapiType::TYPE_USERFILE_MGR;

    return MediaLibraryNapiUtils::NapiCreateAsyncWork(env, asyncContext, "JSCommitModify", JSCommitModifyExecute,
        JSCommitModifyCompleteCallback);
}

napi_value PhotoAlbumNapi::PhotoAccessHelperCommitModify(napi_env env, napi_callback_info info)
{
    auto asyncContext = make_unique<PhotoAlbumNapiAsyncContext>();
    CHECK_NULLPTR_RET(ParseArgsCommitModify(env, info, asyncContext));
    asyncContext->resultNapiType = ResultNapiType::TYPE_PHOTOACCESS_HELPER;

    return MediaLibraryNapiUtils::NapiCreateAsyncWork(env, asyncContext, "JSCommitModify", JSCommitModifyExecute,
        JSCommitModifyCompleteCallback);
}

static napi_value GetAssetsIdArray(napi_env env, napi_value arg, vector<string> &assetsArray)
{
    bool isArray = false;
    CHECK_ARGS(env, napi_is_array(env, arg, &isArray), JS_INNER_FAIL);
    if (!isArray) {
        NapiError::ThrowError(env, JS_ERR_PARAMETER_INVALID, "Failed to check array type");
        return nullptr;
    }

    uint32_t len = 0;
    CHECK_ARGS(env, napi_get_array_length(env, arg, &len), JS_INNER_FAIL);
    if (len < 0) {
        NAPI_ERR_LOG("Failed to check array length: %{public}u", len);
        NapiError::ThrowError(env, JS_ERR_PARAMETER_INVALID, "Failed to check array length");
        return nullptr;
    }
    if (len == 0) {
        napi_value result = nullptr;
        CHECK_ARGS(env, napi_get_boolean(env, true, &result), JS_INNER_FAIL);
        return result;
    }

    for (uint32_t i = 0; i < len; i++) {
        napi_value asset = nullptr;
        CHECK_ARGS(env, napi_get_element(env, arg, i, &asset), JS_INNER_FAIL);
        if (asset == nullptr) {
            NapiError::ThrowError(env, JS_ERR_PARAMETER_INVALID, "Failed to get asset element");
            return nullptr;
        }

        FileAssetNapi *obj = nullptr;
        CHECK_ARGS(env, napi_unwrap(env, asset, reinterpret_cast<void **>(&obj)), JS_INNER_FAIL);
        if (obj == nullptr) {
            NapiError::ThrowError(env, JS_ERR_PARAMETER_INVALID, "Failed to get asset napi object");
            return nullptr;
        }
        if ((obj->GetMediaType() != MEDIA_TYPE_IMAGE && obj->GetMediaType() != MEDIA_TYPE_VIDEO)) {
            NAPI_INFO_LOG("Skip invalid asset, mediaType: %{public}d", obj->GetMediaType());
            continue;
        }
        assetsArray.push_back(obj->GetFileUri());
    }

    napi_value result = nullptr;
    CHECK_ARGS(env, napi_get_boolean(env, true, &result), JS_INNER_FAIL);
    return result;
}

static napi_value ParseArgsAddAssets(napi_env env, napi_callback_info info,
    unique_ptr<PhotoAlbumNapiAsyncContext> &context)
{
    constexpr size_t minArgs = ARGS_ONE;
    constexpr size_t maxArgs = ARGS_TWO;
    CHECK_ARGS(env, MediaLibraryNapiUtils::AsyncContextSetObjectInfo(env, info, context, minArgs, maxArgs),
        JS_ERR_PARAMETER_INVALID);

    auto photoAlbum = context->objectInfo->GetPhotoAlbumInstance();
    if (!PhotoAlbum::IsUserPhotoAlbum(photoAlbum->GetPhotoAlbumType(), photoAlbum->GetPhotoAlbumSubType())) {
        NapiError::ThrowError(env, JS_ERR_PARAMETER_INVALID);
        return nullptr;
    }

    /* Parse the first argument */
    vector<string> assetsArray;
    CHECK_NULLPTR_RET(GetAssetsIdArray(env, context->argv[PARAM0], assetsArray));
    context->assetsArray = assetsArray;
    if (assetsArray.empty()) {
        napi_value result = nullptr;
        CHECK_ARGS(env, napi_get_boolean(env, true, &result), JS_INNER_FAIL);
        return result;
    }
    int32_t albumId = photoAlbum->GetAlbumId();
    for (const auto &assetId : assetsArray) {
        DataShareValuesBucket valuesBucket;
        valuesBucket.Put(PhotoColumn::PHOTO_OWNER_ALBUM_ID, albumId);
        valuesBucket.Put(PhotoColumn::MEDIA_ID, assetId);
        context->valuesBuckets.push_back(valuesBucket);
    }

    napi_value result = nullptr;
    CHECK_ARGS(env, napi_get_boolean(env, true, &result), JS_INNER_FAIL);
    return result;
}

static int32_t FetchNewCount(PhotoAlbumNapiAsyncContext *context)
{
    string queryUri = (context->resultNapiType == ResultNapiType::TYPE_USERFILE_MGR) ?
        CONST_UFM_QUERY_PHOTO_ALBUM : CONST_PAH_QUERY_PHOTO_ALBUM;
    Uri qUri(queryUri);
    int errCode = 0;
    DataSharePredicates predicates;
    predicates.EqualTo(PhotoAlbumColumns::ALBUM_ID, context->objectInfo->GetAlbumId());
    vector<string> fetchColumn = {
        PhotoAlbumColumns::ALBUM_ID,
        PhotoAlbumColumns::ALBUM_COUNT,
    };
    bool isSmartAlbum = (context->objectInfo->GetPhotoAlbumType() == PhotoAlbumType::SMART);
    if (!isSmartAlbum) {
        fetchColumn.push_back(PhotoAlbumColumns::ALBUM_IMAGE_COUNT);
        fetchColumn.push_back(PhotoAlbumColumns::ALBUM_VIDEO_COUNT);
    }
    auto resultSet = UserFileClient::Query(qUri, predicates, fetchColumn, errCode);
    if (resultSet == nullptr) {
        NAPI_ERR_LOG("resultSet == nullptr, errCode is %{public}d", errCode);
        return -1;
    }
    if (resultSet->GoToFirstRow() != 0) {
        NAPI_ERR_LOG("go to first row failed");
        return -1;
    }
    bool hiddenOnly = context->objectInfo->GetHiddenOnly();
    int imageCount = (hiddenOnly || isSmartAlbum) ? -1 :
            get<int32_t>(ResultSetUtils::GetValFromColumn(PhotoAlbumColumns::ALBUM_IMAGE_COUNT, resultSet, TYPE_INT32));
    int videoCount = (hiddenOnly || isSmartAlbum) ? -1 :
            get<int32_t>(ResultSetUtils::GetValFromColumn(PhotoAlbumColumns::ALBUM_VIDEO_COUNT, resultSet, TYPE_INT32));
    context->newCount =
            get<int32_t>(ResultSetUtils::GetValFromColumn(PhotoAlbumColumns::ALBUM_COUNT, resultSet, TYPE_INT32));
    context->newImageCount = imageCount;
    context->newVideoCount = videoCount;
    return 0;
}

static void JSPhotoAlbumAddAssetsIPCExecute(PhotoAlbumNapiAsyncContext *context)
{
    auto objectInfo = context->objectInfo;
    if (objectInfo == nullptr) {
        NAPI_ERR_LOG("objectInfo is nullptr");
        return;
    }
    auto photoAlbum = objectInfo->GetPhotoAlbumInstance();
    if (photoAlbum == nullptr) {
        NAPI_ERR_LOG("photoAlbum is nullptr");
        return;
    }
    AlbumPhotoQueryRespBody respBody;
    AlbumAddAssetsReqBody reqBody;
    reqBody.albumId = photoAlbum->GetAlbumId();
    reqBody.albumType = photoAlbum->GetPhotoAlbumType();
    reqBody.albumSubType = photoAlbum->GetPhotoAlbumSubType();
    reqBody.assetsArray = context->assetsArray;
    uint32_t businessCode = static_cast<uint32_t>(MediaLibraryBusinessCode::PAH_ADD_ASSETS);

    int32_t changedRows = IPC::UserDefineIPCClient().Call(businessCode, reqBody, respBody);
    if (changedRows < 0) {
        context->SaveError(changedRows);
        return;
    }

    bool hiddenOnly = objectInfo->GetHiddenOnly();
    bool isSmartAlbum = photoAlbum->GetPhotoAlbumType() == PhotoAlbumType::SMART;

    context->changedRows = changedRows;
    context->newCount = respBody.newCount;
    context->newImageCount = (hiddenOnly || isSmartAlbum) ? -1 : respBody.newImageCount;
    context->newVideoCount = (hiddenOnly || isSmartAlbum) ? -1 : respBody.newVideoCount;
}

static void JSPhotoAlbumAddAssetsExecute(napi_env env, void *data)
{
    MediaLibraryTracer tracer;
    tracer.Start("JSPhotoAlbumAddAssetsExecute");
    auto *context = static_cast<PhotoAlbumNapiAsyncContext*>(data);
    if (context->valuesBuckets.empty()) {
        return;
    }

    if (context->resultNapiType != ResultNapiType::TYPE_USERFILE_MGR) {
        JSPhotoAlbumAddAssetsIPCExecute(context);
        return;
    }

    Uri uri(CONST_UFM_PHOTO_ALBUM_ADD_ASSET);
    auto changedRows = UserFileClient::BatchInsert(uri, context->valuesBuckets);
    if (changedRows < 0) {
        context->SaveError(changedRows);
        return;
    }
    context->changedRows = changedRows;
    int32_t ret = FetchNewCount(context);
    if (ret < 0) {
        NAPI_ERR_LOG("Update count failed");
        context->SaveError(E_HAS_DB_ERROR);
    }
}

static void JSPhotoAlbumAddAssetsCompleteCallback(napi_env env, napi_status status, void *data)
{
    MediaLibraryTracer tracer;
    tracer.Start("JSPhotoAlbumAddAssetsCompleteCallback");

    auto *context = static_cast<PhotoAlbumNapiAsyncContext*>(data);
    unique_ptr<JSAsyncContextOutput> jsContext = make_unique<JSAsyncContextOutput>();
    jsContext->status = false;
    CHECK_ARGS_RET_VOID(env, napi_get_undefined(env, &jsContext->data), JS_INNER_FAIL);
    if (context->error == ERR_DEFAULT) {
        CHECK_ARGS_RET_VOID(env, napi_get_undefined(env, &jsContext->error), JS_INNER_FAIL);
        jsContext->status = true;
        context->objectInfo->SetCount(context->newCount);
        context->objectInfo->SetImageCount(context->newImageCount);
        context->objectInfo->SetVideoCount(context->newVideoCount);
    } else {
        context->HandleError(env, jsContext->error);
    }

    tracer.Finish();
    if (context->work != nullptr) {
        MediaLibraryNapiUtils::InvokeJSAsyncMethod(env, context->deferred, context->callbackRef,
                                                   context->work, *jsContext);
    }
    MediaLibraryNapiUtils::DeleteAsyncContextWithRef(env, context);
    delete context;
}

napi_value PhotoAlbumNapi::JSPhotoAlbumAddAssets(napi_env env, napi_callback_info info)
{
    unique_ptr<PhotoAlbumNapiAsyncContext> asyncContext = make_unique<PhotoAlbumNapiAsyncContext>();
    CHECK_NULLPTR_RET(ParseArgsAddAssets(env, info, asyncContext));
    asyncContext->resultNapiType = ResultNapiType::TYPE_USERFILE_MGR;

    return MediaLibraryNapiUtils::NapiCreateAsyncWork(env, asyncContext, "JSPhotoAlbumAddAssets",
        JSPhotoAlbumAddAssetsExecute, JSPhotoAlbumAddAssetsCompleteCallback);
}

napi_value PhotoAlbumNapi::PhotoAccessHelperAddAssets(napi_env env, napi_callback_info info)
{
    unique_ptr<PhotoAlbumNapiAsyncContext> asyncContext = make_unique<PhotoAlbumNapiAsyncContext>();
    CHECK_NULLPTR_RET(ParseArgsAddAssets(env, info, asyncContext));
    asyncContext->resultNapiType = ResultNapiType::TYPE_PHOTOACCESS_HELPER;

    return MediaLibraryNapiUtils::NapiCreateAsyncWork(env, asyncContext, "JSPhotoAlbumAddAssets",
        JSPhotoAlbumAddAssetsExecute, JSPhotoAlbumAddAssetsCompleteCallback);
}

static napi_value ParseArgsRemoveAssets(napi_env env, napi_callback_info info,
    unique_ptr<PhotoAlbumNapiAsyncContext> &context)
{
    constexpr size_t minArgs = ARGS_ONE;
    constexpr size_t maxArgs = ARGS_TWO;
    CHECK_ARGS(env, MediaLibraryNapiUtils::AsyncContextSetObjectInfo(env, info, context, minArgs, maxArgs),
        JS_ERR_PARAMETER_INVALID);

    auto photoAlbum = context->objectInfo->GetPhotoAlbumInstance();
    if (!PhotoAlbum::IsUserPhotoAlbum(photoAlbum->GetPhotoAlbumType(), photoAlbum->GetPhotoAlbumSubType())) {
        NapiError::ThrowError(env, JS_ERR_PARAMETER_INVALID);
        return nullptr;
    }

    /* Parse the first argument */
    vector<string> assetsArray;
    CHECK_NULLPTR_RET(GetAssetsIdArray(env, context->argv[PARAM0], assetsArray));
    if (assetsArray.empty()) {
        napi_value result = nullptr;
        CHECK_ARGS(env, napi_get_boolean(env, true, &result), JS_INNER_FAIL);
        return result;
    }

    context->assetsArray = assetsArray;
    context->predicates.EqualTo(PhotoColumn::PHOTO_OWNER_ALBUM_ID, to_string(photoAlbum->GetAlbumId()));
    context->predicates.And()->In(PhotoColumn::MEDIA_ID, assetsArray);

    napi_value result = nullptr;
    CHECK_ARGS(env, napi_get_boolean(env, true, &result), JS_INNER_FAIL);
    return result;
}

static void JSPhotoAlbumRemoveAssetsIPCExecute(PhotoAlbumNapiAsyncContext *context)
{
    auto objectInfo = context->objectInfo;
    CHECK_IF_EQUAL(objectInfo != nullptr, "objectInfo is nullptr");
    auto photoAlbum = objectInfo->GetPhotoAlbumInstance();
    CHECK_IF_EQUAL(photoAlbum != nullptr, "photoAlbum is nullptr");
    AlbumPhotoQueryRespBody respBody;
    AlbumRemoveAssetsReqBody reqBody;
    reqBody.albumId = photoAlbum->GetAlbumId();
    reqBody.albumType = photoAlbum->GetPhotoAlbumType();
    reqBody.albumSubType = photoAlbum->GetPhotoAlbumSubType();
    reqBody.assetsArray = context->assetsArray;
    uint32_t businessCode = static_cast<uint32_t>(MediaLibraryBusinessCode::PAH_REMOVE_ASSETS);

    int32_t deletedRows = IPC::UserDefineIPCClient().Call(businessCode, reqBody, respBody);
    if (deletedRows < 0) {
        NAPI_ERR_LOG("Remove assets failed: %{public}d", deletedRows);
        context->SaveError(deletedRows);
        return;
    }

    bool hiddenOnly = objectInfo->GetHiddenOnly();
    bool isSmartAlbum = photoAlbum->GetPhotoAlbumType() == PhotoAlbumType::SMART;

    context->changedRows = deletedRows;
    context->newCount = respBody.newCount;
    context->newImageCount = (hiddenOnly || isSmartAlbum) ? -1 : respBody.newImageCount;
    context->newVideoCount = (hiddenOnly || isSmartAlbum) ? -1 : respBody.newVideoCount;
}

static void JSPhotoAlbumRemoveAssetsExecute(napi_env env, void *data)
{
    MediaLibraryTracer tracer;
    tracer.Start("JSPhotoAlbumRemoveAssetsExecute");

    auto *context = static_cast<PhotoAlbumNapiAsyncContext*>(data);
    if (context->predicates.GetOperationList().empty()) {
        NAPI_ERR_LOG("Invalid input: operation list is empty");
        return;
    }

    if (context->resultNapiType != ResultNapiType::TYPE_USERFILE_MGR) {
        JSPhotoAlbumRemoveAssetsIPCExecute(context);
        return;
    }

    Uri uri(CONST_UFM_PHOTO_ALBUM_REMOVE_ASSET);
    auto deletedRows = UserFileClient::Delete(uri, context->predicates);
    if (deletedRows < 0) {
        NAPI_ERR_LOG("Remove assets failed: %{public}d", deletedRows);
        context->SaveError(deletedRows);
        return;
    }
    context->changedRows = deletedRows;
    int32_t ret = FetchNewCount(context);
    if (ret < 0) {
        NAPI_ERR_LOG("Update count failed");
        context->SaveError(E_HAS_DB_ERROR);
    }
}

static void JSPhotoAlbumRemoveAssetsCompleteCallback(napi_env env, napi_status status, void *data)
{
    MediaLibraryTracer tracer;
    tracer.Start("JSPhotoAlbumRemoveAssetsCompleteCallback");

    auto *context = static_cast<PhotoAlbumNapiAsyncContext*>(data);
    CHECK_NULL_PTR_RETURN_VOID(context, "Async context is null");
    unique_ptr<JSAsyncContextOutput> jsContext = make_unique<JSAsyncContextOutput>();
    jsContext->status = false;
    CHECK_ARGS_RET_VOID(env, napi_get_undefined(env, &jsContext->data), JS_INNER_FAIL);
    if (context->error == ERR_DEFAULT) {
        CHECK_ARGS_RET_VOID(env, napi_get_undefined(env, &jsContext->error), JS_INNER_FAIL);
        jsContext->status = true;
        context->objectInfo->SetCount(context->newCount);
        context->objectInfo->SetImageCount(context->newImageCount);
        context->objectInfo->SetVideoCount(context->newVideoCount);
    } else {
        context->HandleError(env, jsContext->error);
    }

    tracer.Finish();
    if (context->work != nullptr) {
        MediaLibraryNapiUtils::InvokeJSAsyncMethod(env, context->deferred, context->callbackRef,
                                                   context->work, *jsContext);
    }
    MediaLibraryNapiUtils::DeleteAsyncContextWithRef(env, context);
    delete context;
}

napi_value PhotoAlbumNapi::JSPhotoAlbumRemoveAssets(napi_env env, napi_callback_info info)
{
    auto asyncContext = make_unique<PhotoAlbumNapiAsyncContext>();
    CHECK_NULLPTR_RET(ParseArgsRemoveAssets(env, info, asyncContext));
    asyncContext->resultNapiType = ResultNapiType::TYPE_USERFILE_MGR;

    return MediaLibraryNapiUtils::NapiCreateAsyncWork(env, asyncContext, "JSPhotoAlbumRemoveAssets",
        JSPhotoAlbumRemoveAssetsExecute, JSPhotoAlbumRemoveAssetsCompleteCallback);
}

napi_value PhotoAlbumNapi::PhotoAccessHelperRemoveAssets(napi_env env, napi_callback_info info)
{
    auto asyncContext = make_unique<PhotoAlbumNapiAsyncContext>();
    CHECK_NULLPTR_RET(ParseArgsRemoveAssets(env, info, asyncContext));
    asyncContext->resultNapiType = ResultNapiType::TYPE_PHOTOACCESS_HELPER;

    return MediaLibraryNapiUtils::NapiCreateAsyncWork(env, asyncContext, "JSPhotoAlbumRemoveAssets",
        JSPhotoAlbumRemoveAssetsExecute, JSPhotoAlbumRemoveAssetsCompleteCallback);
}

static int32_t NapiGetAnalysisAlbumPredicates(const shared_ptr<PhotoAlbum>& photoAlbum,
    DataSharePredicates& predicates)
{
    PhotoAlbumSubType subType = photoAlbum->GetPhotoAlbumSubType();
    if (subType == PhotoAlbumSubType::PORTRAIT || subType == PhotoAlbumSubType::GROUP_PHOTO) {
        MediaLibraryNapiUtils::GetPortraitAlbumPredicates(photoAlbum->GetAlbumId(), predicates);
        return E_SUCCESS;
    }
    if (subType == PhotoAlbumSubType::GEOGRAPHY_LOCATION) {
        return MediaLibraryNapiUtils::GetAllLocationPredicates(predicates);
    }
    if (subType == PhotoAlbumSubType::SHOOTING_MODE) {
        ShootingModeAlbumType type {};
        if (!ShootingModeAlbum::AlbumNameToShootingModeAlbumType(photoAlbum->GetAlbumName(), type)) {
            NAPI_ERR_LOG("Invalid shooting mode album name: %{public}s",
                MediaFileUtils::DesensitizeName(photoAlbum->GetAlbumName()).c_str());
            return E_INVALID_ARGUMENTS;
        }
        ShootingModeAlbum::GetShootingModeAlbumPredicates(type, predicates, photoAlbum->GetHiddenOnly());
        return E_SUCCESS;
    }
    string albumName = photoAlbum->GetAlbumName();
    if (MediaLibraryNapiUtils::IsFeaturedSinglePortraitAlbum(albumName, predicates)) {
        return MediaLibraryNapiUtils::GetFeaturedSinglePortraitAlbumPredicates(
            photoAlbum->GetAlbumId(), predicates);
    }
    MediaLibraryNapiUtils::GetAnalysisPhotoMapPredicates(photoAlbum->GetAlbumId(), predicates);
    return E_SUCCESS;
}

static int32_t GetPredicatesByAlbumTypes(const shared_ptr<PhotoAlbum> &photoAlbum,
    DataSharePredicates &predicates, const bool hiddenOnly)
{
    int32_t albumId = photoAlbum->GetAlbumId();
    PhotoAlbumSubType subType = photoAlbum->GetPhotoAlbumSubType();
    bool isLocationAlbum = subType == PhotoAlbumSubType::GEOGRAPHY_LOCATION;
    if (albumId <= 0 && !isLocationAlbum) {
        NAPI_ERR_LOG("Invalid album ID");
        return E_INVALID_ARGUMENTS;
    }
    PhotoAlbumType type = photoAlbum->GetPhotoAlbumType();
    if ((!PhotoAlbum::CheckPhotoAlbumType(type)) || (!PhotoAlbum::CheckPhotoAlbumSubType(subType))) {
        NAPI_ERR_LOG("Invalid album type or subtype: type=%{public}d, subType=%{public}d", static_cast<int>(type),
            static_cast<int>(subType));
        return E_INVALID_ARGUMENTS;
    }

    if (PhotoAlbum::IsUserPhotoAlbum(type, subType)) {
        return MediaLibraryNapiUtils::GetUserAlbumPredicates(photoAlbum->GetAlbumId(), predicates, hiddenOnly);
    }

    if (PhotoAlbum::IsSourceAlbum(type, subType)) {
        return MediaLibraryNapiUtils::GetSourceAlbumPredicates(photoAlbum->GetAlbumId(), predicates, hiddenOnly);
    }

    if (type == PhotoAlbumType::SMART) {
        return NapiGetAnalysisAlbumPredicates(photoAlbum, predicates);
    }

    if (type == PhotoAlbumType::SYSTEM) {
        return MediaLibraryNapiUtils::GetSystemAlbumPredicates(subType, predicates, hiddenOnly);
    }

    NAPI_ERR_LOG("Invalid album type and subtype: type=%{public}d, subType=%{public}d", static_cast<int>(type),
        static_cast<int>(subType));
    return E_INVALID_ARGUMENTS;
}

static napi_value ParseArgsGetPhotoAssets(napi_env env, napi_callback_info info,
    unique_ptr<PhotoAlbumNapiAsyncContext> &context)
{
    constexpr size_t minArgs = ARGS_ONE;
    constexpr size_t maxArgs = ARGS_TWO;
    CHECK_ARGS(env, MediaLibraryNapiUtils::AsyncContextSetObjectInfo(env, info, context, minArgs, maxArgs),
        JS_ERR_PARAMETER_INVALID);

    /* Parse the first argument */
    CHECK_ARGS(env, MediaLibraryNapiUtils::GetFetchOption(env, context->argv[PARAM0], ASSET_FETCH_OPT, context),
        JS_INNER_FAIL);

    auto photoAlbum = context->objectInfo->GetPhotoAlbumInstance();
    auto ret = GetPredicatesByAlbumTypes(photoAlbum, context->predicates, photoAlbum->GetHiddenOnly());
    if (ret != E_SUCCESS) {
        NapiError::ThrowError(env, JS_ERR_PARAMETER_INVALID);
        return nullptr;
    }
    CHECK_NULLPTR_RET(MediaLibraryNapiUtils::AddDefaultAssetColumns(env, context->fetchColumn,
        PhotoColumn::IsPhotoColumn, NapiAssetType::TYPE_PHOTO));
    if (photoAlbum->GetHiddenOnly() || photoAlbum->GetPhotoAlbumSubType() == PhotoAlbumSubType::HIDDEN) {
        if (!MediaLibraryNapiUtils::IsSystemApp()) {
            NapiError::ThrowError(env, E_CHECK_SYSTEMAPP_FAIL, "This interface can be called only by system apps");
            return nullptr;
        }
        context->isSystemApi = true;
        // sort by hidden time desc if is hidden asset
        if (!JsInterfaceHelper::PredicatesHasOrderClause(context->predicates)) {
            context->predicates.OrderByDesc(PhotoColumn::PHOTO_HIDDEN_TIME);
        }
    }

    napi_value result = nullptr;
    CHECK_ARGS(env, napi_get_boolean(env, true, &result), JS_INNER_FAIL);
    return result;
}

static void JSGetPhotoAssetsExecute(napi_env env, void *data)
{
    MediaLibraryTracer tracer;
    tracer.Start("JSGetPhotoAssetsExecute");

    auto *context = static_cast<PhotoAlbumNapiAsyncContext *>(data);
    string queryUri = CONST_UFM_QUERY_PHOTO_MAP;
    Uri uri(queryUri);
    int32_t errCode = 0;
    std::vector<DataShare::OperationItem> operationItems = context->predicates.GetOperationList();
    for (DataShare::OperationItem item : operationItems) {
        if (item.operation == DataShare::OperationType::GROUP_BY) {
            context->fetchColumn.insert(context->fetchColumn.begin(), COUNT_GROUP_BY);
        }
    }
    auto resultSet = UserFileClient::Query(uri, context->predicates, context->fetchColumn, errCode);
    if (resultSet == nullptr) {
        context->SaveError(E_HAS_DB_ERROR);
        return;
    }
    context->fetchResult = make_unique<FetchResult<FileAsset>>(move(resultSet));
    context->fetchResult->SetResultNapiType(ResultNapiType::TYPE_USERFILE_MGR);
}

static bool IsFeaturedSinglePortraitAlbum(const shared_ptr<PhotoAlbum>& photoAlbum)
{
    constexpr int portraitAlbumId = 0;
    return photoAlbum->GetPhotoAlbumSubType() == PhotoAlbumSubType::CLASSIFY &&
        photoAlbum->GetAlbumName().compare(to_string(portraitAlbumId)) == 0;
}

static void ConvertColumnsForPortrait(PhotoAlbumNapiAsyncContext *context)
{
    if (context == nullptr || context->objectInfo == nullptr) {
        NAPI_ERR_LOG("context is null or PhotoAlbumNapi is null");
        return;
    }

    shared_ptr<PhotoAlbum> photoAlbum = context->objectInfo->GetPhotoAlbumInstance();
    if (photoAlbum == nullptr || (photoAlbum->GetPhotoAlbumSubType() != PhotoAlbumSubType::PORTRAIT &&
        photoAlbum->GetPhotoAlbumSubType() != PhotoAlbumSubType::GROUP_PHOTO &&
        !IsFeaturedSinglePortraitAlbum(photoAlbum))) {
        return;
    }

    for (size_t i = 0; i < context->fetchColumn.size(); i++) {
        if (context->fetchColumn[i] != "count(*)") {
            context->fetchColumn[i] = PhotoColumn::PHOTOS_TABLE + "." + context->fetchColumn[i];
        }
    }
}

static void JSPhotoAccessGetPhotoAssetsExecute(napi_env env, void *data)
{
    MediaLibraryTracer tracer;
    tracer.Start("JSPhotoAccessGetPhotoAssetsExecute");

    auto *context = static_cast<PhotoAlbumNapiAsyncContext *>(data);
    CHECK_IF_EQUAL(context != nullptr, "context is nullptr");
    Uri uri(CONST_PAH_QUERY_PHOTO_MAP);
    ConvertColumnsForPortrait(context);
    int32_t errCode = 0;
    int32_t userId = -1;
    if (context->objectInfo != nullptr) {
        shared_ptr<PhotoAlbum> photoAlbum =  context->objectInfo->GetPhotoAlbumInstance();
        if (photoAlbum != nullptr) {
            userId = photoAlbum->GetUserId();
        }
    }
    auto [accessSandbox, resultSet] =
        UserFileClient::QueryAccessibleViaSandBox(uri, context->predicates, context->fetchColumn, errCode, userId);
    if (accessSandbox) {
        if (resultSet == nullptr) {
            NAPI_ERR_LOG("QueryAccessibleViaSandBox failed, resultSet is nullptr");
        }
    } else {
        AlbumGetAssetsReqBody reqBody;
        reqBody.predicates = context->predicates;
        reqBody.columns = context->fetchColumn;
        AlbumGetAssetsRespBody respBody;
        uint32_t businessCode = context->isSystemApi
                                    ? static_cast<uint32_t>(MediaLibraryBusinessCode::ALBUM_SYS_GET_ASSETS)
                                    : static_cast<uint32_t>(MediaLibraryBusinessCode::ALBUM_GET_ASSETS);
        errCode = IPC::UserDefineIPCClient().SetUserId(userId).Call(businessCode, reqBody, respBody);
        if (errCode == E_OK) {
            resultSet = respBody.resultSet;
        } else {
            NAPI_ERR_LOG("UserDefineIPCClient Call failed, errCode is %{public}d", errCode);
        }
    }

    if (resultSet == nullptr) {
        context->SaveError(E_HAS_DB_ERROR);
        return;
    }
    context->fetchResult = make_unique<FetchResult<FileAsset>>(move(resultSet));
    context->fetchResult->SetResultNapiType(ResultNapiType::TYPE_PHOTOACCESS_HELPER);
    context->fetchResult->SetUserId(userId);
}

static napi_value JSPhotoAccessGetPhotoAssetsExecuteSync(napi_env env, PhotoAlbumNapiAsyncContext& asyncContext)
{
    auto context = &asyncContext;
    Uri uri(CONST_PAH_QUERY_PHOTO_MAP);
    ConvertColumnsForPortrait(context);
    int32_t errCode = 0;
    auto resultSet = UserFileClient::Query(uri, context->predicates, context->fetchColumn, errCode);
    CHECK_NULLPTR_RET(resultSet);
    auto fetchResult = make_unique<FetchResult<FileAsset>>(move(resultSet));
    fetchResult->SetResultNapiType(ResultNapiType::TYPE_PHOTOACCESS_HELPER);

    std::vector<std::unique_ptr<FileAsset>> fileAssetArray;
    auto file = fetchResult->GetFirstObject();
    while (file != nullptr) {
        fileAssetArray.push_back(move(file));
        file = fetchResult->GetNextObject();
    }
    napi_value jsFileArray = nullptr;
    size_t len = fileAssetArray.size();
    napi_create_array_with_length(env, len, &jsFileArray);
    size_t i = 0;
    int32_t userId = -1;
    if (context->objectInfo != nullptr) {
        shared_ptr<PhotoAlbum> photoAlbum =  context->objectInfo->GetPhotoAlbumInstance();
        if (photoAlbum != nullptr) {
            userId = photoAlbum->GetUserId();
        }
    }
    for (i = 0; i < len; i++) {
        fileAssetArray[i]->SetUserId(userId);
        napi_value jsFileAsset = FileAssetNapi::CreateFileAsset(env, fileAssetArray[i]);
        if ((jsFileAsset == nullptr) || (napi_set_element(env, jsFileArray, i, jsFileAsset) != napi_ok)) {
            NAPI_ERR_LOG("Failed to get file asset napi object");
            break;
        }
    }
    return (i == len) ? jsFileArray : nullptr;
}

static void GetPhotoMapQueryResult(napi_env env, PhotoAlbumNapiAsyncContext *context,
    unique_ptr<JSAsyncContextOutput> &jsContext)
{
    napi_value fetchRes = FetchFileResultNapi::CreateFetchFileResult(env, move(context->fetchResult));
    if (fetchRes == nullptr) {
        MediaLibraryNapiUtils::CreateNapiErrorObject(env, jsContext->error, ERR_MEM_ALLOCATION,
            "Failed to create js object for FetchFileResult");
        return;
    }
    jsContext->data = fetchRes;
    jsContext->status = true;
}

static void JSGetPhotoAssetsCallbackComplete(napi_env env, napi_status status, void *data)
{
    MediaLibraryTracer tracer;
    tracer.Start("JSGetPhotoAssetsCallbackComplete");

    auto *context = static_cast<PhotoAlbumNapiAsyncContext *>(data);

    unique_ptr<JSAsyncContextOutput> jsContext = make_unique<JSAsyncContextOutput>();
    jsContext->status = false;

    CHECK_ARGS_RET_VOID(env, napi_get_undefined(env, &jsContext->data), JS_INNER_FAIL);
    CHECK_ARGS_RET_VOID(env, napi_get_undefined(env, &jsContext->error), JS_INNER_FAIL);
    if (context->fetchResult != nullptr) {
        GetPhotoMapQueryResult(env, context, jsContext);
    } else {
        NAPI_ERR_LOG("No fetch file result found!");
        context->HandleError(env, jsContext->error);
    }

    tracer.Finish();
    if (context->work != nullptr) {
        MediaLibraryNapiUtils::InvokeJSAsyncMethod(env, context->deferred, context->callbackRef,
                                                   context->work, *jsContext);
    }
    MediaLibraryNapiUtils::DeleteAsyncContextWithRef(env, context);
    delete context;
}

napi_value PhotoAlbumNapi::JSGetPhotoAssets(napi_env env, napi_callback_info info)
{
    unique_ptr<PhotoAlbumNapiAsyncContext> asyncContext = make_unique<PhotoAlbumNapiAsyncContext>();
    CHECK_NULLPTR_RET(ParseArgsGetPhotoAssets(env, info, asyncContext));

    return MediaLibraryNapiUtils::NapiCreateAsyncWork(env, asyncContext, "JSGetPhotoAssets", JSGetPhotoAssetsExecute,
        JSGetPhotoAssetsCallbackComplete);
}

napi_value PhotoAlbumNapi::JSPhotoAccessGetPhotoAssets(napi_env env, napi_callback_info info)
{
    unique_ptr<PhotoAlbumNapiAsyncContext> asyncContext = make_unique<PhotoAlbumNapiAsyncContext>();
    CHECK_NULLPTR_RET(ParseArgsGetPhotoAssets(env, info, asyncContext));

    return MediaLibraryNapiUtils::NapiCreateAsyncWork(env, asyncContext, "JSGetPhotoAssets",
        JSPhotoAccessGetPhotoAssetsExecute, JSGetPhotoAssetsCallbackComplete);
}

napi_value PhotoAlbumNapi::JSPhotoAccessGetPhotoAssetsSync(napi_env env, napi_callback_info info)
{
    MediaLibraryTracer tracer;
    tracer.Start("JSPhotoAccessGetPhotoAssetsSync");

    unique_ptr<PhotoAlbumNapiAsyncContext> asyncContext = make_unique<PhotoAlbumNapiAsyncContext>();
    CHECK_NULLPTR_RET(ParseArgsGetPhotoAssets(env, info, asyncContext));
    return JSPhotoAccessGetPhotoAssetsExecuteSync(env, *asyncContext);
}

static napi_value TrashAlbumParseArgs(napi_env env, napi_callback_info info,
    unique_ptr<PhotoAlbumNapiAsyncContext> &context)
{
    if (!MediaLibraryNapiUtils::IsSystemApp()) {
        NapiError::ThrowError(env, E_CHECK_SYSTEMAPP_FAIL, "This interface can be called only by system apps");
        return nullptr;
    }

    napi_value result = nullptr;
    CHECK_ARGS(env, napi_get_boolean(env, true, &result), JS_INNER_FAIL);
    constexpr size_t minArgs = ARGS_ONE;
    constexpr size_t maxArgs = ARGS_TWO;
    CHECK_ARGS(env, MediaLibraryNapiUtils::AsyncContextSetObjectInfo(env, info, context, minArgs, maxArgs),
        JS_ERR_PARAMETER_INVALID);
    auto photoAlbum = context->objectInfo->GetPhotoAlbumInstance();
    if (photoAlbum == nullptr) {
        NapiError::ThrowError(env, JS_ERR_PARAMETER_INVALID, "PhotoAlbum instance is null");
        return nullptr;
    }
    if (!PhotoAlbum::IsTrashAlbum(photoAlbum->GetPhotoAlbumType(), photoAlbum->GetPhotoAlbumSubType())) {
        NapiError::ThrowError(env, JS_ERR_PARAMETER_INVALID, "Failed to check trash album type");
        return nullptr;
    }

    /* Parse the first argument */
    vector<napi_value> napiValues;
    CHECK_NULLPTR_RET(MediaLibraryNapiUtils::GetNapiValueArray(env, context->argv[PARAM0], napiValues));
    if (napiValues.empty()) {
        return result;
    }
    napi_valuetype valueType = napi_undefined;
    vector<string> uris;
    CHECK_ARGS(env, napi_typeof(env, napiValues.front(), &valueType), JS_ERR_PARAMETER_INVALID);
    if (valueType == napi_string) {
        // The input should be an array of asset uri.
        CHECK_NULLPTR_RET(MediaLibraryNapiUtils::GetStringArray(env, napiValues, uris));
    } else if (valueType == napi_object) {
        // The input should be an array of asset object.
        CHECK_NULLPTR_RET(MediaLibraryNapiUtils::GetUriArrayFromAssets(env, napiValues, uris));
    }
    if (uris.empty()) {
        return result;
    }

    context->uris = uris;
    context->predicates.In(MediaColumn::MEDIA_ID, uris);
    context->valuesBucket.Put(MediaColumn::MEDIA_DATE_TRASHED, 0);

    CHECK_ARGS(env, napi_get_boolean(env, true, &result), JS_INNER_FAIL);
    return result;
}

static void TrashAlbumExecute(const TrashAlbumExecuteOpt &opt)
{
    MediaLibraryTracer tracer;
    tracer.Start(opt.tracerLabel);

    auto *context = static_cast<PhotoAlbumNapiAsyncContext*>(opt.data);
    if (context->predicates.GetOperationList().empty()) {
        NAPI_ERR_LOG("Operation list is empty.");
        return;
    }
    Uri uri(opt.uri);
    int changedRows = UserFileClient::Update(uri, context->predicates, context->valuesBucket);
    if (changedRows < 0) {
        context->SaveError(changedRows);
        NAPI_ERR_LOG("Trash album executed, changeRows: %{public}d.", changedRows);
        return;
    }
    context->changedRows = changedRows;
}

static void TrashAlbumComplete(napi_env env, napi_status status, void *data)
{
    auto *context = static_cast<PhotoAlbumNapiAsyncContext*>(data);
    auto jsContext = make_unique<JSAsyncContextOutput>();
    jsContext->status = false;
    CHECK_ARGS_RET_VOID(env, napi_get_undefined(env, &jsContext->data), JS_INNER_FAIL);
    if (context->error == ERR_DEFAULT) {
        CHECK_ARGS_RET_VOID(env, napi_get_undefined(env, &jsContext->error), JS_INNER_FAIL);
        jsContext->status = true;
    } else {
        context->HandleError(env, jsContext->error);
    }

    if (context->work != nullptr) {
        MediaLibraryNapiUtils::InvokeJSAsyncMethod(env, context->deferred, context->callbackRef,
                                                   context->work, *jsContext);
    }
    MediaLibraryNapiUtils::DeleteAsyncContextWithRef(env, context);
    delete context;
}

static void RecoverPhotosExecute(napi_env env, void *data)
{
    auto *context = static_cast<PhotoAlbumNapiAsyncContext *>(data);
    if (context->resultNapiType == ResultNapiType::TYPE_USERFILE_MGR) {
        TrashAlbumExecuteOpt opt = {
            .env = env,
            .data = data,
            .tracerLabel = "RecoverPhotosExecute",
            .uri = CONST_UFM_RECOVER_PHOTOS,
        };
        TrashAlbumExecute(opt);
        return;
    }

    AlbumRecoverAssetsReqBody reqBody;
    CHECK_IF_EQUAL(context->objectInfo != nullptr, "context->objectInfo is nullptr");
    auto photoAlbum = context->objectInfo->GetPhotoAlbumInstance();
    CHECK_IF_EQUAL(photoAlbum != nullptr, "photoAlbum is nullptr");
    reqBody.albumType = photoAlbum->GetPhotoAlbumType();
    reqBody.albumSubType = photoAlbum->GetPhotoAlbumSubType();
    reqBody.uris = context->uris;
    uint32_t businessCode = static_cast<uint32_t>(MediaLibraryBusinessCode::PAH_RECOVER_ASSETS);

    int32_t changedRows = IPC::UserDefineIPCClient().Call(businessCode, reqBody);
    if (changedRows < 0) {
        context->SaveError(changedRows);
        NAPI_ERR_LOG("changeRows: %{public}d.", changedRows);
        return;
    }
    context->changedRows = changedRows;
}

static void RecoverPhotosComplete(napi_env env, napi_status status, void *data)
{
    TrashAlbumComplete(env, status, data);
}

napi_value PhotoAlbumNapi::JSRecoverPhotos(napi_env env, napi_callback_info info)
{
    auto asyncContext = make_unique<PhotoAlbumNapiAsyncContext>();
    CHECK_NULLPTR_RET(TrashAlbumParseArgs(env, info, asyncContext));
    asyncContext->resultNapiType = ResultNapiType::TYPE_USERFILE_MGR;

    return MediaLibraryNapiUtils::NapiCreateAsyncWork(env, asyncContext, "JSRecoverPhotos", RecoverPhotosExecute,
        RecoverPhotosComplete);
}

static napi_value PrivateAlbumParseArgs(napi_env env, napi_callback_info info,
    unique_ptr<PhotoAlbumNapiAsyncContext> &context)
{
    string uri;
    CHECK_ARGS(env, MediaLibraryNapiUtils::ParseArgsStringCallback(env, info, context, uri),
        JS_ERR_PARAMETER_INVALID);
    auto photoAlbum = context->objectInfo->GetPhotoAlbumInstance();
    if (photoAlbum == nullptr) {
        NapiError::ThrowError(env, JS_ERR_PARAMETER_INVALID, "Failed to get photo album instance");
        return nullptr;
    }
    if (!PhotoAlbum::IsTrashAlbum(photoAlbum->GetPhotoAlbumType(), photoAlbum->GetPhotoAlbumSubType())) {
        NapiError::ThrowError(env, JS_ERR_PARAMETER_INVALID, "Failed to check trash album type");
        return nullptr;
    }

    context->predicates.EqualTo(MediaColumn::MEDIA_ID, MediaFileUtils::GetIdFromUri(uri));
    context->valuesBucket.Put(MediaColumn::MEDIA_DATE_TRASHED, 0);

    napi_value result = nullptr;
    CHECK_ARGS(env, napi_get_boolean(env, true, &result), JS_INNER_FAIL);
    return result;
}

napi_value PhotoAlbumNapi::PrivateAlbumRecoverPhotos(napi_env env, napi_callback_info info)
{
    auto asyncContext = make_unique<PhotoAlbumNapiAsyncContext>();
    asyncContext->resultNapiType = ResultNapiType::TYPE_USERFILE_MGR;
    CHECK_NULLPTR_RET(PrivateAlbumParseArgs(env, info, asyncContext));

    return MediaLibraryNapiUtils::NapiCreateAsyncWork(env, asyncContext, "PrivateAlbumRecoverPhotos",
        RecoverPhotosExecute, RecoverPhotosComplete);
}

napi_value PhotoAlbumNapi::PhotoAccessHelperRecoverPhotos(napi_env env, napi_callback_info info)
{
    auto asyncContext = make_unique<PhotoAlbumNapiAsyncContext>();
    CHECK_NULLPTR_RET(TrashAlbumParseArgs(env, info, asyncContext));
    asyncContext->resultNapiType = ResultNapiType::TYPE_PHOTOACCESS_HELPER;

    return MediaLibraryNapiUtils::NapiCreateAsyncWork(env, asyncContext, "JSRecoverPhotos", RecoverPhotosExecute,
        RecoverPhotosComplete);
}

static void DeletePhotosExecute(napi_env env, void *data)
{
    TrashAlbumExecuteOpt opt = {
        .env = env,
        .data = data,
        .tracerLabel = "DeletePhotosExecute",
        .uri = (static_cast<PhotoAlbumNapiAsyncContext *>(data)->resultNapiType == ResultNapiType::TYPE_USERFILE_MGR) ?
            CONST_UFM_DELETE_PHOTOS : CONST_PAH_DELETE_PHOTOS,
    };
    TrashAlbumExecute(opt);
}

static void DeletePhotosComplete(napi_env env, napi_status status, void *data)
{
    TrashAlbumComplete(env, status, data);
}

napi_value PhotoAlbumNapi::JSDeletePhotos(napi_env env, napi_callback_info info)
{
    auto asyncContext = make_unique<PhotoAlbumNapiAsyncContext>();
    CHECK_NULLPTR_RET(TrashAlbumParseArgs(env, info, asyncContext));
    asyncContext->resultNapiType = ResultNapiType::TYPE_USERFILE_MGR;

    return MediaLibraryNapiUtils::NapiCreateAsyncWork(env, asyncContext, "JSDeletePhotos", DeletePhotosExecute,
        DeletePhotosComplete);
}

napi_value PhotoAlbumNapi::PrivateAlbumDeletePhotos(napi_env env, napi_callback_info info)
{
    auto asyncContext = make_unique<PhotoAlbumNapiAsyncContext>();
    asyncContext->resultNapiType = ResultNapiType::TYPE_USERFILE_MGR;
    CHECK_NULLPTR_RET(PrivateAlbumParseArgs(env, info, asyncContext));

    return MediaLibraryNapiUtils::NapiCreateAsyncWork(env, asyncContext, "PrivateAlbumDeletePhotos",
        DeletePhotosExecute, DeletePhotosComplete);
}

static napi_value DeletePhotosParseArgs(
    napi_env env, napi_callback_info info, unique_ptr<PhotoAlbumNapiAsyncContext> &context)
{
    if (!MediaLibraryNapiUtils::IsSystemApp()) {
        NapiError::ThrowError(env, E_CHECK_SYSTEMAPP_FAIL, "This interface can be called only by system apps");
        return nullptr;
    }

    napi_value result = nullptr;
    CHECK_ARGS(env, napi_get_boolean(env, true, &result), JS_INNER_FAIL);
    constexpr size_t minArgs = ARGS_ONE;
    constexpr size_t maxArgs = ARGS_TWO;
    CHECK_ARGS(env,
        MediaLibraryNapiUtils::AsyncContextSetObjectInfo(env, info, context, minArgs, maxArgs),
        JS_ERR_PARAMETER_INVALID);
    auto photoAlbum = context->objectInfo->GetPhotoAlbumInstance();
    if (!PhotoAlbum::IsTrashAlbum(photoAlbum->GetPhotoAlbumType(), photoAlbum->GetPhotoAlbumSubType())) {
        NapiError::ThrowError(env, JS_ERR_PARAMETER_INVALID, "Failed to check trash album type");
        return nullptr;
    }

    /* Parse the first argument */
    vector<napi_value> napiValues;
    CHECK_NULLPTR_RET(MediaLibraryNapiUtils::GetNapiValueArray(env, context->argv[PARAM0], napiValues));
    if (napiValues.empty()) {
        return result;
    }
    napi_valuetype valueType = napi_undefined;
    CHECK_ARGS(env, napi_typeof(env, napiValues.front(), &valueType), JS_ERR_PARAMETER_INVALID);
    vector<string> uris;
    if (valueType == napi_string) {
        // The input should be an array of asset uri.
        CHECK_NULLPTR_RET(MediaLibraryNapiUtils::GetStringArray(env, napiValues, uris));
    } else if (valueType == napi_object) {
        // The input should be an array of asset object.
        CHECK_NULLPTR_RET(MediaLibraryNapiUtils::GetUriArrayFromAssets(env, napiValues, uris));
    }
    if (uris.empty()) {
        return result;
    }
    context->uris = uris;

    CHECK_ARGS(env, napi_get_boolean(env, true, &result), JS_INNER_FAIL);
    return result;
}

static void PahDeletePhotosExecute(napi_env env, void *data)
{
    MediaLibraryTracer tracer;
    tracer.Start("DeletePhotosExecute");

    auto *context = static_cast<PhotoAlbumNapiAsyncContext *>(data);
    CHECK_NULL_PTR_RETURN_VOID(context, "context is null");
    CHECK_IF_EQUAL(!context->uris.empty(), "uris is empty");

    DeletePhotosReqBody reqBody;
    reqBody.uris = context->uris;
    uint32_t businessCode = static_cast<uint32_t>(MediaLibraryBusinessCode::PAH_DELETE_PHOTOS);
    int32_t changedRows = IPC::UserDefineIPCClient().Call(businessCode, reqBody);
    if (changedRows < 0) {
        context->SaveError(changedRows);
        NAPI_ERR_LOG("pah delete photos executed, changeRows: %{public}d.", changedRows);
        return;
    }
    context->changedRows = changedRows;
}

napi_value PhotoAlbumNapi::PhotoAccessHelperDeletePhotos(napi_env env, napi_callback_info info)
{
    NAPI_INFO_LOG("enter");
    auto asyncContext = make_unique<PhotoAlbumNapiAsyncContext>();
    CHECK_NULLPTR_RET(DeletePhotosParseArgs(env, info, asyncContext));
    asyncContext->resultNapiType = ResultNapiType::TYPE_PHOTOACCESS_HELPER;

    return MediaLibraryNapiUtils::NapiCreateAsyncWork(
        env, asyncContext, "JSDeletePhotos", PahDeletePhotosExecute, DeletePhotosComplete);
}

static napi_value ParseArgsSetCoverUri(napi_env env, napi_callback_info info,
    unique_ptr<PhotoAlbumNapiAsyncContext> &context)
{
    string coverUri;
    CHECK_ARGS(env, MediaLibraryNapiUtils::ParseArgsStringCallback(env, info, context, coverUri),
        JS_ERR_PARAMETER_INVALID);
    auto photoAlbum = context->objectInfo->GetPhotoAlbumInstance();
    if (!MediaLibraryNapiUtils::IsSystemApp()) {
        NapiError::ThrowError(env, JS_ERR_PARAMETER_INVALID, "Only system apps can update album cover");
        return nullptr;
    }

    context->businessCode = static_cast<uint32_t>(MediaLibraryBusinessCode::PAH_SET_COVER_URI);
    context->predicates.EqualTo(PhotoAlbumColumns::ALBUM_ID, to_string(photoAlbum->GetAlbumId()));
    context->valuesBucket.Put(PhotoAlbumColumns::ALBUM_COVER_URI, coverUri);

    napi_value result = nullptr;
    CHECK_ARGS(env, napi_get_boolean(env, true, &result), JS_INNER_FAIL);
    return result;
}

napi_value PhotoAlbumNapi::PhotoAccessHelperSetCoverUri(napi_env env, napi_callback_info info)
{
    auto asyncContext = make_unique<PhotoAlbumNapiAsyncContext>();
    asyncContext->resultNapiType = ResultNapiType::TYPE_PHOTOACCESS_HELPER;
    CHECK_NULLPTR_RET(ParseArgsSetCoverUri(env, info, asyncContext));

    return MediaLibraryNapiUtils::NapiCreateAsyncWork(env, asyncContext, "JSCommitModify", JSCommitModifyExecute,
        JSCommitModifyCompleteCallback);
}

static void PhotoAccessHelperGetFaceIdExec(napi_env env, void *data)
{
    auto *context = static_cast<PhotoAlbumNapiAsyncContext *>(data);
    CHECK_NULL_PTR_RETURN_VOID(context, "Async context is null");

    auto *objectInfo = context->objectInfo;
    CHECK_NULL_PTR_RETURN_VOID(objectInfo, "objectInfo is null");

    auto photoAlbumInstance = objectInfo->GetPhotoAlbumInstance();
    CHECK_NULL_PTR_RETURN_VOID(photoAlbumInstance, "photoAlbumInstance is null");

    PhotoAlbumSubType albumSubType = photoAlbumInstance->GetPhotoAlbumSubType();
    if (albumSubType != PhotoAlbumSubType::PORTRAIT && albumSubType != PhotoAlbumSubType::GROUP_PHOTO) {
        NAPI_WARN_LOG("albumSubType: %{public}d, not support getFaceId", albumSubType);
        return;
    }

    GetFaceIdReqBody reqBody;
    GetFaceIdRespBody respBody;
    reqBody.albumId = objectInfo->GetAlbumId();
    reqBody.albumSubType = static_cast<int32_t>(albumSubType);
    uint32_t businessCode = static_cast<uint32_t>(MediaLibraryBusinessCode::GET_FACE_ID);
    int32_t ret = IPC::UserDefineIPCClient().Call(businessCode, reqBody, respBody);
    if (ret < 0) {
        if (ret == E_PERMISSION_DENIED) {
            context->error = OHOS_PERMISSION_DENIED_CODE;
        } else {
            context->SaveError(E_FAIL);
        }
        NAPI_ERR_LOG("get face id failed, errCode is %{public}d", ret);
        return;
    }
    NAPI_INFO_LOG("respBody.groupTag: %{public}s", respBody.groupTag.c_str());
    context->faceTag = respBody.groupTag;
}

static void GetFaceIdCompleteCallback(napi_env env, napi_status status, void *data)
{
    auto *context = static_cast<PhotoAlbumNapiAsyncContext *>(data);
    CHECK_NULL_PTR_RETURN_VOID(context, "Async context is null");
    auto jsContext = make_unique<JSAsyncContextOutput>();
    jsContext->status = false;

    CHECK_ARGS_RET_VOID(env, napi_get_undefined(env, &jsContext->data), JS_INNER_FAIL);
    if (context->error != ERR_DEFAULT) {
        context->HandleError(env, jsContext->error);
    } else {
        CHECK_ARGS_RET_VOID(env,
            napi_create_string_utf8(env, context->faceTag.c_str(), NAPI_AUTO_LENGTH, &jsContext->data), JS_INNER_FAIL);
        jsContext->status = true;
    }

    if (context->work != nullptr) {
        MediaLibraryNapiUtils::InvokeJSAsyncMethod(env, context->deferred, context->callbackRef, context->work,
            *jsContext);
    }
    MediaLibraryNapiUtils::DeleteAsyncContextWithRef(env, context);
    delete context;
}

napi_value PhotoAlbumNapi::PhotoAccessHelperGetFaceId(napi_env env, napi_callback_info info)
{
    if (!MediaLibraryNapiUtils::IsSystemApp()) {
        NapiError::ThrowError(env, E_CHECK_SYSTEMAPP_FAIL, "Only system apps can get the Face ID of the album");
        return nullptr;
    }

    auto asyncContext = make_unique<PhotoAlbumNapiAsyncContext>();

    CHECK_ARGS(env, MediaLibraryNapiUtils::AsyncContextSetObjectInfo(env, info, asyncContext, 0, 0),
        JS_ERR_PARAMETER_INVALID);

    return MediaLibraryNapiUtils::NapiCreateAsyncWork(env, asyncContext, "JSAnalysisAlbumGetFaceId",
        PhotoAccessHelperGetFaceIdExec, GetFaceIdCompleteCallback);
}

napi_value PhotoAlbumNapi::JSPhotoAccessGetSharedPhotoAssets(napi_env env, napi_callback_info info)
{
    MediaLibraryTracer tracer;
    tracer.Start("JSPhotoAccessGetSharedPhotoAssets");
    unique_ptr<PhotoAlbumNapiAsyncContext> asyncContext =
        make_unique<PhotoAlbumNapiAsyncContext>();
    CHECK_NULLPTR_RET(ParseArgsGetPhotoAssets(env, info, asyncContext));

    PhotoAlbumNapiAsyncContext* context =
        static_cast<PhotoAlbumNapiAsyncContext*>((asyncContext.get()));

    Uri uri(CONST_PAH_QUERY_PHOTO_MAP);
    ConvertColumnsForPortrait(context);
    shared_ptr<NativeRdb::ResultSet> resultSet = UserFileClient::QueryRdb(uri,
        context->predicates, context->fetchColumn);
    CHECK_NULLPTR_RET(resultSet);

    napi_value jsFileArray = 0;
    napi_create_array(env, &jsFileArray);

    int count = 0;
    int err = resultSet->GoToFirstRow();
    if (err != napi_ok) {
        NAPI_ERR_LOG("Failed GoToFirstRow %{public}d", err);
        return jsFileArray;
    }
    do {
        napi_value item = MediaLibraryNapiUtils::GetNextRowObject(env, resultSet, true);
        napi_set_element(env, jsFileArray, count++, item);
    } while (!resultSet->GoToNextRow());
    resultSet->Close();
    return jsFileArray;
}

static napi_value CheckArgsGetSelectedPhotoAssets(
    napi_env env, napi_callback_info info, unique_ptr<PhotoAlbumNapiAsyncContext> &context)
{
    napi_value result = nullptr;
    constexpr size_t minArgs = ARGS_ONE;
    constexpr size_t maxArgs = ARGS_TWO;
    CHECK_ARGS(env,
        MediaLibraryNapiUtils::AsyncContextSetObjectInfo(env, info, context, minArgs, maxArgs),
        NAPI_INVALID_PARAMETER_ERROR);
 
    /* Parse the first argument */
    CHECK_ARGS(env,
        MediaLibraryNapiUtils::GetFetchOption(env, context->argv[PARAM0], ASSET_FETCH_OPT, context),
        NAPI_INVALID_PARAMETER_ERROR);

    if (context->argc == ARGS_TWO) {
        napi_valuetype valueType = napi_undefined;
        CHECK_COND_RET(napi_typeof(env, context->argv[PARAM1], &valueType) == napi_ok, nullptr, "get param type fail");
        if (valueType == napi_string) {
            unique_ptr<char[]> tmp;
            bool succ;
            size_t ignore;
            tie(succ, tmp, ignore) = MediaLibraryNapiUtils::ToUTF8String(env, context->argv[PARAM1]);
            CHECK_COND_RET(succ, nullptr, "parse ARGS_TWO fail");
            context->filter = string(tmp.get());
            size_t maxFilterSize = 255;
            CHECK_COND_RET(context->filter.size() <= maxFilterSize, nullptr, "ARGS_TWO length beyond limit");
            CHECK_COND_RET(nlohmann::json::accept(context->filter), nullptr, "failed to verify the filter format");
            nlohmann::json filterJson = nlohmann::json::parse(context->filter.c_str());
            std::string key = "currentFileId";
            size_t sizeLimit = 1;
            bool cond = !filterJson.is_discarded() &&
                filterJson.size() == sizeLimit && filterJson.contains(key) && filterJson[key].is_string();
            CHECK_COND_RET(cond, nullptr, "ARGS_TWO must be a JSON object with exactly one key : currentFileId");
            std::string value = filterJson[key];
            bool isValidInteger = !value.empty() &&
                                  std::all_of(value.begin(), value.end(), [](char c) { return c >= '0' && c <= '9'; });
            CHECK_COND_RET(isValidInteger, nullptr, "key : currentFileId must be a integer");
        }
    }
 
    auto photoAlbum = context->objectInfo->GetPhotoAlbumInstance();
    CHECK_COND_RET(photoAlbum != nullptr, nullptr, "failed to parse album");
    bool isPortraitAlbum =
        photoAlbum->IsSmartPortraitPhotoAlbum(photoAlbum->GetPhotoAlbumType(), photoAlbum->GetPhotoAlbumSubType());
    CHECK_COND_RET(isPortraitAlbum, nullptr, "this is not portrait album");
    
    for (std::string colum : context->fetchColumn) {
        CHECK_COND_RET(PhotoColumn::IsPhotoColumn(colum), nullptr, "column not in Photos table");
    }
 
    CHECK_ARGS(env, napi_get_boolean(env, true, &result), NAPI_INVALID_PARAMETER_ERROR);
    return result;
}
 
static void JSPhotoAccessGetSelectedPhotoAssetsExecute(napi_env env, void *data)
{
    MediaLibraryTracer tracer;
    tracer.Start("JSPhotoAccessGetPhotoAssetsExecute");
 
    auto *context = static_cast<PhotoAlbumNapiAsyncContext *>(data);
    CHECK_NULL_PTR_RETURN_VOID(context, "Async context is null");
    auto *objectInfo = context->objectInfo;
    CHECK_NULL_PTR_RETURN_VOID(objectInfo, "objectInfo is null");
    auto photoAlbum = objectInfo->GetPhotoAlbumInstance();
    CHECK_NULL_PTR_RETURN_VOID(photoAlbum, "photoAlbumInstance is null");
 
    ConvertColumnsForPortrait(context);
 
    AlbumGetSelectedAssetsReqBody reqBody;
    int32_t userId = photoAlbum->GetUserId();
    reqBody.albumId = photoAlbum->GetAlbumId();
    reqBody.predicates = context->predicates;
    reqBody.columns = context->fetchColumn;
    if (!context->filter.empty()) {
        reqBody.filter = context->filter;
    }
 
    AlbumGetSelectedAssetsRespBody respBody;
    uint32_t businessCode = static_cast<uint32_t>(MediaLibraryBusinessCode::ALBUM_SYS_GET_SELECTED_ASSETS);
    auto client = IPC::UserDefineIPCClient().SetUserId(userId);
    int32_t errCode = client.Call(businessCode, reqBody, respBody);
    if (errCode < 0) {
        if (errCode == E_PERMISSION_DENIED) {
            context->error = OHOS_PERMISSION_DENIED_CODE;
        } else {
            context->error = MEDIA_LIBRARY_INTERNAL_SYSTEM_ERROR;
        }
        NAPI_ERR_LOG("get selected assets failed, errCode is %{public}d", errCode);
        return;
    }
 
    std::shared_ptr<DataShare::DataShareResultSet> resultSet = respBody.resultSet;
    context->fetchResult = make_unique<FetchResult<FileAsset>>(move(resultSet));
    context->fetchResult->SetResultNapiType(ResultNapiType::TYPE_PHOTOACCESS_HELPER);
    context->fetchResult->SetUserId(userId);
}
 
napi_value PhotoAlbumNapi::JSPhotoAccessGetSelectedPhotoAssets(napi_env env, napi_callback_info info)
{
    if (!MediaLibraryNapiUtils::IsSystemApp()) {
        NapiError::ThrowError(env, E_CHECK_SYSTEMAPP_FAIL, "Only system apps can get the selected photo assets");
        return nullptr;
    }
    unique_ptr<PhotoAlbumNapiAsyncContext> asyncContext = make_unique<PhotoAlbumNapiAsyncContext>();
    CHECK_COND(env, CheckArgsGetSelectedPhotoAssets(env, info, asyncContext) != nullptr, NAPI_INVALID_PARAMETER_ERROR);
 
    return MediaLibraryNapiUtils::NapiCreateAsyncWork(env, asyncContext, "JSGetSelectedPhotoAssets",
        JSPhotoAccessGetSelectedPhotoAssetsExecute, JSGetPhotoAssetsCallbackComplete);
}

static void PhotoAccessGetFusionAssetsInfoExec(napi_env env, void *data)
{
    MediaLibraryTracer tracer;
    tracer.Start("PhotoAccessGetFusionAssetsInfoExec");
    NAPI_INFO_LOG("PhotoAccessGetFusionAssetsInfoExec start");
 
    auto *context = static_cast<PhotoAlbumNapiAsyncContext *>(data);
    CHECK_NULL_PTR_RETURN_VOID(context, "Get Fusion Assets Async context is null");
 
    auto *objectInfo = context->objectInfo;
    CHECK_NULL_PTR_RETURN_VOID(objectInfo, "Get Fusion Assets objectInfo is null");
 
    auto photoAlbumInstance = objectInfo->GetPhotoAlbumInstance();
    CHECK_NULL_PTR_RETURN_VOID(photoAlbumInstance, "Get Fusion Assets photoAlbumInstance is null");
 
    PhotoAlbumType albumType = photoAlbumInstance->GetPhotoAlbumType();
    if (!PhotoAlbum::CheckPhotoAlbumType(albumType) || albumType == PhotoAlbumType::SMART) {
        NAPI_WARN_LOG("albumType: %{public}d, not support getFusionAssetsInfo", albumType);
        return;
    }
 
    GetFussionAssetsReqBody reqBody;
    GetFussionAssetsRespBody respBody;
    reqBody.albumId = photoAlbumInstance->GetAlbumId();
    reqBody.albumType = static_cast<int32_t>(albumType);
    uint32_t businessCode = static_cast<uint32_t>(MediaLibraryBusinessCode::PAH_QUERY_FUSION_ASSET_INFO);
    int32_t ret = IPC::UserDefineIPCClient().Call(businessCode, reqBody, respBody);
    if (ret < 0) {
        if (ret == E_PERMISSION_DENIED) {
            context->error = OHOS_PERMISSION_DENIED_CODE;
        } else {
            context->error = MEDIA_LIBRARY_INTERNAL_SYSTEM_ERROR;
        }
        NAPI_ERR_LOG("get fusion assets info failed, errCode is %{public}d", ret);
        return;
    }
    for (auto qryResult: respBody.queryResult) {
        FusionAssetsInfo assetInfo;
        assetInfo.assetsType = static_cast<FusionAssetType>(qryResult.assetsType);
        assetInfo.assetsCount = qryResult.assetsCount;
        std::string filePath = qryResult.assetsPath;
        assetInfo.assetsPath = std::filesystem::path(filePath).parent_path().string();
        if (assetInfo.assetsCount != 0) {
            context->fusionAssetInfos.push_back(assetInfo);
        }
    }
}
 
static bool GetFusionAssetsInfoResult(napi_env env, unique_ptr<JSAsyncContextOutput> &jsContext,
    PhotoAlbumNapiAsyncContext* context)
{
    const std::string assetsType = "assetsType";
    const std::string assetsCount = "assetsCount";
    const std::string assetsPath = "assetsPath";
    napi_value entity = nullptr;
    size_t resultArraySize = context->fusionAssetInfos.size();
    napi_status status = napi_create_array_with_length(env, resultArraySize, &entity);
    CHECK_COND_RET(status == napi_ok, false, "Create array error!");
    NAPI_INFO_LOG("GetFusionAssetsInfoResult, infos size: %{public}zu", context->fusionAssetInfos.size());
 
    for (size_t i = 0; i < context->fusionAssetInfos.size(); ++i) {
        auto assetInfo = context->fusionAssetInfos[i];
        napi_value entityInfo;
        status = napi_create_object(env, &entityInfo);
        CHECK_COND_RET(status == napi_ok, false, "create entityInfo failed");
 
        napi_value entityTypeValue;
        int32_t typeValue = static_cast<int32_t>(assetInfo.assetsType);
        status = napi_create_int32(env, typeValue, &entityTypeValue);
        CHECK_COND_RET(status == napi_ok, false, "create entityType failed");
        status = napi_set_named_property(env, entityInfo, assetsType.c_str(), entityTypeValue);
        CHECK_COND_RET(status == napi_ok, false, "failed to Set named property of entityType");
 
        napi_value entityCountValue;
        status = napi_create_int32(env, assetInfo.assetsCount, &entityCountValue);
        CHECK_COND_RET(status == napi_ok, false, "create entityCount failed");
        status = napi_set_named_property(env, entityInfo, assetsCount.c_str(), entityCountValue);
        CHECK_COND_RET(status == napi_ok, false, "failed to Set named property of entityCount");
 
        napi_value entityPathValue;
        status = napi_create_string_utf8(env, assetInfo.assetsPath.c_str(), NAPI_AUTO_LENGTH, &entityPathValue);
        CHECK_COND_RET(status == napi_ok, false, "create entityPath failed");
        status = napi_set_named_property(env, entityInfo, assetsPath.c_str(), entityPathValue);
        CHECK_COND_RET(status == napi_ok, false, "failed to Set named property of entityPath");
 
        status = napi_set_element(env, entity, i, entityInfo);
        CHECK_COND_RET(status == napi_ok, false, "failed to Set element property of entityInfo");
    }
    jsContext->data = entity;
    return true;
}
 
static void GetFusionAssetsInfoCompleteCallback(napi_env env, napi_status status, void *data)
{
    MediaLibraryTracer tracer;
    tracer.Start("GetFusionAssetsInfoCompleteCallback");
 
    auto *context = static_cast<PhotoAlbumNapiAsyncContext *>(data);
    CHECK_NULL_PTR_RETURN_VOID(context, "Async context is null");
    auto jsContext = make_unique<JSAsyncContextOutput>();
    jsContext->status = false;
 
    CHECK_ARGS_RET_VOID(env, napi_get_undefined(env, &jsContext->data), JS_INNER_FAIL);
    CHECK_ARGS_RET_VOID(env, napi_get_undefined(env, &jsContext->error), JS_INNER_FAIL);
    if (context->error != ERR_DEFAULT) {
        context->HandleError(env, jsContext->error);
    } else {
        jsContext->status = true;
        GetFusionAssetsInfoResult(env, jsContext, context);
    }
    tracer.Finish();
 
    if (context->work != nullptr) {
        MediaLibraryNapiUtils::InvokeJSAsyncMethod(env, context->deferred, context->callbackRef, context->work,
            *jsContext);
    }
    MediaLibraryNapiUtils::DeleteAsyncContextWithRef(env, context);
    delete context;
}
 
napi_value PhotoAlbumNapi::PhotoAccessGetFusionAssetsInfo(napi_env env, napi_callback_info info)
{
    MediaLibraryTracer tracer;
    tracer.Start("PhotoAccessGetFusionAssetsInfo");
    NAPI_INFO_LOG("PhotoAccessGetFusionAssetsInfo start");
    if (!MediaLibraryNapiUtils::IsSystemApp()) {
        NapiError::ThrowError(env, E_CHECK_SYSTEMAPP_FAIL, "Only system apps can get the fusion assets info");
        return nullptr;
    }
    auto asyncContext = make_unique<PhotoAlbumNapiAsyncContext>();
    CHECK_ARGS(env, MediaLibraryNapiUtils::AsyncContextSetObjectInfo(env, info, asyncContext, 0, 0),
        JS_ERR_PARAMETER_INVALID);
    return MediaLibraryNapiUtils::NapiCreateAsyncWork(env, asyncContext, "JSGetFusionAssetsInfo",
        PhotoAccessGetFusionAssetsInfoExec, GetFusionAssetsInfoCompleteCallback);
}
static void JSGetAttributeExecute(napi_env env, void* data)
{
    MediaLibraryTracer tracer;
    tracer.Start("JSGetAttributeExecute");
    NAPI_INFO_LOG("JSGetAttributeExecute start");

    auto *context = static_cast<PhotoAlbumNapiAsyncContext*>(data);
    if (context == nullptr) {
        NAPI_ERR_LOG("Async context is null");
        NapiError::ThrowError(env, JS_E_INNER_FAIL, "Async context is null");
        return;
    }
    auto photoAlbum = context->objectInfo->GetPhotoAlbumInstance();
    if (photoAlbum == nullptr) {
        NAPI_ERR_LOG("photoAlbum is null");
        context->error = JS_E_INNER_FAIL;
        return;
    }

    GetAttributeReqBody reqBody;
    GetAttributeRespBody respBody;
    reqBody.albumId = photoAlbum->GetAlbumId();
    reqBody.albumType = photoAlbum->GetPhotoAlbumType();
    reqBody.albumSubType = photoAlbum->GetPhotoAlbumSubType();
    reqBody.attributeArray = context->attributeArray;
    uint32_t businessCode = static_cast<uint32_t>(MediaLibraryBusinessCode::ANALYSIS_ALBUM_GET_ATTRIBUTE);
    int32_t result = IPC::UserDefineIPCClient().Call(businessCode, reqBody, respBody);
    if (result < 0) {
        NAPI_ERR_LOG("Failed to get system contact, error: %{public}d", result);
        context->SaveError(result);
        return;
    }
    context->attributeQueryResults = respBody.queryResults;
    NAPI_INFO_LOG("GetAttribute: albumId: %{public}d", reqBody.albumId);
}

static napi_status SetValueStringToRecord(napi_env env, const string& key, const string& value,
    napi_value &result)
{
    napi_value outputValue = nullptr;
    napi_value napiValue = nullptr;
    napi_get_undefined(env, &outputValue);
    if (napi_create_object(env, &outputValue) != napi_ok) {
        NAPI_ERR_LOG("Failed to create napi object for extra info");
        return napi_invalid_arg;
    }
    if (napi_create_string_utf8(env, value.c_str(), NAPI_AUTO_LENGTH, &napiValue) != napi_ok) {
        NAPI_ERR_LOG("Failed to create napi string for extra info");
        return napi_invalid_arg;
    }
    if (napi_set_named_property(env, outputValue, "attrValue", napiValue) != napi_ok) {
        NAPI_ERR_LOG("Failed to set extra info to attrValue");
        return napi_invalid_arg;
    }
    if (napi_set_named_property(env, result, key.c_str(), outputValue) != napi_ok) {
        NAPI_ERR_LOG("Failed to set extra info to record");
        return napi_invalid_arg;
    }
    return napi_ok;
}

static void JSGetAttributeCompleteCallback(napi_env env, napi_status status, void* data)
{
    MediaLibraryTracer tracer;
    tracer.Start("JSGetAttributeCompleteCallback");

    auto *context = static_cast<PhotoAlbumNapiAsyncContext*>(data);
    CHECK_NULL_PTR_RETURN_VOID(context, "Async context is null");

    unique_ptr<JSAsyncContextOutput> jsContext = make_unique<JSAsyncContextOutput>();
    jsContext->status = false;

    CHECK_ARGS_RET_VOID(env, napi_get_undefined(env, &jsContext->data), JS_E_INNER_FAIL);
    CHECK_ARGS_RET_VOID(env, napi_get_undefined(env, &jsContext->error), JS_E_INNER_FAIL);
    napi_get_undefined(env, &jsContext->data);
    if (napi_create_object(env, &jsContext->data) != napi_ok) {
        NAPI_ERR_LOG("Failed to create napi object for extra info");
        return;
    }
    if (context->error == ERR_DEFAULT) {
        for (size_t i = 0; i < context->attributeArray.size() && i < context->attributeQueryResults.size(); ++i) {
            const std::string& attrName = context->attributeArray[i];
            if (context->attributeQueryResults[i].count(attrName) == 0) {
                delete context;
                NapiError::ThrowError(env, JS_E_INNER_FAIL, "Attribute not found in query result");
                return;
            }
            const std::string& attrValue = context->attributeQueryResults[i].at(attrName);
            if (SetValueStringToRecord(env, attrName, attrValue, jsContext->data) != napi_ok) {
                delete context;
                NapiError::ThrowError(env, JS_E_INNER_FAIL, "Failed to set attribute value to result");
                return;
            }
        }
        jsContext->status = true;
    } else {
        context->HandleError(env, jsContext->error);
    }

    tracer.Finish();
    if (context->work != nullptr) {
        MediaLibraryNapiUtils::InvokeJSAsyncMethod(
            env, context->deferred, context->callbackRef, context->work, *jsContext);
    }
    delete context;
}

static bool CheckAlbumChangeRequestCallerPermission(string permission)
{
    AccessTokenID tokenCaller = IPCSkeleton::GetSelfTokenID();
    int result = AccessTokenKit::VerifyAccessToken(tokenCaller, permission);
    if (result != PermissionState::PERMISSION_GRANTED) {
        NAPI_ERR_LOG("Have no media permission: %{public}s", permission.c_str());
        return false;
    }
    return true;
}

static bool CheckGetAttributePermission(napi_env env)
{
    if (!MediaLibraryNapiUtils::IsSystemApp()) {
        NapiError::ThrowError(env, E_CHECK_SYSTEMAPP_FAIL, "This interface can be called only by system apps");
        return false;
    }
    if (!CheckAlbumChangeRequestCallerPermission(PERM_READ_IMAGEVIDEO)) {
        NapiError::ThrowError(env, OHOS_PERMISSION_DENIED_CODE, "Permission denied: "
            + string(PERM_READ_IMAGEVIDEO));
        return false;
    }
    return true;
}

static bool ParseAttributeArray(napi_env env, napi_value arg,
    vector<string> &attributeArray)
{
    vector<napi_value> napiValues;
    napi_valuetype valueType = napi_undefined;
    CHECK_ARGS_BASE(env, napi_typeof(env, arg, &valueType), JS_E_PARAM_INVALID, false);
    CHECK_COND_RET(valueType == napi_object, false, "Invalid argument type");
    CHECK_COND_RET(MediaLibraryNapiUtils::GetNapiValueArray(env, arg, napiValues) != nullptr,
        false, "Failed to get attribute array");
    CHECK_COND_RET(!napiValues.empty(), false, "array is empty");
    for (const auto& napiValue : napiValues) {
        std::string attributeValue;
        CHECK_ARGS_BASE(env, MediaLibraryNapiUtils::GetParamStringPathMax(env, napiValue, attributeValue),
            JS_E_PARAM_INVALID, false);
        attributeArray.push_back(attributeValue);
    }
    return true;
}

bool HasDuplicate(std::vector<std::string>& vec)
{
    if (vec.size() <= 1) {
        return false;
    }

    std::vector<std::string> tmp = vec;
    std::sort(tmp.begin(), tmp.end());
    return std::adjacent_find(tmp.begin(), tmp.end()) != tmp.end();
}

napi_value PhotoAlbumNapi::JSAnalysisAlbumGetAttribute(napi_env env, napi_callback_info info)
{
    MediaLibraryTracer tracer;
    tracer.Start("JSAnalysisAlbumGetAttribute");

    if (!CheckGetAttributePermission(env)) {
        return nullptr;
    }

    // Create async context
    unique_ptr<PhotoAlbumNapiAsyncContext> asyncContext = make_unique<PhotoAlbumNapiAsyncContext>();
    CHECK_COND_WITH_ERR_MESSAGE(env, asyncContext != nullptr, JS_E_PARAM_INVALID, "asyncContext context is null");
    CHECK_COND_WITH_ERR_MESSAGE(env,
        MediaLibraryNapiUtils::AsyncContextSetObjectInfo(env, info, asyncContext, ARGS_ONE, ARGS_ONE) == napi_ok,
        MEDIA_LIBRARY_INTERNAL_SYSTEM_ERROR, "Failed to get object info");
    vector<string> attributeArray;
    CHECK_COND_WITH_ERR_MESSAGE(env, ParseAttributeArray(env, asyncContext->argv[ARGS_ZERO], attributeArray),
        JS_E_PARAM_INVALID, "Failed to parse attribute array");
    CHECK_COND_WITH_ERR_MESSAGE(env, attributeArray.size() <= GET_ATTRIBUTE_MAX_COUNT && !attributeArray.empty(),
        JS_E_PARAM_INVALID, "Invalid attribute count");
    CHECK_COND_WITH_ERR_MESSAGE(env, !HasDuplicate(attributeArray), JS_E_PARAM_INVALID,
        "Duplicate attributes found");
    for (const auto& attribute : attributeArray) {
        CHECK_COND_WITH_ERR_MESSAGE(env, attribute == ANALYSIS_ALBUM_ATTR_EXTRA_INFO, JS_E_PARAM_INVALID,
            "Invalid attribute: " + attribute);
    }
    asyncContext->attributeArray = std::move(attributeArray);

    auto photoAlbum = asyncContext->objectInfo->GetPhotoAlbumInstance();
    CHECK_COND_WITH_ERR_MESSAGE(env, photoAlbum != nullptr,
        MEDIA_LIBRARY_INTERNAL_SYSTEM_ERROR, "photoAlbum is null");
    CHECK_COND_WITH_ERR_MESSAGE(env, IsPortraitAlbumAttributeTarget(photoAlbum), JS_E_PARAM_INVALID,
        "Only portrait album can operate attribute");

    return MediaLibraryNapiUtils::NapiCreateAsyncWork(
        env, asyncContext, "JSGetAttribute", JSGetAttributeExecute, JSGetAttributeCompleteCallback);
}
} // namespace OHOS::Media
