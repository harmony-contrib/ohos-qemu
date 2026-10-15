import { InsightIntentForm } from '@ohos.app.ability.InsightIntentDecorator';
import FormExtensionAbility from '@ohos.app.form.FormExtensionAbility';
import formBindingData from '@ohos.app.form.formBindingData';
import formInfo from '@ohos.app.form.formInfo';
import formProvider from '@ohos.app.form.formProvider';
import Want from '@ohos.app.ability.Want';
import fs from '@ohos.file.fs';
import { BusinessError } from '@ohos.base';
@InsightIntentForm({
  intentName: 'AuditForm', domain: 'LocalDomain', intentVersion: '1.0.0',
  displayName: 'Audit form', formName: 'AuditWidget'
})
export default class AuditForm extends FormExtensionAbility {
  private record(name: string, formId: string): void {
    const path = '/data/storage/el2/base/files/insight-form-__INTENT_RUN__-results.log';
    const file = fs.openSync(path, fs.OpenMode.CREATE | fs.OpenMode.WRITE_ONLY | fs.OpenMode.APPEND);
    try {
      fs.writeSync(file.fd, JSON.stringify({ runId: '__INTENT_RUN__', name, formId }) + '\n');
    } finally { fs.closeSync(file); }
  }
  onAddForm(want: Want): formBindingData.FormBindingData {
    const formId = String(want.parameters?.[formInfo.FormParam.IDENTITY_KEY]);
    this.record('add', formId);
    return formBindingData.createFormBindingData({ runId: '__INTENT_RUN__', formId, state: 'added' });
  }
  onUpdateForm(formId: string): void {
    this.record('update', formId);
    const data = formBindingData.createFormBindingData({ runId: '__INTENT_RUN__', formId, state: 'updated' });
    formProvider.updateForm(formId, data).then(() => { this.record('update.success', formId); })
      .catch((error: BusinessError) => { this.record('update.failed.' + error.code, formId); });
  }
  onRemoveForm(formId: string): void { this.record('remove', formId); }
}
