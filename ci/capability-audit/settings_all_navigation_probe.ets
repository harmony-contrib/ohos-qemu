// Ordinary public callers only. A void return does NOT prove that a page rendered.
import settings from '@ohos.settings';
import inputMethod from '@ohos.inputMethod';
import screen from '@ohos.screen';
import fs from '@ohos.file.fs';
import process from '@ohos.process';
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
    this.record('identity', true, JSON.stringify([process.uid, process.euid, process.pid]));
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
    for (let index: number = 0; index < 2; index++) {
      try {
        if (index === 0) settings.openAppDetailSettingsPage(this.context, '');
        else settings.openAppDetailSettingsPage(this.context, 'org.harmonycontrib.capabilityaudit', -1);
        this.record('invalid-app.' + index.toString(), false, 'Unexpected success');
      } catch (error) {
        this.record('invalid-app.' + index.toString(), (error as BusinessError).code === 16900010,
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

  private openExtra(route: string): void {
    try {
      if (route === 'mobile') settings.openMobileNetworkSettingsPage(this.context);
      else if (route === 'refresh') settings.openScreenRefreshRateSettingsPage(this.context);
      else if (route === 'sound') settings.openSoundSettingsPage(this.context);
      else if (route === 'biometrics') settings.openBiometricsSettingsPage(this.context);
      else if (route === 'about') settings.openAboutDeviceSettingsPage(this.context);
      else if (route === 'nfc') settings.openNfcSettingsPage(this.context);
      else if (route === 'double-click') settings.openDoubleClickSettingsPage(this.context);
      else if (route === 'app-detail') settings.openAppDetailSettingsPage(this.context,
        'org.harmonycontrib.capabilityaudit');
      else throw new Error('Unknown diagnostic route');
      this.record(route + '.request-returned', true, 'void-return-only-not-render-proof');
    } catch (error) { this.record(route + '.request-returned', false, JSON.stringify(error)); }
  }

  private async checkScreenPermission(): Promise<void> {
    try {
      await screen.getAllScreens();
      this.record('screen.ordinary-denial', false, 'Unexpected system API access');
    } catch (error) {
      this.record('screen.ordinary-denial', (error as BusinessError).code === 202, JSON.stringify(error));
    }
  }

  build() {
    Column({ space: 16 }) {
      Text('Settings challenge __SETTINGS_RUN__').id('settings-run-marker')
      Text(this.note).id('settings-probe-state')
      Row({ space: 16 }) {
        Button('Input settings').id('settings-probe-input').onClick(() => this.openInput())
        Button('Installed input detail').id('settings-probe-detail').onClick(() => this.openDetail())
      }
      Row({ space: 16 }) {
        Button('Network settings').id('settings-probe-network').onClick(() => { this.openNetwork(); })
        Button('Display settings').id('settings-probe-display').onClick(() => this.openDisplay())
      }
      Row({ space: 16 }) {
        Button('Mobile network').id('settings-probe-mobile').onClick(() => this.openExtra('mobile'))
        Button('Refresh rate').id('settings-probe-refresh').onClick(() => this.openExtra('refresh'))
      }
      Row({ space: 16 }) {
        Button('Sound').id('settings-probe-sound').onClick(() => this.openExtra('sound'))
        Button('Biometrics').id('settings-probe-biometrics').onClick(() => this.openExtra('biometrics'))
      }
      Row({ space: 16 }) {
        Button('About device').id('settings-probe-about').onClick(() => this.openExtra('about'))
        Button('NFC').id('settings-probe-nfc').onClick(() => this.openExtra('nfc'))
      }
      Row({ space: 16 }) {
        Button('Double-click settings').id('settings-probe-double-click').onClick(() => this.openExtra('double-click'))
      }
      Row({ space: 16 }) {
        Button('Own app details').id('settings-probe-app-detail').onClick(() => this.openExtra('app-detail'))
        Button('Screen API boundary').id('settings-probe-screen-denial').onClick(() => { this.checkScreenPermission(); })
      }
    }.width('100%').height('100%').justifyContent(FlexAlign.Center).backgroundColor(Color.White)
  }
}
