// Ordinary API26 caller: real HTTP bytes, own-UID statistics, other-UID denial.
import http from '@ohos.net.http';
import statistics from '@ohos.net.statistics';
import process from '@ohos.process';
import fs from '@ohos.file.fs';
import { BusinessError } from '@ohos.base';

interface Row { runId: string; name: string; values: number[]; error: string; }

@Entry
@Component
struct Index {
  @State private note: string = 'Checking real network accounting';
  private readonly runId: string = '__NETWORK_ACCOUNTING_RUN_ID__';
  private readonly endpoint: string = '__NETWORK_ACCOUNTING_ENDPOINT__';
  private readonly path: string = '/data/storage/el2/base/files/network-accounting-__NETWORK_ACCOUNTING_RUN_ID__-results.log';
  private record(name: string, values: number[], error: string = ''): void {
    const row: Row = { runId: this.runId, name, values, error };
    const file = fs.openSync(this.path, fs.OpenMode.CREATE | fs.OpenMode.WRITE_ONLY | fs.OpenMode.APPEND);
    try { fs.writeSync(file.fd, JSON.stringify(row) + '\n'); } finally { fs.closeSync(file); }
    this.note = name;
  }
  private async exchange(generation: number): Promise<number> {
    const body = this.runId.repeat(generation === 0 ? 1 : generation * 4096);
    const client = http.createHttp();
    try {
      const response = await client.request(this.endpoint + '/' + generation, {
        method: http.RequestMethod.POST,
        extraData: body,
        header: { 'Content-Type': 'application/octet-stream' },
        expectDataType: http.HttpDataType.ARRAY_BUFFER,
        usingCache: false,
        connectTimeout: 10000,
        readTimeout: 10000
      });
      if (response.responseCode !== 200 || !(response.result instanceof ArrayBuffer)) {
        throw new Error('owned HTTP endpoint did not return successful binary data');
      }
      const bytes = new Uint8Array(response.result as ArrayBuffer);
      if (bytes.length !== body.length) { throw new Error('HTTP payload length mismatch'); }
      for (let index = 0; index < bytes.length; index++) {
        if (bytes[index] !== body.charCodeAt(index)) { throw new Error('HTTP nonce payload mismatch'); }
      }
      return bytes.length;
    } finally { client.destroy(); }
  }
  private async ownStats(callback: boolean): Promise<number[]> {
    if (!callback) {
      return [await statistics.getUidRxBytes(process.uid), await statistics.getUidTxBytes(process.uid)];
    }
    const rx = await new Promise<number>((resolve, reject) => {
      statistics.getUidRxBytes(process.uid, (error: BusinessError, value: number) => {
        if (error && error.code) { reject(error); } else { resolve(value); }
      });
    });
    const tx = await new Promise<number>((resolve, reject) => {
      statistics.getUidTxBytes(process.uid, (error: BusinessError, value: number) => {
        if (error && error.code) { reject(error); } else { resolve(value); }
      });
    });
    return [rx, tx];
  }
  private async run(): Promise<void> {
    let complete = false;
    try {
      this.record('identity', [process.uid, process.euid]);
      this.record('warmup', [await this.exchange(0)]);
      for (let generation = 1; generation <= 2; generation++) {
        const before = await this.ownStats(false);
        this.record('before.' + generation, before);
        const bytes = await this.exchange(generation);
        this.record('payload.' + generation, [bytes]);
        let after = await this.ownStats(true);
        for (let retry = 0; retry < 40 &&
          (after[0] - before[0] < bytes || after[1] - before[1] < bytes); retry++) {
          await new Promise<void>((resolve) => { setTimeout(resolve, 250); });
          after = await this.ownStats(true);
        }
        this.record('after.' + generation, after);
      }
      let rxDenied = 0;
      let txDenied = 0;
      try { await statistics.getUidRxBytes(0); }
      catch (error) { rxDenied = (error as BusinessError).code; }
      try { await statistics.getUidTxBytes(0); }
      catch (error) { txDenied = (error as BusinessError).code; }
      this.record('other-uid-denial', [rxDenied, txDenied]);
      complete = true;
    } catch (error) { this.record('failed', [], (error as Error).message || 'network accounting failure'); }
    this.record('summary', [complete ? 1 : 0]);
  }
  aboutToAppear(): void {
    const file = fs.openSync(this.path, fs.OpenMode.CREATE | fs.OpenMode.WRITE_ONLY | fs.OpenMode.TRUNC);
    fs.closeSync(file);
    this.run();
  }
  build() { Column() { Text(this.note) }.width('100%').height('100%') }
}
