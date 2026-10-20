import { Journal, RUN } from '../common/Journal';

@Entry
@Component
struct Child {
  build() {
    Column() {
      Row() {
        Blank().layoutWeight(1).backgroundColor('#FF0044')
        Blank().layoutWeight(1).backgroundColor('#00DD66')
      }.height('40%')
      Text('SESSION578 ' + RUN.substring(0, 8)).fontSize(22).fontColor('#FFFFFF')
      Button('Child touch').id('services578-child-touch').onClick(() => Journal.record('child-touch'))
    }.width('100%').height('100%').backgroundColor('#26324A')
  }
}
