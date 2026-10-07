// SPDX-License-Identifier: Apache-2.0
// Ordinary public HAP; operator hotplug and actual trusted UI are required.
import serial from '@ohos.busManager.serial';
import { BusinessError } from '@ohos.base';
import fs from '@ohos.file.fs';
import acl from 'libserialaclprobe.so';

interface AttachmentRow {
  kind: string; run_id: string; bundle: string; case: string;
  passed: boolean; code: number; code_type: string; details: string;
}
interface AclResult { passed: boolean; }

const RESULTS: string = '/data/storage/el2/base/files/serial-attachment-results.log';
const DISCONNECTED: number = 35700003;
const DENIED: number = 35700007;
const WAIT_OFFLINE_MS: number = 60000;
const POLL_MS: number = 25;
const QUIET_MS: number = 300;

@Entry
@Component
struct Index {
  @State private note: string = 'Use a fresh run and the dedicated USB-serial endpoint';
  private readonly runId: string = '__SERIAL_RUN_ID__';
  private readonly bundle: string = '__SERIAL_BUNDLE__';
  private readonly target: string = '__SERIAL_PORT_NAME__';
  private ports: serial.SerialPort[] = [];
  private original: serial.SerialPortInfo = { portName: '' };
  private step: number = 0;
  private busy: boolean = false;
  private primaryCount: number = 0;
  private secondaryCount: number = 0;
  private primaryCallback = (): void => { this.primaryCount++; };
  private secondaryCallback = (): void => { this.secondaryCount++; };

  aboutToAppear(): void {
    const file = fs.openSync(RESULTS, fs.OpenMode.WRITE_ONLY | fs.OpenMode.CREATE | fs.OpenMode.TRUNC);
    fs.closeSync(file);
    this.record('begin', true, 0, 'number', 'ordinary_hap_actual_UI_required');
  }

  private record(name: string, passed: boolean, code: number, type: string, details: string): void {
    const row: AttachmentRow = { kind: 'serial_attachment_case', run_id: this.runId, bundle: this.bundle,
      case: name, passed: passed, code: code, code_type: type, details: details };
    const file = fs.openSync(RESULTS, fs.OpenMode.WRITE_ONLY | fs.OpenMode.APPEND);
    fs.writeSync(file.fd, JSON.stringify(row) + '\n'); fs.closeSync(file);
    this.note = name + ': ' + (passed ? 'PASS' : 'FAIL') + ' (' + code + ')';
  }

  private async select(name: string, replacement: boolean): Promise<boolean> {
    const found: serial.SerialPort[] = await serial.getSerialPortList();
    this.ports = found.filter((port: serial.SerialPort): boolean => port.portInfo.portName === this.target);
    let matched: boolean = this.ports.length === 1;
    if (matched && replacement) {
      const info: serial.SerialPortInfo = this.ports[0].portInfo;
      matched = info.vendorId === this.original.vendorId && info.productId === this.original.productId &&
        info.manufacturer === this.original.manufacturer;
    }
    if (matched && !replacement) { this.original = this.ports[0].portInfo; }
    this.record(name, matched, 0, 'number', JSON.stringify(found.map(
      (port: serial.SerialPort): serial.SerialPortInfo => port.portInfo)));
    return matched;
  }

  private async rejectOpen(name: string, expected: number): Promise<boolean> {
    try {
      await this.ports[0].open();
      this.record(name, false, 0, 'number', 'unexpected open without expected refusal');
      await this.ports[0].close();
    } catch (error) {
      let err: BusinessError = error;
      const passed: boolean = typeof err.code === 'number' && err.code === expected;
      this.record(name, passed, err.code, typeof err.code, err.message);
      return passed;
    }
    return false;
  }

  private async pendingUnplug(): Promise<void> {
    if (!await this.select('enumerate_original', false)) { return; }
    this.note = 'During the actual authorization UI, detach the endpoint. Do not approve a new session.';
    if (await this.rejectOpen('unplug_pending_open', DISCONNECTED)) { this.step++; }
  }

  private async replacementDeny(): Promise<void> {
    if (!await this.select('enumerate_replacement', true)) { return; }
    this.note = 'Choose Deny in the NEW actual system UI. Silent inherited approval is a failure.';
    if (await this.rejectOpen('deny_replacement', DENIED)) { this.step++; }
  }

  private async approveAndUnplug(): Promise<void> {
    const port: serial.SerialPort = this.ports[0];
    this.note = 'Choose Allow; then detach the endpoint while this port is open.';
    await port.open();
    this.record('allow_replacement', true, 0, 'number', 'actual public open resolved');
    const checked: string = acl.check(this.target);
    const parsed: AclResult = JSON.parse(checked);
    this.record('raw_node_denied_after_grant', parsed.passed, 0, 'number', checked);
    port.onDisconnect(this.primaryCallback); port.onDisconnect(this.secondaryCallback);
    port.offDisconnect(this.primaryCallback);
    const deadline: number = Date.now() + WAIT_OFFLINE_MS;
    while (Date.now() < deadline && this.secondaryCount === 0) {
      await new Promise<void>((resolve: () => void): void => { setTimeout(resolve, POLL_MS); });
    }
    await new Promise<void>((resolve: () => void): void => { setTimeout(resolve, QUIET_MS); });
    this.record('on_off_disconnect', this.primaryCount === 0 && this.secondaryCount === 1, 0, 'number',
      JSON.stringify({ removed: this.primaryCount, retained: this.secondaryCount }));
    const found: serial.SerialPort[] = await serial.getSerialPortList();
    const absent: boolean = found.every((item: serial.SerialPort): boolean => item.portInfo.portName !== this.target);
    this.record('enumerate_absent', absent, 0, 'number', JSON.stringify(found.map(
      (item: serial.SerialPort): serial.SerialPortInfo => item.portInfo)));
    try {
      await port.write(new Uint8Array([1]));
      this.record('write_stale_object', false, 0, 'number', 'unexpected offline write');
    } catch (error) {
      let err: BusinessError = error;
      const passed: boolean = typeof err.code === 'number' && err.code === DISCONNECTED;
      this.record('write_stale_object', passed, err.code, typeof err.code, err.message);
      if (passed && absent && this.primaryCount === 0 && this.secondaryCount === 1) { this.step++; }
    }
  }

  private async replugDeny(): Promise<void> {
    if (!await this.select('enumerate_replug', true)) { return; }
    this.note = 'Choose Deny in a NEW UI after replug; the earlier grant must not survive attachment replacement.';
    if (await this.rejectOpen('deny_replug', DENIED)) { this.step++; }
  }

  private async replugAllow(): Promise<void> {
    await this.ports[0].open();
    this.record('allow_replug', true, 0, 'number', 'new actual user approval resolved');
    await this.ports[0].close();
    this.record('close_replug', true, 0, 'number', 'new attachment closed');
    this.record('completed', true, 0, 'number', 'attachment API transcript only; package/UI/device evidence separate');
    this.step++;
  }

  private async next(): Promise<void> {
    if (this.busy) { return; }
    this.busy = true;
    try {
      switch (this.step) {
        case 0: await this.pendingUnplug(); break;
        case 1: await this.replacementDeny(); break;
        case 2: await this.approveAndUnplug(); break;
        case 3: await this.replugDeny(); break;
        case 4: await this.replugAllow(); break;
      }
    } catch (error) {
      let err: BusinessError = error;
      this.record('unexpected_failure', false, err.code, typeof err.code, err.message);
    } finally { this.busy = false; }
  }

  build() {
    Column({ space: 12 }) {
      Text('Serial attachment boundary audit').fontSize(20)
      Text(this.note).fontSize(14)
      Text('Stage ' + this.step + ': retain actual UI and devnode/sysfs snapshots').fontSize(14)
      Button('Next operator-controlled stage').id('serial-attachment-next').onClick(() => { this.next(); })
    }.padding(20)
  }
}
