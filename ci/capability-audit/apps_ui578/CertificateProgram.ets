import certificate from '@ohos.security.certManager';
import dialog from '@ohos.security.certManagerDialog';
import x509 from '@ohos.security.cert';
import fs from '@ohos.file.fs';
import common from '@ohos.app.ability.common';
import { Journal, RUN } from './Journal';

// Original root fixture producer supplies this nonce's actual PKCS12/DER.
// These are data files in this caller's sandbox, never source/executable input.
export class CertificateProgram {
  private context: common.UIAbilityContext;
  constructor(context: common.UIAbilityContext) { this.context = context; }
  private files(): string { return this.context.getApplicationContext().filesDir; }
  private bytes(suffix: string): Uint8Array {
    const path = this.files() + '/apps578-' + RUN + suffix;
    const file = fs.openSync(path, fs.OpenMode.READ_ONLY | fs.OpenMode.NOFOLLOW);
    try {
      const size = fs.statSync(file.fd).size;
      if (size <= 0 || size > 20480) { throw new Error('bounded actual certificate fixture required'); }
      const data = new ArrayBuffer(size);
      if (fs.readSync(file.fd, data) !== size) { throw new Error('incomplete actual certificate fixture'); }
      return new Uint8Array(data);
    } finally { fs.closeSync(file); }
  }
  private save(name: string, uri: string): void {
    if (uri.length === 0 || uri.length > 256) { throw new Error('actual installed certificate URI required'); }
    const path = this.files() + '/apps578-' + RUN + '-' + name + '.uri';
    const file = fs.openSync(path, fs.OpenMode.WRITE_ONLY | fs.OpenMode.CREATE | fs.OpenMode.TRUNC | fs.OpenMode.NOFOLLOW);
    try { fs.writeSync(file.fd, uri); } finally { fs.closeSync(file); }
  }
  private uri(name: string): string {
    const uri = fs.readTextSync(this.files() + '/apps578-' + RUN + '-' + name + '.uri');
    if (uri.length === 0 || uri.length > 256) { throw new Error('own nonce certificate URI required'); }
    return uri;
  }
  private saveTrustedBaseline(uris: string[]): void {
    const file = fs.openSync(this.files() + '/apps578-' + RUN + '-trusted-before.json',
      fs.OpenMode.WRITE_ONLY | fs.OpenMode.CREATE | fs.OpenMode.TRUNC | fs.OpenMode.NOFOLLOW);
    try { fs.writeSync(file.fd, JSON.stringify(uris)); } finally { fs.closeSync(file); }
  }
  private async recoverOwnCa(): Promise<string> {
    const original = JSON.parse(fs.readTextSync(this.files() + '/apps578-' + RUN + '-trusted-before.json')) as string[];
    const expected = this.bytes('.der');
    const current = await certificate.getAllUserTrustedCertificates();
    if (current.certList === undefined) { throw new Error('actual trusted inventory missing'); }
    const found: string[] = [];
    for (const item of current.certList) {
      if (original.includes(item.uri)) { continue; }
      const cert = await certificate.getUserTrustedCertificate(item.uri);
      if (cert.certInfo !== undefined && cert.certInfo.cert.length === expected.length &&
        expected.every((value: number, index: number) => value === cert.certInfo?.cert[index])) {
        found.push(item.uri);
      }
    }
    if (found.length > 1) { throw new Error('refuse ambiguous nonce CA recovery'); }
    if (found.length === 1) { this.save('ca', found[0]); }
    return JSON.stringify({ uri: found.length === 1 ? found[0] : '' });
  }
  async run(action: string): Promise<string> {
    if (action === 'read') {
      const own = await certificate.getPrivateCertificates();
      const trusted = await certificate.getAllUserTrustedCertificates();
      if (trusted.certList === undefined) { throw new Error('actual trusted inventory missing'); }
      if (Journal.operation === 'baseline') { this.saveTrustedBaseline(trusted.certList.map((item) => item.uri)); }
      return JSON.stringify({ supportsCA: dialog.supportsCACertDialog(), own, trusted });
    }
    if (action === 'invalid') {
      await dialog.openCertificateManagerDialog(this.context, 0 as dialog.CertificateDialogPageType);
    } else if (action === 'ca') {
      await dialog.openCertificateManagerDialog(this.context, dialog.CertificateDialogPageType.PAGE_CA_CERTIFICATE);
    } else if (action === 'import') {
      const imported = await certificate.installPrivateCertificate(this.bytes('.p12'), 'qemu_test_only', 'apps_' + RUN.substring(0, 16));
      if (!imported.uri) { throw new Error('actual credential import returned no URI'); }
      this.save('private', imported.uri);return JSON.stringify(imported);
    } else if (action === 'remove') {
      const uri = this.uri('private');
      const own = await certificate.getPrivateCertificate(uri);
      if (!own.credential || own.credential.alias !== 'apps_' + RUN.substring(0,16)) {
        throw new Error('refuse removal of a credential not owned by this nonce');
      }
      await certificate.uninstallPrivateCertificate(uri);
    } else if (action === 'install-ca') {
      const uri = await dialog.openInstallCertificateDialog(this.context, dialog.CertificateType.CA_CERT,
        dialog.CertificateScope.CURRENT_USER, this.bytes('.der'));
      this.save('ca', uri);return JSON.stringify(uri);
    } else if (action === 'recover-ca') {
      return await this.recoverOwnCa();
    } else if (action === 'invalid-remove-ca') {
      await dialog.openUninstallCertificateDialog(this.context, dialog.CertificateType.CA_CERT, '');
    } else if (action === 'unsupported-remove-ca') {
      await dialog.openUninstallCertificateDialog(this.context, dialog.CertificateType.CA_CERT,
        'apps578-unavailable-' + RUN);
    } else if (action === 'read-ca') {
      const actual = await certificate.getUserTrustedCertificate(this.uri('ca'));
      if (!actual.certInfo) { throw new Error('actual CA consumer returned no certificate'); }
      return JSON.stringify({ uri: actual.certInfo.uri, subject: actual.certInfo.subjectName,
        serial: actual.certInfo.serial, fingerprint: actual.certInfo.fingerprintSha256,
        bytes: Array.from(actual.certInfo.cert) });
    } else if (action === 'remove-ca') {
      const uri = this.uri('ca');
      const actual = await certificate.getUserTrustedCertificate(uri);
      if (!actual.certInfo || !this.bytes('.der').every((x: number, i: number) => x === actual.certInfo?.cert[i]) ||
        actual.certInfo.cert.length !== this.bytes('.der').length) { throw new Error('refuse unrelated CA removal'); }
      await dialog.openUninstallCertificateDialog(this.context, dialog.CertificateType.CA_CERT, uri);
    } else {
      const reference = await dialog.openAuthorizeDialog(this.context, {
        certTypes: [dialog.CertificateType.CREDENTIAL_APP], uri: 'https://apps578.invalid/' + RUN
      });
      Journal.record('certificate.reference', 0, JSON.stringify(reference));
      const actual = await certificate.getPrivateCertificate(reference.keyUri);
      if (!actual.credential) { throw new Error('actual selected URI has no credential'); }
      const parsed = await x509.createX509Cert({ data: actual.credential.credentialData,
        encodingFormat: actual.credential.credentialData[0] === 45 ? x509.EncodingFormat.FORMAT_PEM : x509.EncodingFormat.FORMAT_DER });
      const encoded = await parsed.getEncoded();
      return JSON.stringify({ reference, alias: actual.credential.alias, keyUri: actual.credential.keyUri,
        certNum: actual.credential.certNum, keyNum: actual.credential.keyNum,
        bytes: Array.from(actual.credential.credentialData), der: Array.from(encoded.data) });
    }
    return 'null';
  }
}
