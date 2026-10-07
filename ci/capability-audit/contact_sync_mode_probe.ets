import contact from '@ohos.contact';
import audio from '@ohos.multimedia.audio';
import photoAccessHelper from '@ohos.file.photoAccessHelper';
import fs from '@ohos.file.fs';
import modeProbe from 'libcontactsyncmodeprobe.so';

interface NativeModes {
  values: number[];
  statuses: number[];
  types: number[];
  own: boolean[];
  exception: boolean;
}
interface Observation {
  runId: string; values: number[]; native: NativeModes; audioValues: number[]; audioNative: NativeModes;
  photoValues: number[]; photoNative: NativeModes;
}

@Entry
@Component
struct Index {
  @State private note: string = 'Checking actual Contact, Audio and Photo enum members';
  private readonly runId: string = '__RUN__';
  aboutToAppear(): void {
    // Typed reads and native module/property reads must independently agree.
    // No provider writes, cloud-sync calls, or permission grants are involved.
    const observed: Observation = {
      runId: this.runId,
      values: [contact.ContactSyncMode.MODE_INCREMENTAL, contact.ContactSyncMode.MODE_CLOUD_BASED],
      native: modeProbe.inspect(),
      audioValues: [audio.DeviceBlockStatus.UNBLOCKED, audio.DeviceBlockStatus.BLOCKED],
      audioNative: modeProbe.inspectAudio(),
      photoValues: [photoAccessHelper.FusionAssetType.COMPATIBLE_ASSET],
      photoNative: modeProbe.inspectPhoto()
    };
    const file = fs.openSync('/data/storage/el2/base/files/contact-sync-mode-__RUN__-results.log',
      fs.OpenMode.WRITE_ONLY | fs.OpenMode.CREATE | fs.OpenMode.TRUNC);
    fs.writeSync(file.fd, JSON.stringify(observed) + '\n');
    fs.closeSync(file);
    this.note = 'Actual Contact, Audio and Photo enum observation completed';
  }
  build() { Column() { Text(this.note) }.width('100%').height('100%') }
}
