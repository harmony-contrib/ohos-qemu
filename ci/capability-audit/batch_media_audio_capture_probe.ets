import nativeProbe from 'libbatchmediacapture.so';
import hilog from '@ohos.hilog';
import abilityAccessCtrl from '@ohos.abilityAccessCtrl';
import common from '@ohos.app.ability.common';
import fs from '@ohos.file.fs';

@Entry
@Component
struct Index {
  @State note: string = 'Preparing public microphone capture';
  private readonly runId: string = '__BATCH_MEDIA_CAPTURE_RUN_ID__';
  private readonly denied: boolean = __BATCH_MEDIA_CAPTURE_EXPECT_DENIED__;

  async aboutToAppear(): Promise<void> {
    try {
      const context = getContext(this) as common.UIAbilityContext;
      const access = abilityAccessCtrl.createAtManager();
      // The actual user/permission controller answers this dialog. expectedDenied
      // does not choose the answer or bypass the public permission request.
      const authorization = await access.requestPermissionsFromUser(context, ['ohos.permission.MICROPHONE']);
      const permissionEvidence = JSON.stringify({
        run_id: this.runId,
        expected_denied: this.denied,
        permissions: authorization.permissions,
        auth_results: authorization.authResults,
        dialog_shown_results: authorization.dialogShownResults
      });
      const evidencePath = context.getApplicationContext().filesDir + '/audio-capture-' + this.runId + '-permission.json';
      if (fs.accessSync(evidencePath)) {
        throw new Error('Existing microphone authorization evidence is preserved');
      }
      const evidenceFile = fs.openSync(evidencePath, fs.OpenMode.CREATE | fs.OpenMode.WRONLY);
      try {
        fs.writeSync(evidenceFile.fd, permissionEvidence);
      } finally {
        fs.closeSync(evidenceFile);
      }
      hilog.info(0xD003900, 'BatchMediaCapture', '%{public}s', permissionEvidence);
      // Exercise native capture even when the actual dialog answer disagrees with
      // the requested persona. Native results and independent token checks decide.
      const accepted: boolean = nativeProbe.run(this.runId, this.denied);
      this.note = accepted ? 'Capturing real PCM; host verification pending' : 'Capture probe start rejected';
      hilog.info(0xD003900, 'BatchMediaCapture', '%{public}s:%{public}s', this.runId, this.note);
    } catch (error) {
      this.note = 'Microphone permission request or evidence persistence failed';
      hilog.error(0xD003900, 'BatchMediaCapture', '%{public}s:%{public}s', this.runId, JSON.stringify(error));
    }
  }

  build() {
    Column() {
      Text('Public AudioCapturer audit').fontSize(24)
      Text(this.note).fontSize(18)
    }.width('100%').height('100%').justifyContent(FlexAlign.Center).backgroundColor(Color.White)
  }
}
