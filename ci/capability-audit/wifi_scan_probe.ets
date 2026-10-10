// Real public scan callbacks. Empty results do NOT prove association or AP/P2P.
import wifi from '@ohos.wifiManager';
import fs from '@ohos.file.fs';
import { BusinessError } from '@ohos.base';

interface Row { runId: string; name: string; values: number[]; error: string; }

@Entry
@Component
struct Index {
  @State private note: string = 'Checking WPA scan callbacks';
  private readonly runId: string = '__WIFI_SCAN_RUN_ID__';
  private readonly logPath: string = '/data/storage/el2/base/files/wifi-scan-__WIFI_SCAN_RUN_ID__-results.log';
  private counts: number[] = [0, 0];
  private record(name: string, values: number[], error: string = ''): void {
    const row: Row = { runId: this.runId, name, values, error };
    const file = fs.openSync(this.logPath, fs.OpenMode.CREATE | fs.OpenMode.WRITE_ONLY | fs.OpenMode.APPEND);
    try { fs.writeSync(file.fd, JSON.stringify(row) + '\n'); } finally { fs.closeSync(file); }
    this.note = name;
  }
  private delay(ms: number): Promise<void> {
    return new Promise<void>((resolve) => { setTimeout(() => resolve(), ms); });
  }
  private scan(index: number): Promise<number> {
    return new Promise<number>((resolve, reject) => {
      let timer: number = 0;
      const callback = (state: number): void => {
        this.counts[index]++;
        clearTimeout(timer);
        try {
          wifi.off('wifiScanStateChange', callback);
          if (state !== 1) { reject(new Error('scan backend reported failure')); }
          else { resolve(state); }
        } catch (error) { reject(error as Error); }
      };
      timer = setTimeout(() => {
        try { wifi.off('wifiScanStateChange', callback); }
        catch (error) { reject(error as Error); return; }
        reject(new Error('scan completion timeout'));
      }, 30000);
      try {
        wifi.on('wifiScanStateChange', callback);
        wifi.startScan();
      } catch (error) {
        clearTimeout(timer);
        wifi.off('wifiScanStateChange', callback);
        reject(error as Error);
      }
    });
  }
  private async run(): Promise<void> {
    let completed = 0;
    try {
      this.record('active', [wifi.isWifiActive() ? 1 : 0]); completed++;
      let denied: number = 0;
      try { wifi.scan(); } catch (error) { denied = (error as BusinessError).code; }
      this.record('legacy-location-denial', [denied]); completed++;
      for (let index = 0; index < 2; index++) {
        if (index !== 0) { await this.delay(12000); }
        const state = await this.scan(index);
        const results = wifi.getScanInfoList();
        for (const result of results) {
          if (result.frequency <= 0 || result.ssid.length > 32) {
            throw new Error('malformed real scan result');
          }
        }
        this.record('generation' + index, [state, this.counts[index], results.length]); completed++;
      }
      await this.delay(500);
      this.record('retired', this.counts); completed++;
    } catch (error) {
      this.record('failed', [], (error as Error).message || 'Wi-Fi scan failure');
    }
    this.record('summary', [completed, completed === 5 ? 0 : 1]);
  }
  aboutToAppear(): void {
    const file = fs.openSync(this.logPath, fs.OpenMode.CREATE | fs.OpenMode.WRITE_ONLY | fs.OpenMode.TRUNC);
    fs.closeSync(file); this.run();
  }
  build() { Column() { Text(this.note) }.width('100%').height('100%') }
}
