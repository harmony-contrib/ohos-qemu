import { RecentPhotoComponent, RecentPhotoOptions, PhotoSource, RecentPhotoInfo } from '@ohos.file.RecentPhotoComponent';
import { BaseItemInfo } from '@ohos.file.PhotoPickerComponent';
import photo from '@ohos.file.photoAccessHelper';
import { Journal, RUN } from '../common/Journal';
import { Driver } from '../common/Driver';

@Entry
@Component
struct Index {
  @StorageLink('apps579Recent') showRecent: boolean = false;
  private options: RecentPhotoOptions = new RecentPhotoOptions();
  aboutToAppear(): void {
    this.options.MIMEType = photo.PhotoViewMIMETypes.IMAGE_TYPE;
    this.options.period = 1000;
    this.options.photoSource = PhotoSource.ALL;
  }
  build() {
    Column({space: 16}) {
      Text('PHOTOS579 ' + RUN.substring(0, 12))
      if (this.showRecent) {
        RecentPhotoComponent({recentPhotoOptions: this.options,
          onRecentPhotoCheckResult: (exists: boolean) =>
            Journal.record('recent-component-exists', JSON.stringify(exists), 0, Driver.recentId, 'recent-component'),
          onRecentPhotoCheckInfo: (exists: boolean, info: RecentPhotoInfo) =>
            Journal.record('recent-component-info', JSON.stringify({exists, info}), 0, Driver.recentId, 'recent-component'),
          onRecentPhotoClick: (info: BaseItemInfo): boolean => {
            Journal.record('recent-component-click', JSON.stringify(info), 0, Driver.recentId, 'recent-component');
            return true;
          }}).width('100%').height(320).id('apps579-recent')
      }
      Button('Caller touch').id('apps579-caller-touch').onClick(() => Journal.record('caller-touch'))
    }.width('100%').height('100%').backgroundColor('#C8DBEE')
  }
}
