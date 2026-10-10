// Read-only real service callbacks. This does not emulate temperature or prove hot transitions.
import thermal from '@ohos.thermal';
import fs from '@ohos.file.fs';
import { BusinessError } from '@ohos.base';

interface Row { runId: string; name: string; values: number[]; error: string; }

@Entry
@Component
struct Index {
  @State private note: string = 'Checking thermal service';
  private readonly runId: string = '__THERMAL_RUN_ID__';
  private readonly logPath: string = '/data/storage/el2/base/files/thermal-__THERMAL_RUN_ID__-results.log';
  private counts: number[] = [0, 0, 0, 0];
  private record(name: string, values: number[], error: string = ''): void {
    const row: Row = { runId: this.runId, name, values, error };
    const file = fs.openSync(this.logPath, fs.OpenMode.CREATE | fs.OpenMode.WRITE_ONLY | fs.OpenMode.APPEND);
    try { fs.writeSync(file.fd, JSON.stringify(row) + '\n'); } finally { fs.closeSync(file); }
    this.note = name;
  }
  private delay(): Promise<void> {
    return new Promise<void>((resolve) => { setTimeout(() => resolve(), 250); });
  }
  private initial(index: number, legacy: boolean): Promise<number> {
    return new Promise<number>((resolve, reject) => {
      const timer = setTimeout(() => reject(new Error('thermal callback timeout')), 20000);
      if (legacy) {
        thermal.subscribeThermalLevel((error: BusinessError, level: thermal.ThermalLevel): void => {
          this.counts[index]++;
          clearTimeout(timer);
          if (error && error.code !== 0) { reject(new Error('legacy thermal service failure')); }
          else { resolve(level); }
        });
      } else {
        thermal.registerThermalLevelCallback((level: thermal.ThermalLevel): void => {
          this.counts[index]++;
          clearTimeout(timer); resolve(level);
        });
      }
    });
  }
  private async run(): Promise<void> {
    let completed = 0;
    try {
      this.record('levels', [thermal.getLevel(), thermal.getThermalLevel(), thermal.ThermalLevel.COOL,
        thermal.ThermalLevel.ESCAPE]); completed++;
      for (let index = 0; index < 4; index++) {
        const legacy = index >= 2;
        const level = await this.initial(index, legacy);
        let removed = 0;
        if (index === 0) { thermal.unregisterThermalLevelCallback(() => { removed++; }); }
        if (index === 1) { thermal.unregisterThermalLevelCallback(undefined); removed++; }
        if (index === 2) {
          thermal.unsubscribeThermalLevel((error: BusinessError): void => {
            if (!error || error.code === 0) { removed++; }
          });
        }
        if (index === 3) { thermal.unsubscribeThermalLevel(undefined); removed++; }
        await this.delay();
        this.record('generation' + index, [level, thermal.getLevel(), this.counts[index], removed]);
        completed++;
      }
      thermal.unregisterThermalLevelCallback();
      thermal.unsubscribeThermalLevel();
      await this.delay();
      this.record('retired', this.counts); completed++;
    } catch (error) {
      this.record('failed', [], (error as Error).message || 'thermal failure');
    } finally {
      thermal.unregisterThermalLevelCallback();
      thermal.unsubscribeThermalLevel();
    }
    this.record('summary', [completed, completed === 6 ? 0 : 1]);
  }
  aboutToAppear(): void {
    const file = fs.openSync(this.logPath, fs.OpenMode.CREATE | fs.OpenMode.WRITE_ONLY | fs.OpenMode.TRUNC);
    fs.closeSync(file); this.run();
  }
  build() { Column() { Text(this.note) }.width('100%').height('100%') }
}
