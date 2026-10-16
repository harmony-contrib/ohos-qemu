/* Public AudioHapticPlayer observations; no synthetic haptic/audio success. */
import audioHaptic from '@ohos.multimedia.audioHaptic';
import audio from '@ohos.multimedia.audio';
import fs from '@ohos.file.fs';
import util from '@ohos.util';
import systemDateTime from '@ohos.systemDateTime';
import process from '@ohos.process';
import bundleManager from '@ohos.bundle.bundleManager';
import abilityAccessCtrl from '@ohos.abilityAccessCtrl';
import { common } from '@kit.AbilityKit';
import { BusinessError } from '@ohos.base';

interface Request {
  schema_version: number;
  run_id: string;
  boot_id: string;
  operation_id: string;
  action: string;
  case_id: string;
  mute_audio: boolean;
  mute_haptics: boolean;
  fast: boolean;
}

interface CallbackRow { kind: string; generation: number; monotonic_ns: number; event_type: number; force_type: number; hint_type: number; released: boolean; }

@Entry
@Component
struct Index {
  @State private busy: boolean = false;
  @State private note: string = 'Public AudioHapticPlayer candidate';
  private readonly run: string = '__AUDIO_HAPTIC_RUN__';
  private manager: audioHaptic.AudioHapticManager = audioHaptic.getAudioHapticManager();
  private player: audioHaptic.AudioHapticPlayer | undefined;
  private id: number = -1;
  private released: boolean = false;
  private callbacks: CallbackRow[] = [];
  private callbackOverflow: number = 0;
  private generation: number = 0;
  private used: string[] = [];
  private sequence: number = 0;

  private now(): number {
    const time = systemDateTime.getUptime(systemDateTime.TimeType.ACTIVE, true);
    if (!Number.isSafeInteger(time) || time <= 0) { throw new Error('Unsafe actual ACTIVE uptime'); }
    return time;
  }

  private callback(kind: string, generation: number, eventType: number = -1, forceType: number = -1, hintType: number = -1): void {
    if (this.callbacks.length >= 128) { this.callbackOverflow++; return; }
    this.callbacks.push({ kind: kind, generation: generation, monotonic_ns: this.now(), event_type: eventType,
      force_type: forceType, hint_type: hintType, released: this.released || generation !== this.generation });
  }

  private append(request: Request, event: string, api: string, before: number, value: string,
    code: number = 0, message: string = ''): void {
    const context = getContext(this) as common.UIAbilityContext;
    const row = JSON.stringify({ schema_version: 1, run_id: this.run, boot_id: request.boot_id,
      operation_id: request.operation_id, sequence: ++this.sequence, uid: process.uid,
      event: event, api: api, before_ns: before, after_ns: this.now(), value_json: value,
      error_code: code, error_message: message }) + '\n';
    const bytes = new util.TextEncoder().encodeInto(row);
    const file = fs.openSync(context.filesDir + '/audio-haptic-' + this.run + '.jsonl',
      fs.OpenMode.CREATE | fs.OpenMode.WRITE_ONLY | fs.OpenMode.APPEND | fs.OpenMode.NOFOLLOW);
    try {
      let done: number = 0;
      while (done < bytes.byteLength) {
        const amount = fs.writeSync(file.fd, bytes.slice(done).buffer);
        if (amount <= 0 || amount > bytes.byteLength - done) { throw new Error('Short raw journal write'); }
        done += amount;
      }
    } finally { fs.closeSync(file); }
  }

  private snapshot(request: Request): void {
    const before = this.now();
    if (this.player !== undefined) {
      const audioMuted = this.player.isMuted(audioHaptic.AudioHapticType.AUDIO_HAPTIC_TYPE_AUDIO);
      const hapticsMuted = this.player.isMuted(audioHaptic.AudioHapticType.AUDIO_HAPTIC_TYPE_HAPTIC);
      this.append(request, 'getters', 'AudioHapticPlayer.isMuted', before,
        JSON.stringify({ audio_muted: audioMuted, haptics_muted: hapticsMuted }));
    }
    this.append(request, 'callbacks', 'AudioHapticPlayer.on', this.now(),
      JSON.stringify({ events: this.callbacks, overflow: this.callbackOverflow }));
    // No state/getTime API exists. A resolved start or elapsed timer is not RUNNING.
  }

  private async execute(): Promise<void> {
    if (this.busy) { return; }
    this.busy = true;
    let request: Request | undefined;
    let began: number = 0;
    try {
      const context = getContext(this) as common.UIAbilityContext;
      const path = context.filesDir + '/audio-haptic-request.json';
      if (fs.statSync(path).size > 8192) { throw new Error('Oversized request'); }
      request = JSON.parse(fs.readTextSync(path)) as Request;
      if (request.schema_version !== 1 || request.run_id !== this.run || !/^[a-f0-9-]{36}$/.test(request.boot_id) ||
        !/^[a-f0-9]{32}$/.test(request.operation_id) || this.used.includes(request.operation_id) ||
        this.used.length >= 256 ||
        !['init', 'start', 'snapshot', 'stop', 'release', 'start-after-release'].includes(request.action) ||
        !['expiry', 'stop'].includes(request.case_id) || typeof request.mute_audio !== 'boolean' ||
        typeof request.mute_haptics !== 'boolean' || typeof request.fast !== 'boolean') { throw new Error('Invalid fresh request'); }
      this.used.push(request.operation_id);
      began = this.now();
      this.append(request, 'begin', request.action, began, JSON.stringify(request));
      const info = bundleManager.getBundleInfoForSelfSync(bundleManager.BundleFlag.GET_BUNDLE_INFO_WITH_APPLICATION);
      const grant = abilityAccessCtrl.createAtManager().checkAccessTokenSync(info.appInfo.accessTokenId, 'ohos.permission.VIBRATE');
      this.append(request, 'token', 'abilityAccessCtrl.checkAccessTokenSync', this.now(),
        JSON.stringify({ token_id: info.appInfo.accessTokenId, VIBRATE: grant }));
      if (request.action === 'init') {
        if ((this.player !== undefined && !this.released) || this.id >= 0) { throw new Error('Release current resource before init'); }
        this.player = undefined;
        this.released = false;
        this.callbacks = [];
        this.callbackOverflow = 0;
        const generation = ++this.generation;
        const audioPath = context.filesDir + '/' + this.run + '-' + request.case_id + '.wav';
        const hapticPath = context.filesDir + '/' + this.run + '-' + request.case_id + '.json';
        this.id = await this.manager.registerSource(audioPath, hapticPath);
        this.append(request, 'return', 'AudioHapticManager.registerSource', began, JSON.stringify({ id: this.id, audio_path: audioPath, haptic_path: hapticPath }));
        if (this.id < 0) { throw new Error('Actual registration returned a negative ID'); }
        this.manager.setAudioLatencyMode(this.id, request.fast ? audioHaptic.AudioLatencyMode.AUDIO_LATENCY_MODE_FAST :
          audioHaptic.AudioLatencyMode.AUDIO_LATENCY_MODE_NORMAL);
        this.manager.setStreamUsage(this.id, audio.StreamUsage.STREAM_USAGE_MEDIA);
        const options: audioHaptic.AudioHapticPlayerOptions = { muteAudio: request.mute_audio, muteHaptics: request.mute_haptics };
        this.player = await this.manager.createPlayer(this.id, options);
        this.player.on('endOfStream', (): void => { this.callback('endOfStream', generation); });
        this.player.on('audioInterrupt', (event: audio.InterruptEvent): void => {
          this.callback('audioInterrupt', generation, event.eventType, event.forceType, event.hintType);
        });
        this.append(request, 'return', 'AudioHapticManager.createPlayer', began, JSON.stringify(options));
      } else if (request.action === 'release') {
        if (this.player !== undefined) {
          this.player.off('endOfStream');
          this.player.off('audioInterrupt');
          await this.player.release();
          this.released = true;
          // Retain the real released object for the explicit negative call.
          this.append(request, 'return', 'AudioHapticPlayer.release', began, '{}');
        }
        if (this.id >= 0) {
          await this.manager.unregisterSource(this.id);
          this.append(request, 'return', 'AudioHapticManager.unregisterSource', began, JSON.stringify({ id: this.id }));
          this.id = -1;
        }
      } else if (request.action === 'start' || request.action === 'start-after-release') {
        if (this.player === undefined) { throw new Error('No real player object'); }
        await this.player.start();
        this.append(request, 'return', 'AudioHapticPlayer.start', began, '{}');
      } else if (request.action === 'stop') {
        if (this.player === undefined) { throw new Error('No real player object'); }
        await this.player.stop();
        this.append(request, 'return', 'AudioHapticPlayer.stop', began, '{}');
      }
      if (!this.released) { this.snapshot(request); }
      else { this.append(request, 'callbacks', 'AudioHapticPlayer.on', this.now(),
        JSON.stringify({ events: this.callbacks, overflow: this.callbackOverflow })); }
      this.append(request, 'complete', request.action, began, '{}');
      this.note = 'Actual ' + request.action + ' result saved';
    } catch (error) {
      const actual = error as BusinessError;
      if (request !== undefined && began > 0) {
        this.append(request, 'error', request.action, began, '{}', actual.code ?? -1, actual.message ?? String(actual));
      }
      this.note = 'Failed ' + actual.code + ': ' + actual.message;
    } finally { this.busy = false; }
  }

  build() {
    Column({ space: 20 }) {
      Text(this.note).id('audio_haptic_status')
      Button('Execute requested real AudioHapticPlayer call').id('audio_haptic_run').enabled(!this.busy)
        .onClick(() => { this.execute(); })
    }.width('100%').height('100%').padding(24)
  }
}
