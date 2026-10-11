import { InsightIntentFunction, InsightIntentFunctionMethod } from '@ohos.app.ability.InsightIntentDecorator';
@InsightIntentFunction()
export class AuditFunctions {
  @InsightIntentFunctionMethod({
    intentName: 'AuditFunction', domain: 'LocalDomain', intentVersion: '1.0.0',
    displayName: 'Audit function', parameters: {
      type: 'object', properties: { value: { type: 'string' } }, required: ['value']
    }
  })
  static echo(value: string): string { return value + ':echo'; }
}
