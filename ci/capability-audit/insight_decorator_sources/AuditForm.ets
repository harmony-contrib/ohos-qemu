import { InsightIntentForm } from '@ohos.app.ability.InsightIntentDecorator';
import FormExtensionAbility from '@ohos.app.form.FormExtensionAbility';
@InsightIntentForm({
  intentName: 'AuditForm', domain: 'LocalDomain', intentVersion: '1.0.0',
  displayName: 'Audit form', formName: 'AuditWidget'
})
export default class AuditForm extends FormExtensionAbility {}
