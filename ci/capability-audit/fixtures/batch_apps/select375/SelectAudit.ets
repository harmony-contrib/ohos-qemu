/* SPDX-License-Identifier: Apache-2.0; observations only, never a pass oracle. */
import Want from '@ohos.app.ability.Want';
import { common } from '@kit.AbilityKit';
import { BusinessError } from '@ohos.base';
import bundleManager from '@ohos.bundle.bundleManager';
import process from '@ohos.process';
import fs from '@ohos.file.fs';
import fileUri from '@ohos.file.fileuri';
import util from '@ohos.util';

interface Request {
  schema_version: number; run_id: string; boot_id: string; archive_sha256: string;
  operation_id: string; case_id: string; phase: string; kind: string;
}
interface Row {
  schema_version: number; run_id: string; boot_id: string; archive_sha256: string;
  operation_id: string; case_id: string; phase: string; kind: string;
  role: string; uid: number; token_id: number; pid: number; sequence: number;
  timestamp_ms: number; event: string; api: string; value_json: string;
  error_code: number; error_message: string;
}
const RUN: string = '__RUN__';
const ROLE: string = '__ROLE__';
const CALLER: string = 'org.harmonycontrib.select375caller';
const TARGET_A: string = 'org.harmonycontrib.select375targeta';
const TARGET_B: string = 'org.harmonycontrib.select375targetb';
const CASES: string[] = ['read-a', 'read-b', 'write-a', 'no-grant-a', 'cancel', 'private-start', 'forged-sid'];

export class SelectAudit {
  private readonly context: common.UIAbilityContext;
  private readonly incoming: Want;
  private readonly request: Request;
  private readonly path: string;
  private readonly token: number;
  private sequence: number = 0;
  private api: string = 'request';
  static ready(serialized: string): string {
    if (serialized.length === 0 || serialized.length > 32768) { throw new Error('Invalid outer Want'); }
    const want: Want = JSON.parse(serialized) as Want;
    const raw = want.parameters?.request as string ?? '';
    if (raw.length === 0 || raw.length > 4096) { throw new Error('Missing owned request'); }
    const r: Request = JSON.parse(raw) as Request;
    if (r.schema_version !== 1 || r.run_id !== RUN || !/^[a-f0-9]{32}$/.test(r.operation_id) ||
        !/^[a-f0-9]{8}(-[a-f0-9]{4}){3}-[a-f0-9]{12}$/.test(r.boot_id) ||
        !/^[a-f0-9]{64}$/.test(r.archive_sha256) || !CASES.includes(r.case_id) ||
        !['caller', 'select', 'probe'].includes(r.kind) || !['run', 'choose', 'before', 'after'].includes(r.phase) ||
        (ROLE === 'caller' && (r.kind !== 'caller' || r.phase !== 'run')) ||
        (ROLE !== 'caller' && ((r.kind === 'select' && r.phase !== 'choose') ||
          (r.kind === 'probe' && !['before', 'after'].includes(r.phase)) || r.kind === 'caller'))) {
      throw new Error('Foreign or invalid select request');
    }
    return r.run_id + '/' + r.operation_id + '/' + r.case_id + '/' + r.phase;
  }
  constructor(context: common.UIAbilityContext, serialized: string) {
    SelectAudit.ready(serialized);
    this.incoming = JSON.parse(serialized) as Want;
    this.request = JSON.parse(this.incoming.parameters?.request as string) as Request;
    this.context = context;
    const self = bundleManager.getBundleInfoForSelfSync(bundleManager.BundleFlag.GET_BUNDLE_INFO_WITH_APPLICATION);
    const bundle: string = ROLE === 'caller' ? CALLER : (ROLE === 'target_a' ? TARGET_A : TARGET_B);
    this.token = self.appInfo.accessTokenId;
    if (self.name !== bundle || this.token <= 0 || Math.floor(process.uid / 200000) !== 100) {
      throw new Error('Actual ordinary account100 identity required');
    }
    this.path = context.getApplicationContext().filesDir + '/select375-' + RUN + '-' + this.request.boot_id + '.jsonl';
    if (fs.accessSync(this.path)) {
      const stat = fs.statSync(this.path);
      if (stat.size > 4194304) { throw new Error('Oversized select journal'); }
      const text: string = fs.readTextSync(this.path);
      if (!text.endsWith('\n')) { throw new Error('Truncated select journal'); }
      for (const line of text.trimEnd().split('\n')) {
        const row: Row = JSON.parse(line) as Row;
        if (row.run_id !== RUN || row.boot_id !== this.request.boot_id || row.role !== ROLE ||
            row.archive_sha256 !== this.request.archive_sha256 || row.sequence !== ++this.sequence) {
          throw new Error('Foreign or reordered prior journal');
        }
        if (row.operation_id === this.request.operation_id && row.phase === this.request.phase) {
          throw new Error('Duplicate owned operation/phase');
        }
      }
    }
    this.record('begin', 'request', JSON.stringify(this.request));
    this.record('incoming', 'UIAbility.Want', JSON.stringify(this.incoming));
  }
  identity(): string { return SelectAudit.ready(JSON.stringify(this.incoming)); }
  private record(event: string, api: string, value: string, code: number = 0, message: string = ''): void {
    const r = this.request;
    const row: Row = { schema_version: 1, run_id: RUN, boot_id: r.boot_id, archive_sha256: r.archive_sha256,
      operation_id: r.operation_id, case_id: r.case_id, phase: r.phase, kind: r.kind, role: ROLE,
      uid: process.uid, token_id: this.token, pid: process.pid, sequence: ++this.sequence, timestamp_ms: Date.now(),
      event: event, api: api, value_json: value, error_code: code, error_message: message };
    const bytes = new util.TextEncoder().encodeInto(JSON.stringify(row) + '\n');
    const f = fs.openSync(this.path, fs.OpenMode.CREATE | fs.OpenMode.WRITE_ONLY | fs.OpenMode.APPEND | fs.OpenMode.NOFOLLOW);
    try { this.writeAll(f.fd, bytes); fs.fsyncSync(f.fd); } finally { fs.closeSync(f); }
  }
  private writeAll(fd: number, bytes: Uint8Array): void {
    let done: number = 0;
    while (done < bytes.byteLength) {
      const size = fs.writeSync(fd, bytes.slice(done).buffer);
      if (size <= 0 || size > bytes.byteLength - done) { throw new Error('Short owned file write'); }
      done += size;
    }
  }
  private text(uri: string): string {
    const f = fs.openSync(uri, fs.OpenMode.READ_ONLY);
    try {
      const size = fs.statSync(f.fd).size;
      if (size < 1 || size > 4096) { throw new Error('Unexpected owned payload size'); }
      const buffer = new ArrayBuffer(size);
      let done: number = 0;
      while (done < size) {
        const part = new ArrayBuffer(size - done);
        const count = fs.readSync(f.fd, part);
        if (count <= 0 || count > size - done) { throw new Error('Short owned payload read'); }
        new Uint8Array(buffer).set(new Uint8Array(part).slice(0, count), done);
        done += count;
      }
      return new util.TextDecoder('utf-8', { fatal: true }).decodeToString(new Uint8Array(buffer));
    } finally { fs.closeSync(f); }
  }
  private payload(suffix: string): string {
    return 'SELECT375/' + RUN + '/' + this.request.operation_id + '/' + this.request.case_id + '/' + suffix;
  }
  private phase(kind: string, phase: string): Request {
    const r = this.request;
    return { schema_version: 1, run_id: RUN, boot_id: r.boot_id, archive_sha256: r.archive_sha256,
      operation_id: r.operation_id, case_id: r.case_id, kind: kind, phase: phase };
  }
  private target(): string { return this.request.case_id === 'read-b' ? TARGET_B : TARGET_A; }
  private async foreign(uri: string, phase: string): Promise<void> {
    const other: string = this.target() === TARGET_A ? TARGET_B : TARGET_A;
    const want: Want = { bundleName: other, moduleName: 'entry', abilityName: 'EntryAbility', flags: 0,
      parameters: { request: JSON.stringify(this.phase('probe', phase)), probe_uri: uri } };
    this.api = 'UIAbilityContext.startAbilityForResult';
    this.record('probe_call', this.api, JSON.stringify(want));
    const result = await this.context.startAbilityForResult(want);
    this.record('probe_result', this.api, JSON.stringify(result));
  }
  private access(uri: string, write: boolean, mutate: boolean): void {
    const event: string = write ? 'write' : 'read';
    const api: string = write ? 'fileIo.openSync/writeSync' : 'fileIo.openSync/readSync';
    try {
      if (!write) { this.record(event, api, JSON.stringify(this.text(uri))); return; }
      const f = fs.openSync(uri, fs.OpenMode.WRITE_ONLY);
      try {
        if (mutate) { this.writeAll(f.fd, new util.TextEncoder().encodeInto(this.payload('modified'))); fs.fsyncSync(f.fd); }
      } finally { fs.closeSync(f); }
      this.record(event, api, JSON.stringify(mutate ? this.payload('modified') : 'opened_without_modification'));
    } catch (error) {
      const e = error as BusinessError;
      this.record(event, api, 'null', typeof e.code === 'number' ? e.code : -1, e.message);
    }
  }
  private async targetExecute(): Promise<void> {
    const r = this.request;
    const probe: boolean = r.kind === 'probe';
    const uri: string = probe ? this.incoming.parameters?.probe_uri as string ?? '' : this.incoming.uri ?? '';
    if (!uri.startsWith('file://' + CALLER + '/') || uri.indexOf('/select375-' + RUN + '-' + r.operation_id + '.txt') < 0) {
      throw new Error('Foreign payload URI');
    }
    if (probe && ((this.incoming.flags ?? 0) !== 0 || this.incoming.uri !== undefined)) {
      throw new Error('Probe must carry only URI text without a grant');
    }
    this.access(uri, false, false);
    this.access(uri, true, !probe && r.case_id === 'write-a');
    const result: common.AbilityResult = { resultCode: ROLE === 'target_a' ? 37501 : 37502,
      want: { parameters: { run_id: RUN, operation_id: r.operation_id, case_id: r.case_id,
        phase: r.phase, role: ROLE, receipt: this.payload('result-' + ROLE + '-' + r.phase) } } };
    this.api = 'UIAbilityContext.terminateSelfWithResult';
    this.record('return', this.api, JSON.stringify(result));
    this.record('complete', '', 'null');
    await this.context.terminateSelfWithResult(result);
  }
  private async callerExecute(): Promise<void> {
    const r = this.request;
    if (['private-start', 'forged-sid'].includes(r.case_id)) {
      const want: Want = { bundleName: 'com.ohos.settings', abilityName: 'PickerDialog' };
      if (r.case_id === 'forged-sid') { want.parameters = { dialogSessionId: 'legacy_picker_' + r.operation_id }; }
      this.api = 'UIAbilityContext.startAbility';
      this.record('private_call', this.api, JSON.stringify(want));
      try { await this.context.startAbility(want); this.record('private_resolve', this.api, 'null'); }
      catch (error) { const e = error as BusinessError; this.record('private_reject', this.api, 'null', typeof e.code === 'number' ? e.code : -1, e.message); }
      return;
    }
    const path: string = this.context.getApplicationContext().filesDir + '/select375-' + RUN + '-' + r.operation_id + '.txt';
    this.api = 'fileIo.openSync/writeSync';
    if (fs.accessSync(path)) { throw new Error('Owned payload already exists; preserve it'); }
    const f = fs.openSync(path, fs.OpenMode.CREATE | fs.OpenMode.WRITE_ONLY | fs.OpenMode.NOFOLLOW);
    try { this.writeAll(f.fd, new util.TextEncoder().encodeInto(this.payload('original'))); fs.fsyncSync(f.fd); }
    finally { fs.closeSync(f); }
    const originalStat = fs.statSync(path);
    const uri: string = fileUri.getUriFromPath(path);
    this.record('owned', 'fileUri.getUriFromPath', JSON.stringify(uri));
    this.record('owner_before', 'fileIo.openSync/readSync', JSON.stringify(this.text(uri)));
    if (r.case_id !== 'cancel') { await this.foreign(uri, 'before'); }
    const flags: number = r.case_id === 'write-a' ? 3 : (r.case_id === 'no-grant-a' ? 0 : 1);
    const want: Want = { action: 'ohos.want.action.select', uri: uri,
      type: 'application/vnd.harmonycontrib.select375', entities: ['org.harmonycontrib.select375'], flags: flags,
      parameters: { request: JSON.stringify(this.phase('select', 'choose')) } };
    this.api = 'UIAbilityContext.startAbilityForResult';
    this.record('select_call', this.api, JSON.stringify(want));
    const result = await this.context.startAbilityForResult(want);
    this.record('select_result', this.api, JSON.stringify(result));
    this.api = 'fileIo.openSync/readSync';
    this.record('owner_after', this.api, JSON.stringify(this.text(uri)));
    if (r.case_id !== 'cancel') { await this.foreign(uri, 'after'); }
    this.api = 'fileIo.unlinkSync';
    const finalStat = fs.statSync(path);
    if (finalStat.ino !== originalStat.ino || !finalStat.isFile() ||
        this.text(uri) !== this.payload(r.case_id === 'write-a' ? 'modified' : 'original')) {
      throw new Error('Refuse cleanup of changed or unexpected owned payload');
    }
    fs.unlinkSync(path); // This exact operation's newly created file only.
    const existsAfter: boolean = fs.accessSync(path);
    this.record('deleted', 'fileIo.unlinkSync/accessSync', JSON.stringify({ path: path, exists_after: existsAfter }));
    if (existsAfter) { throw new Error('Owned payload remains after unlink'); }
  }
  async execute(): Promise<void> {
    try {
      if (ROLE === 'caller') { await this.callerExecute(); this.record('complete', '', 'null'); }
      else { await this.targetExecute(); }
    } catch (error) {
      const e = error as BusinessError;
      this.record('error', this.api, 'null', typeof e.code === 'number' ? e.code : -1, e.message);
      this.record('failed', '', 'null');
      // A caller API error leaves the owned nonce file for explicit review;
      // disposal is not reported as public file/URI cleanup.
    }
  }
}
