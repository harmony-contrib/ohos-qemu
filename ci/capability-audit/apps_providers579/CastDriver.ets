import common from '@ohos.app.ability.common';
import window from '@ohos.window';
import av from '@ohos.multimedia.avsession';
import { AVCastPickerState } from '@ohos.multimedia.avCastPickerParam';
import { BusinessError } from '@ohos.base';
import { Journal, RUN } from './Journal';

export class Driver {
  static stage?: window.WindowStage;
  static helper?: av.AVCastPickerHelper;
  static session?: av.AVSession;
  static target?: av.OutputDeviceInfo;
  static discoverId: string = 'lifecycle';
  static pickerId: string = 'lifecycle';
  static pickerCallback?: (state: AVCastPickerState) => void;
  static pickerRegistration: number = 0;
  static async execute(action: string, context: common.UIAbilityContext): Promise<void> {
    const id = Journal.requestId;
    if (action === 'identity') { await Journal.identity();
    } else if (action === 'session-create') {
      Driver.session = await av.createAVSession(context, 'apps579-' + RUN, 'audio');
      Driver.session.on('outputDeviceChange', (state: av.ConnectionState, device: av.OutputDeviceInfo) =>
        Journal.record('output-device-change', JSON.stringify({state, device}), 0, id, action));
      await Driver.session.setAVMetadata({assetId: RUN, title: 'apps579-' + RUN});
      await Driver.session.activate();
      Journal.record('session-created', JSON.stringify({sessionId: Driver.session.sessionId}));
    } else if (action === 'picker') {
      if (Driver.helper) { Driver.helper.off('pickerStateChange'); }
      else { Driver.helper = new av.AVCastPickerHelper(context); }
      Driver.pickerId = id;
      const registration = ++Driver.pickerRegistration;
      // Keep the registration request in the callback itself. A later request
      // must not relabel an older queued callback as a new observation.
      Driver.pickerCallback = (state: AVCastPickerState): void => {
        Journal.record('cast-picker-state', JSON.stringify(state), 0, id, action);
        Journal.record('cast-picker-delivery', JSON.stringify({registration, state}), 0, id, action);
      };
      Driver.helper.on('pickerStateChange', Driver.pickerCallback);
      Journal.record('cast-picker-registered', JSON.stringify({registration}));
      await Driver.helper.select();
      // This is only an immediate request observation. The runtime requires
      // actual remote UI visibility, user action and a real session/peer.
      Journal.record('picker-select-returned', 'null', 0, id, action);
    } else if (action === 'picker-queue-off' || action === 'picker-queue-off-on') {
      const helper = Driver.helper ?? new av.AVCastPickerHelper(context);
      Driver.helper = helper;
      helper.off('pickerStateChange');
      const registration = ++Driver.pickerRegistration;
      let retired: boolean = false;
      const callbackB = (state: AVCastPickerState): void => {
        Journal.record('cast-picker-B', JSON.stringify({registration, state}), 0, id, action);
      };
      const callbackA = (state: AVCastPickerState): void => {
        Journal.record('cast-picker-A-enter', JSON.stringify({registration, state}), 0, id, action);
        if (!retired) {
          retired = true;
          try {
            helper.off('pickerStateChange', callbackB);
            Journal.record('cast-picker-A-off-returned', JSON.stringify({registration}), 0, id, action);
            if (action === 'picker-queue-off-on') {
              helper.on('pickerStateChange', callbackB);
              Journal.record('cast-picker-A-on-returned', JSON.stringify({registration}), 0, id, action);
            }
          } catch (error) {
            Journal.fail('error', error as BusinessError, id, action);
          }
        }
      };
      // A is registered before B. A synchronously retires B from the real
      // callback. Native guest logs must prove both tasks were submitted
      // before A ran; a quiet journal alone cannot prove this boundary.
      helper.on('pickerStateChange', callbackA);
      helper.on('pickerStateChange', callbackB);
      Driver.pickerCallback = callbackB;
      Driver.pickerId = id;
      Journal.record('cast-picker-queue-registration', JSON.stringify({registration}));
      await helper.select();
      Journal.record('picker-select-returned', 'null', 0, id, action);
    } else if (action === 'picker-off' || action === 'picker-off-all' || action === 'picker-off-on') {
      if (!Driver.helper || !Driver.pickerCallback) { throw new Error('actual owned picker registration required'); }
      if (action === 'picker-off-all') { Driver.helper.off('pickerStateChange'); }
      else { Driver.helper.off('pickerStateChange', Driver.pickerCallback); }
      Journal.record('cast-picker-unregistered', JSON.stringify({registration: Driver.pickerRegistration}));
      if (action === 'picker-off-on') {
        // Reuse the exact public callback object in one JS turn. Whether a
        // native event was already queued must be shown by native guest logs.
        Driver.helper.on('pickerStateChange', Driver.pickerCallback);
        Journal.record('cast-picker-reregistered', JSON.stringify({registration: Driver.pickerRegistration}));
      }
    } else if (action === 'picker-on') {
      if (!Driver.helper || !Driver.pickerCallback) { throw new Error('actual owned picker callback required'); }
      Driver.helper.on('pickerStateChange', Driver.pickerCallback);
      Journal.record('cast-picker-reregistered', JSON.stringify({registration: Driver.pickerRegistration}));
    } else if (action === 'picker-reselect') {
      if (!Driver.helper) { throw new Error('actual owned picker required'); }
      await Driver.helper.select();
      Journal.record('picker-select-returned', 'null', 0, id, action);
    } else if (action === 'picker-release') {
      if (!Driver.helper) { throw new Error('actual owned picker required'); }
      Driver.helper.off('pickerStateChange');
      Driver.helper = undefined;
      Driver.pickerCallback = undefined;
      // Releasing JS references does not prove native finalization. The QEMU
      // runner separately observes process/native teardown and reentry.
      Journal.record('cast-picker-references-released');
    } else if (action === 'discover') {
      Driver.discoverId = id;
      av.on('deviceAvailable', (device: av.OutputDeviceInfo) => {
        Journal.record('cast-device-available', JSON.stringify(device), 0, id, action);
        if (device.devices.some((d: av.DeviceInfo) => d.deviceName === 'apps579-' + RUN.substring(0, 12))) {
          Driver.target = device;
        }
      });
      await av.startCastDeviceDiscovery(); Journal.record('cast-discovery-started');
    } else if (action === 'cast') {
      if (!Driver.session || !Driver.target) { throw new Error('real owned session/discovered peer required'); }
      await av.startCasting({sessionId: Driver.session.sessionId}, Driver.target);
      Journal.record('cast-requested', JSON.stringify({sessionId: Driver.session.sessionId, target: Driver.target}));
    } else if (action === 'stop-cast') {
      if (!Driver.session) { throw new Error('actual owned session missing'); }
      await av.stopCasting({sessionId: Driver.session.sessionId}); Journal.record('cast-stopped');
    } else if (action === 'cleanup') {
      if (Driver.helper) { Driver.helper.off('pickerStateChange'); Driver.helper = undefined; }
      Driver.pickerCallback = undefined;
      await av.stopCastDeviceDiscovery(); av.off('deviceAvailable');
      if (Driver.session) { await Driver.session.destroy(); Driver.session = undefined; }
      Journal.record('cast-cleaned');
    } else if (action === 'exit') { Journal.record('exit-request'); await context.terminateSelf();
    } else { throw new Error('unknown fixed cast action'); }
    Journal.record('done', 'null', 0, id, action);
  }
}
