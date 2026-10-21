import common from '@ohos.app.ability.common';
import window from '@ohos.window';
import dm from '@ohos.distributedDeviceManager';
import av from '@ohos.multimedia.avsession';
import { AVCastPickerState } from '@ohos.multimedia.avCastPickerParam';
import audio from '@ohos.multimedia.audio';
import ethernet from '@ohos.net.ethernet';
import connection from '@ohos.net.connection';
import abilityAccessCtrl from '@ohos.abilityAccessCtrl';
import fs from '@ohos.file.fs';
import { BusinessError } from '@ohos.base';
import { Journal, BUNDLE, RUN, ENDPOINT } from './Journal';
import { RemoteCamera } from './RemoteCamera';

interface SavedNetwork { iface: string; config: ethernet.InterfaceConfiguration; }
export class Driver {
  static stage?: window.WindowStage;
  static surfaceId: string = '';
  static manager?: dm.DeviceManager;
  static discovered: dm.DeviceBasicInfo[] = [];
  static target?: dm.DeviceBasicInfo;
  static discoveryId: string = 'lifecycle';
  static dmWatching: boolean = false;
  static castDevices: av.OutputDeviceInfo[] = [];
  static output?: av.OutputDeviceInfo;
  static session?: av.AVSession;
  static controller?: av.AVCastController;
  static helper?: av.AVCastPickerHelper;
  static castId: string = 'lifecycle';
  static castDiscovering: boolean = false;
  static sinkId: string = 'lifecycle';
  static sinkWatching: boolean = false;
  static file?: fs.File;
  static capturer?: audio.AudioCapturer;
  static micBefore?: audio.AudioDeviceDescriptors;
  static micBytes: number = 0;
  static micId: string = 'lifecycle';
  static micPath: string = '';
  static data(name: string): string {
    const value = Journal.payload[name];
    if (typeof value !== 'string' || value.length > 255) { throw new Error('bounded actual data required: ' + name); }
    return value;
  }
  static dm(): dm.DeviceManager {
    if (!Driver.manager) { Driver.manager = dm.createDeviceManager(BUNDLE); }
    return Driver.manager;
  }
  static async picker(context: common.UIAbilityContext): Promise<void> {
    if (Driver.helper) { Driver.helper.off('pickerStateChange'); }
    const id = Journal.requestId;
    Driver.helper = new av.AVCastPickerHelper(context);
    Driver.helper.on('pickerStateChange', (state: AVCastPickerState) =>
      Journal.record('cast-picker-state', JSON.stringify(state), 0, id, 'cast-picker'));
    await Driver.helper.select(); Journal.record('picker-select-returned', 'null', 0, id, 'cast-picker');
  }
  static observeController(controller: av.AVCastController, id: string): void {
    controller.on('playbackStateChange', 'all', (state: av.AVPlaybackState) =>
      Journal.record('actual-cast-playback', JSON.stringify(state), 0, id, 'cast-controller'));
    controller.on('mediaItemChange', (item: av.AVQueueItem) =>
      Journal.record('actual-cast-item', JSON.stringify(item), 0, id, 'cast-controller'));
    controller.on('error', (error: BusinessError) => Journal.fail('actual-cast-error', error, id, 'cast-controller'));
  }
  static async stopMic(context: common.UIAbilityContext): Promise<void> {
    if (Driver.capturer) {
      Journal.record('actual-mic-final-device', JSON.stringify(Driver.capturer.getCurrentInputDevices()));
      const current = Driver.capturer;Driver.capturer = undefined;
      try {
        if (current.state === audio.AudioState.STATE_RUNNING || current.state === audio.AudioState.STATE_PAUSED) {
          await current.stop();
        }
      } finally { await current.release(); }
    }
    const path = context.filesDir + '/paired579-mic-before-' + RUN + '.json';
    if (fs.accessSync(path)) {
      const previous = JSON.parse(fs.readTextSync(path)) as audio.AudioDeviceDescriptors;
      const router = audio.getAudioManager().getRoutingManager();
      const available = await router.getDevices(audio.DeviceFlag.INPUT_DEVICES_FLAG);
      const restore = available.filter((device: audio.AudioDeviceDescriptor) =>
        previous.some((old: audio.AudioDeviceDescriptor) => old.id === device.id && old.networkId === device.networkId));
      if (!restore.length) { throw new Error('actual previous input device unavailable; retain restoration marker'); }
      await router.selectInputDevice(restore);fs.unlinkSync(path);
      Journal.record('actual-mic-route-restored', JSON.stringify(restore));
    }
    Journal.record('actual-mic-stopped', JSON.stringify({bytes: Driver.micBytes, file: Driver.micPath}));
  }
  static async execute(action: string, context: common.UIAbilityContext): Promise<void> {
    const id = Journal.requestId;
    if (action.startsWith('camera-')) { await RemoteCamera.execute(action,context,Driver.surfaceId);return; }
    if (action === 'identity') { await Journal.identity();
    } else if (action === 'permissions') {
      Journal.record('permission-result', JSON.stringify(await abilityAccessCtrl.createAtManager()
        .requestPermissionsFromUser(context, ['ohos.permission.DISTRIBUTED_DATASYNC', 'ohos.permission.MICROPHONE','ohos.permission.CAMERA'])));
    } else if (action === 'local') {
      const manager = Driver.dm();
      Journal.record('actual-local-device', JSON.stringify({networkId: manager.getLocalDeviceNetworkId(),
        deviceId: manager.getLocalDeviceId(), deviceName: manager.getLocalDeviceName(), deviceType: manager.getLocalDeviceType()}));
    } else if (action === 'network-before') {
      const iface = Driver.data('interface');if (iface !== 'eth0') { throw new Error('actual paired data MAC must map to eth0'); }
      const config = await ethernet.getIfaceConfig(iface);
      const path = context.filesDir + '/paired579-network-before-' + RUN + '.json';
      if (fs.accessSync(path)) { throw new Error('refuse replacing actual original Ethernet state'); }
      const out = fs.openSync(path, fs.OpenMode.CREATE | fs.OpenMode.WRITE_ONLY | fs.OpenMode.EXCL);
      try { fs.writeSync(out.fd, JSON.stringify({iface, config})); } finally { fs.closeSync(out); }
      Journal.record('actual-network-before', JSON.stringify({iface, config}));
    } else if (action === 'network-config') {
      const saved = JSON.parse(fs.readTextSync(context.filesDir + '/paired579-network-before-' + RUN + '.json')) as SavedNetwork;
      if (saved.iface !== 'eth0') { throw new Error('actual original data interface differs'); }
      const address = Driver.data('address');const route = Driver.data('route');
      if (!/^[0-9]{1,3}(\.[0-9]{1,3}){3}$/.test(address) || !/^[0-9]{1,3}(\.[0-9]{1,3}){3}$/.test(route)) { throw new Error('actual private IPv4 data required'); }
      await ethernet.setIfaceConfig(saved.iface, {mode: ethernet.IPSetMode.LAN_STATIC, ipAddr: address,
        route, gateway: '0.0.0.0', netMask: '255.255.255.252', dnsServers: ''});
      Journal.record('actual-network-configured', JSON.stringify(await ethernet.getIfaceConfig(saved.iface)));
    } else if (action === 'network-state') {
      Journal.record('actual-ethernet-config', JSON.stringify(await ethernet.getIfaceConfig('eth0')));
      for (const handle of await connection.getAllNets()) {
        Journal.record('actual-network-handle', JSON.stringify({netId: handle.netId,
          caps: await connection.getNetCapabilities(handle), properties: await connection.getConnectionProperties(handle)}));
      }
    } else if (action === 'network-restore') {
      const path = context.filesDir + '/paired579-network-before-' + RUN + '.json';
      if (fs.accessSync(path)) {
        const saved = JSON.parse(fs.readTextSync(path)) as SavedNetwork;
        if (saved.iface !== 'eth0') { throw new Error('refuse management Ethernet mutation'); }
        await ethernet.setIfaceConfig(saved.iface, saved.config);
        Journal.record('actual-network-restored', JSON.stringify(await ethernet.getIfaceConfig(saved.iface)));
        fs.unlinkSync(path);
      }
    } else if (action === 'dm-discover') {
      const manager = Driver.dm();Driver.discoveryId = id;Driver.discovered = [];
      if (!Driver.dmWatching) {
        manager.on('discoverSuccess', (result: {device: dm.DeviceBasicInfo}) => {
          Driver.discovered = Driver.discovered.filter((row: dm.DeviceBasicInfo) => row.deviceId !== result.device.deviceId);
          Driver.discovered.push(result.device);
          Journal.record('actual-device-found', JSON.stringify(result), 0, Driver.discoveryId, 'dm-discover');
        });
        manager.on('discoverFailure', (result: {reason: number}) => Journal.record('actual-discovery-failure', JSON.stringify(result), 0, Driver.discoveryId, 'dm-discover'));
        manager.on('deviceStateChange', (result: {action: dm.DeviceStateChange; device: dm.DeviceBasicInfo}) =>
          Journal.record('actual-device-state', JSON.stringify(result), 0, Driver.discoveryId, 'dm-discover'));
        Driver.dmWatching = true;
      }
      manager.startDiscovering({discoverTargetType: 1}, {availableStatus: 0});Journal.record('actual-discovery-started');
    } else if (action === 'dm-found') { Journal.record('actual-discovered-list', JSON.stringify(Driver.discovered));
    } else if (action === 'dm-select') {
      const target = Driver.data('deviceId');const matches = Driver.discovered.filter((row: dm.DeviceBasicInfo) => row.deviceId === target);
      if (matches.length !== 1) { throw new Error('target must have been found by this actual native discovery'); }
      Driver.target = matches[0];Journal.record('actual-selected-discovered-peer', JSON.stringify(Driver.target));
    } else if (action === 'dm-auth') {
      if (!Driver.target) { throw new Error('actual discovered target missing'); }
      Journal.record('actual-auth-request', JSON.stringify(Driver.target));
      Driver.dm().bindTarget(Driver.target.deviceId, {bindType: 1, targetPkgName: BUNDLE, appName: 'Pair579',
        appOperation: 'Authenticate the owned QEMU peer', customDescription: RUN},
        (error: BusinessError, result: {deviceId: string}) => {
          if (error) { Journal.fail('actual-auth-result', error, id, action); }
          else { Journal.record('actual-auth-result', JSON.stringify(result), 0, id, action); }
        });
    } else if (action === 'dm-trusted') { Journal.record('actual-trusted-list', JSON.stringify(Driver.dm().getAvailableDeviceListSync()));
    } else if (action === 'dm-unbind') {
      const networkId = Driver.data('networkId');
      const trusted = Driver.dm().getAvailableDeviceListSync().filter((device: dm.DeviceBasicInfo) => device.networkId === networkId);
      Journal.record('actual-owned-trusted-before-unbind', JSON.stringify(trusted));
      if (trusted.length > 1) { throw new Error('ambiguous actual owned peer identity'); }
      if (trusted.length === 1) {
        Driver.dm().unbindTarget(trusted[0].deviceId);Journal.record('actual-peer-unbind-request', JSON.stringify(trusted[0]));
      } else { Journal.record('actual-owned-peer-already-unbound'); }
    } else if (action === 'dm-stop') {
      Driver.dm().stopDiscovering();
      if (Driver.dmWatching) {
        Driver.dm().off('discoverSuccess');Driver.dm().off('discoverFailure');Driver.dm().off('deviceStateChange');Driver.dmWatching = false;
      }
      Journal.record('actual-discovery-stopped');
    } else if (action === 'cast-create') {
      if (ENDPOINT !== 'source' || Driver.session) { throw new Error('one actual source session only'); }
      Driver.session = await av.createAVSession(context, 'paired579-' + RUN, 'audio');
      Driver.session.on('outputDeviceChange', (state: av.ConnectionState, device: av.OutputDeviceInfo) =>
        Journal.record('actual-output-device-change', JSON.stringify({state, device}), 0, id, action));
      await Driver.session.setAVMetadata({assetId: RUN, title: 'paired579-' + RUN});
      await Driver.session.activate();Journal.record('actual-source-session-created', JSON.stringify({sessionId: Driver.session.sessionId}));
    } else if (action === 'cast-discover') {
      Driver.castId = id;Driver.castDevices = [];
      av.on('deviceAvailable', (device: av.OutputDeviceInfo) => {
        Driver.castDevices.push(device);Journal.record('actual-cast-device', JSON.stringify(device), 0, Driver.castId, 'cast-discover');
      });
      await av.startCastDeviceDiscovery();Driver.castDiscovering = true;Journal.record('actual-cast-discovery-started');
    } else if (action === 'cast-found') { Journal.record('actual-cast-devices', JSON.stringify(Driver.castDevices));
    } else if (action === 'cast-select') {
      const networkId = Driver.data('networkId');const address = Driver.data('address');
      const matches = Driver.castDevices.filter((output: av.OutputDeviceInfo) => output.devices.some((device: av.DeviceInfo) =>
        device.networkId === networkId && device.ipAddress === address && ((device.supportedProtocols as number) & av.ProtocolType.TYPE_CAST_PLUS_STREAM) !== 0));
      if (!matches.length) { throw new Error('no real discovered Cast+Stream endpoint with actual peer networkId/IP'); }
      Driver.output = matches[matches.length - 1];Journal.record('actual-cast-target', JSON.stringify(Driver.output));
    } else if (action === 'cast-picker') { await Driver.picker(context);
    } else if (action === 'cast-connect') {
      if (!Driver.session || !Driver.output) { throw new Error('actual source session and discovered output required'); }
      await av.startCasting({sessionId: Driver.session.sessionId}, Driver.output);
      Journal.record('actual-cast-connect-request', JSON.stringify({sessionId: Driver.session.sessionId, output: Driver.output}));
    } else if (action === 'cast-controller') {
      if (!Driver.session) { throw new Error('actual source session missing'); }
      if (!Driver.controller) {
        Driver.controller = await Driver.session.getAVCastController();
        if (!Driver.controller) { throw new Error('native source cast controller absent'); }
        Driver.observeController(Driver.controller, id);
      }
      Journal.record('actual-source-controller-ready');
    } else if (action === 'sink-observe') {
      if (ENDPOINT !== 'sink' || Driver.sinkWatching) { throw new Error('one actual sink observer'); }
      Driver.sinkId = id;
      av.on('sessionCreate', (session: av.AVSessionDescriptor) => Journal.record('actual-sink-session-create', JSON.stringify(session), 0, id, action));
      av.on('sessionDestroy', (session: av.AVSessionDescriptor) => Journal.record('actual-sink-session-destroy', JSON.stringify(session), 0, id, action));
      Driver.sinkWatching = true;Journal.record('actual-sink-sessions-before', JSON.stringify(await av.getAllSessionDescriptors()));
    } else if (action === 'sink-attach') {
      if (ENDPOINT !== 'sink' || !Driver.surfaceId) { throw new Error('real sink XComponent producer surface required'); }
      const descriptors = (await av.getAllSessionDescriptors()).filter((session: Readonly<av.AVSessionDescriptor>) =>
        session.sessionTag === 'RemoteCast' && session.elementName.bundleName === 'castBundleName');
      Journal.record('actual-sink-native-descriptors', JSON.stringify(descriptors));
      if (descriptors.length !== 1) { throw new Error('one OS-created Cast+ sink session required'); }
      if (!Driver.controller) {
        Driver.controller = await av.getAVCastController(descriptors[0].sessionId);
        if (!Driver.controller) { throw new Error('native sink cast controller absent'); }
        Driver.observeController(Driver.controller, id);
      }
      await Driver.controller.setDisplaySurface(Driver.surfaceId);
      Journal.record('actual-sink-surface-bound', JSON.stringify({sessionId: descriptors[0].sessionId, surface: Driver.surfaceId}));
    } else if (action === 'cast-start') {
      if (ENDPOINT !== 'source' || !Driver.controller || Driver.file) { throw new Error('one owned source fd/controller required'); }
      const path = context.filesDir + '/cast-' + RUN + '.wav';Driver.file = fs.openSync(path, fs.OpenMode.READ_ONLY);
      const size = fs.statSync(Driver.file.fd).size;
      const item: av.AVQueueItem = {itemId: 1, description: {assetId: RUN, title: 'paired579-' + RUN,
        mediaType: 'AUDIO', mediaSize: size, duration: 60000, fdSrc: {fd: Driver.file.fd, offset: 0, length: size}}};
      await Driver.controller.start(item);Journal.record('actual-cast-started', JSON.stringify({item, path, size}));
    } else if (action === 'cast-pause' || action === 'cast-resume') {
      if (!Driver.controller) { throw new Error('actual cast controller missing'); }
      await Driver.controller.sendControlCommand({command: action === 'cast-pause' ? 'pause' : 'play'});
      Journal.record('actual-cast-control-sent', JSON.stringify(action));
    } else if (action === 'cast-state') {
      if (!Driver.controller) { throw new Error('actual cast controller missing'); }
      Journal.record('actual-cast-state', JSON.stringify(await Driver.controller.getAVPlaybackState()));
      Journal.record('actual-cast-current-item', JSON.stringify(await Driver.controller.getCurrentItem()));
    } else if (action === 'cast-stop') {
      if (!Driver.session) { throw new Error('actual source session missing'); }
      await av.stopCasting({sessionId: Driver.session.sessionId});Journal.record('actual-cast-stopped');
    } else if (action === 'mic-devices') {
      Journal.record('actual-remote-microphones', JSON.stringify(await audio.getAudioManager().getRoutingManager().getDevices(audio.DeviceFlag.DISTRIBUTED_INPUT_DEVICES_FLAG)));
    } else if (action === 'mic-start') {
      if (ENDPOINT !== 'source' || Driver.capturer) { throw new Error('one owned remote microphone stream'); }
      const network = Driver.data('networkId');const router = audio.getAudioManager().getRoutingManager();
      const devices = (await router.getDevices(audio.DeviceFlag.DISTRIBUTED_INPUT_DEVICES_FLAG))
        .filter((device: audio.AudioDeviceDescriptor) => device.networkId === network);
      if (devices.length !== 1) { throw new Error('one actual independent peer microphone descriptor required'); }
      Driver.capturer = await audio.createAudioCapturer({streamInfo: {samplingRate: audio.AudioSamplingRate.SAMPLE_RATE_48000,
        channels: audio.AudioChannel.CHANNEL_2, sampleFormat: audio.AudioSampleFormat.SAMPLE_FORMAT_S16LE,
        encodingType: audio.AudioEncodingType.ENCODING_TYPE_RAW}, capturerInfo: {source: audio.SourceType.SOURCE_TYPE_MIC, capturerFlags: 0}});
      Driver.micBefore = Driver.capturer.getCurrentInputDevices();
      const out = fs.openSync(context.filesDir + '/paired579-mic-before-' + RUN + '.json',fs.OpenMode.CREATE | fs.OpenMode.WRITE_ONLY | fs.OpenMode.EXCL);
      try { fs.writeSync(out.fd, JSON.stringify(Driver.micBefore)); } finally { fs.closeSync(out); }
      Driver.micId = id;Driver.micBytes = 0;Driver.micPath = context.filesDir + '/paired579-mic-' + RUN + '-' + id + '.pcm';
      const empty = fs.openSync(Driver.micPath,fs.OpenMode.CREATE | fs.OpenMode.WRITE_ONLY | fs.OpenMode.EXCL);fs.closeSync(empty);
      Driver.capturer.on('readData', (data: ArrayBuffer) => {
        if (data.byteLength % 4 !== 0 || Driver.micBytes + data.byteLength > 16 * 1024 * 1024) {
          Journal.record('actual-remote-mic-storage-error',JSON.stringify({bytes:data.byteLength,total:Driver.micBytes}),-1,id,action);return;
        }
        if (Driver.micBytes + data.byteLength <= 16 * 1024 * 1024) {
          const stream = fs.openSync(Driver.micPath,fs.OpenMode.WRITE_ONLY | fs.OpenMode.APPEND);
          try { fs.writeSync(stream.fd,data);Driver.micBytes += data.byteLength; } finally { fs.closeSync(stream); }
        }
        Journal.record('actual-remote-mic-data',JSON.stringify({bytes: data.byteLength,total: Driver.micBytes}),0,id,action);
      });
      Driver.capturer.on('inputDeviceChange',(changed: audio.AudioDeviceDescriptors) => Journal.record('actual-mic-device-change',JSON.stringify(changed),0,id,action));
      Driver.capturer.on('stateChange',(state: audio.AudioState) => Journal.record('actual-mic-state-change',JSON.stringify(state),0,id,action));
      await router.selectInputDevice(devices);await Driver.capturer.start();
      Journal.record('actual-remote-mic-started',JSON.stringify({selected:devices,current:Driver.capturer.getCurrentInputDevices(),file:Driver.micPath,stream:await Driver.capturer.getStreamInfo()}));
    } else if (action === 'mic-state') {
      if (!Driver.capturer) { throw new Error('actual remote microphone stream absent'); }
      Journal.record('actual-mic-state',JSON.stringify({state:Driver.capturer.state,devices:Driver.capturer.getCurrentInputDevices(),bytes:Driver.micBytes,file:Driver.micPath,stream:await Driver.capturer.getStreamInfo()}));
    } else if (action === 'mic-stop') { await Driver.stopMic(context);
    } else if (action === 'mic-final') {
      Journal.record('actual-mic-final',JSON.stringify({present:Driver.capturer!==undefined,bytes:Driver.micBytes,file:Driver.micPath}));
    } else if (action === 'cast-cleanup') {
      if (Driver.helper) { Driver.helper.off('pickerStateChange');Driver.helper=undefined; }
      if (Driver.controller) { await Driver.controller.release();Driver.controller=undefined; }
      if (Driver.session) { await Driver.session.destroy();Driver.session=undefined; }
      if (Driver.file) { fs.closeSync(Driver.file);Driver.file=undefined; }
      if (Driver.castDiscovering) { await av.stopCastDeviceDiscovery();av.off('deviceAvailable');Driver.castDiscovering=false; }
      if (Driver.sinkWatching) { av.off('sessionCreate');av.off('sessionDestroy');Driver.sinkWatching=false; }
      Journal.record('actual-cast-cleaned');
    } else if (action === 'cleanup') {
      await RemoteCamera.stop();
      await Driver.stopMic(context);
      await Driver.execute('cast-cleanup',context);
      if (Driver.manager) { if (Driver.dmWatching) { await Driver.execute('dm-stop',context); }
        dm.releaseDeviceManager(Driver.manager);Driver.manager=undefined; }
      await Driver.execute('network-restore',context);
      Journal.record('actual-pair-cleaned');
    } else if (action === 'exit') { Journal.record('exit-request');await context.terminateSelf();
    } else { throw new Error('unknown fixed pair action'); }
    Journal.record('done','null',0,id,action);
  }
}
