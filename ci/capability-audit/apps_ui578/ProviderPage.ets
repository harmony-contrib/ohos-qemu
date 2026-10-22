// Calls real public APIs. No title/window/export observation is a successful
// provider result, and no exception is converted into an empty success.
import common from '@ohos.app.ability.common';
import notification from '@ohos.notificationManager';
import subscription from '@ohos.notificationExtensionSubscription';
import intelligentScene from '@ohos.intelligentScene';
import certificateDialog from '@ohos.security.certManagerDialog';
import certificate from '@ohos.security.certManager';
import policy from '@ohos.net.policy';
import cellular from '@ohos.telephony.data';
import sim from '@ohos.telephony.sim';
import process from '@ohos.process';
import shortKey from '@ohos.multimodalInput.shortKey';
import admin from '@ohos.enterprise.adminManager';
import accessibility from '@ohos.accessibility.config';
import settings from '@ohos.settings';
import Want from '@ohos.app.ability.Want';
import { BusinessError } from '@ohos.base';
import { Journal, CASE, BUNDLE, RUN } from '../common/Journal';
import { CertificateProgram } from '../common/CertificateProgram';
import { SettingsProgram } from '../common/SettingsProgram';
import { ApnProgram } from '../common/ApnProgram';

@Entry
@Component
struct Index {
  @State note: string = 'Real system-provider caller';
  @State input: string = '';
  @State count: number = 0;
  @StorageProp('apps578-request-serial') @Watch('requestChanged') requestSerial: number = 0;
  @State embeddedDnd: boolean = false;
  @State embeddedNetwork: boolean = false;
  private embeddedOperation: string = '';
  private lastQueryGeneration: number = -1;
  private requestChanged(): void {
    if ((CASE === 'intelligent-scene' && Journal.argument === 'read-current-dnd') ||
      (CASE === 'apn' && (Journal.argument === 'read-current-apn' || Journal.argument === 'get-apn-environment'))) {
      // Keep the REAL hosted provider alive while its asynchronous user choice
      // reaches ANS. This is an independent public API consumer, not a UI value.
      if (this.lastQueryGeneration !== Journal.requestGeneration) {
        this.lastQueryGeneration = Journal.requestGeneration;
        this.call(Journal.argument === 'get-apn-environment' ? 'environment' : 'read');
      }
      return;
    }
    this.embeddedDnd = false;
    this.embeddedNetwork = false;
  }
  aboutToAppear(): void { this.requestChanged(); }
  private context(): common.UIAbilityContext { return this.getUIContext().getHostContext() as common.UIAbilityContext; }

  private duplicate(): void {
    const original: string = Journal.operation;
    this.call('invoke');
    Journal.operation = original + '.duplicate';
    this.call('invoke');
    Journal.operation = original;
  }

  private async call(action: string): Promise<void> {
    // Capture the operation before awaiting: a duplicate request/late result
    // must retain its originating session, not borrow the newest onNewWant.
    const operation: string = Journal.operation;
    Journal.record('call.' + action, 0, 'null', operation);
    try {
      let value: string = 'null';
      const context = this.context();
      if (action === 'prime-settings') {
        await context.startAbility({ bundleName: 'com.ohos.settings', abilityName: 'com.ohos.settings.MainAbility' });
      } else if (action === 'open-settings') {
        if (CASE === 'intelligent-scene') {
          this.embeddedOperation = operation;
          this.embeddedDnd = true;
        } else {
          await context.startAbility({ bundleName: 'com.ohos.settings', abilityName: 'com.ohos.settings.MainAbility' });
        }
      } else if (CASE === 'notification-settings') {
        if (action === 'read') { value = JSON.stringify({ settings: await notification.getNotificationSetting(),
          enabled: await notification.isNotificationEnabled() }); }
        else { value = JSON.stringify(await notification.openNotificationSettingsWithResult(
          action === 'invalid' ? null as common.UIAbilityContext : context)); }
      } else if (CASE === 'notification-subscription') {
        if (action === 'read') { value = JSON.stringify(await subscription.isUserGranted()); }
        else { value = JSON.stringify(await subscription.openSubscriptionSettingsWithResult(
          action === 'invalid' ? null as common.UIAbilityContext : context)); }
      } else if (CASE === 'intelligent-scene') {
        // These are two independent public queries, not hard-coded expected values.
        const enabled: boolean = await intelligentScene.isDoNotDisturbEnabled();
        const allowed: boolean = await intelligentScene.isNotifyAllowedInDoNotDisturb();
        value = JSON.stringify([enabled, allowed]);
      } else if (CASE === 'certificate-dialog') {
        value = await new CertificateProgram(context).run(action);
      } else if (CASE === 'network-policy') {
        if (action === 'read') { value = JSON.stringify(await policy.getNetAccessPolicy()); }
        else if (action === 'privileged') { value = JSON.stringify(await policy.getNetworkAccessPolicy(process.uid)); }
        else if (action === 'network-environment') { value = JSON.stringify({ maxSimCount: sim.getMaxSimCount() }); }
        else if (action === 'spoof' || action === 'spoof-self') {
          this.embeddedOperation = operation;
          this.embeddedNetwork = true;
        }
        else { await policy.showAppNetPolicySettings(action === 'invalid' ? null as common.UIAbilityContext : context); }
      } else if (CASE === 'apn') {
        if (action === 'read') { value = await new ApnProgram(context).read(); }
        else if (action === 'environment') { value = await new ApnProgram(context).environment(); }
        else { await cellular.showSystemApnSettings(action === 'invalid' ? null as common.UIAbilityContext : context); }
      } else if (CASE === 'shortkey') {
        await shortKey.setKeyDownDuration(action === 'invalid' ? '' : 'qemu.settings', Journal.numberArgument);
      } else if (CASE === 'enterprise') {
        const target: Want = { bundleName: BUNDLE, abilityName: action === 'invalid' ? 'MissingAdmin578' : 'Admin578' };
        if (action === 'byod') {
          value = JSON.stringify(await context.startAbilityForResult({ bundleName: 'com.ohos.adminprovisioning',
            abilityName: 'ByodAdminProvisionAbility', parameters: { bundleName: BUNDLE, abilityName: 'Admin578', activateId: RUN } }));
        } else if (action === 'byod-read') { value = JSON.stringify(admin.isByodAdmin(target)); }
        else if (action === 'read') { value = JSON.stringify(await admin.isAdminEnabled(target)); }
        else if (action === 'disable') { await admin.disableAdmin(target); }
        else {
          await admin.enableAdmin(target, { name: 'apps578-' + RUN, description: 'Disposable QEMU admin' },
            action === 'super' ? admin.AdminType.ADMIN_TYPE_SUPER : admin.AdminType.ADMIN_TYPE_NORMAL);
        }
      } else if (CASE === 'accessibility-settings') {
        value = await new SettingsProgram(context).run(action);
      } else if (CASE === 'accessibility-input') {
        value = JSON.stringify({ text: this.input, count: this.count });
      } else { throw new Error('unimplemented apps578 public API case'); }
      Journal.record('return.' + action, 0, value === undefined ? 'null' : value, operation);
    } catch (error) {
      if (error === null || error === undefined) {
        Journal.record('return.' + action, -1,
          JSON.stringify({ errorKind: error === null ? 'null' : 'undefined', raw: error === null ? null : 'undefined' }), operation);
      } else {
        const e = error as BusinessError;
        Journal.record('return.' + action, typeof e.code === 'number' ? e.code : -1,
          JSON.stringify({ message: e.message }), operation);
      }
    }
    this.note = operation;
  }

  build() {
    Stack() {
    Column({ space: 10 }) {
      Text('apps578/' + RUN + '/' + CASE).id('apps578-identity')
      Text(this.note).id('apps578-operation')
      Row({ space: 8 }) {
        Button('Invoke').id('apps578-invoke').onClick(() => this.call('invoke'))
        Button('Read').id('apps578-read').onClick(() => this.call('read'))
        Button('Invalid').id('apps578-invalid').onClick(() => this.call('invalid'))
        Button('Two real requests').id('apps578-duplicate').onClick(() => this.duplicate())
      }
      if (CASE === 'intelligent-scene') {
        Button('Initialize Settings').id('apps578-prime-settings').onClick(() => this.call('prime-settings'))
      }
      if (CASE === 'certificate-dialog') {
        Button('CA page').id('apps578-ca').onClick(() => this.call('ca'))
      }
      if (CASE === 'enterprise') {
        Row({ space: 4 }) {
          Button('Disable own').id('apps578-disable').onClick(() => this.call('disable'))
          Button('Super boundary').id('apps578-super').onClick(() => this.call('super'))
          Button('BYOD').id('apps578-byod').onClick(() => this.call('byod'))
          Button('Own BYOD state').id('apps578-byod-read').onClick(() => this.call('byod-read'))
        }
      }
      if (CASE === 'network-policy') {
        Row({ space: 4 }) {
          Button('Own privileged query').id('apps578-privileged').onClick(() => this.call('privileged'))
          Button('SIMs').id('apps578-network-environment').onClick(() => this.call('network-environment'))
        }
        Row({ space: 4 }) {
          Button('Foreign UID').id('apps578-spoof').onClick(() => this.call('spoof'))
          Button('Own UID spoof').id('apps578-spoof-self').onClick(() => this.call('spoof-self'))
        }
      }
      if (CASE === 'certificate-dialog' || CASE === 'accessibility-settings') {
        Flex({ wrap: FlexWrap.Wrap }) {
          ForEach(CASE === 'certificate-dialog' ? ['import','remove','install-ca','read-ca','remove-ca',
            'recover-ca','invalid-remove-ca','unsupported-remove-ca'] :
            ['settings-save','ignore-enable','animation-enable','settings-restore'], (action: string) => {
            Button(action).id('apps578-' + action).onClick(() => this.call(action)).margin(3)
          })
        }
      }
      if (CASE !== 'certificate-dialog') {
      TextInput({ text: this.input }).id('apps578-input')
        .onChange((text: string) => { this.input = text; Journal.record('input.changed', 0, JSON.stringify(text)); })
      Button('Real input target').id('apps578-increment').accessibilityText('apps578 real input target')
        .onClick(() => { ++this.count; Journal.record('input.clicked', 0, JSON.stringify(this.count)); })
      Text(this.count.toString()).id('apps578-count')
      Column().id('apps578-surface').width('90%').height(200).backgroundColor('#203040')
      }
    }.width('100%').height('100%').backgroundColor('#ffffff')
    if (CASE === 'intelligent-scene' && this.embeddedDnd) {
      UIExtensionComponent({ bundleName: 'com.ohos.intelligentscene',
        abilityName: 'IntelligentSceneUIExtSettingAbility', parameters: {
          'ability.want.params.uiExtensionType': 'sys/commonUI', 'action': 'jumpBySettings',
          'specifiedModeId': '1', 'pushParams': 'intelligent_scene_home_entry',
          'navigationMode': NavigationMode.Stack
        } })
        .onRemoteReady((proxy: UIExtensionProxy) => {
          proxy.send({ navigationMode: NavigationMode.Stack });
          Journal.record('dnd.extension.ready', 0, 'null', this.embeddedOperation);
        })
        .onReceive((data: Record<string, Object>) => {
          Journal.record('dnd.extension.data', 0, JSON.stringify(data), this.embeddedOperation);
        })
        .onError((error: BusinessError) => {
          Journal.record('dnd.extension.error', error.code, JSON.stringify(error), this.embeddedOperation);
        })
        .onTerminated(() => {
          Journal.record('dnd.extension.terminated', 0, 'null', this.embeddedOperation);
          this.embeddedDnd = false;
        })
        .width('100%').height('100%')
    }
    if (CASE === 'network-policy' && this.embeddedNetwork) {
      UIExtensionComponent({ bundleName: 'com.ohos.communicationsetting',
        abilityName: 'UIExtensionProvider', parameters: {
          'ability.want.params.uiExtensionType': 'sys/commonUI',
          'appUid': Journal.operation === 'net.spoof.self' ? process.uid : Journal.numberArgument,
          'ohos.aafwk.param.callerUid': Journal.numberArgument,
          'ohos.net.policy.callerUid': Journal.numberArgument,
          'ability.want.params.uiExtensionHostUid': Journal.numberArgument
        } })
        .onRemoteReady(() => Journal.record('network.extension.ready', 0, 'null', this.embeddedOperation))
        .onError((error: BusinessError) => {
          Journal.record('network.extension.error', error.code, JSON.stringify(error), this.embeddedOperation);
          this.embeddedNetwork = false;
        })
        .onTerminated(() => {
          Journal.record('network.extension.terminated', 0, 'null', this.embeddedOperation);
          this.embeddedNetwork = false;
        })
        .width('100%').height('100%')
    }
    }.width('100%').height('100%')
  }
}
