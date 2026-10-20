import fs from '@ohos.file.fs';
import process from '@ohos.process';
import systemDateTime from '@ohos.systemDateTime';
import util from '@ohos.util';
import { common, Want } from '@kit.AbilityKit';

export const RUN: string = '__SETTINGS_IDLE579_RUN__';
export const BUNDLE: string = '__SETTINGS_IDLE579_BUNDLE__';
export const FOREIGN_BUNDLE: string = 'org.harmonycontrib.settingsidle579.foreign';
export const SERVICE: string = '__SETTINGS_IDLE579_SERVICE__';

export interface Request {
  run: string;
  boot: string;
  operation: string;
  action: string;
}

interface Row {
  run: string;
  boot: string;
  operation: string;
  event: string;
  value: string;
  code: number;
  uid: number;
  pid: number;
  seq: number;
  uptimeMs: number;
  filesDir: string;
}

export class Journal {
  private static seq: number = 0;
  // Cache the actually observed module path while Context is alive so the
  // Promise result can still be journalled after real service destruction.
  private static filesDir: string = '';
  private static stream: string = util.generateRandomUUID().replace(/-/g, '');
  static request(want: Want): Request {
    const p = want.parameters;
    if (p?.run !== RUN || typeof p.boot !== 'string' || !/^[a-f0-9-]{36}$/.test(p.boot as string) ||
      typeof p.operation !== 'string' || !/^[a-f0-9]{32}$/.test(p.operation as string) ||
      typeof p.action !== 'string' || !/^[a-z-]{1,40}$/.test(p.action as string)) {
      throw new Error('compiled run and bounded actual request required');
    }
    return { run: RUN, boot: p.boot as string, operation: p.operation as string, action: p.action as string };
  }
  static write(context: common.Context, request: Request, event: string, code: number, value: string): void {
    if (Journal.filesDir === '') { Journal.filesDir = context.filesDir; }
    const filesDir: string = Journal.filesDir;
    const row: Row = { run: RUN, boot: request.boot, operation: request.operation, event, code, value,
      uid: process.uid, pid: process.pid, seq: ++Journal.seq,
      uptimeMs: systemDateTime.getUptime(systemDateTime.TimeType.ACTIVE), filesDir };
    const file = fs.openSync(filesDir + '/settings-idle579-' + RUN + '-' + process.pid.toString() + '-' + Journal.stream + '.jsonl',
      fs.OpenMode.CREATE | fs.OpenMode.WRITE_ONLY | fs.OpenMode.APPEND);
    try {
      const bytes = new util.TextEncoder().encodeInto(JSON.stringify(row) + '\n');
      let offset: number = 0;
      while (offset < bytes.byteLength) {
        const written: number = fs.writeSync(file.fd, bytes.slice(offset).buffer);
        if (written <= 0) { throw new Error('actual journal append failed'); }
        offset += written;
      }
      fs.fsyncSync(file.fd);
    } finally { fs.closeSync(file); }
  }
}
