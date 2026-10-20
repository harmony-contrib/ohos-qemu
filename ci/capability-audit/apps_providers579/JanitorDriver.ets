import common from '@ohos.app.ability.common';
import window from '@ohos.window';
import photo from '@ohos.file.photoAccessHelper';
import predicates from '@ohos.data.dataSharePredicates';
import abilityAccessCtrl from '@ohos.abilityAccessCtrl';
import { Journal, CASE, RUN } from './Journal';

// Test cleanup consumer only. It is never a provider implementation, never
// edits DB rows/dates/grants, and receives only raw-journal-owned fresh URIs.
export class Driver {
  static stage?: window.WindowStage;
  static async execute(action: string, context: common.UIAbilityContext): Promise<void> {
    const id = Journal.requestId;
    if (action === 'identity') { await Journal.identity();
    } else if (action === 'permissions') {
      Journal.record('permission-result', JSON.stringify(await abilityAccessCtrl.createAtManager().requestPermissionsFromUser(context,
        ['ohos.permission.READ_IMAGEVIDEO', 'ohos.permission.WRITE_IMAGEVIDEO'])));
    } else if (action === 'cleanup-owned') {
      const uri = Journal.payload.uri as string;
      if (!uri.startsWith('file://media/Photo/')) { throw new Error('actual owned Photo URI required'); }
      const helper = photo.getPhotoAccessHelper(context);
      try {
        const rows = await helper.getAssets({predicates: new predicates.DataSharePredicates().equalTo(photo.PhotoKeys.URI, uri),
          fetchColumns: [photo.PhotoKeys.TITLE]});
        try {
          const count = rows.getCount();
          Journal.record('cleanup-active-before', JSON.stringify({uri, count}));
          if (count === 1) {
            const asset = await rows.getFirstObject();
            const title = asset.get(photo.PhotoKeys.TITLE) as string;
            if (asset.uri !== uri || (CASE === 'photos' && title !== 'apps579-' + RUN)) { throw new Error('refuse unrelated fresh asset'); }
            Journal.record('cleanup-owned-asset', JSON.stringify({uri: asset.uri, title}));
            await photo.MediaAssetChangeRequest.deleteAssets(context, [asset]);
            Journal.record('cleanup-trash-request', JSON.stringify(uri));
          } else if (count !== 0) { throw new Error('ambiguous owned asset'); }
        } finally { rows.close(); }
        const albums = await helper.getAlbums(photo.AlbumType.SYSTEM, photo.AlbumSubtype.TRASH);
        try {
          if (albums.getCount() !== 1) { throw new Error('unique actual TRASH album required'); }
          const album = await albums.getFirstObject();
          const before = await album.getAssets({predicates: new predicates.DataSharePredicates().equalTo(photo.PhotoKeys.URI, uri), fetchColumns: []});
          try {
            const count = before.getCount();
            Journal.record('cleanup-trash-before', JSON.stringify({uri, count}));
            if (count === 1) {
              const request = new photo.MediaAlbumChangeRequest(album);
              request.deleteAssetsWithUri([uri]); await helper.applyChanges(request);
              Journal.record('cleanup-permanent-delete', JSON.stringify(uri));
            } else if (count !== 0) { throw new Error('ambiguous owned TRASH asset'); }
          } finally { before.close(); }
          const trash = await album.getAssets({predicates: new predicates.DataSharePredicates().equalTo(photo.PhotoKeys.URI, uri), fetchColumns: []});
          try { Journal.record('cleanup-trash-after', JSON.stringify({uri, count: trash.getCount()})); }
          finally { trash.close(); }
        } finally { albums.close(); }
        const after = await helper.getAssets({predicates: new predicates.DataSharePredicates().equalTo(photo.PhotoKeys.URI, uri), fetchColumns: []});
        try { Journal.record('cleanup-active-after', JSON.stringify({uri, count: after.getCount()})); }
        finally { after.close(); }
      } finally { helper.release(); }
    } else { throw new Error('unknown fixed janitor action'); }
    Journal.record('done', 'null', 0, id, action);
  }
}
