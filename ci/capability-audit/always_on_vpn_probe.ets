// Real policy IPC only. Does not claim VPN tunnel/server/traffic coverage.
import vpn from '@ohos.net.vpnExtension';
import fs from '@ohos.file.fs';
import process from '@ohos.process';
import { BusinessError } from '@ohos.base';

interface Row { runId: string; role: string; name: string; values: number[]; error: string; }

@Entry
@Component
struct Index {
  @State private note: string = 'Checking VPN policy';
  private readonly runId: string = '__VPN_RUN__';
  private readonly role: string = '__VPN_ROLE__';
  private readonly bundle: string = 'org.harmonycontrib.capabilityaudit';
  private readonly path: string = '/data/storage/el2/base/files/vpn-policy-__VPN_RUN__-results.log';
  private readonly phasePath: string = '/data/storage/el2/base/files/vpn-policy-__VPN_RUN__-seed';

  private record(name: string, values: number[], error: string = ''): void {
    const row: Row = { runId: this.runId, role: this.role, name, values, error };
    const file = fs.openSync(this.path, fs.OpenMode.CREATE | fs.OpenMode.WRITE_ONLY | fs.OpenMode.APPEND);
    try { fs.writeSync(file.fd, JSON.stringify(row) + '\n'); } finally { fs.closeSync(file); }
    this.note = name;
  }
  private async rejected(write: boolean, bundle: string): Promise<number[]> {
    try {
      if (write) { await vpn.setAlwaysOnVpnEnabled(true, bundle); }
      else { await vpn.isAlwaysOnVpnEnabled(bundle); }
      return [0, 0];
    } catch (error) {
      const code = (error as BusinessError).code;
      return [code, typeof code === 'number' ? 1 : 0];
    }
  }
  private async run(): Promise<void> {
    let seeded = false;
    let complete = false;
    let restore = false;
    try {
      this.record('identity', [process.uid, process.euid, process.pid]);
      for (const invalid of ['', 'com.example\u0000hidden']) {
        this.record('invalid.get', await this.rejected(false, invalid));
        this.record('invalid.set', await this.rejected(true, invalid));
      }
      if (this.role !== 'system') {
        this.record('denied.get', await this.rejected(false, this.bundle));
        this.record('denied.set', await this.rejected(true, this.bundle));
      } else {
        if (fs.accessSync(this.phasePath)) {
          restore = true;
          this.record('restart.persisted', [await vpn.isAlwaysOnVpnEnabled(this.bundle) ? 1 : 0]);
          this.record('restart.other', [await vpn.isAlwaysOnVpnEnabled(this.bundle + '.other') ? 1 : 0]);
          await vpn.setAlwaysOnVpnEnabled(false, this.bundle);
          this.record('restart.disabled', [await vpn.isAlwaysOnVpnEnabled(this.bundle) ? 1 : 0]);
          fs.unlinkSync(this.phasePath);
        } else {
          // Runner must supply a newly packaged disposable guest, never a user's policy store.
          const initial = await vpn.isAlwaysOnVpnEnabled(this.bundle);
          this.record('initial', [initial ? 1 : 0]);
          if (initial) { throw new Error('unexpected existing audit policy'); }
          restore = true;
          for (let round = 0; round < 3; round++) {
            await vpn.setAlwaysOnVpnEnabled(true, this.bundle);
            this.record('enabled.' + round, [await vpn.isAlwaysOnVpnEnabled(this.bundle) ? 1 : 0]);
            this.record('other.' + round, [await vpn.isAlwaysOnVpnEnabled(this.bundle + '.other') ? 1 : 0]);
            await vpn.setAlwaysOnVpnEnabled(false, this.bundle);
            this.record('disabled.' + round, [await vpn.isAlwaysOnVpnEnabled(this.bundle) ? 1 : 0]);
          }
          await vpn.setAlwaysOnVpnEnabled(true, this.bundle);
          this.record('seed.persisted', [await vpn.isAlwaysOnVpnEnabled(this.bundle) ? 1 : 0]);
          const marker = fs.openSync(this.phasePath, fs.OpenMode.CREATE | fs.OpenMode.WRITE_ONLY);
          try { fs.writeSync(marker.fd, this.runId); } finally { fs.closeSync(marker); }
          seeded = true;
        }
      }
      complete = true;
    } catch (error) {
      this.record('failed', [], (error as Error).message || 'VPN policy failure');
    } finally {
      if (restore && !seeded) {
        try {
          await vpn.setAlwaysOnVpnEnabled(false, this.bundle);
          this.record('cleanup', [await vpn.isAlwaysOnVpnEnabled(this.bundle) ? 1 : 0]);
        } catch (error) { complete = false; this.record('cleanup.failed', [], (error as Error).message); }
      }
    }
    this.record('summary', [complete ? 1 : 0, seeded ? 1 : 0]);
  }
  aboutToAppear(): void {
    const file = fs.openSync(this.path, fs.OpenMode.CREATE | fs.OpenMode.WRITE_ONLY | fs.OpenMode.TRUNC);
    fs.closeSync(file);
    this.run();
  }
  build() { Column() { Text(this.note) }.width('100%').height('100%') }
}
