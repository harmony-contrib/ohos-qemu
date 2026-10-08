/*
 * Copyright (c) Huawei Technologies Co., Ltd. 2024-2025. All rights reserved.
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
#include "MediaCreative.h"
#include "HmcService.h"
#include <Material/HmcMaterialUtil.h>
#include <Material/Entity/HmcMaterialUid.h>

IHmcAsset::IHmcAsset() : IHmcAsset(HMC_UID_NULL, nullptr) {}

IHmcAsset::IHmcAsset(HmcUid laneUid, HmcEventHandler *eventHandler)
    : m_laneUid(laneUid),
      m_materialUid(HMC_UID_NULL),
      m_type(HMC_ASSET_NONE),
      m_path_type(HMC_ASEET_PATH_TYPE_ABSOLUTE),
      m_trimIn(0),
      m_trimOut(0),
      m_pureDuration(0),
      m_complexDuration(0),
      m_complexStartTime(0),
      m_speed(ASSET_DEFAULT_SPEED),
      m_isVisibility(TRUE),
      m_isBackward(FALSE),
      m_eventHandler(eventHandler),
      m_size(0)
{
    HmcUidGenerate(&m_uid);
    SINGLETON(HmcUidAdmin)->SetAsset(m_uid, this);
}

IHmcAsset::IHmcAsset(const IHmcAsset &asset) : m_complexDuration(asset.m_complexDuration)
{
    m_laneUid = asset.m_laneUid;
    m_eventHandler = asset.m_eventHandler;
    m_materialUid = asset.m_materialUid;
    m_cloudContentId = asset.m_cloudContentId;
    m_type = asset.m_type;
    m_name = asset.m_name;
    m_path = asset.m_path;
    m_path_type = asset.m_path_type;
    m_trimIn = asset.m_trimIn;
    m_trimOut = asset.m_trimOut;
    m_complexStartTime = asset.m_complexStartTime;
    m_pureDuration = asset.m_pureDuration;
    m_speed = asset.m_speed;
    m_isVisibility = asset.m_isVisibility;
    m_isBackward = asset.m_isBackward;
    m_size = asset.m_size;
    m_orientation = asset.m_orientation;

    HmcUidGenerate(&m_uid);
    SINGLETON(HmcUidAdmin)->SetAsset(m_uid, this);
}

IHmcAsset &IHmcAsset::operator = (const IHmcAsset &asset)
{
    if (this == &asset) {
        return *this;
    }

    m_complexDuration = HmcTime(asset.m_complexDuration);
    m_laneUid = asset.m_laneUid;
    m_eventHandler = asset.m_eventHandler;
    m_materialUid = asset.m_materialUid;
    m_cloudContentId = asset.m_cloudContentId;
    m_type = asset.m_type;
    m_name = asset.m_name;
    m_path = asset.m_path;
    m_trimIn = asset.m_trimIn;
    m_trimOut = asset.m_trimOut;
    m_complexStartTime = asset.m_complexStartTime;
    m_pureDuration = asset.m_pureDuration;
    m_path_type = asset.m_path_type;
    m_speed = asset.m_speed;
    m_isVisibility = asset.m_isVisibility;
    m_isBackward = asset.m_isBackward;
    m_size = asset.m_size;
    m_orientation = asset.m_orientation;
    return *this;
}

IHmcAsset::~IHmcAsset()
{
    SINGLETON(HmcUidAdmin)->Erase(m_uid);
}

HmcUid IHmcAsset::GetUid() const
{
    return m_uid;
}

HmcAssetType IHmcAsset::GetType() const
{
    return m_type;
}

HmcUid IHmcAsset::GetMaterialUid() const
{
    return m_materialUid;
}

HmcUid IHmcAsset::GetLaneUid() const
{
    return m_laneUid;
}

VOID IHmcAsset::SetLaneUid(HmcUid laneUid)
{
    m_laneUid = laneUid;
}

const STRING &IHmcAsset::GetName() const
{
    return m_name;
}

VOID IHmcAsset::SetName(STRING name)
{
    m_name = name;
}

// 从文件路径中获取文件名（带后缀）
std::string GetFileNameFromPath(std::string strFullName)
{
    if (strFullName.empty()) {
        return "";
    }

    std::replace(strFullName.begin(), strFullName.end(), '/', '\\');
    std::string::size_type iPos = strFullName.find_last_of('\\') + 1;
    return strFullName.substr(iPos, strFullName.length() - iPos);
}

VOID IHmcAsset::SetNameFromPath()
{
    if (m_cloudContentId.empty()) {
        STRING name = GetFileNameFromPath(m_path);
        if (!name.empty()) {
            m_name = name;
        }
    } else {
        STRING name;
        INT32 ret =
            SINGLETON(HmcMaterialManager)->GetMaterialContentName(m_cloudContentId, name); // 通过id来找素材的名字
        if (ret == HMC_OK) {
            m_name = name;
        }
    }
}

const STRING &IHmcAsset::GetPath() const
{
    return m_path;
}

VOID IHmcAsset::GetFileSize(MAP<STRING, INT64> &infoList)
{
    if (!m_path.empty()) {
        auto iter = infoList.find(m_path);
        if (iter == infoList.end()) {
            std::pair<STRING, INT64> value(m_path, m_size);
            infoList.insert(value);
        }
    }
}

HmcAssetPathType IHmcAsset::GetPathType() const
{
    return m_path_type;
}

INT32 IHmcAsset::SetAssetPathType(const HmcAssetPathType &pathType)
{
    m_path_type = pathType;
    return HMC_OK;
}

STRING IHmcAsset::CovertPathToRelative(const STRING &path, const HmcAssetPathType &pathType)
{
    if (path.empty()) {
        return path;
    }
    STRING pathTmp(path);
    switch (pathType) {
        case HMC_ASEET_PATH_TYPE_SANDBOX:
            break;
        case HMC_ASEET_PATH_TYPE_ABSOLUTE: {
            size_t pos = pathTmp.find("\\fonts\\word.ttf");
            if (pos != STRING::npos) { // 本地字体的相对存放路径
                pathTmp = "\\fonts\\word.ttf";
            }
            break;
        }
        case HMC_ASEET_PATH_TYPE_DEFAULT_FONT: {
            // todo
            break;
        }
        case HMC_ASEET_PATH_TYPE_NET_MATERIAL: {
            break;
        }
        case HMC_ASEET_PATH_TYPE_RELATIVE:
            break;
        case HMC_ASEET_PATH_TYPE_MAIN_BUNDLE:
            break;
        case HMC_ASEET_PATH_TYPE_FRAMEWORK_BUNDLE:
            break;
        default:
            LOGE("CovertPathToRelative, unsupported path type!");
            break;
    }
    return pathTmp;
}

STRING IHmcAsset::CovertPathToAbsolute(const STRING &path, const HmcAssetPathType &pathType)
{
    if (path.empty()) {
        return path;
    }
    STRING pathTmp(path);
    STRING packageName;
    STRING filePath;
    switch (pathType) {
        case HMC_ASEET_PATH_TYPE_SANDBOX:
            break;
        case HMC_ASEET_PATH_TYPE_ABSOLUTE: {
            size_t pos = pathTmp.find("\\fonts\\word.ttf");
            if (pos != STRING::npos) { // 解析出本地字体的绝对路径
                pathTmp = HmcGetAppPath() + "\\fonts\\word.ttf";
            }
            break;
        }
        case HMC_ASEET_PATH_TYPE_DEFAULT_FONT:
            break;
        case HMC_ASEET_PATH_TYPE_NET_MATERIAL:
            break;
        case HMC_ASEET_PATH_TYPE_RELATIVE:
            break;
        case HMC_ASEET_PATH_TYPE_MAIN_BUNDLE:
            break;
        case HMC_ASEET_PATH_TYPE_FRAMEWORK_BUNDLE:
            break;
        default:
            LOGE("CovertPathToAbsolute, unsupported path type!");
            break;
    }
    return pathTmp;
}

BOOL IHmcAsset::Init(const HmcDict *dict)
{
    INT64 longlongValue = 0;
    if (HmcDictGetInt64(dict, DICT_KEY_ASSET_PROPERTY_DURATION, &longlongValue) == HMC_OK) {
        m_complexDuration.SetTime(longlongValue);
    }

    if (HmcDictGetInt64(dict, DICT_KEY_ASSET_PROPERTY_TRIM_IN, &longlongValue) == HMC_OK) {
        m_trimIn = HmcTimeUtil::NormalizeTime(longlongValue);
    }

    if (HmcDictGetInt64(dict, DICT_KEY_ASSET_PROPERTY_TRIM_OUT, &longlongValue) == HMC_OK) {
        m_trimOut = HmcTimeUtil::NormalizeTime(longlongValue);
    }

    return TRUE;
}

INT64 IHmcAsset::GetStartTime() const
{
    return m_complexStartTime;
}

VOID IHmcAsset::SetStartTime(INT64 startTime)
{
    m_complexStartTime = startTime;
}

INT64 IHmcAsset::GetEndTime() const
{
    return m_complexStartTime + m_complexDuration.GetTime() - 1;
}

VOID IHmcAsset::SetEndTime(INT64 endTime)
{
    m_complexDuration.SetTime(endTime - m_complexStartTime + 1);
}

VOID IHmcAsset::SetTrimIn(INT64 trimIn)
{
    m_trimIn = HmcTimeUtil::NormalizeTime(trimIn);
}

INT64 IHmcAsset::GetTrimOut() const
{
    return m_trimOut;
}

VOID IHmcAsset::SetTrimOut(INT64 trimOut)
{
    m_trimOut = HmcTimeUtil::NormalizeTime(trimOut);
}

INT64 IHmcAsset::GetDurationTime() const
{
    return m_complexDuration.GetTime();
}

VOID IHmcAsset::SetSpeed(FLOAT speed)
{
    m_speed = speed;
}

FLOAT IHmcAsset::GetSpeed() const
{
    return m_speed;
}

VOID IHmcAsset::SetDuration(INT64 duration)
{
    m_complexDuration.SetTime(duration);
}

INT64 IHmcAsset::GetPureDuration() const
{
    if ((m_speed >= -HMC_FLOAT_EPSINON) && (m_speed <= HMC_FLOAT_EPSINON)) {
        LOGE("m_speed zero");
        return m_pureDuration;
    }

    return HmcTimeUtil::NormalizeTime((INT64)((FLOAT)m_pureDuration / m_speed));
}

INT64 IHmcAsset::GetFileDuration()
{
    return 0;
}

BOOL IHmcAsset::GetBackward()
{
    return m_isBackward;
}

BOOL IHmcAsset::SetBackward(BOOL isBackward)
{
    m_isBackward = isBackward;
    std::swap(m_trimIn, m_trimOut);

    return TRUE;
}

Json::Value IHmcAsset::Serialize()
{
    Json::Value json;
    STRING currentPath;

    if (!m_cloudContentId.empty()) {
        json[DICT_KEY_ASSET_PROPERTY_CLOUD_ID] = m_cloudContentId;
        m_path_type = HMC_ASEET_PATH_TYPE_NET_MATERIAL;
    }

    json[DICT_KEY_ASSET_PROPERTY_NAME] = m_name;
    json[DICT_KEY_ASSET_PROPERTY_PATH_TYPE] = m_path_type;
    currentPath = CovertPathToRelative(m_path, m_path_type);
    json[DICT_KEY_ASSET_PROPERTY_PATH] = currentPath;
    json[DICT_KEY_ASSET_PROPERTY_PURE_DURATION] = (Json::Value::Int64)m_pureDuration;
    json[DICT_KEY_ASSET_PROPERTY_SPEED] = m_speed;
    json[DICT_KEY_ASSET_PROPERTY_DURATION] = (Json::Value::Int64)m_complexDuration.GetTime();
    json[DICT_KEY_ASSET_PROPERTY_START] = (Json::Value::Int64)m_complexStartTime;
    json[DICT_KEY_ASSET_PROPERTY_END] = (Json::Value::Int64)(m_complexStartTime + m_complexDuration.GetTime() - 1);
    json[DICT_KEY_ASSET_PROPERTY_TRIM_IN] = (Json::Value::Int64)m_trimIn;
    json[DICT_KEY_ASSET_PROPERTY_TRIM_OUT] = (Json::Value::Int64)m_trimOut;
    json[DICT_KEY_ASSET_PROPERTY_VISIBLE] = m_isVisibility;
    json[DICT_KEY_ASSET_PROPERTY_BACKWARD] = m_isBackward;
    json[DICT_KEY_ASSET_PROPERTY_SIZE] = (Json::Value::Int64)m_size;

    json[DICT_KEY_ASSET_PROPERTY_UID] = HmcUidToString(&m_uid);
    ;

    return json;
}

BOOL IHmcAsset::Deserialize(const Json::Value &jsonData)
{
    STRING assetUid;
    // todo: 解析json前需要判断json中有没有对应的字段，字段类型是否正确
    if (JsonValueUtil::IsString(jsonData, DICT_KEY_ASSET_PROPERTY_MATERIAL_UID)) {
        assetUid = jsonData[DICT_KEY_ASSET_PROPERTY_MATERIAL_UID].asString();
        (VOID)HmcUidFromString(assetUid.c_str(), &m_materialUid); // todo 临时变量
        // 老草稿需要将material_uid转换为cloud_id
        m_cloudContentId = HmcMaterialUtil::GetMaterialContentId(m_materialUid);
        LOGD("materialId is %s", m_cloudContentId.c_str());
    } else if (JsonValueUtil::IsString(jsonData, DICT_KEY_ASSET_PROPERTY_CLOUD_ID)) {
        // 新版本的草稿，会有cloudid字段
        m_cloudContentId = jsonData[DICT_KEY_ASSET_PROPERTY_CLOUD_ID].asString();
    }

    if (!m_cloudContentId.empty()) {
        // 网络素材
        m_path_type = HMC_ASEET_PATH_TYPE_NET_MATERIAL;
    }

    JsonValueUtil::ParseValueIfHas(jsonData, DICT_KEY_ASSET_PROPERTY_SIZE, m_size);
    JsonValueUtil::ParseValueIfHas(jsonData, DICT_KEY_ASSET_PROPERTY_START, m_complexStartTime);
    long int complexDuration;
    if (JsonValueUtil::ParseValueIfHas(jsonData, DICT_KEY_ASSET_PROPERTY_DURATION, complexDuration)) {
        m_complexDuration.SetTime(complexDuration);
    }
    JsonValueUtil::ParseValueIfHas(jsonData, DICT_KEY_ASSET_PROPERTY_PURE_DURATION, m_pureDuration);
    JsonValueUtil::ParseFloatIfHas(jsonData, DICT_KEY_ASSET_PROPERTY_SPEED, m_speed);
    JsonValueUtil::ParseValueIfHas(jsonData, DICT_KEY_ASSET_PROPERTY_TRIM_IN, m_trimIn);
    JsonValueUtil::ParseValueIfHas(jsonData, DICT_KEY_ASSET_PROPERTY_TRIM_OUT, m_trimOut);
    JsonValueUtil::ParseValueIfHas(jsonData, DICT_KEY_ASSET_PROPERTY_VISIBLE, m_isVisibility);
    JsonValueUtil::ParseValueIfHas(jsonData, DICT_KEY_ASSET_PROPERTY_PATH, m_path);

    return TRUE;
}

VOID IHmcAsset::GetAssetParamValue(HmcDict *dict) const
{
    if (dict == nullptr) {
        LOGE("parameter dict is null");
        return;
    }

    HmcDictSetUid(dict, DICT_KEY_ASSET_PROPERTY_UID, &m_uid);
    HmcDictSetUid(dict, DICT_KEY_ASSET_PROPERTY_LANE, &m_laneUid);
    HmcDictSetUid(dict, DICT_KEY_ASSET_PROPERTY_MATERIAL_UID, &m_materialUid);
    HmcDictSetString(dict, DICT_KEY_ASSET_PROPERTY_CLOUD_ID, m_cloudContentId.c_str());
    HmcDictSetString(dict, DICT_KEY_ASSET_PROPERTY_NAME, m_name.c_str());
    HmcDictSetString(dict, DICT_KEY_ASSET_PROPERTY_PATH, m_path.c_str());
    HmcDictSetInt64(dict, DICT_KEY_ASSET_PROPERTY_START, m_complexStartTime);
    HmcDictSetInt64(dict, DICT_KEY_ASSET_PROPERTY_END, GetEndTime());
    HmcDictSetInt64(dict, DICT_KEY_ASSET_PROPERTY_DURATION, m_complexDuration.GetTime());
    HmcDictSetInt64(dict, DICT_KEY_ASSET_PROPERTY_PURE_DURATION, m_pureDuration);
    HmcDictSetDouble(dict, DICT_KEY_ASSET_PROPERTY_SPEED, m_speed);
    HmcDictSetInt64(dict, DICT_KEY_ASSET_PROPERTY_TRIM_IN, m_trimIn);
    HmcDictSetInt64(dict, DICT_KEY_ASSET_PROPERTY_TRIM_OUT, m_trimOut);
    HmcDictSetInt32(dict, DICT_KEY_ASSET_PROPERTY_BACKWARD, m_isBackward);
    HmcDictSetInt64(dict, DICT_KEY_ASSET_PROPERTY_SIZE, m_size);
}

VOID IHmcAsset::SetAssetParamValue(const HmcDict *dict)
{
    if (dict == nullptr) {
        LOGE("parameter dict is null");
        return;
    }

    INT64 value64 = 0;
    if (HmcDictGetInt64(dict, DICT_KEY_ASSET_PROPERTY_START, &value64) == HMC_OK) {
        LOGI("set asset start time to: %lld", value64);
        m_complexStartTime = HmcTimeUtil::NormalizeTime(value64);
    }

    if (HmcDictGetInt64(dict, DICT_KEY_ASSET_PROPERTY_DURATION, &value64) == HMC_OK) {
        LOGI("set asset duration to: %lld", value64);
        m_complexDuration.SetTime(value64);
    }

    if (HmcDictGetInt64(dict, DICT_KEY_ASSET_PROPERTY_TRIM_IN, &value64) == HMC_OK) {
        LOGI("set asset trim in to: %lld", value64);
        m_trimIn = HmcTimeUtil::NormalizeTime(value64);
    }

    if (HmcDictGetInt64(dict, DICT_KEY_ASSET_PROPERTY_TRIM_OUT, &value64) == HMC_OK) {
        LOGI("set asset trim out to: %lld", value64);
        m_trimOut = HmcTimeUtil::NormalizeTime(value64);
    }

    DOUBLE speed = 0.0;
    if (HmcDictGetDouble(dict, DICT_KEY_ASSET_PROPERTY_SPEED, &speed) == HMC_OK) {
        LOGI("set asset speed to: %f", speed);
        m_speed = speed;
    }

    HmcUid materialUid = HMC_UID_NULL;
    if (HmcDictGetUid(dict, DICT_KEY_ASSET_PROPERTY_MATERIAL_UID, &materialUid) == HMC_OK) {
        LOGI("get uid of material from dict success");
        m_materialUid = materialUid;
    }

    auto cloudId = HmcDictGetString(dict, DICT_KEY_ASSET_PROPERTY_CLOUD_ID);
    if (cloudId) {
        LOGI("get asset cloud Id : %s", cloudId);
        m_cloudContentId = cloudId;
    }

    auto assetName = HmcDictGetString(dict, DICT_KEY_ASSET_PROPERTY_NAME);
    if (assetName) {
        LOGI("set asset name to: %s", assetName);
        m_name = assetName;
    } else {
        SetNameFromPath();
    }
}

BOOL IHmcAsset::IsDrawable(INT64 time) const
{
    // 如果剪辑的最后一帧为主轨道结尾，该帧需要显示，其它场景，不显示
    INT64 endTime = 0;
    m_eventHandler->OnGetData(HMC::GET_DATA_TIMELINE_END_TIME, nullptr, &endTime);
    if ((GetEndTime() + 1) == endTime) {
        if (time >= m_complexStartTime && time <= endTime) {
            return TRUE;
        }
    } else {
        if (time >= m_complexStartTime && time <= (GetEndTime())) {
            return TRUE;
        }
    }

    return FALSE;
}

int32_t IHmcAsset::PackGraphicsRenderInfo(uint64_t timestamp, std::shared_ptr<VideoRenderInfo> &renderInfo,
    bool exactMode)
{
    HMC_UNUSED(timestamp);
    HMC_UNUSED(renderInfo);
    HMC_UNUSED(exactMode);
    return HMC_OK;
}

HmcTimeLinePosition IHmcAsset::isTimelineBetweenAsset(INT64 timeline) const
{
    INT64 endTime = GetEndTime();
    if (m_complexStartTime > endTime) {
        return HMC_TIMELINE_INVALID_ASSET;
    }

    if (timeline < m_complexStartTime) {
        return HMC_TIMELINE_NOT_BETWEEN_NEAR_HEAD;
    } else if (timeline > endTime) {
        return HMC_TIMELINE_NOT_BETWEEN_NEAR_TAIL;
    } else {
        HmcTimeLinePosition position = timeline - m_complexStartTime <= endTime - timeline ?
            HMC_TIMELINE_BETWEEN_NEAR_HEAD :
            HMC_TIMELINE_BETWEEN_NEAR_TAIL;
        return position;
    }
}

STRING IHmcAsset::GetOrientation() const { return m_orientation; }

STRING IHmcAsset::GetShotDate() const { return m_shotDate; }

STRING IHmcAsset::GetShotParam() const { return m_shotParam; }

STRING IHmcAsset::GetShotSignFont() const { return m_shotSignFont; }

VECTOR<INT32> IHmcAsset::GetExifXtStyleParam() const { return m_exifXtStyleParam; }

INT32 IHmcAsset::IsXtStyleForceOn() const
{
    return (m_exifXtStyleParam[0] == 0 &&
             m_exifSourceXmageColorMode == 0) ? 1:0;
}

UINT32 IHmcAsset::GetExifXmageColorMode() const { return m_exifSourceXmageColorMode; }