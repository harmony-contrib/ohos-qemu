import { common } from '@kit.AbilityKit';
import fs from '@ohos.file.fs';
import process from '@ohos.process';
import { BusinessError } from '@ohos.base';
import { AudioHapticProbe, HapticRequest } from './AudioHapticProbe';

interface Envelope {
  role: string;
  phase: string;
  request: HapticRequest;
  following_phase?: string;
  following_request?: HapticRequest;
  following_delay_ms?: number;
}

@Entry
@Component
struct Index {
  @State private busy: boolean = false;
  @State private status: string = 'ready';
  private probe: AudioHapticProbe | undefined = undefined;
  private boot: string = '';

  private async execute(): Promise<void> {
    if (this.busy) { return; }
    this.busy = true;
    let operation: string = '';
    try {
      const context = getContext(this) as common.UIAbilityContext;
      const path = context.filesDir + '/audio-haptic-request.json';
      if (fs.statSync(path).size > 65536) { throw new Error('Oversized explicit request'); }
      const envelope = JSON.parse(fs.readTextSync(path)) as Envelope;
      const request = envelope.request;
      operation = request.operation_id;
      if (envelope.role !== '__HAPTIC_ROLE__' || request.run_id !== '__HAPTIC_RUN__' ||
        !/^[a-z0-9-]{1,80}$/.test(envelope.phase)) { throw new Error('Unexpected role/run/phase'); }
      const following = envelope.following_request;
      const delay = envelope.following_delay_ms;
      if (following !== undefined && (request.action !== 'start' ||
        (following.action !== 'stop' && following.action !== 'release') ||
        following.run_id !== request.run_id || following.boot_id !== request.boot_id ||
        following.operation_id === request.operation_id || envelope.following_phase === undefined ||
        !/^[a-z0-9-]{1,80}$/.test(envelope.following_phase) || delay === undefined ||
        !Number.isInteger(delay) || delay < 1 || delay > 10000)) { throw new Error('Invalid explicit lifecycle pair'); }
      if (following === undefined && (envelope.following_phase !== undefined || delay !== undefined)) {
        throw new Error('Incomplete explicit lifecycle pair');
      }
      if (this.probe === undefined) {
        this.boot = request.boot_id;
        this.probe = new AudioHapticProbe(context.filesDir, request.run_id, request.boot_id);
      }
      if (this.boot !== request.boot_id) { throw new Error('Retained caller cannot change boot'); }
      const current = this.probe;
      this.status = 'running|' + operation;
      await current.step(request);
      if (following !== undefined && delay !== undefined) {
        // The same real click authorizes these two fresh operations. This
        // bounded wait avoids host screenshot/HDC work between Start and Stop.
        await new Promise<void>((resolve) => { setTimeout(() => { resolve(); }, delay); });
        operation = following.operation_id;
        this.status = 'running|' + operation;
        await current.step(following);
      }
      this.status = 'done|' + operation;
    } catch (caught) {
      const error = caught as BusinessError;
      this.status = 'error|' + operation + '|' + String(error.code) + '|' + error.message;
    } finally { this.busy = false; }
  }

  build() {
    Column({ space: 20 }) {
      Text('AudioHaptic ordinary __HAPTIC_ROLE__').id('audio_haptic_title')
      Text('pid=' + process.pid).id('audio_haptic_pid')
      Text(this.status).id('audio_haptic_status')
      Button('Run explicit AudioHaptic operation').id('audio_haptic_run').enabled(!this.busy)
        .onClick(() => { this.execute(); })
    }.width('100%').height('100%').padding(24)
  }
}
