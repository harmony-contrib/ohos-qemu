// Native objects and real request completions; no mocked JS RPC or manual callback invocation.
import rpc from '@ohos.rpc';
import fs from '@ohos.file.fs';
import { BusinessError } from '@ohos.base';

const RUN: string = '__RPC_RUN_ID__';
let handled: number = 0;
let callbackCalls: number = 0;
function handle(code: number, data: rpc.MessageSequence, reply: rpc.MessageSequence): boolean {
  const nonce = data.readString();
  const payload = data.readInt();
  if (nonce !== RUN || code === 799) { return false; }
  handled++;
  reply.writeString(nonce);
  reply.writeInt(payload + code);
  return true;
}
class DerivedBase extends rpc.IRemoteObject {
  onRemoteMessageRequest(code: number, data: rpc.MessageSequence, reply: rpc.MessageSequence,
    options: rpc.MessageOption): boolean { return handle(code, data, reply); }
}
class DerivedConcrete extends rpc.RemoteObject {
  constructor() { super(RUN); }
  onRemoteMessageRequest(code: number, data: rpc.MessageSequence, reply: rpc.MessageSequence,
    options: rpc.MessageOption): boolean { return handle(code, data, reply); }
}
class Recipient implements rpc.DeathRecipient {
  calls: number = 0;
  onRemoteDied(): void { this.calls++; }
}
interface Row { runId: string; name: string; values: number[]; text: string; error: string; }
interface Completion { errorNull: boolean; errorType: string; errorCode: number; result?: rpc.RequestResult; }

@Entry
@Component
struct Index {
  @State private note: string = 'Checking native RPC';
  private readonly logPath: string = '/data/storage/el2/base/files/rpc-runtime-__RPC_RUN_ID__-results.log';
  private record(name: string, values: number[], text: string = '', error: string = ''): void {
    const row: Row = { runId: RUN, name, values, text, error };
    const file = fs.openSync(this.logPath, fs.OpenMode.CREATE | fs.OpenMode.WRITE_ONLY | fs.OpenMode.APPEND);
    try { fs.writeSync(file.fd, JSON.stringify(row) + '\n'); } finally { fs.closeSync(file); }
    this.note = name;
  }
  private errorCode(action: () => void): number {
    try { action(); return -1; } catch (error) {
      const value = error as BusinessError;
      return typeof value.code === 'number' ? value.code : -2;
    }
  }
  private async request(object: rpc.IRemoteObject, name: string, code: number): Promise<void> {
    const data = rpc.MessageSequence.create(); const reply = rpc.MessageSequence.create();
    try {
      data.writeString(RUN); data.writeInt(37);
      const before = handled;
      const result = await object.sendMessageRequest(code, data, reply, new rpc.MessageOption());
      this.record(name, [result.errCode, result.code, result.data === data ? 1 : 0,
        result.reply === reply ? 1 : 0, handled - before], reply.readString());
      this.record(name + '.payload', [reply.readInt()]);
    } finally { data.reclaim(); reply.reclaim(); }
  }
  private async callback(object: rpc.IRemoteObject, name: string, code: number): Promise<void> {
    const data = rpc.MessageSequence.create(); const reply = rpc.MessageSequence.create();
    try {
      data.writeString(RUN); data.writeInt(37);
      const before = handled;
      const value = await new Promise<Completion>((resolve, reject): void => {
        const timer = setTimeout((): void => { reject(new Error('native callback timeout')); }, 10000);
        object.sendMessageRequest(code, data, reply, new rpc.MessageOption(),
          (error: BusinessError, result: rpc.RequestResult): void => {
            callbackCalls++;
            clearTimeout(timer);
            resolve({ errorNull: error === null, errorType: typeof error,
              errorCode: error === null ? 0 : (typeof error.code === 'number' ? error.code : -2), result });
          });
      });
      if (code === 799) {
        this.record(name, [value.errorNull ? 1 : 0, value.errorCode,
          value.result === undefined ? 1 : 0, handled - before], value.errorType);
      } else {
        if (value.result === undefined) { throw new Error('missing native callback result'); }
        this.record(name, [value.errorNull ? 1 : 0, value.errorCode, value.result.errCode,
          value.result.code, value.result.data === data ? 1 : 0, value.result.reply === reply ? 1 : 0,
          handled - before], reply.readString());
        this.record(name + '.payload', [reply.readInt()]);
      }
    } finally { data.reclaim(); reply.reclaim(); }
  }
  private async legacyCallback(object: rpc.IRemoteObject): Promise<void> {
    const data = rpc.MessageParcel.create(); const reply = rpc.MessageParcel.create();
    try {
      data.writeString(RUN); data.writeInt(37);
      const before = handled;
      const result = await new Promise<rpc.SendRequestResult>((resolve, reject): void => {
        const timer = setTimeout((): void => { reject(new Error('legacy native callback timeout')); }, 10000);
        object.sendRequest(706, data, reply, new rpc.MessageOption(),
          (error: BusinessError, value: rpc.SendRequestResult): void => {
            callbackCalls++; clearTimeout(timer);
            if (error !== null || value === undefined) { reject(new Error('invalid legacy callback arguments')); }
            else { resolve(value); }
          });
      });
      this.record('legacy-callback', [result.errCode, result.code, result.data === data ? 1 : 0,
        result.reply === reply ? 1 : 0, handled - before], reply.readString());
      this.record('legacy-callback.payload', [reply.readInt()]);
    } finally { data.reclaim(); reply.reclaim(); }
  }
  private async run(): Promise<void> {
    let completed = 0;
    try {
      const base = new DerivedBase(); const concrete = new DerivedConcrete();
      const proxy = rpc.IPCSkeleton.getContextObject();
      this.record('constructors', [base instanceof rpc.IRemoteObject ? 1 : 0,
        base instanceof rpc.RemoteObject ? 1 : 0, concrete instanceof rpc.IRemoteObject ? 1 : 0,
        proxy instanceof rpc.IRemoteObject ? 1 : 0, proxy instanceof rpc.RemoteProxy ? 1 : 0]); completed++;
      this.record('descriptors', [base.getDescriptor() === '' ? 1 : 0,
        base.getInterfaceDescriptor() === '' ? 1 : 0, concrete.getDescriptor() === RUN ? 1 : 0,
        proxy.getDescriptor().length > 0 ? 1 : 0, base.isObjectDead() ? 1 : 0,
        concrete.isObjectDead() ? 1 : 0, proxy.isObjectDead() ? 1 : 0]); completed++;
      const sequence = rpc.MessageSequence.create();
      try {
        sequence.writeRemoteObject(base); sequence.writeRemoteObject(concrete); sequence.writeRemoteObject(proxy);
        sequence.writeRemoteObjectArray([base, concrete, proxy]);
        const first = sequence.readRemoteObject(); const second = sequence.readRemoteObject();
        const third = sequence.readRemoteObject(); const array = sequence.readRemoteObjectArray();
        this.record('sequence', [first === base ? 1 : 0, second === concrete ? 1 : 0,
          third === proxy ? 1 : 0, array.length, array[0] === base ? 1 : 0,
          array[1] === concrete ? 1 : 0, array[2] === proxy ? 1 : 0]); completed++;
      } finally { sequence.reclaim(); }
      const parcel = rpc.MessageParcel.create();
      try { this.record('parcel', [parcel.writeRemoteObject(base) ? 1 : 0,
        parcel.readRemoteObject() === base ? 1 : 0]); completed++; } finally { parcel.reclaim(); }
      const recipient = new Recipient();
      this.record('local-boundaries', [this.errorCode((): void => { base.registerDeathRecipient(recipient, 0); }),
        this.errorCode((): void => { base.unregisterDeathRecipient(recipient, 0); }),
        base.addDeathRecipient(recipient, 0) ? 1 : 0, base.removeDeathRecipient(recipient, 0) ? 1 : 0]); completed++;
      this.record('proxy-boundaries', [this.errorCode((): void => { proxy.getLocalInterface(RUN); })]);
      proxy.registerDeathRecipient(recipient, 0); proxy.unregisterDeathRecipient(recipient, 0);
      this.record('proxy-recipient', [recipient.calls]); completed++;
      await this.request(base, 'base-promise', 701); completed++;
      await this.request(concrete, 'concrete-promise', 702); completed++;
      await this.request(new DerivedBase(), 'recreated-promise', 703); completed++;
      await this.callback(base, 'base-callback', 704); completed++;
      await this.callback(concrete, 'concrete-callback', 705); completed++;
      await this.callback(base, 'failed-callback', 799); completed++;
      await this.legacyCallback(base); completed++;
      await new Promise<void>((resolve): void => { setTimeout(resolve, 100); });
      this.record('quiet', [recipient.calls, handled, callbackCalls]);
    } catch (error) { this.record('failed', [], '', (error as Error).message || 'native RPC failed'); }
    this.record('summary', [completed, completed === 13 ? 0 : 1]);
  }
  aboutToAppear(): void {
    const file = fs.openSync(this.logPath, fs.OpenMode.CREATE | fs.OpenMode.WRITE_ONLY | fs.OpenMode.TRUNC);
    fs.closeSync(file); this.run();
  }
  build() { Column() { Text(this.note) }.width('100%').height('100%') }
}
