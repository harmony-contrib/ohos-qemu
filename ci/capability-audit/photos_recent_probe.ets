// Actual public calls. Empty metadata is not a positive asset or cloud proof.
import photoAccessHelper from '@ohos.file.photoAccessHelper';
import fs from '@ohos.file.fs';
import { common } from '@kit.AbilityKit';
import { BusinessError } from '@kit.BasicServicesKit';

interface Observation { runId: string; sequence: number; name: string; pass: boolean; value: string; }

@Entry
@Component
struct Index {
  @State private note: string = 'Photos recent metadata';
  private readonly path: string = '/data/storage/el2/base/files/photos-recent-__PHOTO_RUN__-results.log';
  private sequence: number = 0;
  private started: boolean = false;
  private context: common.UIAbilityContext = getContext(this) as common.UIAbilityContext;
  private helper: photoAccessHelper.PhotoAccessHelper = photoAccessHelper.getPhotoAccessHelper(this.context);

  private record(name: string, pass: boolean, value: string): void {
    const item: Observation = {runId: '__PHOTO_RUN__', sequence: ++this.sequence, name: name, pass: pass, value: value};
    const file = fs.openSync(this.path, fs.OpenMode.WRITE_ONLY | fs.OpenMode.CREATE | fs.OpenMode.APPEND);
    fs.writeSync(file.fd, JSON.stringify(item) + '\n');
    fs.closeSync(file);
    this.note = name;
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
    if (fs.accessSync(this.path)) throw new Error('Fresh result path already exists');
    this.metadata();
  }

  private async metadata(): Promise<void> {
    const options: photoAccessHelper.RecentPhotoOptions = {};
    for (let cycle: number = 1; cycle <= 2; cycle++) {
      try {
        const name: string = await this.bounded(this.helper.getPhotoPickerComponentDefaultAlbumName());
        this.record('default-album.' + cycle.toString(), typeof name === 'string' && name.trim().length > 0, name);
      } catch (error) {
        this.record('default-album.' + cycle.toString(), false, JSON.stringify(error));
      }
      for (let mode: number = 0; mode < 2; mode++) {
        try {
          const info: photoAccessHelper.RecentPhotoInfo = await this.bounded(mode === 0 ?
            this.helper.getRecentPhotoInfo() : this.helper.getRecentPhotoInfo(options));
          this.record('recent.' + cycle.toString() + '.' + mode.toString(), info !== undefined &&
            typeof info.dateTaken === 'number' && Number.isFinite(info.dateTaken) && info.dateTaken >= 0 &&
            typeof info.identifier === 'string' && info.identifier.length > 0, JSON.stringify(info));
        } catch (error) {
          this.record('recent.' + cycle.toString() + '.' + mode.toString(), false, JSON.stringify(error));
        }
      }
      this.record('options-unmodified.' + cycle.toString(), JSON.stringify(options) === '{}', JSON.stringify(options));
      try {
        const invalid = new photoAccessHelper.PhotoSelectOptions();
        invalid.maxSelectNumber = 0.5;
        await this.bounded(new photoAccessHelper.PhotoViewPicker().select(invalid));
        this.record('picker.invalid-count.' + cycle.toString(), false, 'Unexpected success');
      } catch (error) {
        this.record('picker.invalid-count.' + cycle.toString(), (error as BusinessError).code === 401, JSON.stringify(error));
      }
    }
    this.record('summary', true, 'metadata-defaults-reused-options-and-parameter-rejection-only');
  }

  build() {
    Column() { Text(this.note) }.width('100%').height('100%').justifyContent(FlexAlign.Center)
  }
}
