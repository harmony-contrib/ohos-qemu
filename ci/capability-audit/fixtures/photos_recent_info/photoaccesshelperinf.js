/*
 * Copyright (c) 2023-2024 Huawei Device Co., Ltd.
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

const photoAccessHelper = requireNapi('file.photoAccessHelperNative');
const bundleManager = requireNapi('bundle.bundleManager');
const deviceinfo = requireInternal('deviceInfo');
const rpc = requireInternal('rpc');

const ARGS_ZERO = 0;
const ARGS_ONE = 1;
const ARGS_TWO = 2;
const ARGS_THREE = 3;

const WRITE_PERMISSION = 'ohos.permission.WRITE_IMAGEVIDEO';
const ACROSS_ACCOUNTS_PERMISSION = 'ohos.permission.INTERACT_ACROSS_LOCAL_ACCOUNTS';

const PERMISSION_DENIED = 13900012;
const ERR_CODE_PARAMERTER_INVALID = 13900020;
const ERR_CODE_OHOS_PERMISSION_DENIED = 201;
const ERR_CODE_OHOS_PARAMERTER_INVALID = 401;
const REQUEST_CODE_SUCCESS = 0;
const PERMISSION_STATE_ERROR = -1;
const ERROR_MSG_WRITE_PERMISSION = 'not have ohos.permission.WRITE_IMAGEVIDEO';
const ERROR_MSG_ACROSS_ACCOUNTS_PERMISSION = 'not have ohos.permission.INTERACT_ACROSS_LOCAL_ACCOUNTS';
const ERROR_MSG_USER_DENY = 'user deny';
const ERROR_MSG_PARAMERTER_INVALID = 'input parmaeter invalid';
const ERROR_MSG_INNER_FAIL = 'System inner fail';
const ERROR_MSG_OHOS_INNER_FAIL = 'Internal system error';
const ERROR_MSG_OHOS_NO_PERMISSION = 'Permission denied';
const PARAMETERS_VALIDATE_FAILED_MESSAGE = 
'Scene parameters validate failed, possible causes:' +
'  1. An invalid enumeration value was passed. Only MOVING_PHOTO_ENABLE and' +
'  MOVING_PHOTO_DISABLE are supported for globalMovingPhotoState;' +
'  2. The elements of the array can only be \'image/heic\' or \'image/jpeg\',' +
'  and the array length cannot be greater than two for supportedMimeType;';
const GET_BUNDLE_INFO_FAIL = 'Failed to get bundle info';

const PARAMETERS_VALIDATE_FAILED_CODE = 23800151;

const SECONDS_OF_ONE_DAY = 24 * 60 * 60;
const DELAY_MILLSECONDS = 33;
const RETRY_COUNTER = 10;
const RPC_TOKEN_RECENT_PHOTO_INFO = 'rpcRecentPhotoInfoServiceAbility';
const RPC_MSGID_RECENT_PHOTO_INFO = 1;

const MAX_DELETE_NUMBER = 300;
const MIN_DELETE_NUMBER = 1;
const MAX_CONFIRM_NUMBER = 100;
const MIN_CONFIRM_NUMBER = 1;

let gContext = undefined;

class BusinessError extends Error {
  constructor(msg, code) {
    super(msg);
    this.code = code || PERMISSION_DENIED;
  }
}

function checkArrayAndSize(array, minSize, maxSize) {
  // check whether input is array
  if (!Array.isArray(array)) {
    console.error('photoAccessHelper invalid, array is null.');
    return false;
  }

  // check whether array length is valid
  let len = array.length;
  if ((len < minSize) || (len > maxSize)) {
    console.error('photoAccessHelper invalid, array size invalid.');
    return false;
  }

  return true;
}

function checkIsUriValid(uri, isAppUri) {
  if (!uri) {
    console.error('photoAccessHelper invalid, uri is null.');
    return false;
  }

  if (typeof uri !== 'string') {
    console.error('photoAccessHelper invalid, uri type is not string.');
    return false;
  }

  // media library uri starts with 'file://media/Photo/', createDeleteReques delete media library resource should check
  if (!isAppUri) {
    return uri.includes('file://media/Photo/');
  }

  // showAssetsCreationDialog store third part application resource to media library, no need to check it
  return true;
}

function checkParams(uriList, asyncCallback) {
  if (arguments.length > ARGS_TWO) {
    return false;
  }
  if (!checkArrayAndSize(uriList, MIN_DELETE_NUMBER, MAX_DELETE_NUMBER)) {
    return false;
  }
  if (asyncCallback && typeof asyncCallback !== 'function') {
    return false;
  }
  for (let uri of uriList) {
    if (!checkIsUriValid(uri, false)) {
      console.info(`photoAccessHelper invalid uri: ${uri}`);
      return false;
    }
  }
  return true;
}
function errorResult(rej, asyncCallback) {
  if (asyncCallback) {
    return asyncCallback(rej);
  }
  return new Promise((resolve, reject) => {
    reject(rej);
  });
}

function getAbilityResource(bundleInfo) {
  console.info('getAbilityResource enter.');
  let labelId = 0;
  for (let hapInfo of bundleInfo.hapModulesInfo) {
    if (hapInfo.type === bundleManager.ModuleType.ENTRY) {
      labelId = getLabelId(hapInfo);
    }
  }
  return labelId;
}

function getLabelId(hapInfo) {
  let labelId = 0;
  for (let abilityInfo of hapInfo.abilitiesInfo) {
    let abilitiesInfoName = '';
    if (abilityInfo.name.includes('.')) {
      let abilitiesInfoLength = abilityInfo.name.split('.').length;
      abilitiesInfoName = abilityInfo.name.split('.')[abilitiesInfoLength - 1];
    } else {
      abilitiesInfoName = abilityInfo.name;
    }
    if (abilitiesInfoName === hapInfo.mainElementName) {
      labelId = abilityInfo.labelId;
    }
  }
  return labelId;
}

async function getAppName() {
  let appName = '';
  try {
    const flags = bundleManager.BundleFlag.GET_BUNDLE_INFO_WITH_ABILITY | bundleManager.BundleFlag.GET_BUNDLE_INFO_WITH_HAP_MODULE;
    const bundleInfo = await bundleManager.getBundleInfoForSelf(flags);
    console.info(`photoAccessHelper bundleInfo: ${JSON.stringify(bundleInfo)}`);
    if (bundleInfo === undefined || bundleInfo.hapModulesInfo === undefined || bundleInfo.hapModulesInfo.length === 0) {
      return appName;
    }
    const labelId = getAbilityResource(bundleInfo);
    const resourceMgr = gContext.resourceManager;
    appName = await resourceMgr.getStringValue(labelId);
    console.info(`photoAccessHelper appName: ${appName}`);
  } catch (error) {
    console.info(`photoAccessHelper error: ${JSON.stringify(error)}`);
  }

  return appName;
}

async function createPhotoDeleteRequestParamsOk(uriList, asyncCallback) {
  let flags = bundleManager.BundleFlag.GET_BUNDLE_INFO_WITH_REQUESTED_PERMISSION;
  let { reqPermissionDetails, permissionGrantStates } = await bundleManager.getBundleInfoForSelf(flags);
  let permissionIndex = -1;
  for (let i = 0; i < reqPermissionDetails.length; i++) {
    if (reqPermissionDetails[i].name === WRITE_PERMISSION) {
      permissionIndex = i;
    }
  }
  if (permissionIndex < 0 || permissionGrantStates[permissionIndex] === PERMISSION_STATE_ERROR) {
    console.info('photoAccessHelper permission error');
    return errorResult(new BusinessError(ERROR_MSG_WRITE_PERMISSION), asyncCallback);
  }
  const appName = await getAppName();
  if (appName.length === 0) {
    console.info(`photoAccessHelper appName not found`);
    return errorResult(new BusinessError(ERROR_MSG_PARAMERTER_INVALID, ERR_CODE_PARAMERTER_INVALID), asyncCallback);
  }
  try {
    if (asyncCallback) {
      return photoAccessHelper.createDeleteRequest(getContext(this), appName, uriList, result => {
        if (result.result === REQUEST_CODE_SUCCESS) {
          asyncCallback();
        } else if (result.result === PERMISSION_DENIED) {
          asyncCallback(new BusinessError(ERROR_MSG_USER_DENY));
        } else {
          asyncCallback(new BusinessError(ERROR_MSG_INNER_FAIL, result.result));
        }
      });
    } else {
      return new Promise((resolve, reject) => {
        photoAccessHelper.createDeleteRequest(getContext(this), appName, uriList, result => {
          if (result.result === REQUEST_CODE_SUCCESS) {
            resolve();
          } else if (result.result === PERMISSION_DENIED) {
            reject(new BusinessError(ERROR_MSG_USER_DENY));
          } else {
            reject(new BusinessError(ERROR_MSG_INNER_FAIL, result.result));
          }
        });
      });
    }
  } catch (error) {
    return errorResult(new BusinessError(error.message, error.code), asyncCallback);
  }
}

function createDeleteRequest(...params) {
  if (!checkParams(...params)) {
    throw new BusinessError(ERROR_MSG_PARAMERTER_INVALID, ERR_CODE_PARAMERTER_INVALID);
  }
  return createPhotoDeleteRequestParamsOk(...params);
}

function checkIsPhotoCreationConfigValid(config) {
  if (!config) {
    console.error('photoAccessHelper invalid, config is null.');
    return false;
  }

  // check whether input is a object
  if (typeof config !== 'object') {
    console.error('photoAccessHelper invalid, config type is not object.');
    return false;
  }

  // check whether title is string if exsit
  if ((config.title) && (typeof config.title !== 'string')) {
    console.error('photoAccessHelper invalid, config.title type is not string.');
    return false;
  }

  // check whether fileNameExtension is string
  if (!config.fileNameExtension) {
    console.error('photoAccessHelper invalid, config.fileNameExtension is null.');
    return false;
  }
  if (typeof config.fileNameExtension !== 'string') {
    console.error('photoAccessHelper invalid, config.fileNameExtension type is not string.');
    return false;
  }

  // check whether photoType is number
  if (!config.photoType) {
    console.error('photoAccessHelper invalid, config.photoType is null.');
    return false;
  }
  if (typeof config.photoType !== 'number') {
    console.error('photoAccessHelper invalid, config.photoType type is not number.');
    return false;
  }

  // check whether subtype is number if exsit
  if ((config.subtype) && (typeof config.subtype !== 'number')) {
    console.error('photoAccessHelper invalid, config.subtype type is not number.');
    return false;
  }

  return true;
}

function checkConfirmBoxParams(srcFileUris, photoCreationConfigs, isImageFullyDisplayed) {
  // check param number
  if (arguments.length < ARGS_TWO || arguments.length > ARGS_THREE) {
    return 'Invalid parameter number, expected 2 or 3 parameters.';
  }
  // check whether input array is valid
  if (!checkArrayAndSize(srcFileUris, MIN_CONFIRM_NUMBER, MAX_CONFIRM_NUMBER)) {
    return `srcFileUris must be an array with size between ${MIN_CONFIRM_NUMBER} and ${MAX_CONFIRM_NUMBER}.`;
  }
  if (!checkArrayAndSize(photoCreationConfigs, MIN_CONFIRM_NUMBER, MAX_CONFIRM_NUMBER)) {
    return `photoCreationConfigs must be an array with size between ${MIN_CONFIRM_NUMBER} and ${MAX_CONFIRM_NUMBER}.`;
  }
  if (srcFileUris.length !== photoCreationConfigs.length) {
    return 'srcFileUris and photoCreationConfigs must have the same length';
  }
  // check whether srcFileUris element is valid
  for (let i = 0; i < srcFileUris.length; i++) {
    if (!checkIsUriValid(srcFileUris[i], true)) {
      console.error('photoAccessHelper invalid uri: ${srcFileUri}.');
      return encrypt(`Invalid uri at srcFileUris[${i}]: ${srcFileUris[i]}.`);
    }
  }
  // check whether photoCreationConfigs element is valid
  for (let i = 0; i < photoCreationConfigs.length; i++) {
    if (!checkIsPhotoCreationConfigValid(photoCreationConfigs[i])) {
      return `Invalid photoCreationConfig at index ${i}.`;
    }
  }
  if (isImageFullyDisplayed !== undefined) {
    if (typeof isImageFullyDisplayed !== 'boolean') {
      console.error('photoAccessHelper isImageFullyDisplayed must be boolean if provided.');
      return 'isImageFullyDisplayed must be boolean if provided.';
    }
  }
  return undefined;
}

function getBundleInfo() {
  let flags = bundleManager.BundleFlag.GET_BUNDLE_INFO_WITH_ABILITY | // for appName
    bundleManager.BundleFlag.GET_BUNDLE_INFO_WITH_HAP_MODULE | // for appName
    bundleManager.BundleFlag.GET_BUNDLE_INFO_WITH_SIGNATURE_INFO | // for appId
    bundleManager.BundleFlag.GET_BUNDLE_INFO_WITH_APPLICATION; // for appInfo
  let bundleInfo = bundleManager.getBundleInfoForSelfSync(flags);
  if (((bundleInfo === undefined) || (bundleInfo.name === undefined)) ||
      ((bundleInfo.hapModulesInfo === undefined) || (bundleInfo.hapModulesInfo.length === 0)) ||
      ((bundleInfo.signatureInfo === undefined) || (bundleInfo.signatureInfo.appId === undefined)) ||
    ((bundleInfo.appInfo === undefined) || (bundleInfo.appInfo.labelId === 0))) {
    console.error('photoAccessHelper failed to get bundle info.');
    return undefined;
  }

  return bundleInfo;
}

function showAssetsCreationDialogResult(result, reject, resolve) {
  console.log('showAssetsCreationDialogResult is' + result.result);
  if (result.result !== REQUEST_CODE_SUCCESS) {
    if (result.result === ERR_CODE_OHOS_PERMISSION_DENIED) {
      reject(new BusinessError(ERROR_MSG_OHOS_NO_PERMISSION, result.result));
    } else {
      reject(new BusinessError(ERROR_MSG_OHOS_INNER_FAIL, result.result));
    }
  }

  if (result.data === undefined) {
    result.data = [];
  }

  resolve(result.data);
}

async function showAssetsCreationDialogParamsOk(srcFileUris, photoCreationConfigs, isImageFullyDisplayed = false) {
  let bundleInfo = getBundleInfo();
  if (bundleInfo === undefined) {
    return new Promise((resolve, reject) => {
      reject(new BusinessError(GET_BUNDLE_INFO_FAIL, ERR_CODE_OHOS_PARAMERTER_INVALID));
    });
  }

  // get bundleName and appId and appName
  let bundleName = bundleInfo.name;
  let appId = bundleInfo.signatureInfo.appId;
  console.info('photoAccessHelper bundleName is ' + bundleName + '.');
  console.info('photoAccessHelper appId is ' + appId + '.');

  let labelId = bundleInfo.appInfo.labelId;
  console.info('photoAccessHelper labelId is ' + appId + '.');
  let appName = '';

  try {
    let modeleName = '';
    for (let hapInfo of bundleInfo.hapModulesInfo) {
      if (labelId === hapInfo.labelId) {
        modeleName = hapInfo.name;
      }
    }
    console.info('photoAccessHelper modeleName is ' + modeleName + '.');
    appName = await gContext.createModuleContext(modeleName).resourceManager.getStringValue(labelId);
    console.info('photoAccessHelper appName is ' + appName + '.');
    // only promise type
    return new Promise((resolve, reject) => {
      photoAccessHelper.showAssetsCreationDialog(getContext(this), srcFileUris, photoCreationConfigs, bundleName,
        appName, appId, result => {
          showAssetsCreationDialogResult(result, reject, resolve);
      }, isImageFullyDisplayed);
    });
  } catch (error) {
    return errorResult(new BusinessError(error.message, error.code), null);
  }
}

async function showSingleAssetCreationDialogEx(srcFileUri, photoCreationConfigs, isImageFullyDisplayed) {
  const displayFlag = isImageFullyDisplayed !== undefined ? isImageFullyDisplayed : false;
  const uris = await showAssetsCreationDialog([srcFileUri], [photoCreationConfigs], displayFlag);
  if (!uris || uris.length === 0) {
    return undefined;
  }
  return uris[0];
}

function showAssetsCreationDialogEx(srcFileUri, photoCreationConfigs) {
  return showAssetsCreationDialog(srcFileUri, photoCreationConfigs, false);
}

function showAssetsCreationDialog(...params) {
  let checkConfigResult = checkConfirmBoxParams(...params);
  if (checkConfigResult !== undefined) {
    throw new BusinessError(checkConfigResult, ERR_CODE_OHOS_PARAMERTER_INVALID);
  }
  return showAssetsCreationDialogParamsOk(...params);
}

async function requestPhotoUrisReadPermission(srcFileUris) {
  console.info('requestPhotoUrisReadPermission enter');

  //check whether srcFileUris is valid
  if (srcFileUris === undefined || srcFileUris.length < MIN_CONFIRM_NUMBER) {
    console.error('photoAccessHelper invalid, array size invalid.');
    return false;
  }
  for (let srcFileUri of srcFileUris) {
    if (!checkIsUriValid(srcFileUri, true)) {
      console.error('photoAccesshelper invalid uri : ${srcFileUri}.');
      return false;
    }
  }

  let context = gContext;
  if (context === undefined) {
    console.info('photoAccessHelper gContet undefined');
    context = getContext(this);
  }

  let bundleInfo = getBundleInfo();
  if (bundleInfo === undefined) {
    return new Promise((resolve, reject) => {
      reject(new BusinessError(ERROR_MSG_PARAMERTER_INVALID, ERR_CODE_OHOS_PARAMERTER_INVALID));
    });
  }
  let labelId = bundleInfo.appInfo.labelId;
  console.info('photoAccessHelper labelId is ' + labelId + '.');
  let appName = '';

  try {
    let moduleName = '';
    for (let hapInfo of bundleInfo.hapModulesInfo) {
      if (labelId === hapInfo.labelId) {
        moduleName = hapInfo.name;
      }
    }
    console.info('photoAccessHelper moduleName is ' + moduleName + '.');
    appName = await gContext.createModuleContext(moduleName).resourceManager.getStringValue(labelId);
    console.info('photoAccessHelper appName is ' + appName + '.');
    return new Promise((resolve, reject) => {
      photoAccessHelper.requestPhotoUrisReadPermission(context, srcFileUris, appName, result => {
        showAssetsCreationDialogResult(result, reject, resolve);
      });
    });
  } catch (error) {
    console.error('requestPhotoUrisReadPermission catch error.');
    return errorResult(new BusinessError(ERROR_MSG_INNER_FAIL, error.code), null);
  }
}

async function requestPhotoUrisReadPermissionEx(srcFileUris) {
  console.info('requestPhotoUrisReadPermissionEx enter');
 
  //check whether srcFileUris is valid
  if (srcFileUris === undefined || srcFileUris.length < MIN_CONFIRM_NUMBER) {
    console.error('photoAccessHelper invalid, array size invalid.');
    return false;
  }
  for (let srcFileUri of srcFileUris) {
    if (!checkIsUriValid(srcFileUri, true)) {
      console.error('photoAccesshelper invalid uri : ${srcFileUri}.');
      return false;
    }
  }
 
  let context = gContext;
  if (context === undefined) {
    console.info('photoAccessHelper gContet undefined');
    context = getContext(this);
  }
 
  let bundleInfo = getBundleInfo();
  if (bundleInfo === undefined) {
    return new Promise((resolve, reject) => {
      reject(new BusinessError(ERROR_MSG_PARAMERTER_INVALID, ERR_CODE_OHOS_PARAMERTER_INVALID));
    });
  }
  let labelId = bundleInfo.appInfo.labelId;
  console.info('photoAccessHelper labelId is ' + labelId + '.');
  let appName = '';
 
  try {
    let moduleName = '';
    for (let hapInfo of bundleInfo.hapModulesInfo) {
      if (labelId === hapInfo.labelId) {
        moduleName = hapInfo.name;
      }
    }
    console.info('photoAccessHelper moduleName is ' + moduleName + '.');
    appName = await gContext.createModuleContext(moduleName).resourceManager.getStringValue(labelId);
    console.info('photoAccessHelper appName is ' + appName + '.');
    return new Promise((resolve, reject) => {
      photoAccessHelper.requestPhotoUrisReadPermissionEx(context, srcFileUris, appName, result => {
        showAssetsCreationDialogResult(result, reject, resolve);
      });
    });
  } catch (error) {
    console.error('requestPhotoUrisReadPermissionEx catch error.');
    return errorResult(new BusinessError(ERROR_MSG_INNER_FAIL, error.code), null);
  }
}

async function createAssetWithShortTermPermissionOk(photoCreationConfig) {
  let bundleInfo = getBundleInfo();
  if (bundleInfo === undefined) {
    return new Promise((resolve, reject) => {
      reject(new BusinessError(ERROR_MSG_PARAMERTER_INVALID, ERR_CODE_OHOS_PARAMERTER_INVALID));
    });
  }

  let bundleName = bundleInfo.name;
  let appId = bundleInfo.signatureInfo.appId;
  console.info('photoAccessHelper bundleName is ' + bundleName + '.');
  console.info('photoAccessHelper appId is ' + appId + '.');

  let labelId = bundleInfo.appInfo.labelId;
  console.info('photoAccessHelper labelId is ' + appId + '.');
  let appName = '';
  let tokenId = bundleInfo.appInfo.accessTokenId;
  console.info('photoAccessHelper tokenId is ' + tokenId + '.');
  
  try {
    let modeleName = '';
    for (let hapInfo of bundleInfo.hapModulesInfo) {
      if (labelId === hapInfo.labelId) {
        modeleName = hapInfo.name;
      }
    }
    console.info('photoAccessHelper modeleName is ' + modeleName + '.');
    appName = await gContext.createModuleContext(modeleName).resourceManager.getStringValue(labelId);
    console.info('photoAccessHelper appName is ' + appName + '.');

    if (photoAccessHelper.checkShortTermPermission()) {
      let photoCreationConfigs = [photoCreationConfig];
      let desFileUris = await getPhotoAccessHelper(getContext(this)).createAssetsHasPermission(bundleName, appName, tokenId,
        photoCreationConfigs);
      return new Promise((resolve, reject) => {
        resolve(desFileUris[0]);
      });
    }
    return new Promise((resolve, reject) => {
      photoAccessHelper.createAssetWithShortTermPermission(getContext(this), photoCreationConfig, bundleName, appName,
        appId, result => {
          showAssetsCreationDialogResult(result, reject, resolve);
        });
    });
  } catch (error) {
    return errorResult(new BusinessError(ERROR_MSG_INNER_FAIL, error.code), null);
  }
}

function createAssetWithShortTermPermission(photoCreationConfig) {
  if (!checkIsPhotoCreationConfigValid(photoCreationConfig)) {
    throw new BusinessError(ERROR_MSG_PARAMERTER_INVALID, ERR_CODE_OHOS_PARAMERTER_INVALID);
  }
  return createAssetWithShortTermPermissionOk(photoCreationConfig);
}

function getPhotoPickerComponentDefaultAlbumName() {
  let bundleInfo = getBundleInfo();
  if (bundleInfo === undefined) {
    return new Promise((resolve, reject) => {
      reject(new BusinessError(ERROR_MSG_PARAMERTER_INVALID, ERR_CODE_OHOS_PARAMERTER_INVALID));
    });
  }
  
  try {
    return new Promise((resolve, reject) => {
      photoAccessHelper.getPhotoPickerComponentDefaultAlbumName(getContext(this), result => {
          showAssetsCreationDialogResult(result, reject, resolve);
        });
    });
  } catch (error) {
    return errorResult(new BusinessError(ERROR_MSG_INNER_FAIL, error.code), null);
  }
}

async function delayFunc() {
  return new Promise(resolve => setTimeout(resolve, DELAY_MILLSECONDS));
}

function convertMIMETypeToFilterType(e) {
    let o;
    if (e === PhotoViewMIMETypes.IMAGE_TYPE) {
        o = PHOTO_VIEW_MIME_TYPE_MAP.get(e);
    } else if (e === PhotoViewMIMETypes.VIDEO_TYPE) {
        o = PHOTO_VIEW_MIME_TYPE_MAP.get(e);
    } else if (e === PhotoViewMIMETypes.MOVING_PHOTO_IMAGE_TYPE) {
        o = PHOTO_VIEW_MIME_TYPE_MAP.get(e);
    } else {
        o = PHOTO_VIEW_MIME_TYPE_MAP.get(PhotoViewMIMETypes.IMAGE_VIDEO_TYPE);
    }
    console.info('convertMIMETypeToFilterType: ' + JSON.stringify(o));
    return o;
}

function checkIsRecentPhotoOptionValid(option) {
  if (!option) {
    console.error('photoAccessHelper invalid, option is null.');
    return false;
  }
  // check whether input type is object
  if (typeof option !== 'object') {
    console.error('photoAccessHelper invalid, option type is not object.');
    return false;
  }
  // check whether period is number when it exist
  if (!option.period) {
    option.period = SECONDS_OF_ONE_DAY;
  }
  if (typeof option.period !== 'number') {
    console.error('photoAccessHelper invalid, option.period type is not number.');
    return false;
  }
  if (option.period <= 0 || option.period > SECONDS_OF_ONE_DAY) {
    option.period = SECONDS_OF_ONE_DAY;
  }
  // check whether MIMEType is PhotoViewMIMETypes
  if (!option.MIMEType) {
    option.MIMEType = PhotoViewMIMETypes.IMAGE_VIDEO_TYPE;
  }
  if (typeof option.MIMEType !== 'string') {
    console.error('photoAccessHelper invalid, option.MIMEType is not string.');
    return false;
  }
  // convert MIMEType string
  option.MIMEType = convertMIMETypeToFilterType(option.MIMEType);
  const PhotoSource = {
    ALL: 0,
    CAMERA: 1,
    SCREENSHOT: 2
  };
  // check whether photoSource valid
  if (!option.photoSource) {
    option.photoSource = PhotoSource.ALL;
  }
  if (typeof option.photoSource !== 'number') {
    console.error('photoAccessHelper invalid, option.photoSource is not number');
    return false;
  }
  if (option.photoSource < PhotoSource.ALL || option.photoSource > PhotoSource.SCREENSHOT) {
    option.photoSource = PhotoSource.ALL;
  }
  return true;
}

async function rpcGetRecentPhotoInfoGetProxy() {
  let proxy = undefined;
  let want = {
    'bundleName': 'com.ohos.photos',
    'abilityName': 'RecentPhotoInfoAbility'
  };
  let connect = {
    onConnect: (elementName, remoteProxy) => {
      console.info('RpcClient: js onConnect called');
      proxy = remoteProxy;
    },
    onDisconnect: (elementName) => {
      console.info('RpcClient: onDisconnect');
    },
    onFailed: () => {
      console.info('RpcClient: onFailed');
    }
  };
  let context = gContext;
  if (context === undefined) {
    console.info('photoAccessHelper gContext undefined.');
    context = getContext(this);
  }
  try {
    let connectId = context.connectServiceExtensionAbility(want, connect);
    let retryConter = RETRY_COUNTER;
    while (proxy === undefined) {
      retryConter -= 1;
      if (retryConter < 0) {
        break;
      }
      await delayFunc();
    }
  } catch (error) {
    console.error('rpcGetRecentPhotoInfo Error: ' + error);
  }
  return proxy;
}

async function rpcGetRecentPhotoInfo(recentPhotoOption) {
  let proxy = await rpcGetRecentPhotoInfoGetProxy();
  if (proxy === undefined) {
    console.error('rpcGetRecentPhotoInfo proxy is undefined');
    return undefined;
  }
  let option = new rpc.MessageOption();
  let data = rpc.MessageSequence.create();
  let reply = rpc.MessageSequence.create();
  try { // rpc Request
    data.writeInterfaceToken(RPC_TOKEN_RECENT_PHOTO_INFO);
    data.writeInt(recentPhotoOption.period);
    data.writeString(recentPhotoOption.MIMEType);
    data.writeInt(recentPhotoOption.photoSource);
    let result = await proxy.sendMessageRequest(RPC_MSGID_RECENT_PHOTO_INFO, data, reply, option);
    if (result.errCode !== 0) {
      console.error('rpcGetRecentPhotoInfo sendMessageRequest failed, errCode: ' + result.errCode);
      return undefined;
    }
    let dateTaken = result.reply.readLong();
    let identifier = result.reply.readString();
    console.info('rpcGetRecentPhotoInfo sendMessageRequest succ, result: ' + dateTaken);
    return {'dateTaken': dateTaken, 'identifier': identifier};
  } catch (err) {
    console.error('rpcGetRecentPhotoInfo sendMessageRequest failed: ' + err);
    return undefined;
  } finally {
    data.reclaim();
    reply.reclaim();
  }
}

async function getRecentPhotoInfoOk(recentPhotoOption) {
  try {
    console.info('getRecentPhotoInfoOk enter');
    let photoInfo = rpcGetRecentPhotoInfo(recentPhotoOption);
    if (!photoInfo) {
      photoInfo = { dateTaken: -1, identifier: '-1' };
    }
    if (photoInfo.dateTaken === 0) {
      photoInfo.identifier = '0';
    }
    console.info('recentPhotoInfo result: ' + photoInfo.identifier);
    return new Promise((resolve, reject) => {
      resolve(photoInfo);
    });
  } catch (error) {
    return errorResult(new BusinessError(ERROR_MSG_INNER_FAIL, error.code), null);
  }
}

function getRecentPhotoInfo(recentPhotoOption) {
  if (!checkIsRecentPhotoOptionValid(recentPhotoOption)) {
    throw new BusinessError(ERROR_MSG_PARAMERTER_INVALID, ERR_CODE_OHOS_PARAMERTER_INVALID);
  }
  return getRecentPhotoInfoOk(recentPhotoOption);
}

function getPhotoAccessHelper(context, userId = -1) {
  if (context === undefined) {
    console.log('photoAccessHelper gContext undefined');
    throw Error('photoAccessHelper gContext undefined');
  }
  gContext = context;
  let helper = photoAccessHelper.getPhotoAccessHelper(gContext, userId);
  if (helper !== undefined && helper.constructor.prototype.createDeleteRequest === undefined) {
    console.log('photoAccessHelper getPhotoAccessHelper inner add createDeleteRequest and showAssetsCreationDialog');
    helper.constructor.prototype.createDeleteRequest = createDeleteRequest;
    helper.constructor.prototype.showAssetsCreationDialog = showAssetsCreationDialog;
    helper.constructor.prototype.showAssetsCreationDialogEx = showAssetsCreationDialogEx;
    helper.constructor.prototype.showSingleAssetCreationDialogEx = showSingleAssetCreationDialogEx;
    helper.constructor.prototype.createAssetWithShortTermPermission = createAssetWithShortTermPermission;
    helper.constructor.prototype.createAssetWithShortTermPermissionEx = createAssetWithShortTermPermission;
    helper.constructor.prototype.requestPhotoUrisReadPermission = requestPhotoUrisReadPermission;
    helper.constructor.prototype.requestPhotoUrisReadPermissionEx = requestPhotoUrisReadPermissionEx;
    helper.constructor.prototype.getPhotoPickerComponentDefaultAlbumName = getPhotoPickerComponentDefaultAlbumName;
    helper.constructor.prototype.getRecentPhotoInfo = getRecentPhotoInfo;
  }
  return helper;
}

function startPhotoPicker(context, config) {
  if (context === undefined) {
    console.log('photoAccessHelper gContext undefined');
    throw Error('photoAccessHelper gContext undefined');
  }
  if (config === undefined) {
    console.log('photoAccessHelper config undefined');
    throw Error('photoAccessHelper config undefined');
  }
  gContext = context;
  let helper = photoAccessHelper.startPhotoPicker(gContext, config);
  if (helper !== undefined) {
    console.log('photoAccessHelper startPhotoPicker inner add createDeleteRequest');
    helper.createDeleteRequest = createDeleteRequest;
  }
  return helper;
}

function getPhotoAccessHelperAsync(context, asyncCallback) {
  if (context === undefined) {
    console.log('photoAccessHelper gContext undefined');
    throw Error('photoAccessHelper gContext undefined');
  }
  gContext = context;
  if (arguments.length === 1) {
    return photoAccessHelper.getPhotoAccessHelperAsync(gContext)
      .then((helper) => {
        if (helper !== undefined) {
          console.log('photoAccessHelper getPhotoAccessHelperAsync inner add createDeleteRequest' +
            ' and showAssetsCreationDialog');
          helper.createDeleteRequest = createDeleteRequest;
          helper.showAssetsCreationDialog = showAssetsCreationDialog;
          helper.showAssetsCreationDialogEx = showAssetsCreationDialogEx;
          helper.showSingleAssetCreationDialogEx = showSingleAssetCreationDialogEx;
          helper.createAssetWithShortTermPermission = createAssetWithShortTermPermission;
          helper.createAssetWithShortTermPermissionEx = createAssetWithShortTermPermission;
          helper.requestPhotoUrisReadPermission = requestPhotoUrisReadPermission;
          helper.requestPhotoUrisReadPermissionEx = requestPhotoUrisReadPermissionEx;
          helper.getPhotoPickerComponentDefaultAlbumName = getPhotoPickerComponentDefaultAlbumName;
          helper.getRecentPhotoInfo = getRecentPhotoInfo;
        }
        return helper;
      })
      .catch((err) => {
        console.log('photoAccessHelper getPhotoAccessHelperAsync err ' + err);
        throw Error(err);
      });
  } else if (arguments.length === ARGS_TWO && typeof asyncCallback === 'function') {
    photoAccessHelper.getPhotoAccessHelperAsync(gContext, (err, helper) => {
      console.log('photoAccessHelper getPhotoAccessHelperAsync callback ' + err);
      if (err) {
        asyncCallback(err);
      } else {
        if (helper !== undefined) {
          console.log('photoAccessHelper getPhotoAccessHelperAsync callback add createDeleteRequest' +
            ' and showAssetsCreationDialog');
          helper.createDeleteRequest = createDeleteRequest;
          helper.showAssetsCreationDialog = showAssetsCreationDialog;
          helper.showAssetsCreationDialogEx = showAssetsCreationDialogEx;
          helper.showSingleAssetCreationDialogEx = showSingleAssetCreationDialogEx;
          helper.createAssetWithShortTermPermission = createAssetWithShortTermPermission;
          helper.createAssetWithShortTermPermissionEx = createAssetWithShortTermPermission;
          helper.requestPhotoUrisReadPermission = requestPhotoUrisReadPermission;
          helper.requestPhotoUrisReadPermissionEx = requestPhotoUrisReadPermissionEx;
          helper.getPhotoPickerComponentDefaultAlbumName = getPhotoPickerComponentDefaultAlbumName;
          helper.getRecentPhotoInfo = getRecentPhotoInfo;
        }
        asyncCallback(err, helper);
      }
    });
  } else {
    console.log('photoAccessHelper getPhotoAccessHelperAsync param invalid');
    throw new BusinessError(ERROR_MSG_PARAMERTER_INVALID, ERR_CODE_OHOS_PARAMERTER_INVALID);
  }
  return undefined;
}

const RecommendationType = {
  // Indicates that QR code or barcode photos can be recommended
  QR_OR_BAR_CODE: 1,

  // Indicates that QR code photos can be recommended
  QR_CODE: 2,

  // Indicates that barcode photos can be recommended
  BAR_CODE: 3,

  // Indicates that QR code or barcode photos can be recommended
  ID_CARD: 4,

  // Indicates that profile picture photos can be recommended
  PROFILE_PICTURE: 5,

  // Indicates that passport photos can be recommended
  PASSPORT: 6,

  // Indicates that bank card photos can be recommended
  BANK_CARD: 7,

  // Indicates that driver license photos can be recommended
  DRIVER_LICENSE: 8,

  // Indicates that driving license photos can be recommended
  DRIVING_LICENSE: 9,

  // Indicates that featured single portrait photos can be recommended
  FEATURED_SINGLE_PORTRAIT: 10,

  // Indicates that cat photos can be recommended
  CAT: 13,

  // Indicates that dog photos can be recommended
  DOG: 14,

  // Indicates that architecture photos can be recommended
  ARCHITECTURE: 15,

  // Indicates that landscape photos can be recommended
  LANDSCAPE: 16,

  // Indicates that GAUSSIAN_SPLAT_3D photos can be recommended
  GAUSSIAN_SPLAT_3D: 17
};

const PhotoViewMIMETypes = {
  IMAGE_TYPE: 'image/*',
  VIDEO_TYPE: 'video/*',
  IMAGE_VIDEO_TYPE: '*/*',
  MOVING_PHOTO_IMAGE_TYPE: 'image/movingPhoto',
  JPEG_IMAGE_TYPE: 'image/jpeg',
  GIF_IMAGE_TYPE: 'image/gif',
  PNG_IMAGE_TYPE: 'image/png',
  HEIC_IMAGE_TYPE: 'image/heic',
  HEIF_IMAGE_TYPE: 'image/heif',
  BMP_IMAGE_TYPE: 'image/bmp',
  WEBP_IMAGE_TYPE: 'image/webp',
  AVIF_IMAGE_TYPE: 'image/avif',
  MP4_VIDEO_TYPE: 'video/mp4',
  MOV_VIDEO_TYPE: 'video/quicktime',
  INVALID_TYPE: ''
};

const FilterOperator = {
  INVALID_OPERATOR: -1,
  EQUAL_TO:  0,
  NOT_EQUAL_TO: 1,
  MORE_THAN: 2,
  LESS_THAN: 3,
  MORE_THAN_OR_EQUAL_TO:  4,
  LESS_THAN_OR_EQUAL_TO: 5,
  BETWEEN: 6,
};

const OperationType = {
  EQUAL_TO : 1,
  NOT_EQUAL_TO : 2,
  GREATER_THAN : 3,
  LESS_THAN : 4,
  GREATER_THAN_OR_EQUAL_TO : 5,
  LESS_THAN_OR_EQUAL_TO : 6,
  AND : 7,
  OR : 8,
  IN : 9,
  NOT_IN : 10,
  BEGIN_WRAP : 11,
  END_WRAP : 12,
  BETWEEN : 13,
  NOT_BETWEEN : 14
};

const ValidSupportedMimeType = {
  
  JPEG: 'image/jpeg',
  
  HEIF: 'image/heic'
};

const PickerFilterPhotoKeys = {
  
  URI: 'uri',
  
  PHOTO_TYPE: 'media_type',
  
  DISPLAY_NAME: 'display_name',
  
  SIZE: 'size',
  
  DURATION: 'duration',
  
  WIDTH: 'width',
  
  HEIGHT: 'height',
  
  ORIENTATION: 'orientation',
  
  FAVORITE: 'is_favorite',
  
  TITLE: 'title',
  
  POSITION: 'position',
  
  PHOTO_SUBTYPE: 'subtype',
  
  DYNAMIC_RANGE_TYPE: 'dynamic_range_type',
  
  COVER_POSITION: 'cover_position',
  
  BURST_KEY: 'burst_key',
  
  LCD_SIZE: 'lcd_size',
  
  THM_SIZE: 'thm_size',
  
  DETAIL_TIME: 'detail_time',
  
  OWNER_ALBUM_ID: 'owner_album_id',
  
  MEDIA_SUFFIX: 'media_suffix',
  
  ASPECT_RATIO: 'aspect_ratio',

  DATE_TAKEN_MS: 'date_taken_ms',
};

const PhotoSource = {
  ALL: 0,
  CAMERA: 1,
  SCREENSHOT: 2
};

const SingleSelectionMode = {
  BROWSER_MODE: 0,
  SELECT_MODE: 1,
  BROWSER_AND_SELECT_MODE: 2,
};

const PreferredCompatibleMode = {
  DEFAULT: 0,
  CURRENT: 1,
  COMPATIBLE: 2,
};

const SceneType = {
  GRID_TO_PHOTO_BROWSER: 0,
  PHOTO_BROWSER_SWIPE: 1
};

const PlayMode = {
  DEFAULT: 0,
  AUTO_PLAY: 1,
};

const ErrCode = {
  INVALID_ARGS: 13900020,
  RESULT_ERROR: 13900042,
  CONTEXT_NO_EXIST: 16000011,
};

const CompleteButtonText = {
  TEXT_DONE: 0,
  TEXT_SEND: 1,
  TEXT_ADD: 2,
};

const MovingPhotoBadgeStateType = {
  NOT_MOVING_PHOTO: 0,
  MOVING_PHOTO_ENABLED: 1,
  MOVING_PHOTO_DISABLED: 2,
};

const ERRCODE_MAP = new Map([
  [ErrCode.INVALID_ARGS, 'Invalid argument'],
  [ErrCode.RESULT_ERROR, 'Unknown error'],
  [ErrCode.CONTEXT_NO_EXIST, 'Current ability failed to obtain context'],
]);

const PHOTO_VIEW_MIME_TYPE_MAP = new Map([
  [PhotoViewMIMETypes.IMAGE_TYPE, 'FILTER_MEDIA_TYPE_IMAGE'],
  [PhotoViewMIMETypes.VIDEO_TYPE, 'FILTER_MEDIA_TYPE_VIDEO'],
  [PhotoViewMIMETypes.IMAGE_VIDEO_TYPE, 'FILTER_MEDIA_TYPE_ALL'],
  [PhotoViewMIMETypes.MOVING_PHOTO_IMAGE_TYPE, 'FILTER_MEDIA_TYPE_IMAGE_MOVING_PHOTO'],
  [PhotoViewMIMETypes.JPEG_IMAGE_TYPE, 'JPEG_IMAGE_TYPE'],
  [PhotoViewMIMETypes.GIF_IMAGE_TYPE, 'GIF_IMAGE_TYPE'],
  [PhotoViewMIMETypes.PNG_IMAGE_TYPE, 'PNG_IMAGE_TYPE'],
  [PhotoViewMIMETypes.HEIC_IMAGE_TYPE, 'HEIC_IMAGE_TYPE'],
  [PhotoViewMIMETypes.HEIF_IMAGE_TYPE, 'HEIF_IMAGE_TYPE'],
  [PhotoViewMIMETypes.BMP_IMAGE_TYPE, 'BMP_IMAGE_TYPE'],
  [PhotoViewMIMETypes.WEBP_IMAGE_TYPE, 'WEBP_IMAGE_TYPE'],
  [PhotoViewMIMETypes.AVIF_IMAGE_TYPE, 'AVIF_IMAGE_TYPE'],
  [PhotoViewMIMETypes.MP4_VIDEO_TYPE, 'MP4_VIDEO_TYPE'],
  [PhotoViewMIMETypes.MOV_VIDEO_TYPE, 'MOV_VIDEO_TYPE'],
]);

const GridPinchModeType = {
  FULL_FUNCTION_GRID: 0,
};
 	 
const GridLevel = {
  SPACIOUS: 0,
  STANDARD: 1,
  COMPACT: 2,
};

function checkArguments(args) {
  let checkArgumentsResult = undefined;

  if (args.length === ARGS_TWO && typeof args[ARGS_ONE] !== 'function') {
    checkArgumentsResult = getErr(ErrCode.INVALID_ARGS);
  }

  if (args.length > 0 && typeof args[ARGS_ZERO] === 'object') {
    let option = args[ARGS_ZERO];
    if (option.maxSelectNumber !== undefined) {
      if (option.maxSelectNumber.toString().indexOf('.') !== -1) {
        checkArgumentsResult = getErr(ErrCode.INVALID_ARGS);
      }
    }
  }

  return checkArgumentsResult;
}

function getErr(errCode) {
  return { code: errCode, message: ERRCODE_MAP.get(errCode) };
}

function parsePhotoPickerSelectOption(args) {
  let config = {
    action: 'ohos.want.action.photoPicker',
    type: 'multipleselect',
    parameters: {
      uri: 'multipleselect',
    },
  };

  if (args.length > ARGS_ZERO && typeof args[ARGS_ZERO] === 'object') {
    let option = args[ARGS_ZERO];
    if (option.maxSelectNumber && option.maxSelectNumber > 0) {
      let select = (option.maxSelectNumber === 1) ? 'singleselect' : 'multipleselect';
      config.type = select;
      config.parameters.uri = select;
      config.parameters.maxSelectCount = option.maxSelectNumber;
    }
    if (option.MIMEType && PHOTO_VIEW_MIME_TYPE_MAP.has(option.MIMEType)) {
      config.parameters.filterMediaType = PHOTO_VIEW_MIME_TYPE_MAP.get(option.MIMEType);
    }
    config.parameters.maxPhotoSelectNumber = option.maxPhotoSelectNumber;
    config.parameters.maxVideoSelectNumber = option.maxVideoSelectNumber;
    config.parameters.isSearchSupported = option.isSearchSupported === undefined || option.isSearchSupported;
    config.parameters.isPhotoTakingSupported = option.isPhotoTakingSupported === undefined || option.isPhotoTakingSupported;
    config.parameters.isEditSupported = option.isEditSupported === undefined || option.isEditSupported;
    config.parameters.recommendationOptions = option.recommendationOptions;
    config.parameters.assetCompatibleCapability = option.assetCompatibleCapability;
    config.parameters.preferredCompatibleMode = option.preferredCompatibleMode;
    config.parameters.preselectedUris = option.preselectedUris;
    config.parameters.isPreviewForSingleSelectionSupported = option.isPreviewForSingleSelectionSupported;
    config.parameters.singleSelectionMode = option.singleSelectionMode;
    config.parameters.isOriginalSupported = option.isOriginalSupported;
    config.parameters.contextRecoveryInfo = option.contextRecoveryInfo;
    config.parameters.subWindowName = option.subWindowName;
    config.parameters.globalMovingPhotoState = option.globalMovingPhotoState;
    config.parameters.themeColor = option.themeColor;
    config.parameters.completeButtonText = option.completeButtonText;
    config.parameters.userId = option.userId;
    config.parameters.mimeTypeFilter = parseMimeTypeFilter(option.mimeTypeFilter);
    config.parameters.fileSizeFilter = option.fileSizeFilter;
    config.parameters.videoDurationFilter = option.videoDurationFilter;
    config.parameters.photoViewMimeTypeFileSizeFilters = option.photoViewMimeTypeFileSizeFilters;
    config.parameters.combinedMediaTypeFilter = option.combinedMediaTypeFilter;
    config.parameters.isPc = deviceinfo.deviceType === '2in1';
    config.parameters.isMovingPhotoBadgeShown = option.isMovingPhotoBadgeShown;
    config.parameters.assetFilter = option.assetFilter;
    config.parameters.isDestroyedWithNavigation = option.isDestroyedWithNavigation;
    config.parameters.isReturnToPhotoBrowserEnabled = option.isReturnToPhotoBrowserEnabled;
    config.parameters.autoPlayScenes = parseAutoPlayScenes(option.autoPlayScenes);
    config.parameters.gridPinchMode = option.gridPinchMode;
    config.parameters.showDateOnScrollbar = option.showDateOnScrollbar;
    config.parameters.isSelectionNumberVisible = option.isSelectionNumberVisible;
    config.parameters.isSelectionOrderAdjustable = option.isSelectionOrderAdjustable;
  }

  return config;
}

function parseAutoPlayScenes(autoPlayScenes) {
  if (!autoPlayScenes) {
    return undefined;
  }

  if (autoPlayScenes.length > 2) {
    return autoPlayScenes.slice(0, 2);
  }

  return autoPlayScenes;
}

function parseMimeTypeFilter(filter) {
  if (!filter) {
      return undefined;
  }
  let o = {};
  o.mimeTypeArray = [];
  if (filter.mimeTypeArray) {
    for (let mimeType of filter.mimeTypeArray) {
      if (PHOTO_VIEW_MIME_TYPE_MAP.has(mimeType)) {
        o.mimeTypeArray.push(PHOTO_VIEW_MIME_TYPE_MAP.get(mimeType));
      } else {
        o.mimeTypeArray.push(mimeType);
      }
    }
  }
  return o;
}

function checkAssetFilterInvalid(assetFilter) {
  // 获取所有有效的值
  const validOperationTypes = Object.values(OperationType);
  const validPhotoKeys = Object.values(PickerFilterPhotoKeys);

  //遍历数组中的每个OperationItem
  for (const item of assetFilter) {
    //检查operationType是否有值且在枚举中
    if (!item.operationType || !validOperationTypes.includes(item.operationType)) {
      console.log('[picker] Invalid operationType');
      return true;
    }

    //如果field有值，检查是否在枚举中
    if (item.field !== undefined && item.field !== null) {
      if (!validPhotoKeys.includes(item.field)) {
        console.log('[picker] Invalid photokeys');
        return true;
      }
      // uri仅支持EQUAL_TO操作
      if (item.field === PickerFilterPhotoKeys.URI && item.operationType !== OperationType.EQUAL_TO) {
        console.log('[picker] Invalid uri operation');
        return true;
      }
    }
  }
  return false;
}

function checkGlobalMovingPhotoStateInvalid(globalMovingPhotoState) {
  return !(globalMovingPhotoState === MovingPhotoBadgeStateType.MOVING_PHOTO_ENABLED ||
    globalMovingPhotoState === MovingPhotoBadgeStateType.MOVING_PHOTO_DISABLED);
}

function checkAssetCompatibleCapabilityInvalid(assetCompatibleCapability) {
  if (assetCompatibleCapability.supportedMimeType === undefined) {
    return false;
  }
  let supportedMimeType = assetCompatibleCapability.supportedMimeType;
  if (supportedMimeType.length > 2) {
    return true;
  }

  const validSupportedMimeTypes = Object.values(ValidSupportedMimeType);

  for (let i = 0; i < supportedMimeType.length; i++) {
    if (!validSupportedMimeTypes.includes(supportedMimeType[i])) {
      return true;
    }
  }

  return false;
}

function getPhotoPickerSelectResult(args) {
  let selectResult = {
    error: undefined,
    data: undefined,
  };

  if (args.resultCode === 0) {
    let uris = args.uris;
    let isOrigin = args.isOrigin;
    let contextRecoveryInfo = args.contextRecoveryInfo;
    let movingPhotoBadgeStates = args.movingPhotoBadgeStates;
    let gridLevel = args.gridLevel;
    selectResult.data = new PhotoSelectResult(uris, isOrigin, contextRecoveryInfo, movingPhotoBadgeStates, gridLevel);
  } else if (args.resultCode === -1) {
    selectResult.data = new PhotoSelectResult([], undefined, undefined, undefined, undefined);
  } else {
    selectResult.error = getErr(ErrCode.RESULT_ERROR);
  }

  return selectResult;
}

async function photoPickerSelect(...args) {
  let checkArgsResult = checkArguments(args);
  if (checkArgsResult !== undefined) {
    console.log('[picker] Invalid argument');
    throw checkArgsResult;
  }

  const config = parsePhotoPickerSelectOption(args);
  console.log('[picker] config: ' + encrypt(JSON.stringify(config)));
  if (config.parameters.userId && config.parameters.userId > 0) {
    let check = await checkInteractAcrossLocalAccounts();
    if (!check) {
      console.log('[picker] error: ' + ERROR_MSG_ACROSS_ACCOUNTS_PERMISSION);
      return undefined;
    }
  }

  let assetFilter = config.parameters.assetFilter;
  if (assetFilter) {
    let isAssetFilterInvalid = checkAssetFilterInvalid(assetFilter);
    if (isAssetFilterInvalid) {
      console.error('[picker] config: assetFilter has value but invalid');
      throw new BusinessError(ERROR_MSG_PARAMERTER_INVALID, ERR_CODE_OHOS_PARAMERTER_INVALID);
    }
  }

  let context = undefined;

  let globalMovingPhotoState = config.parameters.globalMovingPhotoState;
  if (globalMovingPhotoState !== undefined) {
    let isGlobalMovingPhotoStateInvalid = checkGlobalMovingPhotoStateInvalid(globalMovingPhotoState);
    if (isGlobalMovingPhotoStateInvalid) {
      console.error('[picker] config: globalMovingPhotoState has value but invalid');
      throw new BusinessError(PARAMETERS_VALIDATE_FAILED_MESSAGE, PARAMETERS_VALIDATE_FAILED_CODE);
    }
  }
  
  let assetCompatibleCapability = config.parameters.assetCompatibleCapability;
  if (assetCompatibleCapability !== undefined) {
    let isAssetCompatibleCapabilityInvalid = checkAssetCompatibleCapabilityInvalid(assetCompatibleCapability);
    if (isAssetCompatibleCapabilityInvalid) {
      console.error('[picker] config: assetCompatibleCapability has value but invalid');
      throw new BusinessError(PARAMETERS_VALIDATE_FAILED_MESSAGE, PARAMETERS_VALIDATE_FAILED_CODE);
    }
  }
  
  try {
    context = getContext(this);
  } catch (getContextError) {
    console.error('[picker] getContext error: ' + getContextError);
    throw getErr(ErrCode.CONTEXT_NO_EXIST);
  }
  try {
    if (context === undefined) {
      throw getErr(ErrCode.CONTEXT_NO_EXIST);
    }
    let result = await startPhotoPicker(context, config);
    console.log('[picker] result: ' + encrypt(JSON.stringify(result)));
    const selectResult = getPhotoPickerSelectResult(result);
    console.log('[picker] selectResult: ' + encrypt(JSON.stringify(selectResult)));
    if (args.length === ARGS_TWO && typeof args[ARGS_ONE] === 'function') {
      return args[ARGS_ONE](selectResult.error, selectResult.data);
    } else if (args.length === ARGS_ONE && typeof args[ARGS_ZERO] === 'function') {
      return args[ARGS_ZERO](selectResult.error, selectResult.data);
    }
    return new Promise((resolve, reject) => {
      if (selectResult.data !== undefined) {
        resolve(selectResult.data);
      } else {
        reject(selectResult.error);
      }
    });
  } catch (error) {
    console.error('[picker] error: ' + JSON.stringify(error));
  }
  return undefined;
}

async function checkInteractAcrossLocalAccounts() {
  let flags = bundleManager.BundleFlag.GET_BUNDLE_INFO_WITH_REQUESTED_PERMISSION;
  let { reqPermissionDetails, permissionGrantStates } = await bundleManager.getBundleInfoForSelf(flags);
  let permissionIndex = -1;
  for (let i = 0; i < reqPermissionDetails.length; i++) {
    if (reqPermissionDetails[i].name === ACROSS_ACCOUNTS_PERMISSION) {
      permissionIndex = i;
    }
  }
  if (permissionIndex < 0 || permissionGrantStates[permissionIndex] === PERMISSION_STATE_ERROR) {
    return false;
  } else {
    return true;
  }
}

function GridPinchMode() {
  this.gridPinchModeType = undefined;
  this.defaultGridLevel = GridLevel.STANDARD;
}

function MimeTypeFilter() {
  this.mimeTypeArray = [];
}

function FileSizeFilter() {
  this.filterOperator = -1;
  this.fileSize = -1;
}

function VideoDurationFilter() {
  this.filterOperator = -1;
  this.videoDuration = -1;
}

function FileSizeFilterArray() {
  this.photoViewMimeTypeFileSizeFilters = [];
}

function OperationItem() {
  this.operationType = -1;
}

function BaseSelectOptions() {
  this.MIMEType = PhotoViewMIMETypes.INVALID_TYPE;
  this.maxSelectNumber = -1;
  this.maxPhotoSelectNumber = -1;
  this.maxVideoSelectNumber = -1;
  this.isSearchSupported = true;
  this.isPhotoTakingSupported = true;
  this.isPreviewForSingleSelectionSupported = true;
  this.singleSelectionMode = SingleSelectionMode.BROWSER_MODE;
  this.isMovingPhotoBadgeShown = false;
  this.autoPlayScenes = [];
}

function PhotoSelectOptions() {
  this.MIMEType = PhotoViewMIMETypes.INVALID_TYPE;
  this.maxSelectNumber = -1;
  this.isSearchSupported = true;
  this.isPhotoTakingSupported = true;
  this.isEditSupported = true;
  this.isOriginalSupported = false;
  this.completeButtonText = CompleteButtonText.TEXT_DONE;
  this.userId = -1;
  this.isDestroyedWithNavigation = false;
  this.isReturnToPhotoBrowserEnabled = false;
  this.isSelectionNumberVisible = false;
  this.isSelectionOrderAdjustable = false;
}

function PhotoSelectResult(uris, isOriginalPhoto, contextRecoveryInfo, movingPhotoBadgeStates, gridLevel) {
  this.photoUris = uris;
  this.isOriginalPhoto = isOriginalPhoto;
  this.contextRecoveryInfo = contextRecoveryInfo;
  this.movingPhotoBadgeStates = movingPhotoBadgeStates;
  this.gridLevel = gridLevel;
}

function PhotoViewPicker() {
  this.select = photoPickerSelect;
}

function RecommendationOptions() {
}

function AssetCompatibleCapability() {
}

function autoPlayScene() {
  this.sceneType = -1;
  this.playMode = -1;
}

function encrypt(data) {
  if (!data || data?.indexOf('file:///data/storage/') !== -1) {
    return '';
  }
  let encryptedData = data.replace(/(\/[\w()%+-]+)\./g, '/******.');
  encryptedData = encryptedData.replace(/"userComment":"([^"]|\")*"/g, '"userComment":"******"');
  encryptedData = encryptedData.replace(/"albumName":"([^"]|\")*"/g, '"albumName":"******"');
  encryptedData = encryptedData.replace(/"displayName":"([^"]|\")*"/g, '"displayName":"******"');
  return encryptedData;
}

class MediaAssetChangeRequest extends photoAccessHelper.MediaAssetChangeRequest {
  static deleteAssets(context, assets, asyncCallback) {
    if (arguments.length > ARGS_THREE || arguments.length < ARGS_TWO) {
      throw new BusinessError(ERROR_MSG_PARAMERTER_INVALID, ERR_CODE_OHOS_PARAMERTER_INVALID);
    }

    try {
      if (asyncCallback) {
        return super.deleteAssets(context, result => {
          if (result.result === REQUEST_CODE_SUCCESS) {
            asyncCallback();
          } else if (result.result === PERMISSION_DENIED) {
            asyncCallback(new BusinessError(ERROR_MSG_USER_DENY, ERR_CODE_OHOS_PERMISSION_DENIED));
          } else {
            asyncCallback(new BusinessError(ERROR_MSG_INNER_FAIL, result.result));
          }
        }, assets, asyncCallback);
      }

      return new Promise((resolve, reject) => {
        super.deleteAssets(context, result => {
          if (result.result === REQUEST_CODE_SUCCESS) {
            resolve();
          } else if (result.result === PERMISSION_DENIED) {
            reject(new BusinessError(ERROR_MSG_USER_DENY, ERR_CODE_OHOS_PERMISSION_DENIED));
          } else {
            reject(new BusinessError(ERROR_MSG_INNER_FAIL, result.result));
          }
        }, assets, (err) => {
          if (err) {
            reject(err);
          } else {
            resolve();
          }
        });
      });
    } catch (error) {
      return errorResult(new BusinessError(error.message, error.code), asyncCallback);
    }
  }
}

export default {
  getPhotoAccessHelper,
  startPhotoPicker,
  getPhotoAccessHelperAsync,
  FusionAssetType: photoAccessHelper.FusionAssetType,
  PhotoType: photoAccessHelper.PhotoType,
  ThumbnailType: photoAccessHelper.ThumbnailType,
  PhotoCreationConfig: photoAccessHelper.PhotoCreationConfig,
  PhotoKeys: photoAccessHelper.PhotoKeys,
  PhotoSource: PhotoSource,
  AlbumKeys: photoAccessHelper.AlbumKeys,
  AlbumType: photoAccessHelper.AlbumType,
  AlbumSubtype: photoAccessHelper.AlbumSubtype,
  AnalysisAlbum: photoAccessHelper.AnalysisAlbum,
  HighlightAlbum: photoAccessHelper.HighlightAlbum,
  PositionType: photoAccessHelper.PositionType,
  PhotoSubtype: photoAccessHelper.PhotoSubtype,
  PhotoPermissionType: photoAccessHelper.PhotoPermissionType,
  HideSensitiveType: photoAccessHelper.HideSensitiveType,
  NotifyType: photoAccessHelper.NotifyType,
  DefaultChangeUri: photoAccessHelper.DefaultChangeUri,
  AlbumAttribute: photoAccessHelper.AlbumAttribute,
  AlbumOperationType: photoAccessHelper.AlbumOperationType,
  HiddenPhotosDisplayMode: photoAccessHelper.HiddenPhotosDisplayMode,
  AnalysisType: photoAccessHelper.AnalysisType,
  HighlightAlbumInfoType: photoAccessHelper.HighlightAlbumInfoType,
  HighlightUserActionType: photoAccessHelper.HighlightUserActionType,
  HighlightAlbumChangeAttribute: photoAccessHelper.HighlightAlbumChangeAttribute,
  RequestPhotoType: photoAccessHelper.RequestPhotoType,
  PhotoViewMIMETypes: PhotoViewMIMETypes,
  SingleSelectionMode: SingleSelectionMode,
  MimeTypeFilter: MimeTypeFilter,
  FileSizeFilter: FileSizeFilter,
  VideoDurationFilter: VideoDurationFilter,
  PhotoViewMimeTypeFileSizeFilters: FileSizeFilterArray,
  FilterOperator: FilterOperator,
  OperationItem: OperationItem,
  OperationType: OperationType,
  DeliveryMode: photoAccessHelper.DeliveryMode,
  SourceMode: photoAccessHelper.SourceMode,
  AuthorizationMode: photoAccessHelper.AuthorizationMode,
  CompatibleMode: photoAccessHelper.CompatibleMode,
  PreferredCompatibleMode: photoAccessHelper.PreferredCompatibleMode,
  BaseSelectOptions: BaseSelectOptions,
  PhotoSelectOptions: PhotoSelectOptions,
  PhotoSelectResult: PhotoSelectResult,
  PhotoViewPicker: PhotoViewPicker,
  RecommendationType: RecommendationType,
  RecommendationOptions: RecommendationOptions,
  AssetCompatibleCapability: AssetCompatibleCapability,
  PreferredCompatibleMode: PreferredCompatibleMode,
  ResourceType: photoAccessHelper.ResourceType,
  MediaAssetEditData: photoAccessHelper.MediaAssetEditData,
  MediaAssetChangeRequest: MediaAssetChangeRequest,
  MediaAssetsChangeRequest: photoAccessHelper.MediaAssetsChangeRequest,
  MediaAlbumChangeRequest: photoAccessHelper.MediaAlbumChangeRequest,
  MediaAnalysisAlbumChangeRequest: photoAccessHelper.MediaAnalysisAlbumChangeRequest,
  MediaHighlightAlbumChangeRequest: photoAccessHelper.MediaHighlightAlbumChangeRequest,
  MediaAssetManager: photoAccessHelper.MediaAssetManager,
  MovingPhoto: photoAccessHelper.MovingPhoto,
  MovingPhotoEffectMode: photoAccessHelper.MovingPhotoEffectMode,
  CompleteButtonText: CompleteButtonText,
  ImageFileType: photoAccessHelper.ImageFileType,
  PhotoRiskStatus: photoAccessHelper.PhotoRiskStatus,
  AssetSourceType: photoAccessHelper.AssetSourceType,
  FieldType: photoAccessHelper.FieldType,
  RankingMethod: photoAccessHelper.RankingMethod,
  SearchSuggestionType: photoAccessHelper.SearchSuggestionType,
  CoverUriSource: photoAccessHelper.CoverUriSource,
  ThumbnailVisibility: photoAccessHelper.ThumbnailVisibility,
  CloudEnhancement: photoAccessHelper.CloudEnhancement,
  CloudEnhancementTaskStage: photoAccessHelper.CloudEnhancementTaskStage,
  CloudEnhancementState: photoAccessHelper.CloudEnhancementState,
  CloudEnhancementTaskState: photoAccessHelper.CloudEnhancementTaskState,
  WatermarkType: photoAccessHelper.WatermarkType,
  VideoEnhancementType: photoAccessHelper.VideoEnhancementType,
  CloudMediaAssetManager: photoAccessHelper.CloudMediaAssetManager,
  CloudMediaDownloadType: photoAccessHelper.CloudMediaDownloadType,
  CloudMediaRetainType: photoAccessHelper.CloudMediaRetainType,
  CloudMediaAssetTaskStatus: photoAccessHelper.CloudMediaAssetTaskStatus,
  CloudMediaTaskPauseCause: photoAccessHelper.CloudMediaTaskPauseCause,
  CloudMediaAssetStatus: photoAccessHelper.CloudMediaAssetStatus,
  PhotoAssetCustomRecordManager: photoAccessHelper.PhotoAssetCustomRecordManager,
  PhotoAssetCustomRecord: photoAccessHelper.PhotoAssetCustomRecord,
  NotifyChangeType: photoAccessHelper.NotifyChangeType,
  ThumbnailChangeStatus: photoAccessHelper.ThumbnailChangeStatus,
  StrongAssociationType: photoAccessHelper.StrongAssociationType,
  CompositeDisplayMode: photoAccessHelper.CompositeDisplayMode,
  SupportedImageFormat: photoAccessHelper.SupportedImageFormat,
  HdrMode: photoAccessHelper.HdrMode,
  CloudMediaDownloadResourcesStatus: photoAccessHelper.CloudMediaDownloadResourcesStatus,
  CloudAssetDownloadNotifyType: photoAccessHelper.CloudAssetDownloadNotifyType,
  CloudAssetDownloadCode: photoAccessHelper.CloudAssetDownloadCode,
  MovingPhotoBadgeStateType: MovingPhotoBadgeStateType,
  VideoMode: photoAccessHelper.VideoMode,
  AutoPlayScene: autoPlayScene,
  SceneType: SceneType,
  DynamicRangeType: photoAccessHelper.DynamicRangeType,
  PlayMode: PlayMode,
  GridPinchModeType: GridPinchModeType,
  GridLevel: GridLevel,
  GridPinchMode: GridPinchMode,
  AppLinkState: photoAccessHelper.AppLinkState,
  LivePhoto4dStatus: photoAccessHelper.LivePhoto4dStatus,
  AvailabilityStatus: photoAccessHelper.AvailabilityStatus,
  MediaAssetPermissionState: photoAccessHelper.MediaAssetPermissionState,
  TaskSignal: photoAccessHelper.TaskSignal,
  DeepOptimizeState: photoAccessHelper.DeepOptimizeState
};
