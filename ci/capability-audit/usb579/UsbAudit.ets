// Copyright (c) 2026 OpenHarmony contributors. Licensed under Apache-2.0.
// Every device, right, descriptor and transfer comes from the public UsbService.
import usb from '@ohos.usbManager';
import commonEventManager from '@ohos.commonEventManager';
import common from '@ohos.app.ability.common';
import fs from '@ohos.file.fs';
import process from '@ohos.process';
import systemDateTime from '@ohos.systemDateTime';
import util from '@ohos.util';
import { BusinessError } from '@ohos.base';

interface Request { run: string; boot: string; operation: string; action: string; }
interface MtpContainer { kind: number; code: number; id: number; data: Uint8Array; }
export class UsbAudit {
  private readonly run: string = '__USB579_RUN__';
  private readonly role: string = '__USB579_ROLE__';
  private sequence: number = 0;
  private used: string[] = [];
  private serial: Promise<void> = Promise.resolve();
  private current: Request | undefined = undefined;
  private subscriber: commonEventManager.CommonEventSubscriber | undefined = undefined;
  private eventCount: number = 0;
  private device: usb.USBDevice | undefined = undefined;
  private pipe: usb.USBDevicePipe | undefined = undefined;
  private iface: usb.USBInterface | undefined = undefined;
  private input: usb.USBEndpoint | undefined = undefined;
  private output: usb.USBEndpoint | undefined = undefined;
  private interrupt: usb.UsbDataTransferParams | undefined = undefined;
  private interruptLive: boolean = false;
  private interruptPending: boolean = false;
  private interruptCount: number = 0;
  private transaction: number = 0;
  private storage: number = 0;
  private uploaded: number = 0;
  private cancelledTransaction: number = 0;
  private payload: Uint8Array = new Uint8Array(0);
  constructor(private context: common.UIAbilityContext) {
    const path = context.filesDir + '/usb579-' + this.run + '.jsonl';
    if (fs.accessSync(path)) {
      const text = fs.readTextSync(path);
      if (!text.endsWith('\n') || text.length > 16 * 1024 * 1024) { throw new Error('Existing USB journal incomplete'); }
      const rows = text.trimEnd().split('\n'); this.sequence = rows.length;
      rows.forEach((line: string): void => {
        const row = JSON.parse(line) as Request;
        if (!this.used.includes(row.operation)) { this.used.push(row.operation); }
      });
    }
  }
  private now(): number { return systemDateTime.getUptime(systemDateTime.TimeType.STARTUP, false); }
  private wait(ms: number): Promise<void> { return new Promise<void>((resolve): void => { setTimeout(resolve, ms); }); }
  private append(c: Request, event: string, value: string = 'null', code: number = 0): void {
    const line = JSON.stringify({ run: this.run, role: this.role, boot: c.boot, operation: c.operation,
      action: c.action, event: event, value: value, code: code, seq: ++this.sequence,
      uid: process.uid, pid: process.pid, uptimeMs: this.now(), filesDir: this.context.filesDir }) + '\n';
    const file = fs.openSync(this.context.filesDir + '/usb579-' + this.run + '.jsonl',
      fs.OpenMode.CREATE | fs.OpenMode.WRITE_ONLY | fs.OpenMode.APPEND | fs.OpenMode.NOFOLLOW);
    try {
      const bytes = new util.TextEncoder().encodeInto(line); let offset: number = 0;
      while (offset < bytes.byteLength) {
        const count = fs.writeSync(file.fd, bytes.slice(offset).buffer);
        if (count <= 0) { throw new Error('Raw USB journal short write'); } offset += count;
      }
    } finally { fs.closeSync(file); }
  }
  accept(text: string): void {
    const c = JSON.parse(text) as Request;
    if (text.length > 2048 || c.run !== this.run || !/^[a-f0-9-]{36}$/.test(c.boot) ||
      !/^[a-f0-9]{32}$/.test(c.operation) || this.used.includes(c.operation) || this.used.length > 80 ||
      !['identity', 'observe', 'enumerate', 'permission', 'open', 'bulk', 'revoke', 'boundary', 'stale',
        'release', 'mtp-open', 'mtp-object', 'mtp-small', 'mtp-cancel', 'mtp-cancel-finish', 'mtp-delete', 'mtp-close', 'cleanup'].includes(c.action)) {
      throw new Error('Fixed actual USB operation required');
    }
    this.used.push(c.operation); this.serial = this.serial.then((): Promise<void> => this.execute(c));
  }
  private hex(bytes: Uint8Array): string {
    let text: string = '';
    for (let i: number = 0; i < bytes.length; ++i) { text += bytes[i].toString(16).padStart(2, '0'); }
    return text;
  }
  private fromHex(text: string): Uint8Array {
    const bytes = new Uint8Array(text.length / 2);
    for (let i: number = 0; i < bytes.length; ++i) { bytes[i] = parseInt(text.substring(i * 2, i * 2 + 2), 16); }
    return bytes;
  }
  private selected(c: Request): usb.USBDevice {
    const devices = usb.getDevices(); this.append(c, 'actual-device-list', JSON.stringify(devices));
    const matches = devices.filter((device: usb.USBDevice): boolean => device.vendorId === 0x1d6b && device.productId === 0x0104);
    if (matches.length !== 1) { throw new Error('Exactly one actual owned USB composite device required'); }
    this.device = matches[0]; return matches[0];
  }
  private async observe(c: Request): Promise<void> {
    if (this.subscriber !== undefined) { throw new Error('Original subscription already live'); }
    this.subscriber = await commonEventManager.createSubscriber({ events: [
      'usual.event.hardware.usb.action.USB_DEVICE_ATTACHED', 'usual.event.hardware.usb.action.USB_DEVICE_DETACHED'] });
    commonEventManager.subscribe(this.subscriber, (error: BusinessError, data: commonEventManager.CommonEventData): void => {
      if (this.current === undefined) { return; }
      if (error) { this.append(this.current, 'native-device-event-error', JSON.stringify(error.message), error.code); return; }
      this.eventCount++; this.append(this.current, 'native-device-event', JSON.stringify(data));
    });
    this.append(c, 'native-subscription-created');
  }
  private open(c: Request, clazz: number): void {
    if (this.pipe !== undefined) { throw new Error('Release prior actual pipe'); }
    const device = this.selected(c); this.append(c, 'actual-right-before-open', JSON.stringify(usb.hasRight(device.name)));
    const pipe = usb.connectDevice(device); this.append(c, 'actual-open', JSON.stringify(pipe));
    this.pipe = pipe;
    this.append(c, 'actual-usb-file-descriptor', JSON.stringify(usb.getFileDescriptor(pipe)));
    const raw = usb.getRawDescriptor(pipe); this.append(c, 'actual-raw-descriptors', JSON.stringify(this.hex(raw)));
    const interfaces = device.configs[0].interfaces.filter((iface: usb.USBInterface): boolean => iface.clazz === clazz);
    if (interfaces.length !== 1) { throw new Error('One real protocol interface required'); }
    const iface = interfaces[0]; const result = usb.claimInterface(pipe, iface, false);
    this.append(c, 'actual-claim', JSON.stringify({ result: result, iface: iface }));
    if (result !== 0) { throw new Error('Original service did not claim interface'); }
    this.iface = iface;
    const inputs = iface.endpoints.filter((ep: usb.USBEndpoint): boolean => ep.type === 2 && ep.direction === 0x80);
    const outputs = iface.endpoints.filter((ep: usb.USBEndpoint): boolean => ep.type === 2 && ep.direction === 0);
    if (inputs.length !== 1 || outputs.length !== 1) { throw new Error('Actual standard bulk endpoints required'); }
    this.input = inputs[0]; this.output = outputs[0];
  }
  private async send(c: Request, bytes: Uint8Array, label: string): Promise<void> {
    if (this.pipe === undefined || this.output === undefined) { throw new Error('Actual live output pipe required'); }
    this.append(c, label + '-submitted', JSON.stringify(this.hex(bytes)));
    const count = await usb.bulkTransfer(this.pipe, this.output, bytes, 10000);
    this.append(c, label + '-completed', JSON.stringify(count));
    if (count !== bytes.length) { throw new Error('Actual original USB bulk write incomplete'); }
  }
  private async receive(c: Request, capacity: number, label: string): Promise<Uint8Array> {
    if (this.pipe === undefined || this.input === undefined) { throw new Error('Actual live input pipe required'); }
    const bytes = new Uint8Array(capacity); const count = await usb.bulkTransfer(this.pipe, this.input, bytes, 10000);
    this.append(c, label + '-completed', JSON.stringify({ count: count, hex: this.hex(bytes.slice(0, Math.max(0, count))) }));
    if (count <= 0 || count > capacity) { throw new Error('Actual original USB bulk read failed'); }
    return bytes.slice(0, count);
  }
  private async bulk(c: Request): Promise<void> {
    const request = new Uint8Array(64); request.set([0x55, 0x48, 0x35, 0x37]);
    request.set(this.fromHex(this.run), 4); request.set(this.fromHex(c.operation), 20);
    for (let i: number = 36; i < request.length; ++i) { request[i] = (i * 37) ^ parseInt(c.operation.substring((i % 16) * 2, (i % 16) * 2 + 2), 16); }
    await this.send(c, request, 'actual-host-request'); const response = await this.receive(c, 128, 'actual-independent-peer-response');
    if (response.length !== 128 || this.hex(response.slice(0, 4)) !== '55503537' || this.hex(response.slice(8, 72)) !== this.hex(request)) {
      throw new Error('Actual peer did not consume this complete nonce request');
    }
    const ack = new Uint8Array(64); ack.set([0x55, 0x41, 0x35, 0x37]); ack.set(this.fromHex(c.operation), 4);
    for (let i: number = 0; i < 32; ++i) { ack[20 + i] = response[72 + i] ^ 0xa5; }
    ack.set(this.fromHex(this.run).slice(0, 12), 52); await this.send(c, ack, 'actual-peer-challenge-ack');
  }
  private release(c: Request): void {
    if (this.pipe === undefined) { return; }
    if (this.iface !== undefined) { this.append(c, 'actual-interface-release', JSON.stringify(usb.releaseInterface(this.pipe, this.iface))); }
    this.append(c, 'actual-pipe-close', JSON.stringify(usb.closePipe(this.pipe)));
    this.pipe = undefined; this.iface = undefined; this.input = undefined; this.output = undefined;
  }
  private async boundary(c: Request, stale: boolean): Promise<void> {
    try {
      if (stale) {
        if (this.pipe === undefined || this.output === undefined) { throw new Error('Actual retained stale pipe required'); }
        const status = await usb.bulkTransfer(this.pipe, this.output, new Uint8Array([0x57]), 1000);
        this.append(c, 'native-boundary-transfer-status', JSON.stringify(status));
      } else {
        const device = this.selected(c); const pipe = usb.connectDevice(device);
        this.append(c, 'unexpected-boundary-open', JSON.stringify(pipe)); usb.closePipe(pipe);
      }
    } catch (error) {
      const value = error as BusinessError;
      this.append(c, 'native-boundary-error', JSON.stringify(value.message), typeof value.code === 'number' ? value.code : -1);
    }
  }
  private async execute(c: Request): Promise<void> {
    this.current = c; this.append(c, 'begin', JSON.stringify(c));
    try {
      if (c.action === 'observe') { await this.observe(c); }
      else if (c.action === 'enumerate') { this.selected(c); }
      else if (c.action === 'permission') {
        const device = this.selected(c); this.append(c, 'actual-right-before-dialog', JSON.stringify(usb.hasRight(device.name)));
        this.append(c, 'actual-request-right', JSON.stringify(await usb.requestRight(device.name)));
        this.append(c, 'actual-right-after-dialog', JSON.stringify(usb.hasRight(device.name)));
      } else if (c.action === 'open') { this.open(c, 0xff); }
      else if (c.action === 'bulk') { await this.bulk(c); }
      else if (c.action === 'release') { this.release(c); }
      else if (c.action === 'revoke') {
        const device = this.selected(c); this.append(c, 'actual-remove-right', JSON.stringify(usb.removeRight(device.name)));
        this.append(c, 'actual-right-after-revoke', JSON.stringify(usb.hasRight(device.name))); await this.boundary(c, true);
      } else if (c.action === 'boundary') { await this.boundary(c, false); }
      else if (c.action === 'stale') { await this.boundary(c, true); }
      else if (c.action.startsWith('mtp-')) { await this.mtp(c); }
      else if (c.action === 'cleanup') {
        await this.stopInterrupt(c); this.release(c);
        if (this.subscriber !== undefined) {
          const subscriber = this.subscriber;
          await new Promise<void>((resolve, reject): void => {
            commonEventManager.unsubscribe(subscriber, (error: BusinessError): void => { if (error) { reject(error); } else { resolve(); } });
          });
          this.subscriber = undefined; this.append(c, 'native-unsubscribed');
        }
        const before = this.eventCount; await this.wait(1500);
        this.append(c, 'native-quiet', JSON.stringify({ before: before, after: this.eventCount }));
      }
      this.append(c, 'return');
    } catch (error) {
      const value = error as BusinessError; this.append(c, 'throw', JSON.stringify(value.message), typeof value.code === 'number' ? value.code : -1);
    } finally { this.append(c, 'end'); }
  }
  private async mtp(c: Request): Promise<void> { await this.mtpOperation(c); }
  // The real MTP transport methods are in this same source below. There is no
  // external selector, native substitute service or expected-response map.
  private async mtpOperation(c: Request): Promise<void> {
    if (c.action === 'mtp-open') {
      this.open(c, 6); this.startInterrupt(c); this.transaction = 0;
      const info = await this.mtpCommand(c, 0x1001, [], undefined, true);
      this.append(c, 'actual-mtp-device-info', JSON.stringify(this.hex(info.data)));
      await this.mtpCommand(c, 0x1002, [1]);
      const storage = await this.mtpCommand(c, 0x1004, [], undefined, true);
      if (storage.data.length < 8 || this.u32(storage.data, 0) === 0) { throw new Error('Actual MTP storage absent'); }
      this.storage = this.u32(storage.data, 4); this.append(c, 'actual-mtp-storage-id', JSON.stringify(this.storage));
      const description = await this.mtpCommand(c, 0x1005, [this.storage], undefined, true);
      this.append(c, 'actual-mtp-storage-info', JSON.stringify(this.hex(description.data)));
    } else if (c.action === 'mtp-object' || c.action === 'mtp-small') {
      this.payload = new Uint8Array(c.action === 'mtp-small' ? 500 : 65536);
      for (let i: number = 0; i < this.payload.length; ++i) {
        this.payload[i] = ((i * 29) ^ (i >>> 8) ^ parseInt(c.operation.substring((i % 16) * 2, (i % 16) * 2 + 2), 16)) & 0xff;
      }
      const filename = 'usb579-' + this.run + '-' + c.operation + '.bin';
      await this.createObject(c, filename, this.payload.length);
      await this.mtpCommand(c, 0x100d, [], this.payload);
      const objectInfo = await this.mtpCommand(c, 0x1008, [this.uploaded], undefined, true);
      this.append(c, 'actual-mtp-created-object-info', JSON.stringify(this.hex(objectInfo.data)));
      const downloaded = await this.mtpCommand(c, 0x1009, [this.uploaded], undefined, true);
      this.append(c, 'actual-mtp-uploaded-file', JSON.stringify({ filename: filename, handle: this.uploaded, hex: this.hex(this.payload) }));
      this.append(c, 'actual-mtp-downloaded-file', JSON.stringify(this.hex(downloaded.data)));
      if (this.hex(downloaded.data) !== this.hex(this.payload)) { throw new Error('Actual MTP media-library file differs from complete nonce input'); }
      const partLength = Math.min(1024, this.payload.length - 123);
      const part = await this.mtpCommand(c, 0x101b, [this.uploaded, 123, partLength], undefined, true);
      if (this.hex(part.data) !== this.hex(this.payload.slice(123, 123 + partLength))) { throw new Error('Actual MTP partial object offsets differ'); }
      // Keep the genuine provider-owned file until the independent root IO
      // records its inode, UID, bytes and hash through the provider mount.
    } else if (c.action === 'mtp-delete') {
      if (this.uploaded === 0) { throw new Error('Actual uploaded object required'); }
      await this.mtpCommand(c, 0x100b, [this.uploaded, 0]);
      const missing = await this.mtpCommand(c, 0x1008, [this.uploaded], undefined, false, 0x2009);
      this.append(c, 'actual-mtp-deleted-handle-code', JSON.stringify(missing.code)); this.uploaded = 0;
    } else if (c.action === 'mtp-cancel') {
      const filename = 'usb579-' + this.run + '-' + c.operation + '-cancel.bin';
      await this.createObject(c, filename, 1048576);
      const id = ++this.transaction; await this.send(c, this.container(1, 0x100d, id, new Uint8Array(0)), 'mtp-cancel-command');
      const prefix = new Uint8Array(4096); prefix.set(this.container(2, 0x100d, id, new Uint8Array(0)).slice(0, 12));
      new DataView(prefix.buffer).setUint32(0, 1048576 + 12, true);
      for (let i: number = 12; i < prefix.length; ++i) { prefix[i] = (i * 19) & 0xff; }
      await this.send(c, prefix, 'mtp-cancel-partial-data'); this.cancelledTransaction = id;
      this.append(c, 'actual-mtp-partial-file', JSON.stringify({ filename: filename, handle: this.uploaded, transaction: id }));
      // The independent root IO must observe this genuine provider-owned
      // incomplete file before dispatching the fixed cancellation successor.
    } else if (c.action === 'mtp-cancel-finish') {
      const id = this.cancelledTransaction;
      if (id === 0) { throw new Error('Actual incomplete transaction required'); }
      if (this.pipe === undefined || this.iface === undefined) { throw new Error('Actual claimed MTP control interface required'); }
      const cancellation = new Uint8Array(6); const cancelView = new DataView(cancellation.buffer);
      cancelView.setUint16(0, 0x4001, true); cancelView.setUint32(2, id, true);
      const cancel = await usb.usbControlTransfer(this.pipe, { bmRequestType: 0x21, bRequest: 0x64,
        wValue: 0, wIndex: this.iface.id, wLength: cancellation.length, data: cancellation }, 10000);
      this.append(c, 'actual-mtp-class-cancel', JSON.stringify({ result: cancel, transaction: id, hex: this.hex(cancellation) }));
      const status = new Uint8Array(4);
      const queried = await usb.usbControlTransfer(this.pipe, { bmRequestType: 0xa1, bRequest: 0x67,
        wValue: 0, wIndex: this.iface.id, wLength: status.length, data: status }, 10000);
      this.append(c, 'actual-mtp-class-status', JSON.stringify({ result: queried, hex: this.hex(status) }));
      const reset = await usb.usbControlTransfer(this.pipe, { bmRequestType: 0x21, bRequest: 0x66,
        wValue: 0, wIndex: this.iface.id, wLength: 0, data: new Uint8Array(0) }, 10000);
      this.append(c, 'actual-mtp-class-reset', JSON.stringify(reset));
      if (cancel < 0 || queried !== 4 || new DataView(status.buffer).getUint16(2, true) !== 0x2019 || reset < 0) {
        throw new Error('Actual normal MTP class cancellation/status/reset boundary failed');
      }
      // The service must remain capable of real commands after the transport
      // cancellation. Every raw recovery response remains in the journal.
      await this.mtpCommand(c, 0x1008, [this.uploaded], undefined, false, 0x2009);
      this.uploaded = 0; this.cancelledTransaction = 0;
      await this.mtpCommand(c, 0x1005, [this.storage], undefined, true);
    } else if (c.action === 'mtp-close') {
      await this.mtpCommand(c, 0x1003, []); await this.stopInterrupt(c); this.release(c); this.storage = 0;
    }
  }
  private startInterrupt(c: Request): void {
    if (this.pipe === undefined || this.iface === undefined || this.interrupt !== undefined) { throw new Error('One actual MTP interrupt reader required'); }
    const eps = this.iface.endpoints.filter((ep: usb.USBEndpoint): boolean => ep.type === 3 && ep.direction === 0x80);
    if (eps.length !== 1) { throw new Error('Actual MTP interrupt descriptor absent'); }
    const transfer: usb.UsbDataTransferParams = { devPipe: this.pipe, flags: 0, endpoint: eps[0].address,
      type: usb.UsbEndpointTransferType.TRANSFER_TYPE_INTERRUPT, timeout: 1000, length: 28,
      userData: new Uint8Array(0), buffer: new Uint8Array(28), isoPacketCount: 0,
      callback: (error: BusinessError, result: usb.SubmitTransferCallback): void => {
        this.interruptPending = false; this.interruptCount++;
        const current = this.current;
        if (current !== undefined) {
          this.append(current, 'actual-mtp-interrupt-callback', JSON.stringify({ status: result.status,
            actualLength: result.actualLength, hex: this.hex(transfer.buffer.slice(0, result.actualLength)) }), error ? error.code : 0);
        }
        if (this.interruptLive && (!error || error.code === 0) &&
          (result.status === usb.UsbTransferStatus.TRANSFER_COMPLETED || result.status === usb.UsbTransferStatus.TRANSFER_TIMED_OUT)) {
          this.interruptPending = true; usb.usbSubmitTransfer(transfer);
        }
      } };
    this.interrupt = transfer; this.interruptLive = true; this.interruptPending = true;
    usb.usbSubmitTransfer(transfer); this.append(c, 'actual-mtp-interrupt-submitted', JSON.stringify(eps[0]));
  }
  private async stopInterrupt(c: Request): Promise<void> {
    if (this.interrupt === undefined) { return; }
    this.interruptLive = false;
    if (this.interruptPending) { usb.usbCancelTransfer(this.interrupt); this.append(c, 'actual-mtp-interrupt-cancelled'); }
    const end = this.now() + 5000;
    while (this.interruptPending && this.now() < end) { await this.wait(20); }
    if (this.interruptPending) { throw new Error('Actual MTP interrupt cancellation callback absent'); }
    const before = this.interruptCount; await this.wait(1500);
    this.append(c, 'actual-mtp-interrupt-quiet', JSON.stringify({ before: before, after: this.interruptCount }));
    this.interrupt = undefined;
  }
  private u32(data: Uint8Array, offset: number): number {
    if (offset < 0 || offset + 4 > data.length) { throw new Error('Truncated actual MTP integer'); }
    return new DataView(data.buffer, data.byteOffset, data.byteLength).getUint32(offset, true);
  }
  private words(values: number[]): Uint8Array {
    const bytes = new Uint8Array(values.length * 4); const view = new DataView(bytes.buffer);
    values.forEach((value: number, index: number): void => { view.setUint32(index * 4, value, true); }); return bytes;
  }
  private container(kind: number, code: number, id: number, body: Uint8Array): Uint8Array {
    const data = new Uint8Array(body.length + 12); const view = new DataView(data.buffer);
    view.setUint32(0, data.length, true); view.setUint16(4, kind, true); view.setUint16(6, code, true); view.setUint32(8, id, true);
    data.set(body, 12); return data;
  }
  private async readContainer(c: Request, label: string): Promise<MtpContainer> {
    const first = await this.receive(c, 65536, label + '-first');
    if (first.length < 12) { throw new Error('Truncated actual MTP container header'); }
    const length = this.u32(first, 0);
    if (length < 12 || length > 2097152 || first.length > length) { throw new Error('Unbounded actual MTP container or coalesced extra bytes'); }
    const all = new Uint8Array(length); all.set(first); let count: number = first.length;
    while (count < length) {
      const next = await this.receive(c, Math.min(65536, length - count), label + '-more');
      all.set(next, count); count += next.length;
    }
    const view = new DataView(all.buffer);
    return { kind: view.getUint16(4, true), code: view.getUint16(6, true), id: view.getUint32(8, true), data: all.slice(12) };
  }
  private async mtpCommand(c: Request, operation: number, args: number[], output?: Uint8Array,
    input: boolean = false, wanted: number = 0x2001): Promise<MtpContainer> {
    const id = operation === 0x1001 || operation === 0x1002 ? 0 : ++this.transaction;
    await this.send(c, this.container(1, operation, id, this.words(args)), 'mtp-command');
    if (output !== undefined) { await this.send(c, this.container(2, operation, id, output), 'mtp-data-output'); }
    let data: MtpContainer = { kind: 2, code: operation, id: id, data: new Uint8Array(0) };
    if (input) {
      data = await this.readContainer(c, 'mtp-data-input');
      if (data.kind !== 2 || data.code !== operation || data.id !== id) { throw new Error('Actual MTP data transaction mismatch'); }
    }
    const result = await this.readContainer(c, 'mtp-response');
    this.append(c, 'actual-mtp-result', JSON.stringify({ operation: operation, transaction: id, code: result.code, hex: this.hex(result.data) }));
    if (result.kind !== 3 || result.id !== id || result.code !== wanted) { throw new Error('Actual media-library MTP response or transaction differs'); }
    return input ? data : result;
  }
  private async createObject(c: Request, filename: string, length: number): Promise<void> {
    if (this.storage === 0 || filename.length > 200) { throw new Error('Actual open MTP storage required'); }
    const info = new Uint8Array(52 + 1 + (filename.length + 1) * 2 + 3); const view = new DataView(info.buffer);
    view.setUint32(0, this.storage, true); view.setUint16(4, 0x3000, true); view.setUint32(8, length, true);
    view.setUint32(38, 0xffffffff, true); info[52] = filename.length + 1;
    for (let i: number = 0; i < filename.length; ++i) { view.setUint16(53 + i * 2, filename.charCodeAt(i), true); }
    const created = await this.mtpCommand(c, 0x100c, [this.storage, 0xffffffff], info);
    if (created.data.length !== 12 || this.u32(created.data, 0) !== this.storage) { throw new Error('Actual MTP object allocation absent'); }
    this.uploaded = this.u32(created.data, 8);
    this.append(c, 'actual-mtp-allocated-object', JSON.stringify({ filename: filename, handle: this.uploaded, size: length }));
  }
}
