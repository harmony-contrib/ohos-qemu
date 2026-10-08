// Runtime capability discovery, not a static declaration or provider-success shim.
import fs from '@ohos.file.fs';
import { BusinessError } from '@kit.BasicServicesKit';
interface Row { runId: string; syscap: string; observed: boolean | null; error: string; }
@Entry
@Component
struct Index {
  @State private note: string = 'Checking actual phone capability discovery';
  private readonly runId: string = '__PROFILE_RUN_ID__';
  private readonly path: string = '/data/storage/el2/base/files/optional-phone-profile-__PROFILE_RUN_ID__-results.log';
  private record(syscap: string, observed: boolean | null, error: string = ''): void {
    const row: Row = { runId: this.runId, syscap, observed, error };
    const file = fs.openSync(this.path, fs.OpenMode.WRITE_ONLY | fs.OpenMode.CREATE | fs.OpenMode.APPEND);
    fs.writeSync(file.fd, JSON.stringify(row) + '\n'); fs.closeSync(file);
  }
  aboutToAppear(): void {
    const file = fs.openSync(this.path, fs.OpenMode.WRITE_ONLY | fs.OpenMode.CREATE | fs.OpenMode.TRUNC);
    fs.closeSync(file);
    const capabilities: string[] = [
      'SystemCapability.SelectionInput.Selection',
      'SystemCapability.FileManagement.File.Environment.FolderObtain',
      'SystemCapability.USB.USBManager.Serial',
      'SystemCapability.Print.PrintFramework',
      'SystemCapability.ArkUI.ArkUI.Full',
      'SystemCapability.Multimedia.Camera.Core',
      'SystemCapability.QemuOwned.' + this.runId,
      ''
    ];
    for (const capability of capabilities) {
      try { this.record(capability, canIUse(capability)); }
      catch (error) { this.record(capability, null, (error as BusinessError).message || 'exception'); }
    }
    // Discovery must remain stable after repeated real queries, not cached
    // expected values emitted by the caller or compile-time condition folding.
    for (let repeat = 0; repeat < 32; repeat++) {
      for (const capability of capabilities) {
        try { this.record(capability, canIUse(capability)); }
        catch (error) { this.record(capability, null, (error as BusinessError).message || 'exception'); }
      }
    }
    this.record('summary', true);
    this.note = 'Actual capability discovery completed';
  }
  build() { Column() { Text(this.note) }.width('100%').height('100%') }
}
