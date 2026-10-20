import { Journal, BUNDLE, RUN } from '../common/Journal';

@Entry
@Component
struct Index {
  build() {
    Column({space: 16}) {
      Text('System services 578').fontSize(30).fontColor('#FFFFFF')
      Text(BUNDLE).fontColor('#FFFFFF')
      Text(RUN).fontColor('#FFFFFF')
      Button('Touch marker').id('services578-touch').onClick(() => Journal.record('touch'))
    }.width('100%').height('100%').backgroundColor('#153B69').justifyContent(FlexAlign.Center)
  }
}
