// Ordinary widget acquisition through FormComponent, then real service lifecycle.
import formHost from '@ohos.app.form.formHost';
import fs from '@ohos.file.fs';
import process from '@ohos.process';

interface Observation {
  runId: string; role: string; cycle: number; name: string; values: number[]; data: string; error: string;
}
@Entry
@Component
struct Index {
  @State status: string = 'ready';
  @State showForm: boolean = false;
  @State cycle: number = 0;
  private formId: string = '';
  private readonly role: string = '__ROLE__';
  private record(name: string, values: number[] = [], data: string = '', error: string = ''): void {
    const row: Observation = { runId: '__RUN__', role: this.role, cycle: this.cycle, name, values, data, error };
    const file = fs.openSync('/data/storage/el2/base/files/insight-form-host-__RUN__-results.log',
      fs.OpenMode.CREATE | fs.OpenMode.WRITE_ONLY | fs.OpenMode.APPEND);
    try { fs.writeSync(file.fd, JSON.stringify(row) + '\n'); } finally { fs.closeSync(file); }
  }
  private async run(): Promise<void> {
    this.record('identity', [process.uid, process.euid, process.pid]);
    if (this.role === 'system') { this.showForm = true; return; }
    try {
      await formHost.requestForm('1'); this.record('denied', [0, 0, 0]);
    } catch (error) {
      this.record('denied', [1, error.code, typeof error.code === 'number' ? 1 : 0]);
    }
    this.record('summary', [1]); this.status = 'finished';
  }
  private acquired(info: FormCallbackInfo): void {
    this.formId = info.idString;
    this.record('acquired', [1, info.isLocked ? 1 : 0], info.idString);
    this.status = 'acquired';
  }
  private async request(): Promise<void> {
    this.status = 'requesting';
    try {
      await formHost.requestForm(this.formId);
      this.record('request', [1], this.formId); this.status = 'requested';
    } catch (error) {
      this.record('failed', [error.code], this.formId, String(error)); this.status = 'failed';
    }
  }
  private async remove(): Promise<void> {
    this.status = 'deleting';
    try {
      await formHost.deleteForm(this.formId);
      this.record('delete', [1], this.formId); this.showForm = false;
      try {
        await formHost.requestForm(this.formId); this.record('deleted.reject', [0, 0, 0], this.formId);
      } catch (error) {
        this.record('deleted.reject', [1, error.code, typeof error.code === 'number' ? 1 : 0], this.formId);
      }
      this.record('summary', [1]); this.status = 'finished';
    } catch (error) {
      this.record('failed', [error.code], this.formId, String(error)); this.status = 'failed';
    }
  }
  aboutToAppear(): void {
    const file = fs.openSync('/data/storage/el2/base/files/insight-form-host-__RUN__-results.log',
      fs.OpenMode.CREATE | fs.OpenMode.WRITE_ONLY | fs.OpenMode.TRUNC);
    fs.closeSync(file);
  }
  build() {
    Column() {
      Button('Run form host').id('insight-form-host-start').onClick(() => {
        if (this.status !== 'ready') { return; }
        this.status = 'running'; this.run();
      })
      Text(this.status).id('insight-form-host-status')
      if (this.showForm) {
        FormComponent({ id: 0, name: 'AuditWidget',
          bundle: 'org.harmonycontrib.capabilityaudit', ability: 'AuditForm', module: 'entry',
          dimension: 2, temporary: true })
          .size({ width: 240, height: 240 }).id('insight-form-host-widget')
          .onAcquired((info: FormCallbackInfo) => { this.acquired(info); })
          .onLoad(() => { this.record('load', [1], this.formId); })
          .onUpdate((info: FormCallbackInfo) => { this.record('update', [1], info.idString); })
          .onUninstall((info: FormCallbackInfo) => { this.record('uninstall', [1], info.idString); })
          .onError((error: ErrorInformation) => {
            this.record('failed', [error.errcode], this.formId, error.msg); this.status = 'failed';
          })
      }
      if (this.status === 'acquired') {
        Button('Request form').id('insight-form-host-request').onClick(() => { this.request(); })
      }
      if (this.status === 'requested' || (this.status === 'failed' && this.formId !== '')) {
        Button('Delete form').id('insight-form-host-delete').onClick(() => { this.remove(); })
      }
      if (this.role === 'system' && this.status === 'finished' && this.cycle === 0) {
        Button('Repeat form').id('insight-form-host-repeat').onClick(() => {
          this.cycle++; this.formId = ''; this.status = 'ready';
        })
      }
    }.width('100%').height('100%')
  }
}
