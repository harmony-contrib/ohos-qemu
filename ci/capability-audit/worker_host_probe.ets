// SPDX-License-Identifier: Apache-2.0
// A fresh HAP process selects only one Worker version: the runtime choice is sticky.
import worker, { __EVENT__ } from '@ohos.worker';
import fs from '@ohos.file.fs';

interface Request { nonce: string; generation: number; sequence: number; action: string; buffer: ArrayBuffer; }
interface Reply {
  nonce: string; generation: number; sequence: number; kind: string; buffer: ArrayBuffer;
  portName: string; portUsable: boolean; otherPortAbsent: boolean; inputBytes: number;
}
interface Identity {
  type: string; run_id: string; worker_class: string; port_name: string;
  main_parent_port_absent: boolean; main_worker_port_absent: boolean;
}
interface Step { type: string; run_id: string; generation: number; name: string; actual: number; }
interface Transfer {
  type: string; run_id: string; generation: number; sequence: number; input_bytes: number;
  detached_bytes: number; detached_length_error: string; detached_access_error: string;
}
interface Data {
  type: string; run_id: string; generation: number; sequence: number; nonce: string; words: number[];
  bytes: number; input_bytes: number; port_name: string; port_usable: boolean; other_port_absent: boolean;
}
interface Summary { type: string; run_id: string; cycles: number; passed: boolean; scope: string; }
interface ErrorRow { type: string; run_id: string; detail: string; }

@Entry
@Component
struct Index {
  @State private note: string = 'Testing __CLASS__ worker-thread port';
  private current?: worker.__CLASS__;
  private done: boolean = false;
  private watchdog: number = -1;
  private runId: string = '__RUN__';
  private path: string = '/data/storage/el2/base/files/worker-__MODE__-__RUN__-results.log';

  private append(value: string): void {
    const file = fs.openSync(this.path, fs.OpenMode.WRITE_ONLY | fs.OpenMode.CREATE | fs.OpenMode.APPEND);
    try { fs.writeSync(file.fd, value + '\n'); } finally { fs.closeSync(file); }
  }
  private step(generation: number, name: string, actual: number): void {
    const row: Step = { type: 'step', run_id: this.runId, generation, name, actual };
    this.append(JSON.stringify(row));
  }
  private fail(detail: string): void {
    if (this.done) { return; }
    const row: ErrorRow = { type: 'error', run_id: this.runId, detail };
    this.append(JSON.stringify(row));
    this.finish(false);
    this.current?.terminate();
  }
  private finish(passed: boolean): void {
    if (this.done) { return; }
    this.done = true;
    if (this.watchdog >= 0) { clearTimeout(this.watchdog); }
    const row: Summary = { type: 'summary', run_id: this.runId, cycles: passed ? 2 : 0, passed,
                          scope: 'ordinary_worker_context_ports_and_transfer_lifecycle_only' };
    this.append(JSON.stringify(row));
    this.note = passed ? 'Two actual Worker generations completed' : 'Worker behavior failed';
  }
  private send(instance: worker.__CLASS__, generation: number, sequence: number): void {
    const buffer: ArrayBuffer = new ArrayBuffer(256);
    const words = new Uint32Array(buffer);
    const salt: number = parseInt(this.runId.substring(0, 8), 16);
    for (let i: number = 0; i < words.length; ++i) {
      words[i] = (salt + i * 257 + generation * 65537 + sequence * 17) >>> 0;
    }
    const message: Request = { nonce: this.runId, generation, sequence, action: 'transform', buffer };
    instance.postMessage(message, [buffer]);
    // OH7's ArrayBuffer getter rejects a detached buffer. Preserve the actual
    // error rather than pretending its byteLength returned zero. Creating a
    // new view must also reject the detached backing storage.
    let detachedBytes: number = -1;
    let lengthError: string = '';
    let accessError: string = '';
    try { detachedBytes = buffer.byteLength; } catch (error) { lengthError = error.toString(); }
    try { new Uint8Array(buffer); } catch (error) { accessError = error.name; }
    const row: Transfer = { type: 'transfer', run_id: this.runId, generation, sequence,
      input_bytes: 256, detached_bytes: detachedBytes, detached_length_error: lengthError,
      detached_access_error: accessError };
    this.append(JSON.stringify(row));
  }
  private cycle(generation: number): void {
    const instance = new worker.__CLASS__('entry/ets/workers/ApiWorker.ets', { name: 'qemu-api26-' + generation });
    this.current = instance;
    let nextSequence: number = 1;
    let acknowledged: boolean = false;
    this.step(generation, 'created', 1);
    instance.onerror = (): void => { this.fail('unexpected worker exception'); };
    instance.onmessageerror = (): void => { this.fail('unexpected message deserialization error'); };
    instance.onmessage = (event: __HOST_EVENT__): void => {
      if (this.done) { return; }
      const reply = event.data as Reply;
      if (reply.nonce !== this.runId || reply.generation !== generation || !reply.portUsable ||
          !reply.otherPortAbsent || reply.portName !== '__PORT__') {
        this.fail('worker context or challenge mismatch'); return;
      }
      if (reply.kind === 'closed' && nextSequence === 3) {
        acknowledged = true;
        this.step(generation, 'close_ack', 1);
        return;
      }
      if (reply.kind !== 'data' || reply.sequence !== nextSequence || reply.buffer.byteLength !== 256) {
        this.fail('unexpected data order or buffer size'); return;
      }
      const words = new Uint32Array(reply.buffer);
      const values: number[] = [];
      for (let i: number = 0; i < words.length; ++i) { values.push(words[i]); }
      const row: Data = { type: 'data', run_id: this.runId, generation, sequence: reply.sequence,
        nonce: reply.nonce, words: values, bytes: reply.buffer.byteLength, input_bytes: reply.inputBytes,
        port_name: reply.portName, port_usable: reply.portUsable, other_port_absent: reply.otherPortAbsent };
      this.append(JSON.stringify(row));
      ++nextSequence;
      if (nextSequence <= 2) { this.send(instance, generation, nextSequence); }
      else {
        const close: Request = { nonce: this.runId, generation, sequence: 3, action: 'close', buffer: new ArrayBuffer(0) };
        instance.postMessage(close);
      }
    };
    instance.onexit = (code: number): void => {
      if (this.done) { return; }
      this.step(generation, 'exit', code);
      if (code !== 0 || !acknowledged) { this.fail('not an acknowledged normal close'); return; }
      let deniedCode: number = 0;
      try {
        const closed: Request = { nonce: this.runId, generation, sequence: 4, action: 'closed', buffer: new ArrayBuffer(0) };
        instance.postMessage(closed);
      } catch (error) { deniedCode = error.code; }
      this.step(generation, 'post_after_exit_error', deniedCode);
      // The deprecated Worker preserves silent no-op behavior; ThreadWorker
      // reports its documented 10200004. Neither may dispatch a late message.
      if (deniedCode !== __POST_EXIT_CODE__) { this.fail('wrong closed Worker boundary'); return; }
      setTimeout((): void => {
        if (this.done) { return; }
        this.step(generation, 'post_after_exit_quiet', 1);
        if (generation === 1) { this.cycle(2); } else { this.finish(true); }
      }, 500);
    };
    this.send(instance, generation, 1);
  }
  aboutToAppear(): void {
    const file = fs.openSync(this.path, fs.OpenMode.WRITE_ONLY | fs.OpenMode.CREATE | fs.OpenMode.TRUNC);
    fs.closeSync(file);
    const identity: Identity = { type: 'identity', run_id: this.runId, worker_class: '__CLASS__', port_name: '__PORT__',
      main_parent_port_absent: typeof worker.parentPort === 'undefined',
      main_worker_port_absent: typeof worker.workerPort === 'undefined' };
    this.append(JSON.stringify(identity));
    this.watchdog = setTimeout((): void => { this.fail('actual Worker lifecycle timed out'); }, 20000);
    try { this.cycle(1); } catch (error) { this.fail('Worker setup failed: ' + error.toString()); }
  }
  build() { Column() { Text(this.note) }.width('100%').height('100%') }
}
