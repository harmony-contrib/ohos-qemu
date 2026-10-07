// SPDX-License-Identifier: Apache-2.0
// Public dynamic API in a normal HAP. User decisions are made by com.usb.right.
import serial from '@ohos.busManager.serial';
import { BusinessError } from '@ohos.base';
import fs from '@ohos.file.fs';
import acl from 'libserialaclprobe.so';

interface Record {
  kind: string;
  run_id: string;
  bundle: string;
  case: string;
  passed: boolean;
  code: number;
  code_type: string;
  details: string;
}
interface AclResult { passed: boolean; }

const RESULT_PATH: string = '/data/storage/el2/base/files/serial-results.log';
const WRITE_LIMIT: number = 4096;
const WRITE_TIMEOUT: number = 3000;
const READ_DEADLINE: number = 10000;
const POLL_INTERVAL: number = 25;
const FRAME_HEADER: number = 21;
const MAX_TIMEOUT: number = 300000;
const ERROR_INVALID_PARAMETER: number = 35700002;
const ERROR_NOT_OPENED: number = 35700005;
const ERROR_PERMISSION: number = 35700007;
const SMALL_FRAME_SIZE: number = 64;
const LISTENER_QUIET_MS: number = 300;
const FRAME_MAGIC_FIRST: number = 0x53;
const FRAME_MAGIC_SECOND: number = 0x37;
const FRAME_RUN_ID_BYTES: number = 16;
const HEX_CHARACTERS_PER_BYTE: number = 2;
const HEX_BASE: number = 16;
const BYTE_MASK: number = 0xff;
const BYTE_BITS: number = 8;
const FRAME_RUN_ID_OFFSET: number = 5;
const PHASE_TWO_LISTENERS: number = 1;
const PHASE_MAX_WRITE: number = 2;
const PHASE_NO_LISTENERS: number = 3;
const PHASE_LISTENER_RESTART: number = 4;
const PHASE_CLOSED_WRITE: number = 5;

@Entry
@Component
struct Index {
  @State private note: string = 'Enumerate the dedicated QEMU USB-serial device';
  private readonly runId: string = '__SERIAL_RUN_ID__';
  private readonly bundle: string = '__SERIAL_BUNDLE__';
  private readonly target: string = '__SERIAL_PORT_NAME__';
  private ports: serial.SerialPort[] = [];
  private busy: boolean = false;
  private opened: boolean = false;
  private primary: number[] = [];
  private secondary: number[] = [];
  private primaryCallback = (data: Uint8Array): void => { this.append(this.primary, data); };
  private secondaryCallback = (data: Uint8Array): void => { this.append(this.secondary, data); };

  aboutToAppear(): void {
    const file = fs.openSync(RESULT_PATH, fs.OpenMode.WRITE_ONLY | fs.OpenMode.CREATE | fs.OpenMode.TRUNC);
    fs.closeSync(file);
    this.record('begin', true, 0, 'number', 'ordinary_hap_no_token_or_permission_grants');
  }

  private record(label: string, passed: boolean, code: number, type: string, details: string): void {
    const row: Record = { kind: 'serial_case', run_id: this.runId, bundle: this.bundle,
      case: label, passed: passed, code: code, code_type: type, details: details };
    const file = fs.openSync(RESULT_PATH, fs.OpenMode.WRITE_ONLY | fs.OpenMode.APPEND);
    fs.writeSync(file.fd, JSON.stringify(row) + '\n');
    fs.closeSync(file);
    this.note = label + ': ' + (passed ? 'PASS' : 'FAIL') + ' (' + code + ')';
  }

  private append(destination: number[], data: Uint8Array): void {
    for (let index: number = 0; index < data.length; index++) { destination.push(data[index]); }
  }

  private async enumerate(): Promise<void> {
    try {
      const found: serial.SerialPort[] = await serial.getSerialPortList();
      this.ports = found.filter((port: serial.SerialPort): boolean => port.portInfo.portName === this.target);
      this.record('enumerate', this.ports.length === 1, 0, 'number', JSON.stringify(found.map(
        (port: serial.SerialPort): serial.SerialPortInfo => port.portInfo)));
      if (this.ports.length === 1) {
        const checked: string = acl.check(this.target);
        const parsed: AclResult = JSON.parse(checked);
        this.record('raw_node_denied_before_grant', parsed.passed, 0, 'number', checked);
        try {
          await acl.unauthorizedGrant();
          this.record('ordinary_authorization_denied', false, 0, 'number', 'unauthorized service grant resolved');
        } catch (error) {
          let err: BusinessError = error;
          this.record('ordinary_authorization_denied', typeof err.code === 'number' && err.code === 202,
            err.code, typeof err.code, err.message);
        }
      }
    } catch (error) {
      let err: BusinessError = error;
      this.record('enumerate', false, err.code, typeof err.code, err.message);
    }
  }

  private async deny(): Promise<void> {
    if (this.busy || this.ports.length !== 1) { return; }
    this.busy = true;
    this.note = 'Choose Deny in the genuine system authorization dialog';
    try {
      await this.ports[0].open();
      this.record('deny_open', false, 0, 'number', 'opened without the expected denial');
      await this.ports[0].close();
    } catch (error) {
      let err: BusinessError = error;
      this.record('deny_open', typeof err.code === 'number' && err.code === ERROR_PERMISSION,
        err.code, typeof err.code, err.message);
    } finally { this.busy = false; }
  }

  private async expectWriteError(label: string, operation: () => Promise<number>, expected: number): Promise<void> {
    try {
      const result: number = await operation();
      this.record(label, false, 0, 'number', 'unexpected byte count ' + result);
    } catch (error) {
      let err: BusinessError = error;
      this.record(label, typeof err.code === 'number' && err.code === expected,
        err.code, typeof err.code, err.message);
    }
  }

  private frame(phase: number, length: number): Uint8Array {
    const bytes: Uint8Array = new Uint8Array(length);
    bytes[0] = FRAME_MAGIC_FIRST; bytes[1] = FRAME_MAGIC_SECOND; bytes[2] = phase;
    bytes[3] = length & BYTE_MASK; bytes[4] = length >>> BYTE_BITS;
    for (let index: number = 0; index < FRAME_RUN_ID_BYTES; index++) {
      const offset: number = index * HEX_CHARACTERS_PER_BYTE;
      bytes[index + FRAME_RUN_ID_OFFSET] = parseInt(this.runId.substring(offset, offset + HEX_CHARACTERS_PER_BYTE), HEX_BASE);
    }
    for (let index: number = FRAME_HEADER; index < length; index++) { bytes[index] = (index + phase) & BYTE_MASK; }
    return bytes;
  }

  private async pause(milliseconds: number): Promise<void> {
    await new Promise<void>((resolve: () => void): void => { setTimeout(resolve, milliseconds); });
  }

  private matches(actual: number[], expected: Uint8Array): boolean {
    if (actual.length !== expected.length) { return false; }
    for (let index: number = 0; index < expected.length; index++) {
      if (actual[index] !== expected[index]) { return false; }
    }
    return true;
  }

  private async exchange(port: serial.SerialPort, phase: number, size: number, both: boolean): Promise<boolean> {
    this.primary = []; this.secondary = [];
    const payload: Uint8Array = this.frame(phase, size);
    const count: number = await port.write(payload, WRITE_TIMEOUT);
    const deadline: number = Date.now() + READ_DEADLINE;
    while (Date.now() < deadline && (this.primary.length < size || (both && this.secondary.length < size))) {
      await this.pause(POLL_INTERVAL);
    }
    const passed: boolean = count === size && this.matches(this.primary, payload) &&
      (both ? this.matches(this.secondary, payload) : this.secondary.length === 0);
    this.record('exchange_' + phase, passed, 0, 'number', 'written=' + count +
      ' primary=' + this.primary.length + ' secondary=' + this.secondary.length);
    return passed;
  }

  private async dataAndBoundaries(port: serial.SerialPort): Promise<void> {
    await this.expectWriteError('write_empty', (): Promise<number> => port.write(new Uint8Array(0)), ERROR_INVALID_PARAMETER);
    await this.expectWriteError('write_oversize', (): Promise<number> => port.write(new Uint8Array(WRITE_LIMIT + 1)), ERROR_INVALID_PARAMETER);
    await this.expectWriteError('write_negative_timeout', (): Promise<number> => port.write(this.frame(PHASE_TWO_LISTENERS, SMALL_FRAME_SIZE), -1), ERROR_INVALID_PARAMETER);
    await this.expectWriteError('write_oversize_timeout', (): Promise<number> => port.write(this.frame(PHASE_TWO_LISTENERS, SMALL_FRAME_SIZE), MAX_TIMEOUT + 1), ERROR_INVALID_PARAMETER);
    port.onDataRead(this.primaryCallback); port.onDataRead(this.secondaryCallback);
    if (!await this.exchange(port, PHASE_TWO_LISTENERS, SMALL_FRAME_SIZE, true)) { throw new Error('binary two-listener echo mismatch'); }
    port.offDataRead(this.secondaryCallback);
    if (!await this.exchange(port, PHASE_MAX_WRITE, WRITE_LIMIT, false)) { throw new Error('4096-byte echo mismatch'); }
    port.offDataRead(this.primaryCallback);
    this.primary = []; this.secondary = [];
    await port.write(this.frame(PHASE_NO_LISTENERS, SMALL_FRAME_SIZE), WRITE_TIMEOUT);
    await this.pause(LISTENER_QUIET_MS);
    this.record('last_listener_removed', this.primary.length === 0 && this.secondary.length === 0,
      0, 'number', 'no callbacks after offDataRead');
    await port.flush();
    port.onDataRead(this.primaryCallback);
    if (!await this.exchange(port, PHASE_LISTENER_RESTART, SMALL_FRAME_SIZE, false)) { throw new Error('listener restart echo mismatch'); }
    port.offDataRead();
  }

  private async controls(port: serial.SerialPort): Promise<void> {
    await port.flush(); await port.drain(); await port.sendBrk();
    await port.setRts(true); const cts: boolean = await port.getCts();
    await port.setRts(false);
    await port.setDtr(true); const dsr: boolean = await port.getDsr();
    await port.setDtr(false);
    this.record('control_api', typeof cts === 'boolean' && typeof dsr === 'boolean',
      0, 'number', 'CTS=' + cts + ' DSR=' + dsr);
  }

  private async allow(): Promise<void> {
    if (this.busy || this.ports.length !== 1) { return; }
    this.busy = true;
    const port: serial.SerialPort = this.ports[0];
    this.note = 'Choose Allow in the genuine system dialog; host USB backend must be connected';
    try {
      await port.open(); this.opened = true;
      this.record('allow_open', true, 0, 'number', 'real user approval returned');
      const checked: string = acl.check(this.target);
      const parsed: AclResult = JSON.parse(checked);
      this.record('raw_node_denied_after_grant', parsed.passed, 0, 'number', checked);
      await this.dataAndBoundaries(port);
      await this.controls(port);
      await port.close(); this.opened = false;
      this.record('close', true, 0, 'number', 'closed real port');
      await this.expectWriteError('write_closed', (): Promise<number> => port.write(this.frame(PHASE_CLOSED_WRITE, SMALL_FRAME_SIZE)), ERROR_NOT_OPENED);
      this.record('completed', true, 0, 'number', 'public API positive path and boundaries finished');
    } catch (error) {
      let err: BusinessError = error;
      this.record('allow_or_data_failed', false, err.code, typeof err.code, err.message);
    } finally {
      if (this.opened) {
        try { await port.close(); this.opened = false; } catch (error) { this.note = 'close failed'; }
      }
      this.busy = false;
    }
  }

  build() {
    Column({ space: 12 }) {
      Text('OHOS 7 BusManager Serial audit').fontSize(20)
      Text(this.note).fontSize(14)
      Button('1. Enumerate + raw-node denial').id('serial-enumerate').onClick(() => { this.enumerate(); })
      Button('2. Open, choose Deny').id('serial-deny').onClick(() => { this.deny(); })
      Button('3. Open, choose Allow + real echo').id('serial-allow').onClick(() => { this.allow(); })
    }.width('100%').height('100%').justifyContent(FlexAlign.Center).backgroundColor(Color.White)
  }
}
