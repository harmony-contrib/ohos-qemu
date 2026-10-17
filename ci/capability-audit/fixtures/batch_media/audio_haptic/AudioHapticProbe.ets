/* Ordinary public API caller candidate. Requires an actual UI host and SDK build.
 * Journals API observations only; the API exposes no first-frame/vibrator callback.
 */
import audioHaptic from '@ohos.multimedia.audioHaptic';
import audio from '@ohos.multimedia.audio';
import fs from '@ohos.file.fs';
import util from '@ohos.util';
import process from '@ohos.process';
import bundleManager from '@ohos.bundle.bundleManager';
import abilityAccessCtrl from '@ohos.abilityAccessCtrl';
import { BusinessError } from '@ohos.base';

export interface HapticRequest {
  schema_version: number;
  run_id: string;
  boot_id: string;
  operation_id: string;
  action: string;
  audio_path: string;
  haptic_path: string;
  fast: boolean;
  mute_audio: boolean;
  mute_haptics: boolean;
  loop: boolean;
  volume: number;
}

interface HapticRow {
  schema_version: number;
  run_id: string;
  boot_id: string;
  operation_id: string;
  sequence: number;
  timestamp_ms: number;
  uid: number;
  token_id: number;
  player_epoch: number;
  event: string;
  api: string;
  value_json: string;
  error_code: number;
  error_message: string;
}

export class AudioHapticProbe {
  private readonly manager: audioHaptic.AudioHapticManager = audioHaptic.getAudioHapticManager();
  private player: audioHaptic.AudioHapticPlayer | undefined = undefined;
  private released: boolean = false;
  private sourceId: number = -1;
  private epoch: number = 0;
  private sequence: number = 0;
  private activeOperation: string = '';
  private seen: Set<string> = new Set<string>();
  private busy: boolean = false;
  private token: number;
  private readonly path: string;
  private readonly run: string;
  private readonly boot: string;

  constructor(filesDir: string, runId: string, bootId: string) {
    if (!/^[a-f0-9]{32}$/.test(runId) || !/^[a-f0-9-]{36}$/.test(bootId)) {
      throw new Error('Fresh run and actual boot identifiers required');
    }
    this.run = runId;
    this.boot = bootId;
    this.path = filesDir + '/audio-haptic-' + runId + '.jsonl';
    // A caller restart must use a fresh run, rather than overwrite an old trace.
    if (fs.accessSync(this.path)) { throw new Error('Existing run journal'); }
    const info = bundleManager.getBundleInfoForSelfSync(bundleManager.BundleFlag.GET_BUNDLE_INFO_WITH_APPLICATION);
    this.token = info.appInfo.accessTokenId;
    if (this.token <= 0) { throw new Error('No actual self token'); }
  }

  private append(event: string, api: string, value: string, epoch: number = this.epoch,
    code: number = 0, message: string = ''): void {
    const row: HapticRow = { schema_version: 1, run_id: this.run, boot_id: this.boot,
      operation_id: this.activeOperation, sequence: ++this.sequence, timestamp_ms: Date.now(),
      uid: process.uid, token_id: this.token, player_epoch: epoch, event: event, api: api,
      value_json: value, error_code: code, error_message: message };
    const bytes = new util.TextEncoder().encodeInto(JSON.stringify(row) + '\n');
    const file = fs.openSync(this.path, fs.OpenMode.CREATE | fs.OpenMode.WRITE_ONLY | fs.OpenMode.APPEND | fs.OpenMode.NOFOLLOW);
    try {
      let done: number = 0;
      while (done < bytes.byteLength) {
        const amount = fs.writeSync(file.fd, bytes.slice(done).buffer);
        if (amount <= 0 || amount > bytes.byteLength - done) { throw new Error('Short journal write'); }
        done += amount;
      }
    } finally { fs.closeSync(file); }
  }

  private requirePlayer(): audioHaptic.AudioHapticPlayer {
    const player = this.player;
    if (player === undefined) { throw new Error('No created player'); }
    return player;
  }

  // Run once per explicit UI request. The host records actual UI/operation timing.
  async step(request: HapticRequest): Promise<void> {
    if (this.busy || request.schema_version !== 1 || request.run_id !== this.run || request.boot_id !== this.boot ||
      !/^[a-f0-9]{32}$/.test(request.operation_id) || this.seen.has(request.operation_id)) {
      throw new Error('Concurrent, stale or invalid operation');
    }
    this.busy = true;
    this.seen.add(request.operation_id);
    this.activeOperation = request.operation_id;
    this.append('begin', request.action, JSON.stringify(request));
    try {
      if (request.action === 'access') {
        const access = abilityAccessCtrl.createAtManager().checkAccessTokenSync(this.token, 'ohos.permission.VIBRATE');
        this.append('return', 'abilityAccessCtrl.checkAccessTokenSync', JSON.stringify(access));
      } else if (request.action === 'register') {
        this.sourceId = await this.manager.registerSource(request.audio_path, request.haptic_path);
        this.append('return', 'AudioHapticManager.registerSource', JSON.stringify(this.sourceId));
      } else if (request.action === 'create') {
        if (this.player !== undefined && !this.released) { throw new Error('Release existing player before replacement'); }
        const mode = request.fast ? audioHaptic.AudioLatencyMode.AUDIO_LATENCY_MODE_FAST :
          audioHaptic.AudioLatencyMode.AUDIO_LATENCY_MODE_NORMAL;
        this.manager.setAudioLatencyMode(this.sourceId, mode);
        this.append('return', 'AudioHapticManager.setAudioLatencyMode', JSON.stringify(mode));
        this.manager.setStreamUsage(this.sourceId, audio.StreamUsage.STREAM_USAGE_MUSIC);
        this.append('return', 'AudioHapticManager.setStreamUsage', JSON.stringify(audio.StreamUsage.STREAM_USAGE_MUSIC));
        const player = await this.manager.createPlayer(this.sourceId,
          { muteAudio: request.mute_audio, muteHaptics: request.mute_haptics });
        this.player = player;
        this.released = false;
        const epoch = ++this.epoch;
        this.append('return', 'AudioHapticManager.createPlayer', '{}', epoch);
        player.on('endOfStream', () => {
          this.append('callback', 'AudioHapticPlayer.endOfStream', '{}', epoch);
        });
        player.on('audioInterrupt', (event: audio.InterruptEvent) => {
          this.append('callback', 'AudioHapticPlayer.audioInterrupt', JSON.stringify(event), epoch);
        });
        this.append('return', 'AudioHapticPlayer.isMuted.audio',
          JSON.stringify(player.isMuted(audioHaptic.AudioHapticType.AUDIO_HAPTIC_TYPE_AUDIO)), epoch);
        this.append('return', 'AudioHapticPlayer.isMuted.haptic',
          JSON.stringify(player.isMuted(audioHaptic.AudioHapticType.AUDIO_HAPTIC_TYPE_HAPTIC)), epoch);
      } else if (request.action === 'start') {
        await this.requirePlayer().start();
        this.append('return', 'AudioHapticPlayer.start', '{}');
      } else if (request.action === 'stop') {
        await this.requirePlayer().stop();
        this.append('return', 'AudioHapticPlayer.stop', '{}');
      } else if (request.action === 'loop') {
        await this.requirePlayer().setLoop(request.loop);
        this.append('return', 'AudioHapticPlayer.setLoop', JSON.stringify(request.loop));
      } else if (request.action === 'volume') {
        await this.requirePlayer().setVolume(request.volume);
        this.append('return', 'AudioHapticPlayer.setVolume', JSON.stringify(request.volume));
      } else if (request.action === 'release') {
        await this.requirePlayer().release();
        this.released = true;
        this.append('return', 'AudioHapticPlayer.release', '{}');
      } else if (request.action === 'unregister') {
        await this.manager.unregisterSource(this.sourceId);
        this.append('return', 'AudioHapticManager.unregisterSource', JSON.stringify(this.sourceId));
      } else {
        throw new Error('Unknown explicit action');
      }
      this.append('complete', request.action, '{}');
    } catch (caught) {
      const error = caught as BusinessError;
      this.append('error', request.action, '{}', this.epoch, error.code ?? -1, error.message ?? String(error));
      throw new Error('AudioHaptic operation failed: ' + String(error.code) + ': ' + error.message);
    } finally { this.busy = false; }
  }
}
