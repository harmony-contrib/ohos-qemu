import nativeProbe from 'libavcmediaprobe.so';
import hilog from '@ohos.hilog';

@Entry
@Component
struct Index {
  @State note: string = 'Preparing real public AVC media APIs';
  private readonly runId: string = '__AVC_RUN_ID__';
  aboutToAppear(): void {
    const started: boolean = nativeProbe.run(this.runId);
    this.note = started ? 'Real AVC encode/decode test running' : 'Probe start rejected';
    hilog.info(0xD003900, 'AvcMediaAudit', '%{public}s:%{public}s', this.runId, this.note);
  }
  build() {
    Column() {
      Text('QEMU software AVC media audit').fontSize(24)
      Text(this.note).fontSize(18)
    }.width('100%').height('100%').justifyContent(FlexAlign.Center).backgroundColor(Color.White)
  }
}
