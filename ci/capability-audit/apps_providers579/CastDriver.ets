import common from '@ohos.app.ability.common';
import window from '@ohos.window';
import av from '@ohos.multimedia.avsession';
import { Journal, RUN } from './Journal';

export class Driver {
  static stage?: window.WindowStage;
  static helper?: av.AVCastPickerHelper;
  static session?: av.AVSession;
  static target?: av.OutputDeviceInfo;
  static discoverId: string = 'lifecycle';
  static pickerId: string = 'lifecycle';
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
      Driver.pickerId = id;
      Driver.helper = new av.AVCastPickerHelper(context);
      Driver.helper.on('pickerStateChange', (state: av.AVCastPickerState) =>
        Journal.record('cast-picker-state', JSON.stringify(state), 0, Driver.pickerId, 'picker'));
      await Driver.helper.select();
      // This is only an immediate request observation. The runtime requires
      // actual remote UI visibility, user action and a real session/peer.
      Journal.record('picker-select-returned');
    } else if (action === 'discover') {
      Driver.discoverId = id;
      av.on('deviceAvailable', (device: av.OutputDeviceInfo) => {
        Journal.record('cast-device-available', JSON.stringify(device), 0, Driver.discoverId, 'discover');
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
      await av.stopCastDeviceDiscovery(); av.off('deviceAvailable');
      if (Driver.session) { await Driver.session.destroy(); Driver.session = undefined; }
      Journal.record('cast-cleaned');
    } else if (action === 'exit') { Journal.record('exit-request'); await context.terminateSelf();
    } else { throw new Error('unknown fixed cast action'); }
    Journal.record('done', 'null', 0, id, action);
  }
}
