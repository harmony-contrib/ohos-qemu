import photoAccessHelper from '@ohos.file.photoAccessHelper';
import predicates from '@ohos.data.dataSharePredicates';
import { common } from '@kit.AbilityKit';
import { BusinessError } from '@ohos.base';
import { AuditStore, Item } from '../model/AuditStore';

@Entry
@Component
struct Index {
  @State private note: string = 'Knowledge system query';
  @State private busy: boolean = false;

  private async related(store: AuditStore, item: Item): Promise<void> {
    const context: photoAccessHelper.ContextMap = { topicField: [photoAccessHelper.FieldType.DAY] };
    const options: photoAccessHelper.Options = { suggestionFields: [photoAccessHelper.FieldType.HOLIDAY], recommendationCount: 64 };
    const result = await photoAccessHelper.KnowledgeContent.getRelatedEntity(item.day, context, options);
    store.append('related', 'KnowledgeContent.getRelatedEntity', JSON.stringify({ case_id: item.case_id,
      topic: item.day, context: context, options: options, entities: result }));
  }

  private async accessOnly(store: AuditStore): Promise<void> {
    try {
      const result = await photoAccessHelper.KnowledgeContent.getRelatedEntity(store.request.items[0].day,
        { topicField: [photoAccessHelper.FieldType.DAY] }, { suggestionFields: [photoAccessHelper.FieldType.HOLIDAY] });
      store.append('access_resolved', 'KnowledgeContent.getRelatedEntity', JSON.stringify(result));
    } catch (error) {
      const actual = error as BusinessError;
      store.append('access_error', 'KnowledgeContent.getRelatedEntity', '{}', actual.code, actual.message);
    }
  }

  private async bounds(store: AuditStore): Promise<void> {
    const day = store.request.items[0].day;
    const zero = await photoAccessHelper.KnowledgeContent.getRelatedEntity(day,
      { topicField: [photoAccessHelper.FieldType.DAY] },
      { suggestionFields: [photoAccessHelper.FieldType.HOLIDAY], recommendationCount: 0 });
    store.append('zero_count', 'KnowledgeContent.getRelatedEntity', JSON.stringify(zero));
    for (const kind of ['negative-count', 'none-field', 'empty-search']) {
      try {
        if (kind === 'negative-count') {
          const value = await photoAccessHelper.KnowledgeContent.getRelatedEntity(day,
            { topicField: [photoAccessHelper.FieldType.DAY] }, { recommendationCount: -1 });
          store.append('boundary_resolved', kind, JSON.stringify(value));
        } else if (kind === 'none-field') {
          const value = await photoAccessHelper.KnowledgeContent.getRelatedEntity(day,
            { topicField: [photoAccessHelper.FieldType.NONE] });
          store.append('boundary_resolved', kind, JSON.stringify(value));
        } else {
          const value = await photoAccessHelper.KnowledgeContent.getSearchSuggestion([]);
          store.append('boundary_resolved', kind, JSON.stringify(value));
        }
      } catch (error) {
        const actual = error as BusinessError;
        store.append('boundary_error', kind, '{}', actual.code, actual.message);
      }
    }
  }

  private async query(store: AuditStore): Promise<void> {
    const helper = photoAccessHelper.getPhotoAccessHelper(store.context);
    try {
      for (const item of store.request.items) {
        const filter = new predicates.DataSharePredicates();
        if (store.request.action === 'baseline') { filter.equalTo(photoAccessHelper.PhotoKeys.DATE_DAY, item.day); }
        else { filter.equalTo(photoAccessHelper.PhotoKeys.URI, item.uri); }
        const result = await helper.getAssets({ predicates: filter, fetchColumns: [photoAccessHelper.PhotoKeys.DATE_DAY,
          photoAccessHelper.PhotoKeys.DATE_TAKEN, photoAccessHelper.PhotoKeys.TITLE] });
        try {
          const count = result.getCount();
          if (store.request.action === 'baseline') {
            store.append('baseline_assets', 'PhotoAccessHelper.getAssets', JSON.stringify({ case_id: item.case_id, count: count }));
          } else {
            let uri: string = '';
            let day: string = '';
            let taken: photoAccessHelper.MemberType = 0;
            let title: string = '';
            if (count === 1) {
              const asset = await result.getFirstObject();
              uri = asset.uri;
              day = String(asset.get(photoAccessHelper.PhotoKeys.DATE_DAY));
              taken = asset.get(photoAccessHelper.PhotoKeys.DATE_TAKEN);
              title = String(asset.get(photoAccessHelper.PhotoKeys.TITLE));
            }
            store.append('asset', 'PhotoAccessHelper.getAssets', JSON.stringify({ case_id: item.case_id,
              requested_uri: item.uri, count: count, uri: uri, date_day: day, date_taken: taken, title: title }));
          }
        } finally { result.close(); }
        await this.related(store, item);
      }
      const types: photoAccessHelper.SearchSuggestionType[] = [photoAccessHelper.SearchSuggestionType.TIME_PEOPLE];
      const suggestions = await photoAccessHelper.KnowledgeContent.getSearchSuggestion(types);
      store.append('search', 'KnowledgeContent.getSearchSuggestion', JSON.stringify({ types: types, results: suggestions }));
      // Empty results prove this real call only, not a populated people-analysis producer.
      if (store.request.phase === 'present') { await this.bounds(store); }
      if (store.request.phase === 'deleted' || store.request.phase === 'cleanup') {
        const albums = await helper.getAlbums(photoAccessHelper.AlbumType.SYSTEM, photoAccessHelper.AlbumSubtype.TRASH);
        try {
          const albumCount = albums.getCount();
          store.append('trash_album', 'PhotoAccessHelper.getAlbums', JSON.stringify({ count: albumCount }));
          if (albumCount > 1) { throw new Error('Ambiguous system trash album'); }
          if (albumCount === 1) {
            const album = await albums.getFirstObject();
            for (const item of store.request.items) {
              const rows = await album.getAssets({ predicates: new predicates.DataSharePredicates()
                .equalTo(photoAccessHelper.PhotoKeys.URI, item.uri), fetchColumns: [] });
              try {
                store.append('trash_asset', 'Album.getAssets', JSON.stringify({ case_id: item.case_id,
                  uri: item.uri, count: rows.getCount() }));
              } finally { rows.close(); }
            }
          }
        } finally { albums.close(); }
      }
    } finally { await helper.release(); }
  }

  private async execute(): Promise<void> {
    if (this.busy) { return; }
    this.busy = true;
    let store: AuditStore | undefined;
    try {
      store = new AuditStore(getContext(this) as common.UIAbilityContext);
      store.access();
      if (store.request.action === 'permission') { await store.permission(); }
      else if (store.request.action === 'access') { await this.accessOnly(store); }
      else if (store.request.action === 'query' || store.request.action === 'baseline') { await this.query(store); }
      else { throw new Error('Unexpected query action'); }
      store.complete();
      this.note = 'Actual Knowledge query operation finished';
    } catch (error) {
      const actual = error as BusinessError;
      if (store !== undefined) { store.failure('query', actual); }
      this.note = 'Failed ' + actual.code + ': ' + actual.message;
    } finally { this.busy = false; }
  }

  build() {
    Column({ space: 20 }) {
      Text(this.note).id('knowledge_status')
      Button('Run actual requested Knowledge query').id('knowledge_run').enabled(!this.busy)
        .onClick(() => { this.execute(); })
    }.width('100%').height('100%').padding(24)
  }
}
