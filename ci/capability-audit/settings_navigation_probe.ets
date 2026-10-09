// Ordinary public callers only. A void return does NOT prove that a page rendered.
import settings from '@ohos.settings';
import inputMethod from '@ohos.inputMethod';
import fs from '@ohos.file.fs';
import { common } from '@kit.AbilityKit';
import { BusinessError } from '@kit.BasicServicesKit';

interface Observation { runId: string; sequence: number; name: string; pass: boolean; value: string; }

@Entry
@Component
struct Index {
  @State private note: string = 'Settings public navigation';
  private context: common.UIAbilityContext = getContext(this) as common.UIAbilityContext;
  private readonly path: string = '/data/storage/el2/base/files/settings-navigation-__SETTINGS_RUN__-results.log';
  private sequence: number = 0;
  private started: boolean = false;
  private methods: inputMethod.InputMethodProperty[] = [];

  private record(name: string, pass: boolean, value: string): void {
    const observation: Observation = { runId: '__SETTINGS_RUN__', sequence: ++this.sequence,
      name: name, pass: pass, value: value };
    const file = fs.openSync(this.path, fs.OpenMode.WRITE_ONLY | fs.OpenMode.CREATE | fs.OpenMode.APPEND);
    fs.writeSync(file.fd, JSON.stringify(observation) + '\n');
    fs.closeSync(file);
    this.note = name;
  }

  aboutToAppear(): void {
    if (this.started) return;
    this.started = true;
    if (fs.accessSync(this.path)) throw new Error('Fresh Settings result path already exists');
    try {
      this.methods = inputMethod.getSetting().getAllInputMethodsSync();
      this.record('installed-input-methods', this.methods.length > 0, JSON.stringify(this.methods));
    } catch (error) {
      this.record('installed-input-methods', false, JSON.stringify(error));
    }
    for (let index: number = 0; index < 2; index++) {
      try {
        settings.openInputMethodDetail(this.context, index === 0 ? '' : 'not.an.installed.ime',
          index === 0 ? 'id' : '');
        this.record('empty-identity.' + index.toString(), false, 'Unexpected success');
      } catch (error) {
        this.record('empty-identity.' + index.toString(), (error as BusinessError).code === 16900010,
          JSON.stringify(error));
      }
    }
    this.record('ready', true, 'Host must verify real provider UI and return-to-caller for each request');
  }

  private openInput(): void {
    try {
      settings.openInputMethodSettings(this.context);
      this.record('input.request-returned', true, 'void-return-only-not-render-proof');
    } catch (error) { this.record('input.request-returned', false, JSON.stringify(error)); }
  }

  private openDetail(): void {
    if (this.methods.length === 0) {
      this.record('detail.request-returned', false, 'No actual installed input method');
      return;
    }
    const ime = this.methods[0];
    try {
      settings.openInputMethodDetail(this.context, ime.name, ime.id);
      this.record('detail.request-returned', true, JSON.stringify(ime));
    } catch (error) { this.record('detail.request-returned', false, JSON.stringify(error)); }
  }

  private async openNetwork(): Promise<void> {
    try {
      const result: boolean = await settings.openNetworkManagerSettings(this.context);
      this.record('network.result', result === true, JSON.stringify(result));
    } catch (error) { this.record('network.result', false, JSON.stringify(error)); }
  }

  private openDisplay(): void {
    try {
      settings.openDisplaySettingsPage(this.context);
      this.record('display.request-returned', true, 'void-return-only-not-render-proof');
    } catch (error) { this.record('display.request-returned', false, JSON.stringify(error)); }
  }

  build() {
    Column({ space: 16 }) {
      Text(this.note).id('settings-probe-state')
      Button('Input settings').id('settings-probe-input').onClick(() => this.openInput())
      Button('Installed input detail').id('settings-probe-detail').onClick(() => this.openDetail())
      Button('Network settings').id('settings-probe-network').onClick(() => { this.openNetwork(); })
      Button('Display settings').id('settings-probe-display').onClick(() => this.openDisplay())
    }.width('100%').height('100%').justifyContent(FlexAlign.Center).backgroundColor(Color.White)
  }
}
