/* Separate legitimate system mutation test role; READ + WRITE only, empty ACL.
 * Never mutate dates, user IDs, DB rows, calendars, grants or arbitrary paths.
 * Keep this singleton process alive between prepare/hide/unhide: an original
 * public PhotoAsset object is retained; no private hidden-query permission.
 */
import photoAccessHelper from '@ohos.file.photoAccessHelper';
import predicates from '@ohos.data.dataSharePredicates';
import { common } from '@kit.AbilityKit';
import { BusinessError } from '@ohos.base';
import { AuditStore } from '../model/AuditStore';

@Entry
@Component
struct Index {
  @State private note: string = 'Knowledge system asset curator';
  @State private busy: boolean = false;
  private held: photoAccessHelper.PhotoAsset[] = [];

  private async execute(): Promise<void> {
    if (this.busy) { return; }
    this.busy = true;
    let store: AuditStore | undefined;
    try {
      store = new AuditStore(getContext(this) as common.UIAbilityContext);
      store.access();
      if (store.request.action === 'permission') { await store.permission(true); }
      else {
        const helper = photoAccessHelper.getPhotoAccessHelper(store.context);
        try {
          const action = store.request.action;
          if (action === 'prepare') {
            if (this.held.length !== 0) { throw new Error('Curator already prepared'); }
            for (const item of store.request.items) {
              const rows = await helper.getAssets({ predicates: new predicates.DataSharePredicates()
                .equalTo(photoAccessHelper.PhotoKeys.URI, item.uri), fetchColumns: [photoAccessHelper.PhotoKeys.TITLE] });
              try {
                if (rows.getCount() !== 1) { throw new Error('Owned public asset missing'); }
                const asset = await rows.getFirstObject();
                if (asset.uri !== item.uri || asset.get(photoAccessHelper.PhotoKeys.TITLE) !== item.title) {
                  throw new Error('Refusing mutation of unrelated asset');
                }
                this.held.push(asset);
                store.append('held', 'PhotoAccessHelper.getAssets', JSON.stringify({ case_id: item.case_id,
                  uri: asset.uri, title: asset.get(photoAccessHelper.PhotoKeys.TITLE) }));
              } finally { rows.close(); }
            }
          } else {
            if (!['hide', 'unhide', 'trash', 'recover', 'delete', 'cleanup'].includes(action)) {
              throw new Error('Unexpected curator action');
            }
            const uris: string[] = [];
            for (const item of store.request.items) {
              const matches = this.held.filter((asset: photoAccessHelper.PhotoAsset) => asset.uri === item.uri);
              if (matches.length !== 1) { throw new Error('No retained owned asset; process restart is a failure'); }
              uris.push(item.uri);
              if (action === 'hide' || action === 'unhide') {
                const request = new photoAccessHelper.MediaAssetChangeRequest(matches[0]);
                request.setHidden(action === 'hide');
                await helper.applyChanges(request);
                store.append('mutation', 'MediaAssetChangeRequest.setHidden+PhotoAccessHelper.applyChanges',
                  JSON.stringify({ case_id: item.case_id, uri: item.uri, hidden: action === 'hide' }));
              }
            }
            if (action === 'trash' || action === 'cleanup') {
              await photoAccessHelper.MediaAssetChangeRequest.deleteAssets(store.context, uris);
              store.append('mutation', 'MediaAssetChangeRequest.deleteAssets', JSON.stringify({ uris: uris }));
            }
            if (action === 'recover' || action === 'delete' || action === 'cleanup') {
              const albums = await helper.getAlbums(photoAccessHelper.AlbumType.SYSTEM, photoAccessHelper.AlbumSubtype.TRASH);
              try {
                if (albums.getCount() !== 1) { throw new Error('No unique actual trash album'); }
                const album = await albums.getFirstObject();
                const request = new photoAccessHelper.MediaAlbumChangeRequest(album);
                if (action === 'recover') { request.recoverAssetsWithUri(uris); }
                else { request.deleteAssetsWithUri(uris); }
                await helper.applyChanges(request);
                store.append('mutation', action === 'recover' ?
                  'MediaAlbumChangeRequest.recoverAssetsWithUri+PhotoAccessHelper.applyChanges' :
                  'MediaAlbumChangeRequest.deleteAssetsWithUri+PhotoAccessHelper.applyChanges', JSON.stringify({ uris: uris }));
              } finally { albums.close(); }
            }
          }
        } finally { await helper.release(); }
      }
      store.complete();
      this.note = 'Actual owned asset operation finished';
    } catch (error) {
      const actual = error as BusinessError;
      this.note = (store === undefined ? 'Request initialization failed;' : 'Operation failed;') +
        ' application filesDir=' + (getContext(this) as common.UIAbilityContext).getApplicationContext().filesDir +
        '; code=' + String(actual.code) + '; message=' + (actual.message ?? String(error));
      if (store !== undefined) { store.failure('curator', actual); }
    } finally { this.busy = false; }
  }

  build() {
    Column({ space: 20 }) {
      Text(this.note).id('knowledge_status')
      Button('Run requested owned asset operation').id('knowledge_run').enabled(!this.busy)
        .onClick(() => { this.execute(); })
    }.width('100%').height('100%').padding(24)
  }
}
