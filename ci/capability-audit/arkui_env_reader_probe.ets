// Real inherited environment and ContainerReader two-way native measurements.
import { WithEnv } from '@ohos.arkui.WithEnv';
import { ContainerReader, ContainerReaderAttribute } from '@ohos.arkui.components.ContainerReader';
import fs from '@ohos.file.fs';
import process from '@ohos.process';

const MESSAGE_KEY: CustomEnvKey<string> = CustomEnvKey.create<string>();
interface Measurement { width: number; height: number; }
interface Observation { runId: string; family: string; cycle: number; phase: number; name: string; values: number[]; data: string; }
class Journal {
  static family: string = 'none';
  static cycle: number = 0;
  static phase: number = 0;
  static record(name: string, values: number[] = [], data: string = ''): void {
    const row: Observation = { runId: '__RUN__', family: Journal.family, cycle: Journal.cycle, phase: Journal.phase, name, values, data };
    const file = fs.openSync('/data/storage/el2/base/files/arkui-env-reader-__RUN__-results.log',
      fs.OpenMode.CREATE | fs.OpenMode.WRITE_ONLY | fs.OpenMode.APPEND);
    try { fs.writeSync(file.fd, JSON.stringify(row) + '\n'); } finally { fs.closeSync(file); }
  }
}
class ReaderModifier implements AttributeModifier<ContainerReaderAttribute> {
  applyNormalAttribute(instance: ContainerReaderAttribute): void {
    try {
      const reset = instance.breakpointConfig(undefined) === instance;
      const chain = instance.breakpointConfig({ width: [100, 200, 300, 400], height: [0.8, 1.25] })
        .width(180).height(120) === instance;
      Journal.record('modifier.reader', [reset ? 1 : 0, chain ? 1 : 0]);
    } catch (error) { Journal.record('failed', [], String(error)); }
  }
}
@ComponentV2
struct EnvChild {
  @Param label: string = 'outside';
  @Env(WritableEnvKey.DIRECTION) envDirection: Direction;
  @Env(WritableEnvKey.FONT_SCALE) envFontScale: number;
  @CustomEnv(MESSAGE_KEY) message: string = 'unset';
  private observe(): void { Journal.record('env.' + this.label, [this.envDirection, this.envFontScale], this.message); }
  aboutToAppear(): void { this.observe(); }
  build() {
    Column() {
      Text('__RUN__:' + this.label + ':' + this.message + ':' + this.envDirection + ':' + this.envFontScale)
        .id('env-reader-' + this.label + '-marker').fontSize(12)
      Row() {
        Text('A').id('env-reader-' + this.label + '-a').width(60).height(40).fontSize(20).backgroundColor('#ff0000')
        Text('B').id('env-reader-' + this.label + '-b').width(60).height(40).fontSize(20).backgroundColor('#00ff00')
      }.width(240)
      Button('Observe ' + this.label).id('env-reader-' + this.label + '-observe').onClick(() => { this.observe(); })
    }.width(360)
  }
}
@Entry
@ComponentV2
struct Index {
  @Local scene: string = 'none';
  @Local displayState: string = 'idle __RUN__';
  @Local selectedDirection: Direction = Direction.Ltr;
  @Local selectedFontScale: number = 1;
  @Local fontOverride: boolean = true;
  @Local message: string = 'outer-0';
  @Local measured: Measurement = { width: 0, height: 0 };
  @Local widthBp: WidthBreakpoint = WidthBreakpoint.WIDTH_XS;
  @Local heightBp: HeightBreakpoint = HeightBreakpoint.HEIGHT_SM;
  @Local readerWidth: number = 180;
  @Local readerHeight: number = 120;
  private readonly modifier: ReaderModifier = new ReaderModifier();
  private envCycle: number = 0;
  private readerCycle: number = 0;
  @Monitor('measured', 'widthBp', 'heightBp')
  readerChanged(): void {
    Journal.record('reader.native', [this.measured.width, this.measured.height, this.widthBp, this.heightBp]);
  }
  build() {
    Column({ space: 8 }) {
      Text('__RUN__').id('env-reader-ready')
      Text(this.displayState).id('env-reader-state')
      Row({ space: 8 }) {
        Button('Environment').id('env-reader-env').onClick(() => {
          if (this.scene !== 'none' || this.envCycle >= 2) { Journal.record('failed', [], 'only two separate environment cycles allowed'); return; }
          Journal.family = 'env';
          Journal.cycle = this.envCycle++;
          this.selectedDirection = Direction.Ltr; this.selectedFontScale = 1; this.fontOverride = true; this.message = 'outer-0';
          Journal.phase = 0; Journal.record('identity', [process.uid, process.euid, process.pid]);
          Journal.record('density', [this.getUIContext().vp2px(1)]);
          this.scene = 'env'; this.displayState = 'active env __RUN__:' + Journal.cycle;
        })
        Button('Reader').id('env-reader-reader').onClick(() => {
          if (this.scene !== 'none' || this.readerCycle >= 2) { Journal.record('failed', [], 'only two separate reader cycles allowed'); return; }
          Journal.family = 'reader';
          Journal.cycle = this.readerCycle++;
          this.readerWidth = 180; this.readerHeight = 120;
          Journal.phase = 2; Journal.record('identity', [process.uid, process.euid, process.pid]);
          Journal.record('density', [this.getUIContext().vp2px(1)]);
          this.scene = 'reader'; this.displayState = 'active reader __RUN__:' + Journal.cycle;
        })
      }
      if (this.scene === 'env') {
        WithEnv() {
          Column() {
            EnvChild({ label: 'outer' })
            WithEnv() { EnvChild({ label: 'inner' }) }
              .env(WritableEnvKey.DIRECTION, Direction.Rtl).env(WritableEnvKey.FONT_SCALE, 1)
              .customEnv(MESSAGE_KEY, 'inner-fixed')
          }
        }.env(WritableEnvKey.DIRECTION, this.selectedDirection)
          .env(WritableEnvKey.FONT_SCALE, this.fontOverride ? this.selectedFontScale : undefined)
          .customEnv(MESSAGE_KEY, this.message)
        EnvChild({ label: 'outside' })
        Button('Update environment').id('env-reader-update').onClick(() => {
          Journal.phase = 1;
          this.selectedDirection = Direction.Rtl; this.selectedFontScale = 1.5; this.message = 'outer-1';
          Journal.record('env.update.request', [1]);
        })
        Button('Remove font override').id('env-reader-font-reset').onClick(() => {
          Journal.phase = 5; this.fontOverride = false; Journal.record('env.font.reset.request', [1]);
        })
      } else if (this.scene === 'reader') {
        ContainerReader({ size: this.measured!!, widthBreakpoint: this.widthBp!!, heightBreakpoint: this.heightBp!! }) {
          Text('__RUN__:reader:' + this.measured.width + ':' + this.measured.height + ':' + this.widthBp + ':' + this.heightBp)
            .id('env-reader-native-marker').fontSize(12).backgroundColor('#ddeeff')
        }.attributeModifier(this.modifier).width(this.readerWidth).height(this.readerHeight).id('env-reader-factory')
        Button('Resize reader').id('env-reader-resize').onClick(() => {
          Journal.phase = 3;
          this.readerWidth = 280; this.readerHeight = 300; Journal.record('reader.resize.request', [1]);
        })
        Button('Restore reader').id('env-reader-restore').onClick(() => {
          Journal.phase = 4;
          this.readerWidth = 180; this.readerHeight = 120; Journal.record('reader.restore.request', [1]);
        })
        Row({ space: 8 }) {
          Button('Width 199').id('env-reader-below').onClick(() => {
            Journal.phase = 6; this.readerWidth = 199; this.readerHeight = 120; Journal.record('reader.below.request', [1]);
          })
          Button('Width 200').id('env-reader-at').onClick(() => {
            Journal.phase = 7; this.readerWidth = 200; this.readerHeight = 120; Journal.record('reader.at.request', [1]);
          })
        }
        Row({ space: 8 }) {
          Button('Ratio below 0.8').id('env-reader-ratio-sm-below').onClick(() => {
            Journal.phase = 8; this.readerWidth = 200; this.readerHeight = 159; Journal.record('reader.ratio-sm-below.request', [1]);
          })
          Button('Ratio at 0.8').id('env-reader-ratio-sm-at').onClick(() => {
            Journal.phase = 9; this.readerWidth = 200; this.readerHeight = 160; Journal.record('reader.ratio-sm-at.request', [1]);
          })
          Button('Ratio below 1.25').id('env-reader-ratio-lg-below').onClick(() => {
            Journal.phase = 10; this.readerWidth = 200; this.readerHeight = 249; Journal.record('reader.ratio-lg-below.request', [1]);
          })
          Button('Ratio at 1.25').id('env-reader-ratio-lg-at').onClick(() => {
            Journal.phase = 11; this.readerWidth = 200; this.readerHeight = 250; Journal.record('reader.ratio-lg-at.request', [1]);
          })
        }
        Row({ space: 8 }) {
          Button('Width 99').id('env-reader-xs-below').onClick(() => {
            Journal.phase = 12; this.readerWidth = 99; this.readerHeight = 120; Journal.record('reader.xs-below.request', [1]);
          })
          Button('Width 100').id('env-reader-xs-at').onClick(() => {
            Journal.phase = 13; this.readerWidth = 100; this.readerHeight = 80; Journal.record('reader.xs-at.request', [1]);
          })
          Button('Width 300').id('env-reader-lg-at').onClick(() => {
            Journal.phase = 14; this.readerWidth = 300; this.readerHeight = 240; Journal.record('reader.lg-at.request', [1]);
          })
          Button('Width 400').id('env-reader-xl-at').onClick(() => {
            Journal.phase = 15; this.readerWidth = 400; this.readerHeight = 250; Journal.record('reader.xl-at.request', [1]);
          })
        }
      }
      Button('Remove scene').id('env-reader-remove').onClick(() => {
        this.scene = 'none'; this.displayState = 'removed ' + Journal.family + ' __RUN__:' + Journal.cycle;
        Journal.record('remove.request', [1]);
      })
    }.width('100%').height('100%')
  }
}
