import { InsightIntentPage } from '@ohos.app.ability.InsightIntentDecorator';
import { AuditFunctions } from '../intents/AuditFunctions';
import { AuditLink } from '../intents/AuditLink';
import { AuditEntity } from '../intents/AuditEntity';
import fs from '@ohos.file.fs';

interface PageParam { value?: string; }

@InsightIntentPage({
  intentName: 'AuditPage', domain: 'LocalDomain', intentVersion: '1.0.0',
  displayName: 'Audit page', uiAbility: 'EntryAbility', pagePath: './ets/pages/Index.ets'
})
@Entry
@Component
struct Index {
  @State result: string = '__INTENT_RUN__';
  @StorageLink('auditIntentUri') uri: string = '';
  private update(parameter: PageParam, event: string): void {
    const entity = new AuditEntity();
    entity.value = 'actual';
    const value: string = parameter?.value || '';
    this.result = '__INTENT_RUN__:' + value + ':' + AuditFunctions.echo(entity.value) + ':' + new AuditLink().tag;
    const file = fs.openSync('/data/storage/el2/base/files/insight-page-__INTENT_RUN__-results.log',
      fs.OpenMode.CREATE | fs.OpenMode.WRITE_ONLY | fs.OpenMode.APPEND);
    try { fs.writeSync(file.fd, JSON.stringify({ runId: '__INTENT_RUN__', event, value,
      routerParameters: JSON.stringify(parameter || {}), result: this.result }) + '\n'); }
    finally { fs.closeSync(file); }
  }
  aboutToAppear(): void { this.update(this.getUIContext().getRouter().getParams() as PageParam, 'appear'); }
  onNewParam(parameter: PageParam): void { this.update(parameter, 'newParam'); }
  build() {
    Column() {
      Text(this.result).id('insight-decorator-ready')
      Text('__INTENT_RUN__:' + this.uri).id('insight-decorator-uri')
    }.width('100%').height('100%')
  }
}
