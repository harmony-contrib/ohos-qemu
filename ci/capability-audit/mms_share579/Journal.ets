/* SPDX-License-Identifier: Apache-2.0 */
import fs from '@ohos.file.fs';
import process from '@ohos.process';
import util from '@ohos.util';
import systemDateTime from '@ohos.systemDateTime';
import Want from '@ohos.app.ability.Want';
import { common } from '@kit.AbilityKit';

export const RUN: string = '__RUN__';
export const ROLE: string = '__ROLE__';
export const BUNDLE: string = '__BUNDLE__';
export interface Request {
  run: string; boot: string; archive: string; operation: string; object: string;
  caseId: string; action: string; uri: string; delivery: string;
}
export class Journal {
  static context: common.UIAbilityContext;
  static filesDir: string = '';
  static sequence: number = 0;
  static generation: string = util.generateRandomUUID(true).replace(/-/g, '');
  static current: Request | undefined = undefined;
  static request(want: Want): Request {
    const encoded: string = (want.parameters?.request as string) ?? (want.parameters?.['ability.subject'] as string) ?? '';
    if (encoded.length < 1 || encoded.length > 8192) { throw new Error('Actual finite request missing'); }
    const r: Request = JSON.parse(encoded) as Request;
    if (r.run !== RUN || !/^[a-f0-9-]{36}$/.test(r.boot) || !/^[a-f0-9]{64}$/.test(r.archive) ||
        !/^[a-f0-9]{32}$/.test(r.operation) || !/^[a-f0-9]{32}$/.test(r.object) ||
        !/^[a-f0-9]{32}$/.test(r.delivery) ||
        !['share-close','share-write-close','share-receiver-death','share-owner-death',
          'mms-no-grant','mms-forged-owner','mms-cancel','mms-owner-death','mms-receiver-death'].includes(r.caseId) ||
        !['create','owner-read','share','mms','probe','consume','cleanup'].includes(r.action) ||
        typeof r.uri !== 'string' || r.uri.length > 2048) { throw new Error('Foreign request'); }
    return r;
  }
  static record(r: Request, event: string, value: string = 'null', code: number = 0): void {
    if (Journal.filesDir.length === 0) { throw new Error('Actual application filesDir not captured'); }
    const row = { run: RUN, boot: r.boot, archive: r.archive, role: ROLE, bundle: BUNDLE,
      operation: r.operation, object: r.object, caseId: r.caseId, action: r.action,
      uid: process.uid, pid: process.pid, seq: ++Journal.sequence,
      activeMs: systemDateTime.getUptime(systemDateTime.TimeType.ACTIVE), filesDir: Journal.filesDir,
      event: event, value: value, code: code };
    const bytes = new util.TextEncoder().encodeInto(JSON.stringify(row) + '\n');
    const file = fs.openSync(Journal.filesDir + '/uri579-' + RUN + '-' + process.pid.toString() + '-' + Journal.generation + '.jsonl',
      fs.OpenMode.CREATE | fs.OpenMode.WRITE_ONLY | fs.OpenMode.APPEND | fs.OpenMode.NOFOLLOW);
    try {
      let done: number = 0;
      while (done < bytes.byteLength) {
        const n = fs.writeSync(file.fd, bytes.slice(done).buffer);
        if (n <= 0 || n > bytes.byteLength - done) { throw new Error('Short journal write'); }
        done += n;
      }
      fs.fsyncSync(file.fd);
    } finally { fs.closeSync(file); }
  }
}
