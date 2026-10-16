import nativeProbe from 'libbatchmediacapture.so';
import hilog from '@ohos.hilog';

@Entry
@Component
struct Index {
  @State note: string = 'Preparing public microphone capture';
  private readonly runId: string = '__BATCH_MEDIA_CAPTURE_RUN_ID__';
  private readonly denied: boolean = __BATCH_MEDIA_CAPTURE_EXPECT_DENIED__;

  aboutToAppear(): void {
    const accepted: boolean = nativeProbe.run(this.runId, this.denied);
    this.note = accepted ? 'Capturing real PCM; host verification pending' : 'Capture probe start rejected';
    hilog.info(0xD003900, 'BatchMediaCapture', '%{public}s:%{public}s', this.runId, this.note);
  }
  build() {
    Column() {
      Text('Public AudioCapturer audit').fontSize(24)
      Text(this.note).fontSize(18)
    }.width('100%').height('100%').justifyContent(FlexAlign.Center).backgroundColor(Color.White)
  }
}
