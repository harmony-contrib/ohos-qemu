import { common } from '@kit.AbilityKit';
import fs from '@ohos.file.fs';
import process from '@ohos.process';
import { BusinessError } from '@ohos.base';
import { AudioHapticProbe, HapticRequest } from './AudioHapticProbe';

interface Envelope {
  role: string;
  phase: string;
  request: HapticRequest;
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
      if (this.probe === undefined) {
        this.boot = request.boot_id;
        this.probe = new AudioHapticProbe(context.filesDir, request.run_id, request.boot_id);
      }
      if (this.boot !== request.boot_id) { throw new Error('Retained caller cannot change boot'); }
      const current = this.probe;
      this.status = 'running|' + operation;
      await current.step(request);
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
