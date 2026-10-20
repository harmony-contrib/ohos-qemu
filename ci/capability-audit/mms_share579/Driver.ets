/* SPDX-License-Identifier: Apache-2.0; records actual API outcomes only. */
import Want from '@ohos.app.ability.Want';
import fs from '@ohos.file.fs';
import fileUri from '@ohos.file.fileuri';
import util from '@ohos.util';
import { BusinessError } from '@ohos.base';
import { common } from '@kit.AbilityKit';
import { Journal, Request, ROLE, RUN } from './Journal';

interface Owned { run: string; boot: string; archive: string; object: string; caseId: string;
  uri: string; path: string; inode: string; content: string; }
const OWNER: string = 'org.harmonycontrib.urilifetime579.owner';
const RECEIVER: string = 'org.harmonycontrib.urilifetime579.receiver';
const MIME: string = 'application/vnd.harmonycontrib.uri579';

export class Driver {
  constructor(private context: common.UIAbilityContext, private want: Want, private r: Request) {}
  private emit(event: string, value: string = 'null', code: number = 0): void { Journal.record(this.r, event, value, code); }
  private content(): string {
    const text: string = 'URI579/' + RUN + '/' + this.r.object + '/' + this.r.caseId + '/original';
    return this.r.caseId.startsWith('mms-') ? 'BEGIN:VCARD\r\nVERSION:3.0\r\nFN:' + text + '\r\nEND:VCARD\r\n' : text;
  }
  private path(): string { return this.context.getApplicationContext().filesDir + '/uri579-source-' + RUN + '-' + this.r.object +
    (this.r.caseId.startsWith('mms-') ? '.vcf' : '.txt'); }
  private statePath(): string { return this.context.getApplicationContext().filesDir + '/uri579-owned-' + RUN + '-' + this.r.object + '.json'; }
  private write(path: string, content: string): void {
    if (fs.accessSync(path)) { throw new Error('Refuse existing owned file'); }
    const bytes = new util.TextEncoder().encodeInto(content);
    const file = fs.openSync(path, fs.OpenMode.CREATE | fs.OpenMode.WRITE_ONLY | fs.OpenMode.NOFOLLOW);
    try {
      let done: number = 0;
      while (done < bytes.byteLength) {
        const n = fs.writeSync(file.fd, bytes.slice(done).buffer);
        if (n <= 0 || n > bytes.byteLength - done) { throw new Error('Short file write'); }
        done += n;
      }
      fs.fsyncSync(file.fd);
    } finally { fs.closeSync(file); }
  }
  private text(uri: string): string {
    const file = fs.openSync(uri, fs.OpenMode.READ_ONLY);
    try {
      const size = fs.statSync(file.fd).size;
      if (size < 1 || size > 4096) { throw new Error('Unexpected bounded payload size'); }
      const all = new Uint8Array(size);
      let done: number = 0;
      while (done < size) {
        const part = new ArrayBuffer(size - done); const n = fs.readSync(file.fd, part);
        if (n <= 0 || n > size - done) { throw new Error('Short payload read'); }
        all.set(new Uint8Array(part).slice(0, n), done); done += n;
      }
      return new util.TextDecoder('utf-8', { fatal: true }).decodeToString(all);
    } finally { fs.closeSync(file); }
  }
  private owned(): Owned {
    if (ROLE !== 'owner') { throw new Error('Only actual file owner can read metadata'); }
    const state: Owned = JSON.parse(fs.readTextSync(this.statePath())) as Owned;
    if (state.run !== RUN || state.boot !== this.r.boot || state.archive !== this.r.archive ||
        state.object !== this.r.object || state.caseId !== this.r.caseId || state.path !== this.path() ||
        state.uri !== fileUri.getUriFromPath(this.path()) || state.content !== this.content() ||
        fs.statSync(state.path).ino.toString() !== state.inode || this.text(state.uri) !== state.content) {
      throw new Error('Owned source changed; preserve it');
    }
    return state;
  }
  private actualAccess(uri: string): void {
    // Every attempt opens a new FD, closes it, and retains the actual error.
    // A cached FD or original receiver's content string cannot satisfy replay.
    try { this.emit('file.read', JSON.stringify({ uri: uri, content: this.text(uri) })); }
    catch (error) {
      const e = error as BusinessError;
      this.emit('file.read', JSON.stringify({ uri: uri, codeType: typeof e.code, message: e.message }),
        typeof e.code === 'number' ? e.code : -1);
    }
    try {
      const file = fs.openSync(uri, fs.OpenMode.WRITE_ONLY);
      fs.closeSync(file.fd); this.emit('file.write', JSON.stringify({ uri: uri, noModification: true }));
    } catch (error) {
      const e = error as BusinessError;
      this.emit('file.write', JSON.stringify({ uri: uri, codeType: typeof e.code, message: e.message }),
        typeof e.code === 'number' ? e.code : -1);
    }
  }
  private actualUri(): string {
    const uri: string = this.r.action === 'consume' ? (this.want.uri ?? '') : this.r.uri;
    const suffix = '/uri579-source-' + RUN + '-' + this.r.object + (this.r.caseId.startsWith('mms-') ? '.vcf' : '.txt');
    if (!uri.startsWith('file://' + OWNER + '/') || !uri.endsWith(suffix) || uri.length > 2048) {
      throw new Error('Not the fixed owner/object URI');
    }
    return uri;
  }
  private async invokeShare(): Promise<void> {
    const state = this.owned();
    const delivery: Request = { ...this.r, action: 'consume', operation: this.r.delivery, uri: state.uri };
    const params: Record<string, Object> = { type: MIME, uri: state.uri, 'ability.params.stream': [state.uri],
      'ability.subject': JSON.stringify(delivery),
      'ability.want.params.uriPermissionFlag': this.r.caseId === 'share-write-close' ? 3 : 1 };
    this.emit('share.call', JSON.stringify({ type: 'share', parameters: params }));
    let settled: boolean = false;
    const callback: common.AbilityStartCallback = {
      onResult: (result: common.AbilityResult): void => {
        this.emit(settled ? 'share.duplicate' : 'share.result', JSON.stringify(result)); settled = true;
      },
      onError: (code: number, name: string, message: string): void => {
        this.emit(settled ? 'share.duplicate' : 'share.error', JSON.stringify({ name: name, message: message }), code); settled = true;
      }
    };
    await this.context.startAbilityByType('share', params, callback);
    this.emit('share.opened');
  }
  private async invokeMms(): Promise<void> {
    const uri: string = ROLE === 'owner' ? this.owned().uri : this.actualUri();
    if (ROLE === 'foreign' && this.r.caseId !== 'mms-forged-owner') { throw new Error('No arbitrary foreign grant'); }
    const want: Want = { action: 'ohos.want.action.sendData', type: 'text/vcard',
      flags: this.r.caseId === 'mms-no-grant' ? 0 : 1, uri: uri,
      bundleName: 'com.ohos.mms', moduleName: 'entry', abilityName: 'com.ohos.mms.MainAbility',
      parameters: { 'ability.params.stream': [uri] } };
    this.emit('mms.call', JSON.stringify(want));
    try { await this.context.startAbility(want); this.emit('mms.opened'); }
    catch (error) {
      const e = error as BusinessError;
      this.emit('mms.error', JSON.stringify({ codeType: typeof e.code, message: e.message }), typeof e.code === 'number' ? e.code : -1);
    }
  }
  async execute(): Promise<void> {
    try {
      switch (this.r.action) {
        case 'create': {
          if (ROLE !== 'owner') { throw new Error('Only ordinary owner creates its own file'); }
          this.write(this.path(), this.content());
          const state: Owned = { run: RUN, boot: this.r.boot, archive: this.r.archive, object: this.r.object,
            caseId: this.r.caseId, path: this.path(), uri: fileUri.getUriFromPath(this.path()),
            inode: fs.statSync(this.path()).ino.toString(), content: this.content() };
          this.write(this.statePath(), JSON.stringify(state)); this.emit('owner.file', JSON.stringify(state)); break;
        }
        case 'owner-read': this.emit('owner.file', JSON.stringify(this.owned())); break;
        case 'share': await this.invokeShare(); break;
        case 'mms': await this.invokeMms(); break;
        case 'consume':
          if (ROLE !== 'receiver' || this.want.action !== 'ohos.want.action.sendData' || this.want.type !== MIME ||
              this.want.flags !== 1) { throw new Error('Actual READ-only Share route required'); }
          this.emit('receiver.incoming', JSON.stringify(this.want)); this.actualAccess(this.actualUri()); break;
        case 'probe':
          if (ROLE === 'owner' || this.want.uri !== undefined || (this.want.flags ?? 0) !== 0 ||
              this.want.parameters?.['ability.params.stream'] !== undefined) { throw new Error('Probe carries text only, no grant'); }
          this.emit('probe.incoming', JSON.stringify(this.want)); this.actualAccess(this.actualUri()); break;
        case 'cleanup': {
          const state = this.owned(); fs.unlinkSync(state.path); fs.unlinkSync(this.statePath());
          this.emit('owner.deleted', JSON.stringify({ uri: state.uri, path: state.path, exists: fs.accessSync(state.path) })); break;
        }
        default: throw new Error('Unknown finite action');
      }
      this.emit('done');
    } catch (error) {
      const e = error as BusinessError;
      this.emit('fixture.error', JSON.stringify({ message: e.message, codeType: typeof e.code }), typeof e.code === 'number' ? e.code : -1);
      throw error as Error;
    }
  }
  async close(): Promise<void> {
    if (ROLE === 'owner') { throw new Error('Receiver control only'); }
    this.emit('receiver.close');
    await this.context.terminateSelf();
  }
}
