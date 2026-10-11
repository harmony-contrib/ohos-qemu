import { InsightIntentEntry } from '@ohos.app.ability.InsightIntentDecorator';
import InsightIntentEntryExecutor from '@ohos.app.ability.InsightIntentEntryExecutor';
import insightIntent from '@ohos.app.ability.insightIntent';
import { AuditEntity } from './AuditEntity';

@InsightIntentEntry({
  intentName: 'AuditEntry', domain: 'LocalDomain', intentVersion: '1.0.0',
  displayName: 'Audit entry', abilityName: 'EntryAbility',
  executeMode: [insightIntent.ExecuteMode.UI_ABILITY_BACKGROUND],
  parameters: {
    type: 'object', properties: {
      value: { type: 'string' }, entity: { $ref: '/schemas/AuditEntity' }
    }, required: ['value', 'entity']
  }
})
export default class AuditEntry extends InsightIntentEntryExecutor<AuditEntity> {
  value: string = '';
  entity: AuditEntity = new AuditEntity();
  onExecute(): Promise<insightIntent.IntentResult<AuditEntity>> {
    const output = new AuditEntity();
    output.value = this.value + ':entry';
    const result: insightIntent.IntentResult<AuditEntity> = { code: 0, result: output };
    return Promise.resolve(result);
  }
}
