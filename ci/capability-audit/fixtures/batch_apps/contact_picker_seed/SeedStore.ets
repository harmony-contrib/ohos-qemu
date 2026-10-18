/* SPDX-License-Identifier: Apache-2.0 */
import { BusinessError } from '@kit.BasicServicesKit';
import contact from '@ohos.contact';
import abilityAccessCtrl from '@ohos.abilityAccessCtrl';
import { common } from '@kit.AbilityKit';
import { fileIo as fs } from '@kit.CoreFileKit';

export class SeedRequest {
  runId: string = '';
  operationId: string = '';
  mode: string = '';
}

class SeedObservation {
  schema_version: number = 1;
  timestamp_ms: number = Date.now();
  run_id: string = '';
  operation_id: string = '';
  mode: string = '';
  event: string = '';
  api: string = '';
  raw_json: string = '';
  error_type: string = '';
  error_code: number | undefined = undefined;
  error_message: string = '';
}

export default class SeedStore {
  private readonly context: common.UIAbilityContext;
  private readonly request: SeedRequest;
  private readonly prefix: string;
  private readonly path: string;

  constructor(context: common.UIAbilityContext, request: SeedRequest) {
    if (typeof request.runId !== 'string' || typeof request.operationId !== 'string' ||
          typeof request.mode !== 'string' || !/^[A-Za-z0-9_-]{1,64}$/.test(request.runId) ||
        !/^[A-Za-z0-9_-]{1,64}$/.test(request.operationId) ||
        !['create', 'cleanup'].includes(request.mode)) { throw new Error('Invalid seed request'); }
    this.context = context;
    this.request = request;
    this.prefix = 'QCP_' + request.runId + '_';
    this.path = context.getApplicationContext().filesDir + '/contact-seed-' + request.runId + '.jsonl';
  }

  private record(event: string, api: string, raw: string, error?: Error): void {
    const row = new SeedObservation();
    row.run_id = this.request.runId;
    row.operation_id = this.request.operationId;
    row.mode = this.request.mode;
    row.event = event;
    row.api = api;
    row.raw_json = raw;
    if (error !== undefined) {
      row.error_type = typeof error;
      row.error_message = error.message;
      row.error_code = (error as BusinessError).code;
    }
    const file = fs.openSync(this.path, fs.OpenMode.CREATE | fs.OpenMode.READ_WRITE | fs.OpenMode.APPEND);
    try { fs.writeSync(file.fd, JSON.stringify(row) + '\n'); }
    finally { fs.closeSync(file); }
  }

  private owned(records: contact.Contact[]): contact.Contact[] {
    return records.filter((item: contact.Contact) =>
      item.name?.fullName?.startsWith(this.prefix) === true);
  }

  async execute(): Promise<void> {
    this.record('begin', '', 'undefined');
    let currentApi: string = 'abilityAccessCtrl.requestPermissionsFromUser';
    try {
      const manager = abilityAccessCtrl.createAtManager();
      const grant = await manager.requestPermissionsFromUser(this.context,
        ['ohos.permission.READ_CONTACTS', 'ohos.permission.WRITE_CONTACTS']);
      this.record('permission_result', currentApi, JSON.stringify(grant));
      if (grant.authResults.length !== 2 || grant.authResults.some((value: number) => value !== 0)) {
        throw new Error('User did not grant both Contacts permissions');
      }
      currentApi = 'contact.queryContacts';
      const before = await contact.queryContacts(this.context);
      this.record('query_before', currentApi, JSON.stringify(before));
      const existing = this.owned(before);
      if (this.request.mode === 'create') {
        if (existing.length !== 0) { throw new Error('Nonce already has Contacts records; cleanup required'); }
        for (let index = 0; index < 205; index++) {
          const info: contact.Contact = {
            name: { fullName: this.prefix + index.toString().padStart(3, '0') },
            phoneNumbers: [{ phoneNumber: '+1555' + index.toString().padStart(7, '0') }]
          };
          currentApi = 'contact.addContact';
          const id = await contact.addContact(this.context, info);
          this.record('created', currentApi, JSON.stringify(id));
          if (!Number.isSafeInteger(id) || id <= 0) { throw new Error('Public addContact returned invalid ID'); }
        }
      } else {
        // Delete only contacts read back with this exact run's namespace. A partial
        // create or previous cleanup failure remains recoverable without DB access.
        for (const item of existing) {
          if (typeof item.key !== 'string' || item.key.length === 0) {
            throw new Error('Public readback did not provide a deletion key');
          }
          currentApi = 'contact.deleteContact';
          await contact.deleteContact(this.context, item.key);
          this.record('deleted', currentApi, JSON.stringify(item.key));
        }
      }
      currentApi = 'contact.queryContacts';
      const after = await contact.queryContacts(this.context);
      this.record('query_after', currentApi, JSON.stringify(after));
      this.record('readback', currentApi, JSON.stringify(this.owned(after)));
      this.record('complete', '', 'undefined');
    } catch (error) {
      this.record('error', currentApi, 'undefined', error as Error);
      this.record('complete', '', 'undefined');
    }
  }
}
