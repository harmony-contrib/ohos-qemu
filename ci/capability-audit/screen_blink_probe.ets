// Actual public synchronous calls. A runner must independently verify pixels,
// caller death and cleanup; return values alone are not a capability proof.
import config from '@ohos.accessibility.config';
import settings from '@ohos.settings';
import fs from '@ohos.file.fs';
import process from '@ohos.process';
import common from '@ohos.app.ability.common';
import { BusinessError } from '@ohos.base';

interface BlinkRow { runId: string; role: string; name: string; values: number[]; text: string; }

@Entry
@Component
struct Index {
  @State private note: string = 'Screen blink regression';
  private readonly runId: string = '__BLINK_RUN__';
  private readonly role: string = '__BLINK_ROLE__';
  private readonly path: string = '/data/storage/el2/base/files/screen-blink-__BLINK_RUN__-results.log';
  private readonly restorePath: string = '/data/storage/el2/base/files/screen-blink-__BLINK_RUN__-restore';
  private readonly settingKey: string = 'accessibility_flash_reminder_switch';
  private original: string = '';

  private record(name: string, values: number[], text: string = ''): void {
    const row: BlinkRow = { runId: this.runId, role: this.role, name, values, text };
    const file = fs.openSync(this.path, fs.OpenMode.CREATE | fs.OpenMode.WRITE_ONLY | fs.OpenMode.APPEND);
    try { fs.writeSync(file.fd, JSON.stringify(row) + '\n'); } finally { fs.closeSync(file); }
    this.note = name;
  }

  private invoke(start: boolean, mode: config.BlinkingMode, scenario: config.BlinkingScenario): number[] {
    try {
      const value = start ? config.startBlinking(mode, scenario) : config.stopBlinking(mode, scenario);
      return [value, 0, typeof value === 'number' ? 1 : 0];
    } catch (error) {
      const code = (error as BusinessError).code;
      return [-1, typeof code === 'number' ? code : -999, typeof code === 'number' ? 1 : 0];
    }
  }

  private control(name: string, start: boolean, mode: config.BlinkingMode,
    scenario: config.BlinkingScenario = config.BlinkingScenario.TESTING): void {
    this.record(name, this.invoke(start, mode, scenario));
  }

  private master(value: string, name: string): void {
    if (this.role !== 'system' || this.original !== '0') {
      this.record('refused.settings', [], this.original); return;
    }
    const context = this.getUIContext().getHostContext() as common.UIAbilityContext;
    try {
      const written = settings.setValueSync(context, this.settingKey, value, settings.domainName.USER_SECURITY);
      const read = settings.getValueSync(context, this.settingKey, '__missing__', settings.domainName.USER_SECURITY);
      this.record(name, [written ? 1 : 0], read);
      if (name === 'cleanup.master' && written && read === '0' && fs.accessSync(this.restorePath)) {
        fs.unlinkSync(this.restorePath);
      }
    } catch (error) {
      this.record('settings.failed', [], (error as Error).message);
    }
  }

  private restore(): void {
    this.control('cleanup.stop', false, config.BlinkingMode.CONTINUOUS_BLINK);
    this.master(this.original, 'cleanup.master');
  }

  aboutToAppear(): void {
    const file = fs.openSync(this.path, fs.OpenMode.CREATE | fs.OpenMode.WRITE_ONLY | fs.OpenMode.TRUNC);
    fs.closeSync(file);
    this.record('identity', [process.uid, process.euid, process.pid]);
    if (this.role === 'system') {
      const context = this.getUIContext().getHostContext() as common.UIAbilityContext;
      this.original = settings.getValueSync(context, this.settingKey, '__missing__', settings.domainName.USER_SECURITY);
      this.record('initial.master', [], this.original);
      const seed = fs.accessSync(this.restorePath) ? fs.readTextSync(this.restorePath) : '';
      if (seed === this.runId + ':0' && this.original === '1') {
        // The runner restarts only this exact nonce-scoped test caller after
        // proving its original disabled setting and its own enabled write.
        this.original = '0';
      } else if (this.original === '0' && seed === '') {
        const saved = fs.openSync(this.restorePath, fs.OpenMode.CREATE | fs.OpenMode.WRITE_ONLY);
        try { fs.writeSync(saved.fd, this.runId + ':0'); } finally { fs.closeSync(saved); }
      } else if (seed !== '') {
        this.record('unexpected.restore.seed', [], seed); return;
      }
      // A newly packaged disposable guest must start disabled. Never take
      // ownership of an existing enabled user setting.
      if (this.original !== '0') { this.record('unexpected.initial', [], this.original); return; }
    }
    this.control('initial.start', true, config.BlinkingMode.CONTINUOUS_BLINK);
    this.control('initial.stop', false, config.BlinkingMode.CONTINUOUS_BLINK);
    for (const invalid of [0, 3, -1]) {
      this.control('invalid.mode.' + invalid.toString(), true, invalid as config.BlinkingMode);
    }
    for (const invalid of [0, 5, -1]) {
      this.control('invalid.scenario.' + invalid.toString(), false,
        config.BlinkingMode.CONTINUOUS_BLINK, invalid as config.BlinkingScenario);
    }
    this.record('ready', [1]);
  }

  build() {
    Column({ space: 8 }) {
      Text(this.note).fontColor('#ffffff')
      Row({ space: 8 }) {
        Button('Enable').id('blink-enable').onClick(() => this.master('1', 'master.enabled'))
        Button('Disable').id('blink-disable').onClick(() => this.master('0', 'master.disabled'))
        Button('Restore').id('blink-restore').onClick(() => this.restore())
      }
      Row({ space: 8 }) {
        Button('Start').id('blink-start').onClick(() =>
          this.control('continuous.start', true, config.BlinkingMode.CONTINUOUS_BLINK))
        Button('Stop').id('blink-stop').onClick(() =>
          this.control('continuous.stop', false, config.BlinkingMode.CONTINUOUS_BLINK))
        Button('Single').id('blink-single').onClick(() =>
          this.control('single.start', true, config.BlinkingMode.SINGLE_BLINK))
        Button('Wrong scenario').id('blink-wrong-stop').onClick(() => this.control('wrong.stop', false,
          config.BlinkingMode.CONTINUOUS_BLINK, config.BlinkingScenario.CALL))
      }
      Column().id('blink-pixel-surface').width('90%').height(320).backgroundColor('#203040')
    }.width('100%').height('100%').backgroundColor('#203040')
  }
}
