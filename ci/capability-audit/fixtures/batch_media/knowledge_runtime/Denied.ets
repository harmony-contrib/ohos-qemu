import photoAccessHelper from '@ohos.file.photoAccessHelper';
import { common } from '@kit.AbilityKit';
import { BusinessError } from '@ohos.base';
import { AuditStore } from '../model/AuditStore';

@Entry
@Component
struct Index {
  @State private busy: boolean = false;
  @State private note: string = 'Knowledge normal identity negative';

  private async execute(): Promise<void> {
    if (this.busy) { return; }
    this.busy = true;
    let store: AuditStore | undefined;
    try {
      store = new AuditStore(getContext(this) as common.UIAbilityContext);
      if (store.request.action !== 'access') { throw new Error('Unexpected normal caller action'); }
      store.access();
      for (const method of ['getRelatedEntity', 'getSearchSuggestion']) {
        try {
          if (method === 'getRelatedEntity') {
            const result = await photoAccessHelper.KnowledgeContent.getRelatedEntity(store.request.items[0].day,
              { topicField: [photoAccessHelper.FieldType.DAY] }, { suggestionFields: [photoAccessHelper.FieldType.HOLIDAY] });
            store.append('access_resolved', 'KnowledgeContent.' + method, JSON.stringify(result));
          } else {
            const result = await photoAccessHelper.KnowledgeContent.getSearchSuggestion([photoAccessHelper.SearchSuggestionType.TIME_PEOPLE]);
            store.append('access_resolved', 'KnowledgeContent.' + method, JSON.stringify(result));
          }
        } catch (error) {
          const actual = error as BusinessError;
          store.append('access_error', 'KnowledgeContent.' + method, '{}', actual.code, actual.message);
        }
      }
      store.complete();
      this.note = 'Actual normal caller outcomes recorded';
    } catch (error) {
      const actual = error as BusinessError;
      if (store !== undefined) { store.failure('denied', actual); }
      this.note = 'Failed ' + actual.code + ': ' + actual.message;
    } finally { this.busy = false; }
  }

  build() {
    Column({ space: 20 }) {
      Text(this.note).id('knowledge_status')
      Button('Invoke real Knowledge APIs as normal app').id('knowledge_run').enabled(!this.busy)
        .onClick(() => { this.execute(); })
    }.width('100%').height('100%').padding(24)
  }
}
