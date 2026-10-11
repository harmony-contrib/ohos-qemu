import { InsightIntentEntity } from '@ohos.app.ability.InsightIntentDecorator';
import insightIntent from '@ohos.app.ability.insightIntent';
@InsightIntentEntity({
  entityCategory: 'audit entity',
  parameters: {
    $id: '/schemas/AuditEntity', type: 'object',
    properties: { value: { type: 'string' } }, required: ['value']
  }, supportedQueryProperties: ['value']
})
export class AuditEntity implements insightIntent.IntentEntity {
  entityId: string = 'audit';
  value: string = '';
}
