// SPDX-License-Identifier: Apache-2.0
import osAccount from '@ohos.account.osAccount';
import fs from '@ohos.file.fs';
import native from 'libuseridprobe.so';

interface UserIdProbe { run: (expected: number, runId: string) => number; }
interface NativeResult { kind: string; run_id: string; exit_code: number; }

@Entry
@Component
struct Index {
  @State private note: string = 'Running ordinary AppSpawn account checks';
  aboutToAppear(): void { this.check(); }
  private async check(): Promise<void> {
    // Truncate even if the account service fails before the native call.
    const file = fs.openSync('/data/storage/el2/base/files/userid-results.log',
      fs.OpenMode.WRITE_ONLY | fs.OpenMode.CREATE | fs.OpenMode.TRUNC);
    fs.closeSync(file);
    try {
      const account: number = await osAccount.getAccountManager().getOsAccountLocalId();
      const run: string = '__USERID_RUN_ID__'; // Fresh host challenge frozen by the HAP builder.
      const result: number = (native as UserIdProbe).run(account, run);
      // Record the returned native status after fclose, not an assumed process exit.
      const status: NativeResult = { kind: 'native_result', run_id: run, exit_code: result };
      const results = fs.openSync('/data/storage/el2/base/files/userid-results.log',
        fs.OpenMode.WRITE_ONLY | fs.OpenMode.APPEND);
      fs.writeSync(results.fd, JSON.stringify(status) + '\n');
      fs.closeSync(results);
      this.note = 'account=' + account + ' run=' + run + ' result=' + result;
    } catch (error) {
      this.note = 'FAILED to query actual account or run native probe';
    }
  }
  build() {
    Column({ space: 12 }) {
      Text('QEMU AppSpawn user ID audit').fontSize(18)
      Text(this.note).fontSize(12)
    }.width('100%').height('100%').justifyContent(FlexAlign.Center)
  }
}
