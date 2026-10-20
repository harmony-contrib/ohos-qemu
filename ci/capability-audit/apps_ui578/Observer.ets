import fs from '@ohos.file.fs';
import process from '@ohos.process';
import systemDateTime from '@ohos.systemDateTime';
import { RUN, CASE, ROLE, BUNDLE } from './Journal';

// Extension JS runtimes can share a PID without sharing module statics with the
// UIAbility. Keep actual extension callbacks out of the UI process-seq journal.
export function observe(event: string, value: string): void {
  const file = fs.openSync('/data/storage/el2/base/files/apps578-observer-' + RUN + '-' + process.pid.toString() + '.jsonl',
    fs.OpenMode.CREATE | fs.OpenMode.WRITE_ONLY | fs.OpenMode.APPEND);
  try {
    fs.writeSync(file.fd, JSON.stringify({ run: RUN, kind: CASE, role: ROLE, bundle: BUNDLE,
      uid: process.uid, pid: process.pid, activeMs: systemDateTime.getUptime(systemDateTime.TimeType.ACTIVE), event, value }) + '\n');
  } finally { fs.closeSync(file); }
}
