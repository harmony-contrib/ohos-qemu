import config from '@ohos.accessibility.config';
import settings from '@ohos.settings';
import common from '@ohos.app.ability.common';
import osAccount from '@ohos.account.osAccount';
import display from '@ohos.display';
import screen from '@ohos.screen';
import { BusinessError } from '@ohos.base';
import { Journal, RUN } from '../common/Journal';
import { AccountProgram } from '../common/AccountProgram';

@Entry
@Component
struct Index {
  @State serial: number = 0;
  @State note: string = 'Owned real public blinking';
  private key: string = 'accessibility_flash_reminder_switch';
  private readonly removed = (id: number): void => { Journal.record('display.removed', 0, JSON.stringify(id)); };
  private readonly added = (id: number): void => { Journal.record('display.added', 0, JSON.stringify(id)); };
  private readonly changed = (id: number): void => { Journal.record('display.changed', 0, JSON.stringify(id)); };
  private context(): common.UIAbilityContext { return this.getUIContext().getHostContext() as common.UIAbilityContext; }
  aboutToAppear(): void {
    display.on('remove', this.removed);
    display.on('add', this.added);
    display.on('change', this.changed);
  }
  aboutToDisappear(): void {
    display.off('remove', this.removed);
    display.off('add', this.added);
    display.off('change', this.changed);
  }
  private async call(action: string): Promise<void> {
    const operation: string = Journal.operation;
    Journal.record('call.' + action, 0, 'null', operation);
    try {
      let value: string = 'null';
      if (action === 'read') {
        value = JSON.stringify(settings.getValueSync(this.context(), this.key, '__missing__', settings.domainName.USER_SECURITY));
      } else if (action === 'enable' || action === 'disable') {
        const wanted: string = action === 'enable' ? '1' : '0';
        const written = settings.setValueSync(this.context(), this.key, wanted, settings.domainName.USER_SECURITY);
        const read = settings.getValueSync(this.context(), this.key, '__missing__', settings.domainName.USER_SECURITY);
        value = JSON.stringify({ written, read });
      } else if (action === 'account-program') {
        await new AccountProgram(this.context()).run();
      } else if (action === 'account-read') {
        const manager = osAccount.getAccountManager();
        value = JSON.stringify({ foreground: await manager.getForegroundOsAccountLocalId(),
          accounts: await manager.queryAllCreatedOsAccounts() });
      } else if (action === 'display-read') {
        const current = display.getDefaultDisplaySync();
        value = JSON.stringify({ id: current.id, width: current.width, height: current.height });
      } else if (action === 'screen-read' || action === 'screen-mode') {
        const current = display.getDefaultDisplaySync();
        const screens = await screen.getAllScreens();
        const matches = screens.filter((item: screen.Screen) =>
          item.id === current.id && item.sourceMode === screen.ScreenSourceMode.SCREEN_MAIN);
        if (matches.length !== 1) { throw new Error('unique actual main Screen/default Display binding required'); }
        const actual = matches[0];
        if (action === 'screen-mode') {
          const modes = actual.supportedModeInfo.filter((mode: screen.ScreenModeInfo) => mode.id === Journal.numberArgument);
          if (!Number.isInteger(Journal.numberArgument) || modes.length !== 1) {
            throw new Error('only a real advertised main-screen mode ID is allowed');
          }
          await actual.setScreenActiveMode(Journal.numberArgument);
        } else {
          value = JSON.stringify({ defaultDisplay: { id: current.id, width: current.width, height: current.height },
            screens: screens.map((item: screen.Screen) => ({ id: item.id, sourceMode: item.sourceMode,
              activeModeIndex: item.activeModeIndex, modes: item.supportedModeInfo.map((mode: screen.ScreenModeInfo) =>
                ({ id: mode.id, width: mode.width, height: mode.height, refreshRate: mode.refreshRate })) })) });
        }
      } else {
        const mode: config.BlinkingMode = (action === 'single' ? config.BlinkingMode.SINGLE_BLINK :
          action === 'invalid-mode' ? -1 : config.BlinkingMode.CONTINUOUS_BLINK) as config.BlinkingMode;
        const scenario: config.BlinkingScenario = (action === 'wrong-stop' ? config.BlinkingScenario.CALL :
          action === 'invalid-scenario' ? -1 : config.BlinkingScenario.TESTING) as config.BlinkingScenario;
        value = JSON.stringify(action === 'stop' || action === 'wrong-stop' || action === 'invalid-scenario' ?
          config.stopBlinking(mode, scenario) : config.startBlinking(mode, scenario));
      }
      Journal.record('return.' + action, 0, value, operation);
    } catch (error) {
      const e = error as BusinessError;
      Journal.record('return.' + action, typeof e.code === 'number' ? e.code : -1,
        JSON.stringify({ message: e.message }), operation);
    }
    this.serial = Journal.serial;
    this.note = operation;
  }
  build() {
    Column({ space: 5 }) {
      Text('apps578/' + RUN).fontColor('#ffffff').id('apps578-identity')
      Text(this.note).fontColor('#ffffff')
      Row({ space: 0 }) {
        ForEach([0,1,2,3,4,5,6,7], (bit: number) => {
          Column().width(20).height(20).backgroundColor((this.serial & (1 << bit)) ? '#ffffff' : '#000000')
        })
      }.id('blink-frame-marker').width(160).height(20)
      Row({ space: 4 }) {
        ForEach(['read','enable','disable','start','stop','wrong-stop','single','invalid-mode','invalid-scenario'], (action: string) => {
          Button(action).id('apps578-' + action).onClick(() => this.call(action))
        })
      }
      Row({ space: 4 }) {
        ForEach(['account-program','account-read','display-read','screen-read','screen-mode'], (action: string) => {
          Button(action).id('apps578-' + action).onClick(() => this.call(action))
        })
      }
      Column().id('blink-pixel-surface').width('90%').height(320).backgroundColor('#203040')
    }.width('100%').height('100%').backgroundColor('#203040')
  }
}
