import { InsightIntentPage } from '@ohos.app.ability.InsightIntentDecorator';
import { AuditFunctions } from '../intents/AuditFunctions';
import { AuditLink } from '../intents/AuditLink';
import { AuditEntity } from '../intents/AuditEntity';

@InsightIntentPage({
  intentName: 'AuditPage', domain: 'LocalDomain', intentVersion: '1.0.0',
  displayName: 'Audit page', uiAbility: 'EntryAbility', pagePath: './ets/pages/Index.ets'
})
@Entry
@Component
struct Index {
  @State result: string = '__INTENT_RUN__';
  aboutToAppear(): void {
    const entity = new AuditEntity();
    entity.value = 'actual';
    this.result += ':' + AuditFunctions.echo(entity.value) + ':' + new AuditLink().tag;
  }
  build() { Column() { Text(this.result).id('insight-decorator-ready') }.width('100%').height('100%') }
}
