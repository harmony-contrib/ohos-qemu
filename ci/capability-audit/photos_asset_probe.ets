// Real ordinary-app asset creation, picker consent and pixel readback.
// This does not prove unselected gallery browsing, FA cards or cloud backends.
import photoAccessHelper from '@ohos.file.photoAccessHelper';
import fs from '@ohos.file.fs';
import fileUri from '@ohos.file.fileuri';
import image from '@ohos.multimedia.image';
import { common } from '@kit.AbilityKit';
import { BusinessError } from '@kit.BasicServicesKit';

interface Observation { runId: string; sequence: number; name: string; pass: boolean; value: string; }

@Entry
@Component
struct Index {
  @State private note: string = 'Photos asset round trip';
  private readonly runId: string = '__PHOTO_ASSET_RUN__';
  private readonly path: string = '/data/storage/el2/base/files/photos-asset-__PHOTO_ASSET_RUN__-results.log';
  private sequence: number = 0;
  private started: boolean = false;
  private runningPicker: boolean = false;
  private runningSave: boolean = false;
  private savedUri: string = '';
  private context: common.UIAbilityContext = getContext(this) as common.UIAbilityContext;
  private helper: photoAccessHelper.PhotoAccessHelper = photoAccessHelper.getPhotoAccessHelper(this.context);

  private record(name: string, pass: boolean, value: string): void {
    const item: Observation = {runId: this.runId, sequence: ++this.sequence, name: name, pass: pass, value: value};
    const file = fs.openSync(this.path, fs.OpenMode.WRITE_ONLY | fs.OpenMode.CREATE | fs.OpenMode.APPEND);
    fs.writeSync(file.fd, JSON.stringify(item) + '\n');
    fs.closeSync(file);
    this.note = name + ': ' + (pass ? 'observed' : 'FAIL');
  }

  private bounded<T>(value: Promise<T>): Promise<T> {
    return new Promise<T>((resolve, reject) => {
      const timer: number = setTimeout(() => reject(new Error('Provider deadline exceeded')), 45000);
      value.then(result => { clearTimeout(timer); resolve(result); })
        .catch((error: BusinessError) => { clearTimeout(timer); reject(error); });
    });
  }

  aboutToAppear(): void {
    if (this.started) return;
    this.started = true;
    if (fs.accessSync(this.path)) throw new Error('Fresh challenge file already exists');
    this.metadata();
  }

  private async metadata(): Promise<void> {
    for (let cycle: number = 1; cycle <= 2; cycle++) {
      try {
        const name: string = await this.bounded(this.helper.getPhotoPickerComponentDefaultAlbumName());
        this.record('default-album.' + cycle.toString(), typeof name === 'string' && name.trim().length > 0, name);
      } catch (error) {
        this.record('default-album.' + cycle.toString(), false, JSON.stringify(error));
      }
      try {
        const info: photoAccessHelper.RecentPhotoInfo = await this.bounded(this.helper.getRecentPhotoInfo());
        this.record('recent-empty-or-current.' + cycle.toString(), info !== undefined &&
          typeof info.dateTaken === 'number' && Number.isFinite(info.dateTaken) && info.dateTaken >= 0 &&
          typeof info.identifier === 'string' && info.identifier.length > 0, JSON.stringify(info));
      } catch (error) {
        this.record('recent-empty-or-current.' + cycle.toString(), false, JSON.stringify(error));
      }
      try {
        const options: photoAccessHelper.RecentPhotoOptions = {};
        const info: photoAccessHelper.RecentPhotoInfo = await this.bounded(this.helper.getRecentPhotoInfo(options));
        this.record('recent-explicit-options.' + cycle.toString(), info !== undefined &&
          typeof info.dateTaken === 'number' && Number.isFinite(info.dateTaken) && info.dateTaken >= 0 &&
          typeof info.identifier === 'string' && info.identifier.length > 0, JSON.stringify(info));
        this.record('recent-options-unmodified.' + cycle.toString(), JSON.stringify(options) === '{}', JSON.stringify(options));
      } catch (error) {
        this.record('recent-explicit-options.' + cycle.toString(), false, JSON.stringify(error));
      }
    }
    try {
      const invalid = new photoAccessHelper.PhotoSelectOptions();
      invalid.MIMEType = photoAccessHelper.PhotoViewMIMETypes.IMAGE_TYPE;
      invalid.maxSelectNumber = 0.5;
      await this.bounded(new photoAccessHelper.PhotoViewPicker().select(invalid));
      this.record('picker.invalid-count', false, 'Unexpected success');
    } catch (error) {
      this.record('picker.invalid-count', (error as BusinessError).code === 401, JSON.stringify(error));
    }
    this.record('metadata.complete', true, 'Observations only; no asset/FA-card/backend closure claimed');
  }

  private async picker(): Promise<void> {
    if (this.runningPicker) return;
    this.runningPicker = true;
    this.record('picker.opened', true, 'Awaiting actual user UI action');
    try {
      const options = new photoAccessHelper.PhotoSelectOptions();
      options.MIMEType = photoAccessHelper.PhotoViewMIMETypes.IMAGE_TYPE;
      options.maxSelectNumber = 1;
      const result = await this.bounded(new photoAccessHelper.PhotoViewPicker().select(options));
      this.record('picker.user-cancel-result', Array.isArray(result.photoUris) && result.photoUris.length === 0,
        JSON.stringify(result));
    } catch (error) {
      this.record('picker.user-cancel-result', false, JSON.stringify(error));
    } finally {
      this.runningPicker = false;
    }
  }

  private async saveAsset(): Promise<void> {
    if (this.runningSave) return;
    this.runningSave = true;
    try {
      const pixels: Uint8Array = new Uint8Array(64 * 64 * 4);
      for (let index: number = 0; index < pixels.length; index += 4) {
        pixels[index] = 37;
        pixels[index + 1] = 149;
        pixels[index + 2] = 211;
        pixels[index + 3] = 255;
      }
      const map: image.PixelMap = await image.createPixelMap(pixels.buffer,
        {size: {width: 64, height: 64}, srcPixelFormat: image.PixelMapFormat.RGBA_8888,
          pixelFormat: image.PixelMapFormat.RGBA_8888});
      const packer: image.ImagePacker = image.createImagePacker();
      const jpeg: ArrayBuffer = await packer.packing(map, {format: 'image/jpeg', quality: 95});
      await packer.release();
      await map.release();
      const sourcePath: string = '/data/storage/el2/base/files/photos-source-' + this.runId + '.jpg';
      const source = fs.openSync(sourcePath, fs.OpenMode.CREATE | fs.OpenMode.READ_WRITE);
      fs.writeSync(source.fd, jpeg);
      fs.closeSync(source);
      const sourceUri: string = fileUri.getUriFromPath(sourcePath);
      const config: photoAccessHelper.PhotoCreationConfig = {title: 'qemu-' + this.runId,
        fileNameExtension: 'jpg', photoType: photoAccessHelper.PhotoType.IMAGE};
      this.record('asset.dialog-requested', jpeg.byteLength > 100, sourceUri);
      const uris: string[] = await this.bounded(this.helper.showAssetsCreationDialog([sourceUri], [config]));
      this.record('asset.dialog-result', uris.length === 1, JSON.stringify(uris));
      if (uris.length !== 1) throw new Error('Asset creation was not confirmed');
      const destination = fs.openSync(uris[0], fs.OpenMode.WRITE_ONLY);
      fs.writeSync(destination.fd, jpeg);
      fs.closeSync(destination);
      this.savedUri = uris[0];
      this.record('asset.written', true, uris[0]);
      await new Promise<void>((resolve) => { setTimeout(resolve, 2000); });
      const info = await this.bounded(this.helper.getRecentPhotoInfo({}));
      this.record('asset.recent', typeof info.dateTaken === 'number' && info.dateTaken > 0 &&
        typeof info.identifier === 'string' && info.identifier !== '0' && info.identifier !== '-1',
        JSON.stringify(info));
    } catch (error) {
      this.record('asset.failed', false, JSON.stringify({code: (error as BusinessError).code,
        message: (error as BusinessError).message}));
    } finally {
      this.runningSave = false;
    }
  }

  private async readSavedAsset(): Promise<void> {
    if (this.savedUri.length === 0 || this.runningPicker) return;
    this.runningPicker = true;
    let file: fs.File | undefined = undefined;
    let source: image.ImageSource | undefined = undefined;
    let map: image.PixelMap | undefined = undefined;
    try {
      const options = new photoAccessHelper.PhotoSelectOptions();
      options.MIMEType = photoAccessHelper.PhotoViewMIMETypes.IMAGE_TYPE;
      options.maxSelectNumber = 1;
      options.preselectedUris = [this.savedUri];
      this.record('asset.read-picker-requested', true, this.savedUri);
      const selected = await this.bounded(new photoAccessHelper.PhotoViewPicker().select(options));
      this.record('asset.selected', selected.photoUris.length === 1 && selected.photoUris[0] === this.savedUri,
        JSON.stringify(selected));
      if (selected.photoUris.length !== 1 || selected.photoUris[0] !== this.savedUri) {
        throw new Error('Picker did not return the newly created test asset');
      }
      file = fs.openSync(selected.photoUris[0], fs.OpenMode.READ_ONLY);
      source = image.createImageSource(file.fd);
      map = await source.createPixelMap({desiredPixelFormat: image.PixelMapFormat.RGBA_8888});
      const info = await map.getImageInfo();
      const data: ArrayBuffer = new ArrayBuffer(info.size.width * info.size.height * 4);
      await map.readPixelsToBuffer(data);
      const rgba = new Uint8Array(data);
      const offset: number = ((32 * info.size.width) + 32) * 4;
      this.record('asset.readback', info.size.width === 64 && info.size.height === 64 &&
        Math.abs(rgba[offset] - 37) <= 8 && Math.abs(rgba[offset + 1] - 149) <= 8 &&
        Math.abs(rgba[offset + 2] - 211) <= 8 && rgba[offset + 3] === 255,
        JSON.stringify({width: info.size.width, height: info.size.height,
          red: rgba[offset], green: rgba[offset + 1], blue: rgba[offset + 2], alpha: rgba[offset + 3]}));
    } catch (error) {
      this.record('asset.failed', false, JSON.stringify({code: (error as BusinessError).code,
        message: (error as BusinessError).message}));
    } finally {
      if (map !== undefined) await map.release();
      if (source !== undefined) await source.release();
      if (file !== undefined) fs.closeSync(file);
      this.runningPicker = false;
    }
  }

  build() {
    Column({space: 24}) {
      Text(this.note).id('photos-asset-note')
      Button('Open photo picker').id('photos-open-picker').onClick(() => { this.picker(); })
      Button('Create test photo').id('photos-save-asset').onClick(() => { this.saveAsset(); })
      Button('Read saved photo').id('photos-read-asset').onClick(() => { this.readSavedAsset(); })
    }.width('100%').height('100%').justifyContent(FlexAlign.Center)
  }
}
