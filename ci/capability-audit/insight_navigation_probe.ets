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
  @State pageCycle: number = 0;
  @State linkCycle: number = 0;
  private readonly role: string = '__ROLE__';
  private uri: string = 'audit://intent/__TARGET_RUN__';
  private record(name: string, values: number[] = [], data: string = '', error: string = ''): void {
    const row: Observation = { runId: '__RUN__', role: this.role, name, values, data, error };
    const file = fs.openSync('/data/storage/el2/base/files/insight-navigation-__RUN__-results.log',
      fs.OpenMode.CREATE | fs.OpenMode.WRITE_ONLY | fs.OpenMode.APPEND);
    try { fs.writeSync(file.fd, JSON.stringify(row) + '\n'); } finally { fs.closeSync(file); }
  }
  private parameter(kind: string, cycle: number): driver.ExecuteParam {
    const parameter: driver.ExecuteParam = { bundleName: 'org.harmonycontrib.capabilityaudit',
      moduleName: 'entry', abilityName: kind === 'link' ? '' : 'EntryAbility',
      insightIntentName: kind === 'link' ? 'AuditLink' : 'AuditPage',
      executeMode: intent.ExecuteMode.UI_ABILITY_FOREGROUND,
      insightIntentParam: { value: '__RUN__:' + kind + ':' + cycle } };
    if (kind === 'link') { parameter.uris = [this.uri + '?challenge=__RUN__:' + cycle]; }
    return parameter;
  }
  private async initialize(): Promise<void> {
    this.record('identity', [process.uid, process.euid, process.pid]);
    try {
      if (this.role !== 'system') {
        for (const kind of ['page', 'link']) {
          try { await driver.execute(this.parameter(kind, 0)); this.record('denied.' + kind, [0, 0, 0]); }
          catch (error) { this.record('denied.' + kind, [1, error.code, typeof error.code === 'number' ? 1 : 0]); }
        }
        this.record('summary', [1]); this.status = 'finished';
      } else {
        const link = await driver.getInsightIntentInfoByIntentName(
          'org.harmonycontrib.capabilityaudit', 'entry', 'AuditLink', 5);
        const page = await driver.getInsightIntentInfoByIntentName(
          'org.harmonycontrib.capabilityaudit', 'entry', 'AuditPage', 5);
        this.uri = (link.subIntentInfo as driver.LinkIntentInfo).uri;
        this.record('lookup.link', [], JSON.stringify(link));
        this.record('lookup.page', [], JSON.stringify(page)); this.status = 'initialized';
      }
    } catch (error) { this.record('failed', [error.code], '', String(error)); this.status = 'failed'; }
  }
  private async navigate(kind: string): Promise<void> {
    this.status = 'busy';
    const cycle: number = kind === 'page' ? this.pageCycle : this.linkCycle;
    const parameter = this.parameter(kind, cycle);
    this.record('dispatch.' + kind + '.' + cycle, [], JSON.stringify(parameter));
    try {
      const output = await driver.execute(parameter);
      this.record('returned.' + kind + '.' + cycle, [output.code], JSON.stringify(output.result || {}));
      if (kind === 'page') { this.pageCycle++; } else { this.linkCycle++; }
      this.status = 'initialized';
      if (this.pageCycle === 2 && this.linkCycle === 2) { this.record('summary', [1]); this.status = 'finished'; }
    } catch (error) { this.record('failed', [error.code], '', String(error)); this.status = 'failed'; }
  }
  aboutToAppear(): void {
    const file = fs.openSync('/data/storage/el2/base/files/insight-navigation-__RUN__-results.log',
      fs.OpenMode.CREATE | fs.OpenMode.WRITE_ONLY | fs.OpenMode.TRUNC);
    fs.closeSync(file);
  }
  build() {
    Column() {
      Button('Initialize navigation').id('insight-navigation-start').onClick(() => {
        if (this.status === 'ready') { this.status = 'initializing'; this.initialize(); }
      })
      if (this.status === 'initialized') {
        if (this.pageCycle < 2) {
          Button('Execute page').id('insight-navigation-page').onClick(() => { this.navigate('page'); })
        }
        if (this.linkCycle < 2) {
          Button('Execute link').id('insight-navigation-link').onClick(() => { this.navigate('link'); })
        }
      }
      Text(this.status).id('insight-navigation-status')
    }.width('100%').height('100%')
  }
}
