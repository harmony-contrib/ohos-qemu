import fs from '@ohos.file.fs';
import fileUri from '@ohos.file.fileuri';
import photoAccessHelper from '@ohos.file.photoAccessHelper';
import image from '@ohos.multimedia.image';
import { common } from '@kit.AbilityKit';
import { BusinessError } from '@ohos.base';
import { AuditStore } from '../model/AuditStore';

@Entry
@Component
struct Index {
  @State private note: string = 'Knowledge normal importer';
  @State private busy: boolean = false;

  private async execute(): Promise<void> {
    if (this.busy) { return; }
    this.busy = true;
    let store: AuditStore | undefined;
    try {
      store = new AuditStore(getContext(this) as common.UIAbilityContext);
      if (store.request.action !== 'import' && store.request.action !== 'remove-private') {
        throw new Error('Unexpected importer action');
      }
      store.access();
      if (store.request.action === 'remove-private') {
        for (const item of store.request.items) {
          const path = store.context.filesDir + '/' + item.file_name;
          if (!fs.accessSync(path)) { throw new Error('Owned private source missing before cleanup'); }
          fs.unlinkSync(path);
          store.append('private_removed', 'fs.unlinkSync', JSON.stringify({ case_id: item.case_id,
            file_name: item.file_name, exists_after: fs.accessSync(path) }));
        }
      } else {
        const helper = photoAccessHelper.getPhotoAccessHelper(store.context);
        try {
          const sourceUris: string[] = [];
          const configs: photoAccessHelper.PhotoCreationConfig[] = [];
          for (const item of store.request.items) {
            const path = store.context.filesDir + '/' + item.file_name;
            const size = fs.statSync(path).size;
            if (size < 100 || size > 4194304) { throw new Error('Invalid bounded private JPEG'); }
            const source = image.createImageSource(path);
            try {
              const original = await source.getImageProperty(image.PropertyKey.DATE_TIME_ORIGINAL);
              const digitized = await source.getImageProperty(image.PropertyKey.DATE_TIME_DIGITIZED);
              store.append('source', 'ImageSource.getImageProperty', JSON.stringify({ case_id: item.case_id,
                file_name: item.file_name, bytes: size, date_time_original: original, date_time_digitized: digitized }));
            } finally { await source.release(); }
            sourceUris.push(fileUri.getUriFromPath(path));
            configs.push({ title: item.title, fileNameExtension: 'jpg', photoType: photoAccessHelper.PhotoType.IMAGE });
          }
          store.append('consent_request', 'PhotoAccessHelper.showAssetsCreationDialog', JSON.stringify({ source_uris: sourceUris, configs: configs }));
          const uris = await helper.showAssetsCreationDialog(sourceUris, configs);
          store.append('consent_result', 'PhotoAccessHelper.showAssetsCreationDialog', JSON.stringify({ uris: uris }));
          if (uris.length !== store.request.items.length || new Set(uris).size !== uris.length) {
            throw new Error('Actual user did not create every unique test image');
          }
          for (let index: number = 0; index < uris.length; ++index) {
            const item = store.request.items[index];
            if (!/^file:\/\/media\/Photo\/[1-9][0-9]*\//.test(uris[index])) { throw new Error('Invalid actual media URI'); }
            const source = fs.openSync(store.context.filesDir + '/' + item.file_name, fs.OpenMode.READ_ONLY | fs.OpenMode.NOFOLLOW);
            try {
              const size = fs.statSync(source.fd).size;
              const destination = fs.openSync(uris[index], fs.OpenMode.WRITE_ONLY);
              let done: number = 0;
              try {
                while (done < size) {
                  const part = new ArrayBuffer(Math.min(size - done, 65536));
                  const read = fs.readSync(source.fd, part);
                  if (read <= 0 || read > part.byteLength) { throw new Error('Short private source read'); }
                  let written: number = 0;
                  while (written < read) {
                    const amount = fs.writeSync(destination.fd, part.slice(written, read));
                    if (amount <= 0 || amount > read - written) { throw new Error('Short media write'); }
                    written += amount;
                  }
                  done += read;
                }
              } finally { fs.closeSync(destination); }
              store.append('created', 'fs.writeSync+closeSync', JSON.stringify({ case_id: item.case_id,
                uri: uris[index], bytes: done, title: item.title }));
            } finally { fs.closeSync(source); }
          }
        } finally { await helper.release(); }
      }
      store.complete();
      this.note = 'Actual import/cleanup operation finished';
    } catch (error) {
      const actual = error as BusinessError;
      if (store !== undefined) { store.failure('importer', actual); }
      this.note = 'Failed ' + actual.code + ': ' + actual.message;
    } finally { this.busy = false; }
  }

  build() {
    Column({ space: 20 }) {
      Text(this.note).id('knowledge_status')
      Button('Run requested public import or private cleanup').id('knowledge_run').enabled(!this.busy)
        .onClick(() => { this.execute(); })
    }.width('100%').height('100%').padding(24)
  }
}
