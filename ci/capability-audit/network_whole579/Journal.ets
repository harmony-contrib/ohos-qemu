import fs from '@ohos.file.fs';
import process from '@ohos.process';
import systemDateTime from '@ohos.systemDateTime';
import Want from '@ohos.app.ability.Want';
import bundleManager from '@ohos.bundle.bundleManager';
import { BusinessError } from '@ohos.base';

export const RUN: string = '__APPS579_RUN__';
export const CASE: string = '__APPS579_CASE__';
export const ROLE: string = '__APPS579_ROLE__';
export const BUNDLE: string = '__APPS579_BUNDLE__';
export class Journal {
  static seq: number = 0;
  static requestId: string = 'lifecycle';
  static action: string = 'lifecycle';
  static payload: Record<string, string | number | boolean> = {};
  static record(event: string, value: string = 'null', code: number = 0,
    requestId: string = Journal.requestId, action: string = Journal.action): void {
    const row = {run_id: RUN, kind: CASE, role: ROLE, bundle: BUNDLE, uid: process.uid, pid: process.pid,
      seq: Journal.seq++, active_ms: systemDateTime.getUptime(systemDateTime.TimeType.ACTIVE),
      request_id: requestId, action, event, code, value};
    const f = fs.openSync('/data/storage/el2/base/files/apps579-' + RUN + '-' + process.pid + '.jsonl',
      fs.OpenMode.CREATE | fs.OpenMode.WRITE_ONLY | fs.OpenMode.APPEND);
    try { fs.writeSync(f.fd, JSON.stringify(row) + '\n'); } finally { fs.closeSync(f); }
  }
  static fail(event: string, error: BusinessError, requestId: string = Journal.requestId,
    action: string = Journal.action): void {
    const text = String(error.code);
    Journal.record(event, JSON.stringify({message: error.message, rawCode: error.code,
      codeType: typeof error.code}), /^-?[0-9]+$/.test(text) ? Number(text) : -1, requestId, action);
  }
  static request(want: Want): void {
    const p = want.parameters;
    if (p?.run_id !== RUN || typeof p?.request_id !== 'string' || typeof p?.action !== 'string' ||
      !/^[a-z0-9_-]{1,64}$/.test(p.request_id as string) || typeof p?.payload !== 'string') {
      throw new Error('exact compiled nonce and finite request required');
    }
    Journal.requestId = p.request_id as string;
    Journal.action = p.action as string;
    Journal.payload = JSON.parse(p.payload as string) as Record<string, string | number | boolean>;
    Journal.record('request', JSON.stringify(p));
  }
  static async identity(): Promise<void> {
    const info = await bundleManager.getBundleInfoForSelf(bundleManager.BundleFlag.GET_BUNDLE_INFO_WITH_SIGNATURE_INFO);
    Journal.record('self-identity', JSON.stringify({bundle: info.name, appIdentifier: info.signatureInfo.appIdentifier,
      fingerprint: info.signatureInfo.fingerprint}));
  }
}
