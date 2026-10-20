import fs from '@ohos.file.fs';
import process from '@ohos.process';
import systemDateTime from '@ohos.systemDateTime';
import Want from '@ohos.app.ability.Want';

export const RUN: string = '__APPS578_RUN__';
export const CASE: string = '__APPS578_CASE__';
export const ROLE: string = '__APPS578_ROLE__';
export const BUNDLE: string = '__APPS578_BUNDLE__';

interface Row {
  run: string; kind: string; role: string; bundle: string; uid: number; pid: number;
  seq: number; activeMs: number; operation: string; event: string; code: number; value: string;
}

// Each real process has a separate append-only journal. A restart cannot replace
// its predecessor's final pending/terminal observations.
export class Journal {
  static sequence: number = 0;
  static operation: string = 'lifecycle';
  static argument: string = '';
  static numberArgument: number = 0;
  static serial: number = 0;
  static requestGeneration: number = 0;
  static record(event: string, code: number, value: string = 'null', operation?: string): void {
    const row: Row = { run: RUN, kind: CASE, role: ROLE, bundle: BUNDLE, uid: process.uid,
      pid: process.pid, seq: Journal.sequence++, activeMs: systemDateTime.getUptime(systemDateTime.TimeType.ACTIVE),
      operation: operation ?? Journal.operation, event, code, value };
    const path: string = '/data/storage/el2/base/files/apps578-' + RUN + '-' + process.pid.toString() + '.jsonl';
    const file = fs.openSync(path, fs.OpenMode.CREATE | fs.OpenMode.WRITE_ONLY | fs.OpenMode.APPEND);
    try { fs.writeSync(file.fd, JSON.stringify(row) + '\n'); } finally { fs.closeSync(file); }
    ++Journal.serial;
  }
  static request(want: Want): void {
    const p = want.parameters;
    if (p?.run !== RUN || p?.kind !== CASE || typeof p?.operation !== 'string' ||
      !/^[a-z][a-z0-9.-]{0,63}$/.test(p.operation as string)) {
      throw new Error('actual compiled run/case and bounded operation required');
    }
    Journal.operation = p.operation as string;
    Journal.argument = typeof p.argument === 'string' ? p.argument : '';
    Journal.numberArgument = typeof p.numberArgument === 'number' ? p.numberArgument : 0;
    Journal.record('request', 0, JSON.stringify(p));
    AppStorage.setOrCreate('apps578-request-serial', ++Journal.requestGeneration);
  }
}
