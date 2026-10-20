// SPDX-License-Identifier: Apache-2.0
// Ordinary USB host caller. Only the genuine USB dialog can grant access.
import usbManager from '@ohos.usbManager';
import { BusinessError } from '@ohos.base';
import fs from '@ohos.file.fs';

interface UsbRecord {
  kind: string;
  run_id: string;
  bundle: string;
  actor: string;
  case: string;
  passed: boolean;
  code: number;
  code_type: string;
  details: string;
}
interface UsbQuery {
  devices: usbManager.USBDevice[];
  matching_count: number;
}
interface UsbRight {
  name: string;
  result: boolean;
  has_right: boolean;
}
interface UsbDescriptorData {
  name: string;
  pipe: usbManager.USBDevicePipe;
  control_count: number;
  control_bytes: number[];
  raw_bytes: number[];
  language_count: number;
  language_bytes: number[];
  serial_count: number;
  serial_bytes: number[];
}

const PATH: string = '/data/storage/el2/base/files/usb-manager-results.log';
const VENDOR: number = 0x0403;
const PRODUCT: number = 0x6001;
const NO_RIGHT: number = 14400001;
const TIMEOUT_MS: number = 3000;

@Entry
@Component
struct Index {
  @State private note: string = 'Use the next control only after the host step';
  private readonly runId: string = '__SERIAL_RUN_ID__';
  private readonly bundle: string = '__SERIAL_BUNDLE__';
  private readonly actor: string = '__USB_ACTOR__';
  private phase: number = 0;
  private busy: boolean = false;
  private livePipe: usbManager.USBDevicePipe | undefined = undefined;

  aboutToAppear(): void {
    const file = fs.openSync(PATH, fs.OpenMode.WRITE_ONLY | fs.OpenMode.CREATE | fs.OpenMode.TRUNC);
    fs.closeSync(file);
    this.record('begin', true, 0, 'ordinary_hap_no_permissions_or_token_grants');
  }

  private record(label: string, passed: boolean, code: number, details: string): void {
    const row: UsbRecord = { kind: 'usb_manager_case', run_id: this.runId, bundle: this.bundle,
      actor: this.actor, case: label, passed: passed, code: code, code_type: typeof code, details: details };
    const file = fs.openSync(PATH, fs.OpenMode.WRITE_ONLY | fs.OpenMode.APPEND);
    fs.writeSync(file.fd, JSON.stringify(row) + '\n');
    fs.closeSync(file);
    this.note = label + ': ' + (passed ? 'PASS' : 'FAIL');
    if (!passed) { throw new Error('actual USB case failed: ' + label); }
  }

  private bytes(data: Uint8Array, count: number): number[] {
    const result: number[] = [];
    for (let index: number = 0; index < count && index < data.length; index++) { result.push(data[index]); }
    return result;
  }

  private query(label: string, present: boolean): usbManager.USBDevice | undefined {
    const devices: usbManager.USBDevice[] = usbManager.getDevices();
    const matching: usbManager.USBDevice[] = devices.filter((device: usbManager.USBDevice): boolean =>
      device.vendorId === VENDOR && device.productId === PRODUCT);
    const detail: UsbQuery = { devices: devices, matching_count: matching.length };
    this.record(label, matching.length === (present ? 1 : 0), 0, JSON.stringify(detail));
    return present ? matching[0] : undefined;
  }

  private target(label: string): usbManager.USBDevice {
    const result: usbManager.USBDevice | undefined = this.query(label, true);
    if (result === undefined) { throw new Error('target device missing'); }
    return result;
  }

  private denied(label: string, device: usbManager.USBDevice): void {
    const right: boolean = usbManager.hasRight(device.name);
    if (right) { this.record(label, false, 0, 'hasRight unexpectedly true'); return; }
    let observed: number = 0;
    let message: string = '';
    try {
      const pipe: usbManager.USBDevicePipe = usbManager.connectDevice(device);
      if (pipe !== undefined) { usbManager.closePipe(pipe); }
    } catch (error) {
      let err: BusinessError = error;
      observed = err.code;
      message = err.message;
    }
    const detail: UsbRight = { name: device.name, result: false, has_right: right };
    this.record(label, typeof observed === 'number' && observed === NO_RIGHT, observed,
      JSON.stringify(detail) + '\n' + message);
  }

  private async right(label: string, device: usbManager.USBDevice, expected: boolean): Promise<void> {
    const result: boolean = await usbManager.requestRight(device.name);
    const observed: boolean = usbManager.hasRight(device.name);
    const detail: UsbRight = { name: device.name, result: result, has_right: observed };
    this.record(label, result === expected && observed === expected, 0, JSON.stringify(detail));
  }

  private async getDescriptor(pipe: usbManager.USBDevicePipe, value: number, language: number,
    data: Uint8Array): Promise<number> {
    const request: usbManager.USBDeviceRequestParams = { bmRequestType: 0x80, bRequest: 6,
      wValue: value, wIndex: language, wLength: data.length, data: data };
    return await usbManager.usbControlTransfer(pipe, request, TIMEOUT_MS);
  }

  private async descriptors(label: string, device: usbManager.USBDevice, keepOpen: boolean): Promise<void> {
    const pipe: usbManager.USBDevicePipe = usbManager.connectDevice(device);
    if (pipe === undefined) { this.record(label, false, 0, 'connectDevice returned undefined'); return; }
    this.livePipe = pipe;
    const control: Uint8Array = new Uint8Array(18);
    const count: number = await this.getDescriptor(pipe, 0x0100, 0, control);
    const raw: Uint8Array = usbManager.getRawDescriptor(pipe);
    const languages: Uint8Array = new Uint8Array(255);
    const languageCount: number = await this.getDescriptor(pipe, 0x0300, 0, languages);
    const language: number = languageCount >= 4 ? languages[2] | (languages[3] << 8) : 0;
    const serial: Uint8Array = new Uint8Array(255);
    const serialCount: number = count === 18 && control[16] > 0 && language > 0 ?
      await this.getDescriptor(pipe, 0x0300 | control[16], language, serial) : -1;
    const detail: UsbDescriptorData = { name: device.name, pipe: pipe, control_count: count,
      control_bytes: this.bytes(control, count), raw_bytes: raw === undefined ? [] : this.bytes(raw, raw.length),
      language_count: languageCount, language_bytes: this.bytes(languages, languageCount),
      serial_count: serialCount, serial_bytes: this.bytes(serial, serialCount) };
    this.record(label, count === 18 && control[0] === 18 && control[1] === 1 &&
      (control[8] | (control[9] << 8)) === VENDOR && (control[10] | (control[11] << 8)) === PRODUCT &&
      raw !== undefined && raw.length >= 18 && languageCount >= 4 && serialCount >= 2,
      0, JSON.stringify(detail));
    if (!keepOpen) { this.close(label + '_close'); }
  }

  private close(label: string, expected: number = 0): void {
    if (this.livePipe === undefined) { this.record(label, false, 0, 'no owned open pipe'); return; }
    const result: number = usbManager.closePipe(this.livePipe);
    this.livePipe = undefined;
    this.record(label, result === expected, result, 'closePipe');
  }

  private revoke(label: string, device: usbManager.USBDevice): void {
    const result: boolean = usbManager.removeRight(device.name);
    const detail: UsbRight = { name: device.name, result: result,
      has_right: usbManager.hasRight(device.name) };
    this.record(label, result && !detail.has_right, 0, JSON.stringify(detail));
  }

  private async ownerStep(): Promise<void> {
    let device: usbManager.USBDevice;
    switch (this.phase) {
      case 0:
        this.query('query_absent_initial', false);
        break;
      case 1:
        device = this.target('query_original'); this.denied('connect_denied_original', device);
        break;
      case 2:
        device = this.target('query_before_deny'); await this.right('right_denied', device, false);
        this.denied('connect_denied_after_user_denial', device);
        break;
      case 3:
        device = this.target('query_before_allow'); await this.right('right_granted', device, true);
        await this.descriptors('descriptors_original', device, false);
        break;
      case 4:
        device = this.target('query_after_other_bundle');
        this.record('right_retained_after_other_bundle', usbManager.hasRight(device.name), 0, device.name);
        this.revoke('right_removed', device); this.denied('connect_denied_after_revoke', device);
        break;
      case 5:
        device = this.target('query_before_live_pipe'); await this.right('right_granted_live', device, true);
        await this.descriptors('descriptors_live', device, true);
        break;
      case 6:
        this.query('query_detached', false);
        if (this.livePipe === undefined) { throw new Error('owned live pipe missing'); }
        const stale: number = await this.getDescriptor(this.livePipe, 0x0100, 0, new Uint8Array(18));
        this.record('stale_control_transfer', stale === -1, stale, 'usbControlTransfer after actual detach');
        // DelDevice has removed this device and its temporary right. A second
        // public close must report the documented invalid/service value 22.
        this.close('stale_pipe_close_rejected', 22);
        break;
      case 7:
        device = this.target('query_replug'); this.denied('connect_denied_replug', device);
        break;
      case 8:
        device = this.target('query_before_replug_deny'); await this.right('right_denied_replug', device, false);
        this.denied('connect_denied_replug_after_denial', device);
        break;
      case 9:
        device = this.target('query_before_replug_allow'); await this.right('right_granted_replug', device, true);
        await this.descriptors('descriptors_replug', device, false); this.revoke('right_removed_final', device);
        break;
      case 10:
        this.query('query_absent_final', false);
        this.record('completed', true, 0, 'USB_host_query_descriptor_right_and_attachment_cases_finished');
        break;
      default:
        throw new Error('no further USB owner steps');
    }
  }

  private peerStep(): void {
    if (this.phase !== 0) { throw new Error('peer scenario has exactly one operation'); }
    const device: usbManager.USBDevice = this.target('query_peer_while_owner_granted');
    this.denied('connect_denied_other_bundle', device);
    this.record('completed', true, 0, 'independent_ordinary_bundle_did_not_inherit_owner_right');
  }

  private async next(): Promise<void> {
    if (this.busy) { return; }
    this.busy = true;
    try {
      if (this.actor === 'owner') { await this.ownerStep(); }
      else if (this.actor === 'peer') { this.peerStep(); }
      else { throw new Error('invalid actor'); }
      this.phase++;
    } catch (error) {
      let err: BusinessError = error;
      const row: UsbRecord = { kind: 'usb_manager_case', run_id: this.runId, bundle: this.bundle,
        actor: this.actor, case: 'phase_failed', passed: false,
        code: typeof err.code === 'number' ? err.code : -2, code_type: 'number', details: err.message };
      const file = fs.openSync(PATH, fs.OpenMode.WRITE_ONLY | fs.OpenMode.APPEND);
      fs.writeSync(file.fd, JSON.stringify(row) + '\n'); fs.closeSync(file);
      this.note = 'USB step failed; retain raw evidence';
    } finally { this.busy = false; }
  }

  build() {
    Column({ space: 12 }) {
      Text('USBManager ordinary host audit').fontSize(20)
      Text(this.note).fontSize(14)
      Button('Next host-controlled USB step').id('usb-manager-next').onClick(() => { this.next(); })
    }.width('100%').height('100%').justifyContent(FlexAlign.Center).backgroundColor(Color.White)
  }
}
