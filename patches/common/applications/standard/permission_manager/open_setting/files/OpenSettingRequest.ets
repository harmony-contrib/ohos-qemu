/* Copyright (c) 2026 OpenHarmony QEMU contributors. Licensed under Apache-2.0. */
import abilityAccessCtrl, { Permissions } from '@ohos.abilityAccessCtrl';
import bundleManager from '@ohos.bundle.bundleManager';
import deviceInfo from '@ohos.deviceInfo';
import Want from '@ohos.app.ability.Want';

export const USER_REJECTED: number = -1;
export const INTERNAL_ERROR: number = -2;
export const USER_OPENED: number = 0;
export const ALREADY_GRANTED: number = 1;
export const NOT_DECLARED: number = 2;
export const NOT_SUPPORTED: number = 3;
// access_token.h: PERMISSION_USER_SET = 1 << 0. Do not inherit USER_FIXED
// from the old user_grant sheet or set administrative grant flags.
const PERMISSION_USER_SET: number = 1;

// These are exactly the pinned release's PC/tablet manual_settings entries.
// Do not turn ordinary user_grant/system_grant permissions into manual grants.
const MANUAL_PERMISSIONS: Permissions[] = [
  'ohos.permission.HOOK_KEY_EVENT',
  'ohos.permission.CUSTOM_SCREEN_RECORDING',
  'ohos.permission.ACCESS_USER_FULL_DISK',
  'ohos.permission.CONTROL_DEVICE'
];

export class OpenSettingRequest {
  bundleName: string = '';
  permission: Permissions = 'ohos.permission.HOOK_KEY_EVENT';
  tokenId: number = 0;
  active: boolean = true;
  private busy: boolean = false;
  private want: Want;

  constructor(want: Want) {
    this.want = want;
  }

  async prepare(): Promise<number> {
    if (!this.active) {
      return USER_REJECTED;
    }
    if (deviceInfo.deviceType !== '2in1' && deviceInfo.deviceType !== 'tablet' && deviceInfo.deviceType !== 'pc') {
      return NOT_SUPPORTED;
    }
    const parameters = this.want.parameters;
    if (!parameters) {
      return NOT_SUPPORTED;
    }
    const permission = parameters['ohos.open.setting.permission'];
    const bundle = parameters['ohos.aafwk.param.callerBundleName'];
    const uid = parameters['ohos.aafwk.param.callerUid'];
    const token = parameters['ohos.aafwk.param.callerToken'];
    if (typeof permission !== 'string' || MANUAL_PERMISSIONS.indexOf(permission as Permissions) < 0 ||
      typeof bundle !== 'string' || bundle.length === 0 ||
      typeof uid !== 'number' || !Number.isInteger(uid) || uid < 10000 || uid > 2147483647 || uid % 200000 < 10000 ||
      typeof token !== 'number' || !Number.isInteger(token) || token < -2147483648 || token > 4294967295 || (token >>> 0) === 0) {
      return NOT_SUPPORTED;
    }
    try {
      const flags = bundleManager.BundleFlag.GET_BUNDLE_INFO_WITH_APPLICATION |
        bundleManager.BundleFlag.GET_BUNDLE_INFO_WITH_REQUESTED_PERMISSION;
      const info = await bundleManager.getBundleInfo(bundle, flags, Math.floor(uid / 200000));
      // Caller fields are injected by AbilityManager. Also bind them to the
      // real per-account BMS record; never grant a token supplied in app data.
      if (!this.active) {
        return USER_REJECTED;
      }
      if (info.name !== bundle || info.appInfo.uid !== uid || info.appInfo.accessTokenId !== (token >>> 0)) {
        return NOT_SUPPORTED;
      }
      if (!info.reqPermissionDetails.some((item) => item.name === permission)) {
        return NOT_DECLARED;
      }
      this.bundleName = info.name;
      this.permission = permission as Permissions;
      this.tokenId = info.appInfo.accessTokenId;
      const manager = abilityAccessCtrl.createAtManager();
      return manager.checkAccessTokenSync(this.tokenId, this.permission) === abilityAccessCtrl.GrantStatus.PERMISSION_GRANTED ?
        ALREADY_GRANTED : USER_OPENED;
    } catch (error) {
      return INTERNAL_ERROR;
    }
  }

  async confirm(): Promise<number> {
    if (!this.active || this.busy) {
      return USER_REJECTED;
    }
    this.busy = true;
    try {
      // Revalidate after display: uninstall/reinstall/account changes must
      // not reuse a stale token or a no-longer-declared permission.
      const status = await this.prepare();
      if (status !== USER_OPENED || !this.active) {
        return this.active ? status : USER_REJECTED;
      }
      const manager = abilityAccessCtrl.createAtManager();
      await manager.grantPermission(this.tokenId, this.permission, PERMISSION_USER_SET);
      return manager.checkAccessTokenSync(this.tokenId, this.permission) === abilityAccessCtrl.GrantStatus.PERMISSION_GRANTED ?
        USER_OPENED : INTERNAL_ERROR;
    } catch (error) {
      return INTERNAL_ERROR;
    } finally {
      this.busy = false;
    }
  }
}
