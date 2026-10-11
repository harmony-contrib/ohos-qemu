// Public controls and read-only Linux eth0 flags. Never change raw nodes or permissions.
import ethernet from '@ohos.net.ethernet';
import fs from '@ohos.file.fs';
import process from '@ohos.process';
import { BusinessError } from '@ohos.base';

interface Row { runId: string; role: string; name: string; values: number[]; error: string; }

@Entry
@Component
struct Index {
  @State private note: string = 'Ethernet regression';
  private readonly nonce: string = '__ETHERNET_RUN__';
  private readonly role: string = '__ETHERNET_ROLE__';
  private readonly path: string = '/data/storage/el2/base/files/ethernet-control-__ETHERNET_RUN__-results.log';
  private readonly marker: string = '/data/storage/el2/base/files/ethernet-control-__ETHERNET_RUN__-seed';

  private record(name: string, values: number[] = [], error: string = ''): void {
    const row: Row = { runId: this.nonce, role: this.role, name, values, error };
    const file = fs.openSync(this.path, fs.OpenMode.CREATE | fs.OpenMode.WRITE_ONLY | fs.OpenMode.APPEND);
    try { fs.writeSync(file.fd, JSON.stringify(row) + '\n'); } finally { fs.closeSync(file); }
    this.note = name;
  }
  private snapshot(name: string): void {
    const enabled: boolean = ethernet.isEthernetEnabled();
    const text: string = fs.readTextSync('/sys/class/net/eth0/flags').trim();
    if (!/^0x[0-9a-fA-F]+$/.test(text)) { throw new Error('missing real eth0 kernel flags'); }
    const flags = Number.parseInt(text.substring(2), 16);
    if (!Number.isInteger(flags) || flags < 0 || flags > 0xFFFFFFFF) { throw new Error('invalid kernel flags'); }
    this.record(name, [typeof enabled === 'boolean' ? 1 : 0, enabled ? 1 : 0, flags]);
  }
  private async denied(method: number): Promise<number[]> {
    try {
      if (method === 0) { await ethernet.disableEthernetInterface(); }
      else if (method === 1) { await ethernet.enableEthernetInterface(); }
      else { ethernet.isEthernetEnabled(); }
      return [0, 0, 0];
    } catch (error) {
      const code = (error as BusinessError).code;
      return [1, code, typeof code === 'number' ? 1 : 0];
    }
  }
  private async run(): Promise<void> {
    let completed = false;
    let seeded = false;
    let ownsPolicy = false;
    try {
      this.record('identity', [process.uid, process.euid, process.pid]);
      if (this.role !== 'system') {
        for (let method = 0; method < 3; method++) {
          this.record('denied.' + method, await this.denied(method));
        }
      } else {
        const restarted = fs.accessSync(this.marker);
        this.snapshot(restarted ? 'restart.initial' : 'seed.initial');
        if (!ethernet.isEthernetEnabled()) { throw new Error('fresh test guest policy is not enabled'); }
        ownsPolicy = true;
        for (let round = 0; round < (restarted ? 1 : 3); round++) {
          await ethernet.disableEthernetInterface();
          this.snapshot('disabled.' + round);
          await ethernet.disableEthernetInterface();
          this.snapshot('disabled-again.' + round);
          // Recovery runs inside the same real caller even when TCP HDC disconnects.
          await ethernet.enableEthernetInterface();
          this.snapshot('enabled.' + round);
          await ethernet.enableEthernetInterface();
          this.snapshot('enabled-again.' + round);
        }
        if (restarted) { fs.unlinkSync(this.marker); }
        else {
          const marker = fs.openSync(this.marker, fs.OpenMode.CREATE | fs.OpenMode.WRITE_ONLY);
          try { fs.writeSync(marker.fd, this.nonce); } finally { fs.closeSync(marker); }
          seeded = true;
        }
      }
      completed = true;
    } catch (error) {
      this.record('failed', [], (error as Error).message || 'Ethernet regression failed');
    } finally {
      if (ownsPolicy) {
        try { await ethernet.enableEthernetInterface(); this.snapshot('cleanup'); }
        catch (error) { completed = false; this.record('cleanup.failed', [], String(error)); }
      }
      this.record('summary', [completed ? 1 : 0, seeded ? 1 : 0]);
    }
  }
  aboutToAppear(): void {
    const file = fs.openSync(this.path, fs.OpenMode.CREATE | fs.OpenMode.WRITE_ONLY | fs.OpenMode.TRUNC);
    fs.closeSync(file); this.run();
  }
  build() { Column() { Text(this.note) }.width('100%').height('100%') }
}
