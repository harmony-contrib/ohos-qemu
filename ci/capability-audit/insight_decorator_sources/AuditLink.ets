import { InsightIntentLink } from '@ohos.app.ability.InsightIntentDecorator';
@InsightIntentLink({
  intentName: 'AuditLink', domain: 'LocalDomain', intentVersion: '1.0.0',
  displayName: 'Audit link', uri: 'audit://intent/__INTENT_RUN__'
})
export class AuditLink { tag: string = 'link'; }
