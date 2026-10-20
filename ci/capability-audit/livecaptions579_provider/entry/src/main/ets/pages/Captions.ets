import { CaptionActions } from '../common/CaptionActions';

@Entry
@Component
struct Captions {
  @State private showNotices: boolean = false;
  @LocalStorageLink('notices') notices: string = '';
  @LocalStorageLink('session') session: string = '';
  @LocalStorageLink('text') text: string = '';
  @LocalStorageLink('status') status: string = '正在准备本地字幕';
  @LocalStorageLink('fontScale') fontScale: number = 100;
  @LocalStorageLink('fontColor') fontColor: number | string = '#FFFFFFFF';
  @LocalStorageLink('backgroundColor') backgroundColor: number | string = '#EE000000';

  build() {
    Column({ space: 8 }) {
      Row() {
        Text('实时字幕（英语）').fontSize(16).fontColor(this.fontColor).layoutWeight(1)
        Button('许可').id('live-captions-notices').onClick((): void => { this.showNotices = !this.showNotices; })
        Button('关闭').id('live-captions-close')
          .onClick((): void => { CaptionActions.close(this.session); })
      }.width('100%')
      Text(this.status).id('live-captions-status').fontSize(12).fontColor(this.fontColor)
      Scroll() {
        Text(this.showNotices ? this.notices : (this.text.length > 0 ? this.text : '尚未识别到英语语音')).id('live-captions-text')
          .fontSize(20 * Math.max(1, Math.min(this.fontScale, 200)) / 100)
          .fontColor(this.fontColor).width('100%')
      }.layoutWeight(1).width('100%')
    }.padding(12).width('100%').height('100%').backgroundColor(this.backgroundColor).borderRadius(12)
  }
}
