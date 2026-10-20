import common from '@ohos.app.ability.common';
import window from '@ohos.window';
import audio from '@ohos.multimedia.audio';
import fs from '@ohos.file.fs';
import abilityAccessCtrl from '@ohos.abilityAccessCtrl';
import { Journal, RUN } from './Journal';

export class Driver {
  static stage?: window.WindowStage;
  static group?: audio.AudioVolumeGroupManager;
  static before?: number;
  static capturer?: audio.AudioCapturer;
  static dataBytes: number = 0;
  static streamId: string = 'lifecycle';
  static inputId: string = 'lifecycle';
  static async execute(action: string, context: common.UIAbilityContext): Promise<void> {
    const id = Journal.requestId;
    const manager = audio.getAudioManager().getVolumeManager();
    if (action === 'identity') { await Journal.identity();
    } else if (action === 'permissions') {
      Journal.record('permission-result', JSON.stringify(await abilityAccessCtrl.createAtManager()
        .requestPermissionsFromUser(context, ['ohos.permission.MICROPHONE'])));
    } else if (action === 'observe') {
      Driver.group = manager.getVolumeGroupManagerSync(audio.DEFAULT_VOLUME_GROUP_ID);
      Driver.before = await Driver.group.getVolume(audio.AudioVolumeType.MEDIA);
      const path = context.filesDir + '/apps579-volume-before-' + RUN + '.txt';
      if (!fs.accessSync(path)) {
        const file = fs.openSync(path, fs.OpenMode.CREATE | fs.OpenMode.WRITE_ONLY | fs.OpenMode.EXCL);
        try { fs.writeSync(file.fd, String(Driver.before)); } finally { fs.closeSync(file); }
      } else { Driver.before = Number(fs.readTextSync(path)); }
      manager.on('volumeChange', (event: audio.VolumeEvent) => Journal.record('volume-change', JSON.stringify(event), 0, id, action));
      Journal.record('volume-before', JSON.stringify(Driver.before));
    } else if (action === 'show-volume') {
      AppStorage.setOrCreate('apps579Volume', true);
      Journal.record('volume-component-request');
    } else if (action === 'hide-volume') {
      AppStorage.setOrCreate('apps579Volume', false);
      Journal.record('volume-component-hidden');
    } else if (action === 'volume-current') {
      const group = manager.getVolumeGroupManagerSync(audio.DEFAULT_VOLUME_GROUP_ID);
      Journal.record('volume-current', JSON.stringify(await group.getVolume(audio.AudioVolumeType.MEDIA)));
    } else if (action === 'show-input') {
      Driver.inputId = id;
      AppStorage.setOrCreate('apps579Input', true);
      Journal.record('input-component-request', JSON.stringify(canIUse('SystemCapability.Multimedia.AVSession.AVInputCast')));
    } else if (action === 'hide-input') {
      AppStorage.setOrCreate('apps579Input', false); Journal.record('input-component-hidden');
    } else if (action === 'capture-start') {
      Driver.streamId = id; Driver.dataBytes = 0;
      Driver.capturer = await audio.createAudioCapturer({streamInfo: {samplingRate: audio.AudioSamplingRate.SAMPLE_RATE_48000,
        channels: audio.AudioChannel.CHANNEL_1, sampleFormat: audio.AudioSampleFormat.SAMPLE_FORMAT_S16LE,
        encodingType: audio.AudioEncodingType.ENCODING_TYPE_RAW},
        capturerInfo: {source: audio.SourceType.SOURCE_TYPE_MIC, capturerFlags: 0}});
      const output = context.filesDir + '/apps579-input-' + id + '.pcm';
      const truncate = fs.openSync(output, fs.OpenMode.CREATE | fs.OpenMode.WRITE_ONLY | fs.OpenMode.TRUNC);
      fs.closeSync(truncate);
      Driver.capturer.on('readData', (data: ArrayBuffer) => {
        if (Driver.dataBytes >= 1048576) { return; }
        const file = fs.openSync(output, fs.OpenMode.WRITE_ONLY | fs.OpenMode.APPEND);
        try { fs.writeSync(file.fd, data); Driver.dataBytes += data.byteLength; } finally { fs.closeSync(file); }
        Journal.record('capture-data', JSON.stringify({bytes: data.byteLength, total: Driver.dataBytes}), 0, Driver.streamId, 'capture-start');
      });
      Driver.capturer.on('inputDeviceChange', (devices: audio.AudioDeviceDescriptors) =>
        Journal.record('input-device-change', JSON.stringify(devices), 0, Driver.streamId, 'capture-start'));
      await Driver.capturer.start();
      Journal.record('capture-started', JSON.stringify({device: Driver.capturer.getCurrentInputDevices(), file: output}));
    } else if (action === 'capture-stop') {
      if (!Driver.capturer) { throw new Error('actual owned capturer missing'); }
      Journal.record('capture-device-final', JSON.stringify(Driver.capturer.getCurrentInputDevices()));
      await Driver.capturer.stop(); await Driver.capturer.release(); Driver.capturer = undefined;
      Journal.record('capture-stopped', JSON.stringify(Driver.dataBytes));
    } else if (action === 'restore') {
      if (!Driver.group) { Driver.group = manager.getVolumeGroupManagerSync(audio.DEFAULT_VOLUME_GROUP_ID); }
      if (Driver.before === undefined) {
        Driver.before = Number(fs.readTextSync(context.filesDir + '/apps579-volume-before-' + RUN + '.txt'));
      }
      if (!Driver.group || Driver.before === undefined) { throw new Error('actual before volume missing'); }
      if (Driver.capturer) { await Driver.capturer.stop(); await Driver.capturer.release(); Driver.capturer = undefined; }
      await Driver.group.setVolume(audio.AudioVolumeType.MEDIA, Driver.before);
      Journal.record('volume-restored', JSON.stringify(await Driver.group.getVolume(audio.AudioVolumeType.MEDIA)));
      manager.off('volumeChange');
      AppStorage.setOrCreate('apps579Volume', false); AppStorage.setOrCreate('apps579Input', false);
    } else if (action === 'exit') { Journal.record('exit-request'); await context.terminateSelf();
    } else { throw new Error('unknown fixed volume/input action'); }
    Journal.record('done', 'null', 0, id, action);
  }
}
