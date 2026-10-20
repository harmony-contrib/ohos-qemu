import { Driver } from '../common/Driver';
import { Journal } from '../common/Journal';
import formInfo from '@ohos.app.form.formInfo';

@Entry
@Component
struct Index {
  @StorageLink('apps579-form-visible') visible: boolean = false;
  @StorageLink('apps579-form-id') formId: string = '';
  build() {
    Column() {
      Text('Owned Photos form host').id('apps579-form-host-label')
      if (this.visible) {
        FormComponent({id: this.formId || 0, name: 'widget1', bundle: 'com.ohos.photos',
          ability: 'FormAbility', module: 'phone_photos', dimension: FormDimension.Dimension_2_4,
          temporary: false, want: {parameters: {'ohos.extra.param.key.form_location': this.formId ? formInfo.FormLocation.DESKTOP : formInfo.FormLocation.FORM_CENTER}}})
          .size({width: 360, height: 180}).id('apps579-form-widget')
          .onAcquired((info: FormCallbackInfo) => { Driver.acquired(info); })
          .onLoad(() => { Journal.record('form-render-load', 'null', 0, Driver.pendingId, Driver.pendingAction); })
          .onUpdate((info: FormCallbackInfo) => {
            Journal.record('form-render-update', JSON.stringify(info), 0, Driver.pendingId, Driver.pendingAction);
          })
          .onUninstall((info: FormCallbackInfo) => {
            Journal.record('form-uninstall', JSON.stringify(info), 0, Driver.pendingId, Driver.pendingAction);
          })
          .onError((error: ErrorInformation) => {
            Journal.record('form-component-error', JSON.stringify(error), error.errcode,
              Driver.pendingId, Driver.pendingAction);
          })
      }
    }.width('100%').height('100%')
  }
}
