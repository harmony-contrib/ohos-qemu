import common from '@ohos.app.ability.common';
import window from '@ohos.window';
import formHost from '@ohos.app.form.formHost';
import formInfo from '@ohos.app.form.formInfo';
import formObserver from '@ohos.app.form.formObserver';
import fs from '@ohos.file.fs';
import { BusinessError } from '@ohos.base';
import { Journal, BUNDLE, RUN } from './Journal';

export class Driver {
  static stage?: window.WindowStage;
  static context?: common.UIAbilityContext;
  static formId: string = '';
  static pendingId: string = 'lifecycle';
  static pendingAction: string = 'lifecycle';
  static acquiredResolve?: () => void;
  static watching: boolean = false;
  static marker(): string {
    if (!Driver.context) { throw new Error('actual form host context missing'); }
    return Driver.context.filesDir + '/apps579-form-' + RUN + '.txt';
  }
  static acquired(info: FormCallbackInfo): void {
    if (!/^[1-9][0-9]*$/.test(info.idString)) { throw new Error('native FMS did not allocate a real form id'); }
    if (Driver.formId && Driver.formId !== info.idString) { throw new Error('reacquired a different owned form'); }
    Driver.formId = info.idString;
    const file = fs.openSync(Driver.marker(), fs.OpenMode.CREATE | fs.OpenMode.WRITE_ONLY | fs.OpenMode.TRUNC);
    try { fs.writeSync(file.fd, Driver.formId); } finally { fs.closeSync(file); }
    Journal.record('form-acquired', JSON.stringify(info), 0, Driver.pendingId, Driver.pendingAction);
    if (Driver.acquiredResolve) { Driver.acquiredResolve(); Driver.acquiredResolve = undefined; }
  }
  static async owned(): Promise<formInfo.RunningFormInfo[]> {
    return await formObserver.getRunningFormInfos(true, BUNDLE);
  }
  static watch(): void {
    if (Driver.watching) { return; }
    formObserver.on('formAdd', BUNDLE, (info: formInfo.RunningFormInfo) =>
      Journal.record('native-form-add', JSON.stringify(info), 0, Driver.pendingId, Driver.pendingAction));
    formObserver.on('formRemove', BUNDLE, (info: formInfo.RunningFormInfo) =>
      Journal.record('native-form-remove', JSON.stringify(info), 0, Driver.pendingId, Driver.pendingAction));
    Driver.watching = true;
  }
  static async execute(action: string, context: common.UIAbilityContext): Promise<void> {
    const id = Journal.requestId;
    Driver.context = context;
    if (action === 'identity') { await Journal.identity();
    } else if (action === 'describe') {
      Journal.record('form-provider-info', JSON.stringify(await formHost.getFormsInfo('com.ohos.photos', 'phone_photos')));
      Journal.record('running-forms', JSON.stringify(await Driver.owned()));
    } else if (action === 'boundaries') {
      try {
        Journal.record('form-info-returned', JSON.stringify(await formHost.getFormsInfo('com.ohos.photos', 'phone_photos')));
      } catch (error) { Journal.fail('form-info-error', error as BusinessError); }
      try { Journal.record('form-running-returned', JSON.stringify(await Driver.owned()));
      } catch (error) { Journal.fail('form-running-error', error as BusinessError); }
    } else if (action === 'show' || action === 'attach') {
      Driver.watch(); Driver.pendingId = id; Driver.pendingAction = action;
      if (action === 'show') {
        if (fs.accessSync(Driver.marker()) || (await Driver.owned()).length !== 0) { throw new Error('owned form already exists'); }
        Driver.formId = '';
      } else {
        Driver.formId = fs.readTextSync(Driver.marker());
        if (!/^[1-9][0-9]*$/.test(Driver.formId)) { throw new Error('actual retained form id missing'); }
      }
      await new Promise<void>((resolve, reject) => {
        Driver.acquiredResolve = resolve;
        AppStorage.setOrCreate<string>('apps579-form-id', Driver.formId);
        AppStorage.setOrCreate<boolean>('apps579-form-visible', true);
        setTimeout(() => { if (Driver.acquiredResolve) { Driver.acquiredResolve = undefined;
          reject(new Error('actual FormComponent.onAcquired did not arrive')); } }, 30000);
      });
      Journal.record('running-forms', JSON.stringify(await Driver.owned()));
    } else if (action === 'publish') {
      if (!Driver.formId) { throw new Error('actual acquired form required'); }
      formHost.updateFormLocation(Driver.formId, formInfo.FormLocation.DESKTOP);
      Journal.record('form-published', JSON.stringify(await Driver.owned()));
    } else if (action === 'configure') {
      if (!Driver.formId) { throw new Error('actual acquired form required'); }
      // The provider declares this exact public formConfigAbility. The only
      // formId comes from our real FMS acquisition, never an injected registry.
      await context.startAbility({bundleName: 'com.ohos.photos', moduleName: 'phone_photos',
        abilityName: 'com.ohos.photos.MainAbility', parameters: {formId: Driver.formId}});
      Journal.record('form-config-requested', JSON.stringify({formId: Driver.formId}));
    } else if (action === 'observe') {
      if (!Driver.formId && fs.accessSync(Driver.marker())) { Driver.formId = fs.readTextSync(Driver.marker()); }
      Journal.record('running-forms', JSON.stringify(await Driver.owned()));
    } else if (action === 'delete-form') {
      const before = await Driver.owned();
      Journal.record('form-delete-before', JSON.stringify(before));
      if (!Driver.formId && fs.accessSync(Driver.marker())) { Driver.formId = fs.readTextSync(Driver.marker()); }
      if (before.length) {
        if (before.length !== 1 || before[0].formId !== Driver.formId || before[0].bundleName !== 'com.ohos.photos' ||
          before[0].moduleName !== 'phone_photos' || before[0].abilityName !== 'FormAbility') {
          throw new Error('refuse unrelated native form mutation');
        }
        await formHost.deleteForm(Driver.formId);
      }
      const after = await Driver.owned();
      Journal.record('form-delete-after', JSON.stringify(after));
      if (after.length !== 0) { throw new Error('real owned form still retained'); }
      AppStorage.setOrCreate<boolean>('apps579-form-visible', false);
      if (fs.accessSync(Driver.marker())) { fs.unlinkSync(Driver.marker()); }
      Driver.formId = '';
      if (Driver.watching) {
        formObserver.off('formAdd', BUNDLE); formObserver.off('formRemove', BUNDLE); Driver.watching = false;
      }
    } else if (action === 'exit') { Journal.record('exit-request'); await context.terminateSelf();
    } else { throw new Error('unknown fixed real Photos form action'); }
    Journal.record('done', 'null', 0, id, action);
  }
}
