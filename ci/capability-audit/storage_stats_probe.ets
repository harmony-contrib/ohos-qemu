// Ordinary application: only nonce-owned private files are created/deleted.
import storage from '@ohos.file.storageStatistics';
import fs from '@ohos.file.fs';
import { BusinessError } from '@ohos.base';

interface Row { runId: string; name: string; values: number[]; error: string; }

@Entry
@Component
struct Index {
  @State private note: string = 'Checking actual application storage statistics';
  private readonly runId: string = '__STORAGE_RUN_ID__';
  private readonly logPath: string = '/data/storage/el2/base/files/storage-stats-__STORAGE_RUN_ID__-results.log';
  private readonly dataPath: string = '/data/storage/el2/base/files/quota-data-__STORAGE_RUN_ID__';
  private readonly cachePath: string = '/data/storage/el2/base/cache/quota-cache-__STORAGE_RUN_ID__';
  private record(name: string, values: number[] = [], error: string = ''): void {
    const row: Row = { runId: this.runId, name, values, error };
    const file = fs.openSync(this.logPath, fs.OpenMode.CREATE | fs.OpenMode.WRITE_ONLY | fs.OpenMode.APPEND);
    try { fs.writeSync(file.fd, JSON.stringify(row) + '\n'); } finally { fs.closeSync(file); }
    this.note = name;
  }
  private fill(path: string, bytes: number): void {
    const block = new Uint8Array(65536);
    const seed = parseInt(this.runId.substring(0, 2), 16);
    for (let i = 0; i < block.length; i++) { block[i] = (i * 31 + seed) % 256; }
    const file = fs.openSync(path, fs.OpenMode.CREATE | fs.OpenMode.WRITE_ONLY | fs.OpenMode.TRUNC);
    try {
      let written = 0;
      while (written < bytes) {
        const count = fs.writeSync(file.fd, block.buffer, { length: Math.min(block.length, bytes - written) });
        if (count <= 0 || count > bytes - written) { throw new Error('invalid write progress'); }
        written += count;
      }
      fs.fsyncSync(file.fd);
      if (fs.statSync(file.fd).size !== bytes) { throw new Error('owned file size mismatch'); }
    } finally { fs.closeSync(file); }
  }
  private callbackStats(): Promise<storage.BundleStats> {
    return new Promise<storage.BundleStats>((resolve, reject) => {
      storage.getCurrentBundleStats((error: BusinessError, value: storage.BundleStats) => {
        if (error && error.code) { reject(error); } else { resolve(value); }
      });
    });
  }
  private statsRow(name: string, value: storage.BundleStats): void {
    this.record(name, [value.appSize, value.cacheSize, value.dataSize]);
  }
  private async generation(index: number): Promise<void> {
    const dataBytes = (index + 1) * 4 * 1024 * 1024;
    const cacheBytes = (index + 1) * 2 * 1024 * 1024;
    const before = await storage.getCurrentBundleStats();
    this.statsRow('before.' + index, before);
    this.fill(this.dataPath, dataBytes);
    this.fill(this.cachePath, cacheBytes);
    this.record('written.' + index, [fs.statSync(this.dataPath).size, fs.statSync(this.cachePath).size]);
    let occupied = await this.callbackStats();
    for (let retry = 0; retry < 40 &&
      (occupied.dataSize - before.dataSize < dataBytes || occupied.cacheSize - before.cacheSize < cacheBytes); retry++) {
      await new Promise<void>((resolve) => { setTimeout(resolve, 250); });
      occupied = await this.callbackStats();
    }
    this.statsRow('occupied.' + index, occupied);
    fs.unlinkSync(this.dataPath); fs.unlinkSync(this.cachePath);
    let restored = await storage.getCurrentBundleStats();
    for (let retry = 0; retry < 40 &&
      (occupied.dataSize - restored.dataSize < dataBytes - 65536 ||
       occupied.cacheSize - restored.cacheSize < cacheBytes - 65536); retry++) {
      await new Promise<void>((resolve) => { setTimeout(resolve, 250); });
      restored = await storage.getCurrentBundleStats();
    }
    this.statsRow('restored.' + index, restored);
  }
  private async run(): Promise<void> {
    let success = false;
    try {
      for (let generation = 0; generation < 2; generation++) { await this.generation(generation); }
      let denial = 0;
      try { await storage.getBundleStats('com.ohos.settings'); }
      catch (error) { denial = (error as BusinessError).code; }
      this.record('other-bundle-denial', [denial]);
      success = true;
    } catch (error) { this.record('failed', [], (error as Error).message || 'storage exception'); }
    finally {
      let cleaned = true;
      for (const path of [this.dataPath, this.cachePath]) {
        try { if (fs.accessSync(path)) { fs.unlinkSync(path); } }
        catch (error) { cleaned = false; }
      }
      this.record('summary', [success ? 1 : 0, cleaned ? 1 : 0]);
    }
  }
  aboutToAppear(): void {
    const file = fs.openSync(this.logPath, fs.OpenMode.CREATE | fs.OpenMode.WRITE_ONLY | fs.OpenMode.TRUNC);
    fs.closeSync(file); this.run();
  }
  build() { Column() { Text(this.note) }.width('100%').height('100%') }
}
