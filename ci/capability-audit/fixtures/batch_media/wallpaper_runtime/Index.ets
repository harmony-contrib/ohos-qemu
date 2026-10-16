/* Test caller only. No permissions, grants, database writes or generated pixels. */
import fs from '@ohos.file.fs';
import fileUri from '@ohos.file.fileuri';
import photoAccessHelper from '@ohos.file.photoAccessHelper';
import image from '@ohos.multimedia.image';
import wallpaper from '@ohos.wallpaper';
import { common } from '@kit.AbilityKit';
import { BusinessError } from '@ohos.base';
import util from '@ohos.util';

interface SeedRecord {
  runId: string;
  sequence: number;
  name: string;
  detail: string;
  timestampMs: number;
}

@Entry
@Component
struct Index {
  @State private busy: boolean = false;
  @State private note: string = 'Wallpaper challenge __WALLPAPER_RUN__';
  private readonly run: string = '__WALLPAPER_RUN__';
  private readonly cases: string[] = ['desktop-1', 'desktop-2', 'lock-1', 'lock-2', 'cancel'];
  private sequence: number = 0;

  aboutToAppear(): void {
    const path = (getContext(this) as common.UIAbilityContext).filesDir + '/wallpaper-' + this.run + '.jsonl';
    if (!fs.accessSync(path)) { return; }
    const text = fs.readTextSync(path);
    if (text.length > 65536) { this.busy = true; this.note = 'Oversized existing evidence'; return; }
    const lines = text.trim().split('\n');
    for (let index: number = 0; index < lines.length; ++index) {
      const row = JSON.parse(lines[index]) as SeedRecord;
      if (row.runId !== this.run || row.sequence !== index + 1) {
        this.busy = true; this.note = 'Stale existing evidence'; return;
      }
    }
    this.sequence = lines.length;
  }

  private append(name: string, detail: string): void {
    const path = (getContext(this) as common.UIAbilityContext).filesDir + '/wallpaper-' + this.run + '.jsonl';
    const file = fs.openSync(path, fs.OpenMode.CREATE | fs.OpenMode.WRITE_ONLY | fs.OpenMode.APPEND);
    try {
      const line = JSON.stringify({ runId: this.run, sequence: ++this.sequence, name: name,
        detail: detail, timestampMs: Date.now() }) + '\n';
      const encoded = new util.TextEncoder().encodeInto(line);
      if (fs.writeSync(file.fd, encoded.buffer) !== encoded.byteLength) { throw new Error('Short evidence write'); }
    } finally { fs.closeSync(file); }
  }

  private read(name: string): ArrayBuffer {
    const file = fs.openSync((getContext(this) as common.UIAbilityContext).filesDir + '/' + name + '.png', fs.OpenMode.READ_ONLY);
    try {
      const size = fs.statSync(file.fd).size;
      if (size < 100 || size > 33554432) { throw new Error('Invalid private PNG size'); }
      const data = new ArrayBuffer(size);
      let done: number = 0;
      while (done < size) {
        const part = new ArrayBuffer(size - done);
        const amount = fs.readSync(file.fd, part);
        if (amount <= 0 || amount > part.byteLength) { throw new Error('Short private PNG'); }
        new Uint8Array(data).set(new Uint8Array(part, 0, amount), done);
        done += amount;
      }
      const head = new Uint8Array(data);
      if (head[0] !== 137 || head[1] !== 80 || head[2] !== 78 || head[3] !== 71) { throw new Error('Expected external PNG'); }
      return data;
    } finally { fs.closeSync(file); }
  }

  private async seed(name: string): Promise<void> {
    if (this.busy) { return; }
    this.busy = true;
    try {
      const data = this.read(name);
      const context = getContext(this) as common.UIAbilityContext;
      const sourceUri = fileUri.getUriFromPath(context.filesDir + '/' + name + '.png');
      const config: photoAccessHelper.PhotoCreationConfig = { title: 'wallpaper-' + this.run + '-' + name,
        fileNameExtension: 'png', photoType: photoAccessHelper.PhotoType.IMAGE };
      this.append('import.request', JSON.stringify({ case: name, sourceUri: sourceUri, bytes: data.byteLength }));
      const uris = await photoAccessHelper.getPhotoAccessHelper(context).showAssetsCreationDialog([sourceUri], [config]);
      if (uris.length !== 1 || !uris[0].startsWith('file://media/Photo/')) { throw new Error('No actual created Photo URI'); }
      const destination = fs.openSync(uris[0], fs.OpenMode.WRITE_ONLY);
      try {
        let done: number = 0;
        while (done < data.byteLength) {
          const part = data.slice(done);
          const amount = fs.writeSync(destination.fd, part);
          if (amount <= 0 || amount > part.byteLength) { throw new Error('Short media write'); }
          done += amount;
        }
      } finally { fs.closeSync(destination); }
      this.append('import.complete', JSON.stringify({ case: name, uri: uris[0], bytes: data.byteLength }));
      this.note = 'Created ' + name;
    } catch (error) {
      const actual = error as BusinessError;
      this.append('failure', JSON.stringify({ case: name, code: actual.code, message: actual.message }));
      this.note = 'Failed ' + actual.code + ': ' + actual.message;
    } finally { this.busy = false; }
  }

  private async denied(): Promise<void> {
    if (this.busy) { return; }
    this.busy = true;
    let source: image.ImageSource | undefined;
    let pixels: image.PixelMap | undefined;
    try {
      source = image.createImageSource(this.read('cancel'));
      pixels = await source.createPixelMap();
      for (let kind: number = 0; kind < 2; ++kind) {
        for (let operation: number = 0; operation < 4; ++operation) {
          const label = ['setWallpaper', 'reset', 'setImage', 'restore'][operation];
          this.append('denied.request', JSON.stringify({ type: kind, operation: label }));
          try {
            if (operation === 0) { await wallpaper.setWallpaper(pixels, kind); }
            else if (operation === 1) { await wallpaper.reset(kind); }
            else if (operation === 2) { await wallpaper.setImage(pixels, kind); }
            else { await wallpaper.restore(kind); }
            this.append('denied.unexpected-success', JSON.stringify({ type: kind, operation: label }));
          } catch (error) {
            const actual = error as BusinessError;
            this.append('denied.error', JSON.stringify({ type: kind, operation: label,
              code: actual.code, message: actual.message }));
          }
        }
      }
    } catch (error) {
      const actual = error as BusinessError;
      this.append('failure', JSON.stringify({ code: actual.code, message: actual.message }));
    } finally {
      try { if (pixels !== undefined) { await pixels.release(); } }
      catch (error) {
        const actual = error as BusinessError;
        this.append('failure', JSON.stringify({ code: actual.code, message: actual.message }));
      }
      try { if (source !== undefined) { await source.release(); } }
      catch (error) {
        const actual = error as BusinessError;
        this.append('failure', JSON.stringify({ code: actual.code, message: actual.message }));
      }
      this.busy = false;
    }
  }

  build() {
    Column({ space: 12 }) {
      Text(this.note).id('wallpaper_challenge_status')
      ForEach(this.cases, (name: string) => {
        Button('Import ' + name).id('wallpaper_import_' + name).enabled(!this.busy).onClick(() => { this.seed(name); })
      })
      Button('Try denied wallpaper writes').id('wallpaper_denied').enabled(!this.busy).onClick(() => { this.denied(); })
    }.padding(24).width('100%').height('100%')
  }
}
