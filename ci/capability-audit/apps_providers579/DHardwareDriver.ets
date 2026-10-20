import common from '@ohos.app.ability.common';
import window from '@ohos.window';
import dm from '@ohos.distributedDeviceManager';
import { BusinessError } from '@ohos.base';
import { Journal, BUNDLE, RUN } from './Journal';

interface Found { device: dm.DeviceBasicInfo; }
interface DiscoveryFailure { reason: number; }
interface Bound { deviceId: string; }

export class Driver {
  static stage?: window.WindowStage;
  static manager?: dm.DeviceManager;
  static target?: dm.DeviceBasicInfo;
  static discoverId: string = 'lifecycle';
  static async execute(action: string, context: common.UIAbilityContext): Promise<void> {
    const id = Journal.requestId;
    if (action === 'identity') { await Journal.identity();
    } else {
      if (!Driver.manager) { Driver.manager = dm.createDeviceManager(BUNDLE); }
      const manager = Driver.manager;
      if (action === 'discover') {
        Driver.discoverId = id;
        manager.on('discoverSuccess', (result: Found) => {
          Journal.record('device-found', JSON.stringify(result), 0, Driver.discoverId, 'discover');
          // Select only the root-owned peer's independently observed device
          // name. Never accept a networkId/deviceId supplied as a success.
          if (result.device.deviceName === 'apps579-' + RUN.substring(0, 12)) { Driver.target = result.device; }
        });
        manager.on('discoverFailure', (result: DiscoveryFailure) =>
          Journal.record('discovery-failure', JSON.stringify(result), 0, Driver.discoverId, 'discover'));
        manager.startDiscovering({discoverTargetType: 1}, {availableStatus: 0});
        Journal.record('discovery-started');
      } else if (action === 'authenticate') {
        if (!Driver.target) { throw new Error('no actually discovered nonce-named peer'); }
        Journal.record('auth-request', JSON.stringify(Driver.target));
        manager.bindTarget(Driver.target.deviceId, {bindType: 1, targetPkgName: BUNDLE,
          appName: 'Apps579', appOperation: 'Authenticate owned QEMU peer', customDescription: RUN},
          (error: BusinessError, result: Bound) => {
            if (error) { Journal.fail('auth-result', error, id, action); }
            else { Journal.record('auth-result', JSON.stringify(result), 0, id, action); }
          });
      } else if (action === 'trusted') {
        Journal.record('trusted-devices', JSON.stringify(manager.getAvailableDeviceListSync()));
      } else if (action === 'unbind') {
        if (!Driver.target) { throw new Error('actual owned target missing'); }
        manager.unbindTarget(Driver.target.deviceId);
        Journal.record('unbound', JSON.stringify(Driver.target));
      } else if (action === 'stop-discover') {
        manager.stopDiscovering(); manager.off('discoverSuccess'); manager.off('discoverFailure');
        Journal.record('discovery-stopped');
      } else if (action === 'invalid-auth') {
        manager.bindTarget('', {bindType: 1}, (error: BusinessError, result: Bound) => {
          if (error) { Journal.fail('invalid-auth-result', error, id, action); }
          else { Journal.record('invalid-auth-result', JSON.stringify(result), 0, id, action); }
        });
      } else if (action === 'exit') { Journal.record('exit-request'); await context.terminateSelf();
      } else { throw new Error('unknown fixed DHardware action'); }
    }
    Journal.record('done', 'null', 0, id, action);
  }
}
