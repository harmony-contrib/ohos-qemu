import contact from '@ohos.contact';
import audio from '@ohos.multimedia.audio';
import photoAccessHelper from '@ohos.file.photoAccessHelper';
import fs from '@ohos.file.fs';
import modeProbe from 'libcontactsyncmodeprobe.so';
import { ConnectOptions, ConnectOptionsCollections } from '@ohos.arkui.StateManagement';

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
  records: ContactRecordObservation[];
  stateRecords: StateRecordObservation;
}

interface StateRecordObservation { flags: boolean[]; values: string[]; }
class RecordValue { value: string = ''; }

function stateRecords(runId: string): StateRecordObservation {
  const first = new ConnectOptions<RecordValue>();
  const second = new ConnectOptions<RecordValue>();
  const collection = new ConnectOptionsCollections<Array<RecordValue>, RecordValue>();
  const other = new ConnectOptionsCollections<Array<RecordValue>, RecordValue>();
  const flags: boolean[] = [first instanceof ConnectOptions, second instanceof ConnectOptions,
    first !== second, collection instanceof ConnectOptionsCollections, collection instanceof ConnectOptions,
    other instanceof ConnectOptionsCollections, other instanceof ConnectOptions, collection !== other,
    first.type === undefined && first.key === undefined && first.defaultCreator === undefined && first.areaMode === undefined,
    collection.type === undefined && collection.key === undefined && collection.defaultCreator === undefined &&
      collection.defaultSubCreator === undefined && collection.areaMode === undefined];
  first.type = RecordValue;
  second.type = RecordValue;
  first.key = runId + '-first'; second.key = runId + '-second';
  first.defaultCreator = (): RecordValue => { const value = new RecordValue(); value.value = first.key!; return value; };
  second.defaultCreator = (): RecordValue => { const value = new RecordValue(); value.value = second.key!; return value; };
  first.key += '-changed';
  collection.key = runId + '-collection'; other.key = runId + '-other';
  collection.defaultSubCreator = (): RecordValue => { const value = new RecordValue(); value.value = collection.key!; return value; };
  collection.defaultCreator = (): Array<RecordValue> => [collection.defaultSubCreator!()];
  flags.push(first.type === RecordValue && second.type === RecordValue);
  flags.push(other.defaultSubCreator === undefined && other.defaultCreator === undefined);
  return { flags: flags, values: [first.defaultCreator().value, second.defaultCreator().value,
    collection.defaultCreator()[0].value, other.key] };
}

interface ContactRecordObservation { name: string; first: string; second: string; flags: boolean[]; }

function contactRecords(runId: string): ContactRecordObservation[] {
  const a0 = new contact.ContactAttributes(); const b0 = new contact.ContactAttributes();
  a0.attributes = [contact.Attribute.ATTR_EMAIL]; b0.attributes = [contact.Attribute.ATTR_NAME];
  a0.attributes.push(contact.Attribute.ATTR_PHONE);
  const a1 = new contact.Group(); const b1 = new contact.Group();
  a1.title = runId + '-Group'; b1.title = runId + '-second-Group'; a1.title += '-changed';
  const a2 = new contact.Holder(); const b2 = new contact.Holder();
  a2.holderId = 17; b2.holderId = 29;
  const a3 = new contact.Name(); const b3 = new contact.Name();
  a3.fullName = runId + '-Name'; b3.fullName = runId + '-second-Name'; a3.fullName += '-changed';
  const a4 = new contact.NickName(); const b4 = new contact.NickName();
  a4.nickName = runId + '-NickName'; b4.nickName = runId + '-second-NickName'; a4.nickName += '-changed';
  const a5 = new contact.Note(); const b5 = new contact.Note();
  a5.noteContent = runId + '-Note'; b5.noteContent = runId + '-second-Note'; a5.noteContent += '-changed';
  const a6 = new contact.Organization(); const b6 = new contact.Organization();
  a6.name = runId + '-Organization'; b6.name = runId + '-second-Organization'; a6.name += '-changed';
  const a7 = new contact.Portrait(); const b7 = new contact.Portrait();
  a7.uri = runId + '-Portrait'; b7.uri = runId + '-second-Portrait'; a7.uri += '-changed';
  const a8 = new contact.Website(); const b8 = new contact.Website();
  a8.website = runId + '-Website'; b8.website = runId + '-second-Website'; a8.website += '-changed';
  return [
    { name: 'ContactAttributes', first: JSON.stringify(a0.attributes), second: JSON.stringify(b0.attributes),
      flags: [a0 instanceof contact.ContactAttributes, b0 instanceof contact.ContactAttributes, a0 !== b0] },
    { name: 'Group', first: a1.title, second: b1.title,
      flags: [a1 instanceof contact.Group, b1 instanceof contact.Group, a1 !== b1] },
    { name: 'Holder', first: a2.bundleName + ':' + a2.holderId, second: b2.bundleName + ':' + b2.holderId,
      flags: [a2 instanceof contact.Holder, b2 instanceof contact.Holder, a2 !== b2] },
    { name: 'Name', first: a3.fullName, second: b3.fullName,
      flags: [a3 instanceof contact.Name, b3 instanceof contact.Name, a3 !== b3] },
    { name: 'NickName', first: a4.nickName, second: b4.nickName,
      flags: [a4 instanceof contact.NickName, b4 instanceof contact.NickName, a4 !== b4] },
    { name: 'Note', first: a5.noteContent, second: b5.noteContent,
      flags: [a5 instanceof contact.Note, b5 instanceof contact.Note, a5 !== b5] },
    { name: 'Organization', first: a6.name, second: b6.name,
      flags: [a6 instanceof contact.Organization, b6 instanceof contact.Organization, a6 !== b6] },
    { name: 'Portrait', first: a7.uri, second: b7.uri,
      flags: [a7 instanceof contact.Portrait, b7 instanceof contact.Portrait, a7 !== b7] },
    { name: 'Website', first: a8.website, second: b8.website,
      flags: [a8 instanceof contact.Website, b8 instanceof contact.Website, a8 !== b8] }
  ];
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
      photoNative: modeProbe.inspectPhoto(),
      records: contactRecords(this.runId),
      stateRecords: stateRecords(this.runId)
    };
    const file = fs.openSync('/data/storage/el2/base/files/contact-sync-mode-__RUN__-results.log',
      fs.OpenMode.WRITE_ONLY | fs.OpenMode.CREATE | fs.OpenMode.TRUNC);
    fs.writeSync(file.fd, JSON.stringify(observed) + '\n');
    fs.closeSync(file);
    this.note = 'Actual Contact, Audio and Photo enum observation completed';
  }
  build() { Column() { Text(this.note) }.width('100%').height('100%') }
}
