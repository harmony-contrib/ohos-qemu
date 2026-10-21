import common from '@ohos.app.ability.common';
import window from '@ohos.window';
import fs from '@ohos.file.fs';
import fileUri from '@ohos.file.fileuri';
import image from '@ohos.multimedia.image';
import photo from '@ohos.file.photoAccessHelper';
import { BusinessError } from '@ohos.base';
import { Journal, RUN } from './Journal';
import { MediaBytes } from './MediaBytes';

export class Driver {
  static stage?: window.WindowStage;
  static uri: string = '';
  static recentId: string = 'lifecycle';
  static async execute(action: string, context: common.UIAbilityContext): Promise<void> {
    const id = Journal.requestId;
    const helper = photo.getPhotoAccessHelper(context);
    try {
    if (action === 'identity') { await Journal.identity();
    } else if (action === 'recent-info') {
      const defaults = await helper.getRecentPhotoInfo();
      const options: photo.RecentPhotoOptions = {};
      const explicit = await helper.getRecentPhotoInfo(options);
      Journal.record('recent-info', JSON.stringify({defaults, explicit, options}));
    } else if (action === 'default-album') {
      Journal.record('default-album', JSON.stringify(await helper.getPhotoPickerComponentDefaultAlbumName()));
    } else if (action === 'recent-component') {
      Driver.recentId = id;
      AppStorage.setOrCreate('apps579Recent', true);
      Journal.record('recent-component-request');
    } else if (action === 'hide-recent') {
      AppStorage.setOrCreate('apps579Recent', false);
      Journal.record('recent-component-hidden');
    } else if (action === 'create') {
      const nonce = Journal.payload.nonce as string;
      if (!/^[a-f0-9]{32}$/.test(nonce)) { throw new Error('fresh bounded restart challenge required'); }
      const title = 'photos579-' + RUN + '-' + nonce;
      Journal.record('fresh-nonce', JSON.stringify({nonce, title}));
      // Same ordinary showAssetsCreationDialog/write path used by the strict
      // photos-asset family, with fresh nonce-dependent source pixels.
      const bytes = new Uint8Array(64 * 64 * 4);
      const centerValue = parseInt(nonce.substring(20, 22), 16);
      const rgb = [32 + centerValue % 160, 32 + (centerValue * 3 + 10) % 160,
        32 + (centerValue * 7 + 10) % 160];
      for (let p: number = 0; p < bytes.length; p += 4) {
        const x = (p / 4) % 64;
        const y = Math.floor(p / 256);
        const tile = Math.floor(y / 16) * 4 + Math.floor(x / 16);
        const value = parseInt(nonce.substring(tile * 2, tile * 2 + 2), 16);
        bytes[p] = 32 + value % 160; bytes[p + 1] = 32 + (value * 3 + tile) % 160;
        bytes[p + 2] = 32 + (value * 7 + tile) % 160; bytes[p + 3] = 255;
      }
      const map = await image.createPixelMap(bytes.buffer, {size: {width: 64, height: 64},
        srcPixelFormat: image.PixelMapFormat.RGBA_8888, pixelFormat: image.PixelMapFormat.RGBA_8888});
      const packer = image.createImagePacker();
      let jpeg: ArrayBuffer;
      try { jpeg = await packer.packing(map, {format: 'image/jpeg', quality: 98}); }
      finally { await packer.release(); await map.release(); }
      const path = context.filesDir + '/photos579-source-' + nonce + '.jpg';
      const file = fs.openSync(path, fs.OpenMode.CREATE | fs.OpenMode.WRITE_ONLY | fs.OpenMode.TRUNC);
      try { fs.writeSync(file.fd, jpeg); } finally { fs.closeSync(file); }
      Journal.record('creation-dialog-request', JSON.stringify({bytes: jpeg.byteLength, center: rgb}));
      const uris = await helper.showAssetsCreationDialog([fileUri.getUriFromPath(path)],
        [{title, fileNameExtension: 'jpg', photoType: photo.PhotoType.IMAGE}]);
      Journal.record('creation-dialog-result', JSON.stringify(uris));
      if (uris.length === 1) {
        const out = fs.openSync(uris[0], fs.OpenMode.WRITE_ONLY);
        try { fs.writeSync(out.fd, jpeg); } finally { fs.closeSync(out); }
        Driver.uri = uris[0];
        const saved = fs.openSync(context.filesDir + '/apps579-uri-' + RUN + '.txt',
          fs.OpenMode.CREATE | fs.OpenMode.WRITE_ONLY | fs.OpenMode.TRUNC);
        try { fs.writeSync(saved.fd, Driver.uri); } finally { fs.closeSync(saved); }
        Journal.record('asset-created', JSON.stringify({uri: Driver.uri, center: rgb, nonce, title}));
        await MediaBytes.read(Driver.uri, false);
      }
    } else if (action === 'select' || action === 'cancel-select') {
      const options = new photo.PhotoSelectOptions();
      options.MIMEType = photo.PhotoViewMIMETypes.IMAGE_TYPE;
      options.maxSelectNumber = 1;
      // The harness selects the actual nonce thumbnail from real rendered
      // pixels. Preselection would make that physical click deselect it.
      Journal.record('select-request', JSON.stringify(options));
      const result = await new photo.PhotoViewPicker().select(options);
      Journal.record('select-result', JSON.stringify(result));
      if (result.photoUris.length === 1) {
        Journal.record('selected-fixture', JSON.stringify({uri: result.photoUris[0], created: Driver.uri}));
        await MediaBytes.read(result.photoUris[0], false);
      }
    } else if (action === 'use-owned-fixture') {
      const uri = Journal.payload.uri as string;
      if (!uri.startsWith('file://media/Photo/')) { throw new Error('actual strict-family owned asset URI required'); }
      Driver.uri = uri;
      Journal.record('owned-fixture', JSON.stringify(uri));
    } else if (action === 'reload-owned-uri') {
      Driver.uri = fs.readTextSync(context.filesDir + '/apps579-uri-' + RUN + '.txt');
      Journal.record('owned-uri', JSON.stringify(Driver.uri));
    } else if (action === 'read-denied') {
      const uri = Journal.payload.uri as string;
      if (!uri.startsWith('file://media/Photo/')) { throw new Error('exact actual owned Photo URI required'); }
      await MediaBytes.read(uri, false);
      Journal.record('ungranted-uri-read-returned');
    } else if (action === 'delete') {
      if (!Driver.uri) { throw new Error('actual owned asset missing'); }
      Journal.record('delete-request', JSON.stringify(Driver.uri));
      await photo.MediaAssetChangeRequest.deleteAssets(context, [Driver.uri]);
      Journal.record('asset-deleted', JSON.stringify(Driver.uri));
    } else if (action === 'exit') { Journal.record('exit-request'); await context.terminateSelf();
    } else { throw new Error('unknown fixed Photos action'); }
    } finally { helper.release(); }
    Journal.record('done', 'null', 0, id, action);
  }
}
