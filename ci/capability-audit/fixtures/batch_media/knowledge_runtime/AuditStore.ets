/* Raw observations only. No expected-result substitution or permission grants. */
import fs from '@ohos.file.fs';
import util from '@ohos.util';
import process from '@ohos.process';
import bundleManager from '@ohos.bundle.bundleManager';
import abilityAccessCtrl from '@ohos.abilityAccessCtrl';
import { common } from '@kit.AbilityKit';
import { BusinessError } from '@ohos.base';

export interface Item {
  case_id: string;
  day: string;
  title: string;
  file_name: string;
  uri: string;
}

export interface Request {
  schema_version: number;
  run_id: string;
  boot_id: string;
  operation_id: string;
  role: string;
  phase: string;
  action: string;
  items: Item[];
}

interface Row {
  schema_version: number;
  run_id: string;
  boot_id: string;
  operation_id: string;
  role: string;
  phase: string;
  sequence: number;
  timestamp_ms: number;
  uid: number;
  token_id: number;
  event: string;
  api: string;
  value_json: string;
  error_code: number;
  error_message: string;
}

export class AuditStore {
  readonly request: Request;
  readonly context: common.UIAbilityContext;
  readonly filesDir: string;
  readonly role: string = '__KNOWLEDGE_ROLE__';
  readonly run: string = '__KNOWLEDGE_RUN__';
  private sequence: number = 0;
  private token: number;
  private readonly path: string;

  constructor(context: common.UIAbilityContext) {
    this.context = context;
    this.filesDir = context.getApplicationContext().filesDir;
    this.path = this.filesDir + '/knowledge-' + this.run + '.jsonl';
    const requestPath = this.filesDir + '/knowledge-request.json';
    if (fs.statSync(requestPath).size > 65536) { throw new Error('Oversized request'); }
    this.request = JSON.parse(fs.readTextSync(requestPath)) as Request;
    const r = this.request;
    if (r.schema_version !== 1 || r.run_id !== this.run || r.role !== this.role ||
      !/^[a-f0-9]{32}$/.test(r.operation_id) || !/^[a-f0-9-]{36}$/.test(r.boot_id) ||
      !/^[a-z][a-z0-9-]{0,31}$/.test(r.phase) || r.items.length === 0 || r.items.length > 64 ||
      process.uid < 10000 || Math.floor(process.uid / 200000) !== 100) {
      throw new Error('Invalid fresh account100 request');
    }
    const ids: string[] = [];
    for (const item of r.items) {
      if (!/^d[0-9]{8}$/.test(item.case_id) || item.day !== item.case_id.substring(1) ||
        item.file_name !== item.case_id + '.jpg' || item.title !== 'kh-' + this.run + '-' + item.case_id ||
        ids.includes(item.case_id) || (this.role !== 'importer' && this.role !== 'denied' &&
        !['permission', 'access', 'baseline'].includes(r.action) &&
        !/^file:\/\/media\/Photo\/[1-9][0-9]*\//.test(item.uri))) {
        throw new Error('Unexpected or repeated owned image');
      }
      ids.push(item.case_id);
    }
    if (fs.accessSync(this.path)) {
      if (fs.statSync(this.path).size > 16777216) { throw new Error('Oversized journal'); }
      const raw = fs.readTextSync(this.path);
      if (!raw.endsWith('\n')) { throw new Error('Incomplete prior journal'); }
      for (const line of raw.trimEnd().split('\n')) {
        const row = JSON.parse(line) as Row;
        if (row.run_id !== this.run || row.role !== this.role || row.boot_id !== r.boot_id ||
          row.sequence !== ++this.sequence || row.operation_id === r.operation_id) {
          throw new Error('Stale, reordered or reused operation');
        }
      }
    }
    const info = bundleManager.getBundleInfoForSelfSync(bundleManager.BundleFlag.GET_BUNDLE_INFO_WITH_APPLICATION);
    this.token = info.appInfo.accessTokenId;
    if (this.token <= 0) { throw new Error('No actual self token'); }
    this.append('begin', 'request', JSON.stringify(r));
  }

  append(event: string, api: string, value: string, code: number = 0, message: string = ''): void {
    const row: Row = { schema_version: 1, run_id: this.run, boot_id: this.request.boot_id,
      operation_id: this.request.operation_id, role: this.role, phase: this.request.phase,
      sequence: ++this.sequence, timestamp_ms: Date.now(), uid: process.uid, token_id: this.token,
      event: event, api: api, value_json: value, error_code: code, error_message: message };
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

  failure(api: string, error: BusinessError): void {
    this.append('error', api, '{}', error.code ?? -1, error.message ?? String(error));
  }

  access(): void {
    const manager = abilityAccessCtrl.createAtManager();
    const read = manager.checkAccessTokenSync(this.token, 'ohos.permission.READ_IMAGEVIDEO');
    const write = manager.checkAccessTokenSync(this.token, 'ohos.permission.WRITE_IMAGEVIDEO');
    this.append('access', 'abilityAccessCtrl.checkAccessTokenSync', JSON.stringify({ read: read, write: write }));
  }

  async permission(curator: boolean = false): Promise<void> {
    const manager = abilityAccessCtrl.createAtManager();
    const result = curator ? await manager.requestPermissionsFromUser(this.context,
      ['ohos.permission.READ_IMAGEVIDEO', 'ohos.permission.WRITE_IMAGEVIDEO']) :
      await manager.requestPermissionsFromUser(this.context, ['ohos.permission.READ_IMAGEVIDEO']);
    this.append('permission', 'abilityAccessCtrl.requestPermissionsFromUser', JSON.stringify(result));
    this.access();
  }

  complete(): void { this.append('complete', 'request', '{}'); }
}
