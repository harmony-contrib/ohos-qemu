import fs from '@ohos.file.fs';
import process from '@ohos.process';
import systemDateTime from '@ohos.systemDateTime';
import Want from '@ohos.app.ability.Want';
import { BusinessError } from '@ohos.base';
import bundleManager from '@ohos.bundle.bundleManager';

export const RUN: string = '__SERVICES578_RUN__';
export const CASE: string = '__SERVICES578_CASE__';
export const ROLE: string = '__SERVICES578_ROLE__';
export const BUNDLE: string = '__SERVICES578_BUNDLE__';
export const HOST: string = '__SERVICES578_HOST__';
export const OTHER_HOST: string = '__SERVICES578_OTHER_HOST__';
export const TARGET: string = 'org.ohos.qemu.services578.domain.target';
export const OTHER: string = 'org.ohos.qemu.services578.domain.other';

interface Row {
  run_id: string; kind: string; role: string; bundle: string; uid: number; pid: number;
  seq: number; active_ms: number; request_id: string; action: string; event: string; code: number; value: string;
}

export class Journal {
  static sequence: number = 0;
  static requestId: string = 'lifecycle';
  static action: string = 'lifecycle';
  static record(event: string, code: number = 0, value: string = 'null', requestId?: string, action?: string): void {
    const row: Row = {run_id: RUN, kind: CASE, role: ROLE, bundle: BUNDLE, uid: process.uid, pid: process.pid,
      seq: Journal.sequence++, active_ms: systemDateTime.getUptime(systemDateTime.TimeType.ACTIVE),
      request_id: requestId ?? Journal.requestId, action: action ?? Journal.action, event, code, value};
    const file = fs.openSync('/data/storage/el2/base/files/services578-' + RUN + '-' +
      process.pid.toString() + '.jsonl', fs.OpenMode.CREATE | fs.OpenMode.WRITE_ONLY | fs.OpenMode.APPEND);
    try { fs.writeSync(file.fd, JSON.stringify(row) + '\n'); } finally { fs.closeSync(file); }
  }
  static request(want: Want): void {
    const p = want.parameters;
    if (p?.run_id !== RUN || typeof p?.request_id !== 'string' || typeof p?.action !== 'string' ||
      !/^[a-z0-9_-]{1,64}$/.test(p.request_id as string)) {
      throw new Error('compiled nonce and bounded request ID required');
    }
    Journal.requestId = p.request_id as string;
    Journal.action = p.action as string;
    Journal.record('request', 0, JSON.stringify(p));
  }
  static fail(event: string, error: BusinessError, requestId?: string, action?: string): void {
    // Some upstream napi_throw_error paths expose a decimal string code.
    // Retain its actual value/type as well as the numeric comparison field.
    const codeText = String(error.code);
    Journal.record(event, /^-?[0-9]+$/.test(codeText) ? Number(codeText) : -1,
      JSON.stringify({message: error.message, rawCode: error.code, codeType: typeof error.code}), requestId, action);
  }
  static async identity(): Promise<void> {
    const actual = await bundleManager.getBundleInfoForSelf(bundleManager.BundleFlag.GET_BUNDLE_INFO_WITH_SIGNATURE_INFO);
    Journal.record('self-identity', 0, JSON.stringify({bundle: actual.name,
      appIdentifier: actual.signatureInfo.appIdentifier, fingerprint: actual.signatureInfo.fingerprint}));
  }
}
