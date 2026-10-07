import nativeProbe from 'libaudiostreamprobe.so';
import hilog from '@ohos.hilog';

@Entry
@Component
struct Index {
  @State note: string = 'Preparing real OHAudio renderer';
  private readonly runId: string = '__AUDIO_RUN_ID__';

  aboutToAppear(): void {
    const started: boolean = nativeProbe.run(this.runId);
    this.note = started ? 'Renderer lifecycle/data-path test running' : 'Probe start rejected';
    hilog.info(0xD003900, 'AudioStreamAudit', '%{public}s:%{public}s', this.runId, this.note);
  }
  build() {
    Column() {
      Text('QEMU real-time audio audit').fontSize(24)
      Text(this.note).fontSize(18)
    }.width('100%').height('100%').justifyContent(FlexAlign.Center).backgroundColor(Color.White)
  }
}
