// SPDX-License-Identifier: Apache-2.0
// Real service calls. Only this fresh probe's own imported credential is removed.
import certificateManager from '@ohos.security.certManager';
import fs from '@ohos.file.fs';
import { BusinessError } from '@kit.BasicServicesKit';

interface Result {
  name: string; runId: string; role: string; code: number; uri: string;
  credentials: certificateManager.CredentialAbstract[]; values: number[]; error: string;
}

@Entry
@Component
struct Index {
  @State private note: string = 'Checking CertificateManager';
  private readonly runId: string = '__CERTIFICATE_RUN_ID__';
  private readonly role: string = '__CERTIFICATE_ROLE__';
  private readonly path: string = '/data/storage/el2/base/files/certificate-__CERTIFICATE_RUN_ID__-results.log';
  private readonly keystore: Uint8Array = new Uint8Array(__CERTIFICATE_BYTES__);
  private failures: number = 0;
  private count: number = 0;
  private record(name: string, code: number = 0, uri: string = '',
    credentials: certificateManager.CredentialAbstract[] = [], values: number[] = [], error: string = ''): void {
    const row: Result = { name, runId: this.runId, role: this.role, code, uri, credentials, values, error };
    const file = fs.openSync(this.path, fs.OpenMode.WRITE_ONLY | fs.OpenMode.CREATE | fs.OpenMode.APPEND);
    fs.writeSync(file.fd, JSON.stringify(row) + '\n'); fs.closeSync(file); this.note = name; this.count++;
  }
  private callbackList(): Promise<certificateManager.CMResult> {
    return new Promise<certificateManager.CMResult>((resolve, reject) => {
      certificateManager.getAllAppPrivateCertificates((error, value) => {
        if (error) { reject(error); } else { resolve(value); }
      });
    });
  }
  private list(name: string, result: certificateManager.CMResult): void {
    // Never coerce undefined into an empty success: this is the original bug.
    if (result === undefined || result.credentialList === undefined || !Array.isArray(result.credentialList)) {
      throw new Error('CMResult.credentialList is not an actual array');
    }
    this.record(name, 0, '', result.credentialList);
  }
  private async errorCase(name: string, operation: () => Promise<Object | void>): Promise<void> {
    try {
      await operation(); this.record(name, 0, '', [], [], 'unexpected success');
    } catch (error) { this.record(name, (error as BusinessError).code); }
  }
  private async installErrorCase(name: string, bytes: Uint8Array, password: string, alias: string): Promise<void> {
    let installed: certificateManager.CMResult | undefined = undefined;
    try { installed = await certificateManager.installPrivateCertificate(bytes, password, alias); }
    catch (error) { this.record(name, (error as BusinessError).code); return; }
    // Record the unexpected success before cleanup: cleanup denial cannot be
    // mistaken for rejection of the original install operation.
    this.record(name, 0, '', [], [], 'unexpected install success');
    if (installed !== undefined && installed.uri !== undefined && installed.uri.length > 0) {
      await certificateManager.uninstallPrivateCertificate(installed.uri);
    }
  }
  private async snapshots(prefix: string): Promise<void> {
    this.list(prefix + '.promise', await certificateManager.getAllAppPrivateCertificates());
    this.list(prefix + '.callback', await this.callbackList());
    this.list(prefix + '.own', await certificateManager.getPrivateCertificates());
  }
  private async generation(generation: number): Promise<void> {
    const alias: string = 'qemu_' + this.runId.substring(0, 16) + '_' + generation;
    let ownUri: string = '';
    try {
      const installed: certificateManager.CMResult = await certificateManager.installPrivateCertificate(
        this.keystore, 'qemu_test_only', alias);
      if (installed === undefined || installed.uri === undefined || installed.uri.length === 0) {
        throw new Error('real imported credential URI missing');
      }
      ownUri = installed.uri; this.record('install.' + generation, 0, ownUri);
      await this.snapshots('populated.' + generation);
      await certificateManager.uninstallPrivateCertificate(ownUri);
      this.record('uninstall.' + generation, 0, ownUri); ownUri = '';
      await this.snapshots('after.' + generation);
    } finally {
      // No uninstall-all, no deletion of a URI returned by a list operation.
      if (ownUri.length > 0) { await certificateManager.uninstallPrivateCertificate(ownUri); }
    }
  }
  private async system(): Promise<void> {
    await this.snapshots('empty');
    for (let generation = 0; generation < 2; generation++) { await this.generation(generation); }
    const invalidAlias: string = 'qemu_' + this.runId.substring(0, 16) + '_bad';
    await this.installErrorCase('boundary.format', new Uint8Array(64), 'qemu_test_only', invalidAlias);
    await this.installErrorCase('boundary.password', this.keystore, 'incorrect_password', invalidAlias);
    await this.installErrorCase('boundary.alias', this.keystore, 'qemu_test_only', '');
    await this.errorCase('boundary.uri', async () => {
      return await certificateManager.uninstallPrivateCertificate('');
    });
    let bad: number = 0;
    for (let i = 0; i < 64; i++) {
      const result: certificateManager.CMResult = await certificateManager.getAllAppPrivateCertificates();
      if (result === undefined || result.credentialList === undefined || !Array.isArray(result.credentialList) ||
        result.credentialList.length !== 0) { bad++; }
    }
    this.record('repeat.empty', 0, '', [], [64, bad]);
  }
  private async normal(): Promise<void> {
    await this.errorCase('denied.promise', async () => { return await certificateManager.getAllAppPrivateCertificates(); });
    await this.errorCase('denied.callback', async () => { return await this.callbackList(); });
    await this.errorCase('denied.own', async () => { return await certificateManager.getPrivateCertificates(); });
    await this.installErrorCase('denied.install', this.keystore, 'qemu_test_only',
      'qemu_' + this.runId.substring(0, 16) + '_denied');
  }
  private async run(): Promise<void> {
    try { if (this.role === 'normal') { await this.normal(); } else { await this.system(); } }
    catch (error) { this.failures++; this.record('failed', 0, '', [], [], (error as Error).message || 'exception'); }
    this.record('summary', 0, '', [], [this.count, this.failures]);
  }
  aboutToAppear(): void {
    const file = fs.openSync(this.path, fs.OpenMode.WRITE_ONLY | fs.OpenMode.CREATE | fs.OpenMode.TRUNC);
    fs.closeSync(file); this.run();
  }
  build() { Column() { Text(this.note) }.width('100%').height('100%') }
}
