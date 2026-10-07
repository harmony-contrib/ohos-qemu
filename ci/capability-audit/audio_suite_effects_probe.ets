import nativeProbe from 'libaudiosuiteeffectsprobe.so';
import hilog from '@ohos.hilog';

@Entry
@Component
struct Index {
  @State note: string = 'Preparing real AudioSuite DSP';
  private readonly runId: string = '__AUDIO_SUITE_EFFECTS_RUN_ID__';

  aboutToAppear(): void {
    const started: boolean = nativeProbe.run(this.runId);
    this.note = started ? 'AudioSuite DSP pipeline test running' : 'Probe start rejected';
    hilog.info(0xD003900, 'AudioSuiteEffectsAudit', '%{public}s:%{public}s', this.runId, this.note);
  }
  build() {
    Column() {
      Text('QEMU AudioSuite DSP audit').fontSize(24)
      Text(this.note).fontSize(18)
    }.width('100%').height('100%').justifyContent(FlexAlign.Center).backgroundColor(Color.White)
  }
}
