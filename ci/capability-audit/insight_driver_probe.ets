// Candidate real BMS lookup and execution caller; not a reflection or compile-only proof.
import driver from '@ohos.app.ability.insightIntentDriver';
import intent from '@ohos.app.ability.insightIntent';
import fs from '@ohos.file.fs';
import process from '@ohos.process';

interface Observation {
  runId: string; role: string; name: string; values: number[]; data: string; error: string;
}

@Entry
@Component
struct Index {
  @State status: string = 'ready';
  private readonly role: string = '__ROLE__';
  private readonly path: string = '/data/storage/el2/base/files/insight-driver-__RUN__-results.log';
  private record(name: string, values: number[] = [], data: string = '', error: string = ''): void {
    const row: Observation = { runId: '__RUN__', role: '__ROLE__', name, values, data, error };
    const file = fs.openSync(this.path, fs.OpenMode.CREATE | fs.OpenMode.WRITE_ONLY | fs.OpenMode.APPEND);
    try { fs.writeSync(file.fd, JSON.stringify(row) + '\n'); } finally { fs.closeSync(file); }
  }
  private parameter(value: string): driver.ExecuteParam {
    return {
      bundleName: 'org.harmonycontrib.capabilityaudit', moduleName: 'entry', abilityName: 'EntryAbility',
      insightIntentName: 'AuditEntry', executeMode: intent.ExecuteMode.UI_ABILITY_BACKGROUND,
      insightIntentParam: { value, entity: { entityId: 'audit', value } }
    };
  }
  private async denied(method: number): Promise<void> {
    try {
      if (method === 0) {
        await driver.getInsightIntentInfoByBundleName('org.harmonycontrib.capabilityaudit', 5);
      } else {
        const parameter = this.parameter('__RUN__');
        if (method === 2) {
          parameter.insightIntentName = 'AuditFunction'; parameter.insightIntentParam = { value: '__RUN__' };
        }
        await driver.execute(parameter);
      }
      this.record('denied.' + method, [0, 0, 0]);
    } catch (error) {
      const code: number = error.code;
      this.record('denied.' + method, [1, code, typeof error.code === 'number' ? 1 : 0]);
    }
  }
  private async run(): Promise<void> {
    this.record('identity', [process.uid, process.euid, process.pid]);
    try {
      if (this.role !== 'system') {
        await this.denied(0); await this.denied(1); await this.denied(2);
      } else {
        const info = await driver.getInsightIntentInfoByBundleName('org.harmonycontrib.capabilityaudit', 5);
        this.record('lookup', [info.length], JSON.stringify(info));
        for (let cycle = 0; cycle < 2; cycle++) {
          const output = await driver.execute(this.parameter('__RUN__:' + cycle));
          this.record('entry.' + cycle, [output.code], JSON.stringify(output.result));
        }
        const named = await driver.getInsightIntentInfoByIntentName(
          'org.harmonycontrib.capabilityaudit', 'entry', 'AuditFunction', 5);
        this.record('function.metadata', [], JSON.stringify(named));
        for (let cycle = 0; cycle < 2; cycle++) {
          const parameter = this.parameter('__RUN__:' + cycle);
          parameter.insightIntentName = 'AuditFunction';
          parameter.insightIntentParam = { value: '__RUN__:' + cycle };
          const output = await driver.execute(parameter);
          this.record('function.' + cycle, [output.code], JSON.stringify(output.result));
        }
      }
      this.record('summary', [1]); this.status = 'finished';
    } catch (error) {
      this.record('failed', [], '', String(error)); this.status = 'failed';
    }
  }
  aboutToAppear(): void {
    const file = fs.openSync(this.path, fs.OpenMode.CREATE | fs.OpenMode.WRITE_ONLY | fs.OpenMode.TRUNC);
    fs.closeSync(file);
  }
  build() {
    Column() {
      Button('Run intent driver').id('insight-driver-start').onClick(() => {
        if (this.status !== 'ready') { return; }
        this.status = 'running'; this.run();
      })
      Text(this.status).id('insight-driver-status')
    }.width('100%').height('100%')
  }
}
