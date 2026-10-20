import { AVVolumePanel } from '@ohos.multimedia.avVolumePanel';
import { AVInputCastPicker } from '@ohos.multimedia.avInputCastPicker';
import { AVCastPickerState } from '@ohos.multimedia.avCastPickerParam';
import { Journal, RUN } from '../common/Journal';
import { Driver } from '../common/Driver';

@Entry
@Component
struct Index {
  @StorageLink('apps579Volume') showVolume: boolean = false;
  @StorageLink('apps579Input') showInput: boolean = false;
  build() {
    Column({space: 24}) {
      Text('VOLUME/INPUT579 ' + RUN.substring(0, 12))
      if (this.showVolume) { AVVolumePanel().height(160).width('90%').id('apps579-volume-panel') }
      if (this.showInput) {
        AVInputCastPicker({onStateChange: (state: AVCastPickerState) =>
          Journal.record('input-picker-state', JSON.stringify(state), 0, Driver.inputId, 'show-input')})
          .height(64).width(64).id('apps579-input-picker')
      }
      Button('Caller touch').id('apps579-caller-touch').onClick(() => Journal.record('caller-touch'))
    }.width('100%').height('100%').backgroundColor('#BDCEE2')
  }
}
