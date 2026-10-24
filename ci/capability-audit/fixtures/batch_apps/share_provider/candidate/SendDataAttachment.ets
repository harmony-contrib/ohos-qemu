/* SPDX-License-Identifier: Apache-2.0 */
import Want from '@ohos.app.ability.Want';
import fs from '@ohos.file.fs';
import uri from '@ohos.uri';
import util from '@ohos.util';
import common from '../data/commonData';
import { Mms } from './TypesUtils';

export class SharedAttachment {
  id: string = '';
  directory: string = '';
  path: string = '';
  suffix: string = '';
  type: number = 0;
  size: number = 0;
  name: string = '';
  reserved: boolean = false;
}

// Exactly one bounded imported file. No provider, permission grant or SMS API.
export class SendDataAttachment {
  private static active: SharedAttachment | undefined = undefined;
  private static readonly prefix: string = 'senddata-import-';
  private static recovered: boolean = false;
  static recover(context: Context): void {
    if (SendDataAttachment.recovered) { return; }
    // Only our private previous-process staging directories, never sender URIs,
    // draft files, existing MMS attachments, or arbitrary cache contents.
    for (const name of fs.listFileSync(context.getApplicationContext().cacheDir)) {
      if (!/^senddata-import-[a-f0-9-]{36}$/.test(name)) { continue; }
      const dir: string = context.getApplicationContext().cacheDir + '/' + name;
      const names: string[] = fs.listFileSync(dir);
      if (names.length > 1 || names.some((n: string) => !/^source\.(png|jpg|gif|bmp|mp3|wav|mp4|vcf)$/.test(n))) {
        throw new Error('Unknown shared attachment staging contents; preserve them');
      }
      for (const n of names) { fs.unlinkSync(dir + '/' + n); }
      fs.rmdirSync(dir);
    }
    SendDataAttachment.recovered = true;
  }
  private static mime(type: string): string[] | undefined {
    const types: Record<string, string[]> = {
      'image/png': ['png', '1'], 'image/jpeg': ['jpg', '1'], 'image/gif': ['gif', '1'], 'image/bmp': ['bmp', '1'],
      'audio/mpeg': ['mp3', '3'], 'audio/wav': ['wav', '3'], 'video/mp4': ['mp4', '2'], 'text/vcard': ['vcf', '4']
    };
    return types[type];
  }
  private static copy(source: string, destination: string, maximum: number): number {
    if (fs.accessSync(destination)) { throw new Error('Refuse replacement of an existing attachment'); }
    const input = fs.openSync(source, fs.OpenMode.READ_ONLY);
    let output: fs.File | undefined = undefined;
    let created: boolean = false;
    try {
      const original = fs.statSync(input.fd);
      if (!original.isFile() || original.size <= 0 || original.size > maximum) {
        throw new Error('Shared attachment must be a bounded real file');
      }
      output = fs.openSync(destination, fs.OpenMode.CREATE | fs.OpenMode.WRITE_ONLY | fs.OpenMode.NOFOLLOW);
      created = true;
      let total: number = 0;
      while (total < original.size) {
        const buffer = new ArrayBuffer(Math.min(65536, original.size - total));
        const read = fs.readSync(input.fd, buffer);
        if (read <= 0 || read > buffer.byteLength) { throw new Error('Short shared attachment read'); }
        const bytes = new Uint8Array(buffer).slice(0, read);
        let written: number = 0;
        while (written < read) {
          const count = fs.writeSync(output.fd, bytes.slice(written).buffer);
          if (count <= 0 || count > read - written) { throw new Error('Short shared attachment write'); }
          written += count;
        }
        total += read;
      }
      // Do not turn a growing/truncated/changed source into a successful draft.
      const final = fs.statSync(input.fd);
      if (final.ino !== original.ino || final.size !== original.size || final.mtime !== original.mtime ||
          fs.statSync(output.fd).size !== original.size) { throw new Error('Shared attachment changed during import'); }
      fs.fsyncSync(output.fd);
      return total;
    } catch (error) {
      if (output !== undefined) { fs.closeSync(output); output = undefined; }
      if (created) { fs.unlinkSync(destination); }
      throw error as Error;
    } finally {
      try {
        if (output !== undefined) { fs.closeSync(output); }
      } finally {
        fs.closeSync(input);
      }
    }
  }
  static stage(context: Context, want: Want): SharedAttachment | undefined {
    if (want.action !== 'ohos.want.action.sendData') { return undefined; }
    if (SendDataAttachment.active !== undefined) { throw new Error('Finish or cancel the current attachment draft first'); }
    const stream = want.parameters?.['ability.params.stream'];
    const possibleFile: boolean = (want.uri ?? '') !== '' || (Array.isArray(stream) &&
      ((want.type ?? '') !== 'text/plain' || stream.some((item: Object) => typeof item === 'string' && item.startsWith('file://'))));
    if (!possibleFile) { return undefined; }
    const format = SendDataAttachment.mime(want.type ?? '');
    if (format === undefined) { throw new Error('Unsupported shared file MIME type'); }
    if (((want.flags ?? 0) & 1) === 0) { throw new Error('Shared file requires caller URI READ authorization'); }
    let source: string = want.uri ?? '';
    if (stream !== undefined) {
      if (!Array.isArray(stream) || stream.length !== 1 || typeof stream[0] !== 'string' ||
          (source !== '' && source !== stream[0])) { throw new Error('One matching shared URI required'); }
      source = stream[0] as string;
    }
    const parsed = new uri.URI(source);
    if (parsed.scheme !== 'file' || parsed.authority === '' || parsed.path.length < 2 || parsed.userInfo !== '' ||
        parsed.fragment !== '' || source.length > 8192 || /[\u0000\r\n\s\\]/.test(source) || /%(?![0-9a-fA-F]{2})/.test(source)) {
      throw new Error('Invalid shared file URI');
    }
    SendDataAttachment.recover(context);
    const item = new SharedAttachment();
    item.id = util.generateRandomUUID(); item.directory = context.getApplicationContext().cacheDir + '/' + SendDataAttachment.prefix + item.id;
    item.suffix = format[0]; item.type = Number(format[1]);
    item.name = decodeURIComponent(parsed.path.substring(parsed.path.lastIndexOf('/') + 1));
    if (item.name.length === 0 || item.name.length > 255 || /[\u0000-\u001f/\\]/.test(item.name)) { throw new Error('Invalid attachment filename'); } item.path = item.directory + '/source.' + item.suffix;
    fs.mkdirSync(item.directory); // Fresh private directory; never reuse/overwrite.
    try {
      item.size = SendDataAttachment.copy(source, item.path, item.type === common.MM_ATTACHMENT_TYPE.AUDIO ?
        common.int.MMS_AUDIO_FILE_MAX_SIZE : common.int.MMS_FILE_MAX_SIZE);
      SendDataAttachment.active = item;
      return item;
    } catch (error) {
      fs.rmdirSync(item.directory);
      throw error as Error;
    }
  }
  static description(id: string): string {
    const item = SendDataAttachment.active;
    return item !== undefined && item.id === id ? item.name + '\n' + fs.statSync(item.path).size.toString() + ' B' : '';
  }
  static dispose(): void {
    if (SendDataAttachment.active !== undefined) { SendDataAttachment.cancel(SendDataAttachment.active.id, true); }
  }
  static reserve(id: string): void {
    if (!id) { return; }
    const item = SendDataAttachment.active;
    if (item === undefined || item.id !== id || item.reserved) { throw new Error('Attachment draft ownership changed'); }
    item.reserved = true;
  }
  static cancel(id: string, reserved: boolean = false): void {
    const item = SendDataAttachment.active;
    if (item === undefined || item.id !== id || (item.reserved && !reserved)) { return; }
    fs.unlinkSync(item.path); fs.rmdirSync(item.directory); SendDataAttachment.active = undefined;
  }
  static handoff(id: string, context: Context): Mms {
    const item = SendDataAttachment.active;
    if (item === undefined || item.id !== id || !item.reserved) { throw new Error('No reserved attachment draft'); }
    const name: string = 'SHARED_' + item.id + '.' + item.suffix;
    const destination: string = context.getApplicationContext().filesDir + '/' + name;
    let copied: boolean = false;
    try {
      const size: number = SendDataAttachment.copy(item.path, destination, common.int.MMS_FILE_MAX_SIZE);
      copied = true;
      const result: Mms = { duration: '', type: item.type, path: destination, name: name, size: size.toString() };
      SendDataAttachment.cancel(id, true);
      // Existing Conversation/DraftUtils now owns this actual copied attachment.
      // No automatic sending is performed by this helper or WantUtil.
      return result;
    } catch (error) {
      if (copied) { fs.unlinkSync(destination); }
      SendDataAttachment.cancel(id, true);
      throw error as Error;
    }
  }
}
