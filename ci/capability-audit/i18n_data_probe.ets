// SPDX-License-Identifier: Apache-2.0
// Actual bundled-data calls in a normal application, not library presence.
import i18n from '@ohos.i18n';
import intl from '@ohos.intl';
import fs from '@ohos.file.fs';
import hilog from '@ohos.hilog';
import { BusinessError } from '@kit.BasicServicesKit';

interface Result { name: string; pass: boolean; values: string[]; runId: string; }
// The public installed SDK strips this system API. The pinned sdk-js declares
// it; explicitly test rejection in a NORMAL app, not with a system signature.
interface SystemPermissionProbe {
  getSystemLanguage: () => string;
  setSystemLanguage: (language: string) => void;
}
interface WrongTypeProbe { setSystemLanguage: (language: number) => void; }
interface MissingParameterProbe { setSystemLanguage: () => void; }

@Entry
@Component
struct Index {
  @State private note: string = 'Running I18n data and permission checks';
  private readonly runId: string = '__I18N_RUN_ID__';
  private readonly path: string = '/data/storage/el2/base/files/i18n-data-__I18N_RUN_ID__-results.log';

  private record(name: string, pass: boolean, values: string[]): void {
    const result: Result = { name: name, pass: pass, values: values, runId: this.runId };
    const line: string = JSON.stringify(result);
    const file = fs.openSync(this.path, fs.OpenMode.WRITE_ONLY | fs.OpenMode.CREATE | fs.OpenMode.APPEND);
    fs.writeSync(file.fd, line + '\n');
    fs.closeSync(file);
    hilog.info(0xD003900, 'I18nDataAudit', '%{public}s', line);
    this.note = name + ': ' + (pass ? 'pass' : 'FAIL');
  }
  private check(name: string, run: () => string[]): void {
    try { this.record(name, true, run()); }
    catch (error) { this.record(name, false, ['ERROR', (error as BusinessError).message]); }
  }
  private require(condition: boolean): void {
    if (!condition) { throw new Error('I18n data assertion failed'); }
  }
  aboutToAppear(): void {
    // A relaunch must not concatenate previous results into a passing run.
    const file = fs.openSync(this.path, fs.OpenMode.WRITE_ONLY | fs.OpenMode.CREATE | fs.OpenMode.TRUNC);
    fs.closeSync(file);
    const winter: number = Date.UTC(2026, 0, 1, 12);
    const summer: number = Date.UTC(2026, 6, 1, 12);
    this.check('timezone.offsets', () => {
      const shanghai: number = i18n.getTimeZone('Asia/Shanghai').getOffset(winter);
      const nyWinter: number = i18n.getTimeZone('America/New_York').getOffset(winter);
      const nySummer: number = i18n.getTimeZone('America/New_York').getOffset(summer);
      this.require(shanghai === 28800000 && nyWinter === -18000000 && nySummer === -14400000);
      return [shanghai.toString(), nyWinter.toString(), nySummer.toString()];
    });
    this.check('timezone.catalog', () => {
      const ids: string[] = i18n.TimeZone.getAvailableIDs();
      const cities: string[] = i18n.TimeZone.getAvailableZoneCityIDs();
      this.require(ids.includes('Asia/Shanghai') && ids.includes('America/New_York') && cities.length > 0);
      const display: string = i18n.TimeZone.getCityDisplayName(cities[0], 'en-US');
      const zone: string = i18n.TimeZone.getTimezoneFromCity(cities[0]).getID();
      this.require(display.length > 0 && ids.includes(zone));
      return [ids.length.toString(), cities.length.toString(), display, zone];
    });
    this.check('phone.format', () => {
      const formatter = new i18n.PhoneNumberFormat('US', { type: 'E164' });
      const valid: boolean = formatter.isValidNumber('+12025550123');
      const invalid: boolean = formatter.isValidNumber('123');
      const value: string = formatter.format('(202) 555-0123');
      this.require(valid && !invalid && value === '+12025550123');
      return [valid.toString(), invalid.toString(), value];
    });
    this.check('locale.display', () => {
      const country: string = i18n.System.getDisplayCountry('CN', 'en-US');
      this.require(country === 'China');
      return [country];
    });
    this.check('intl.year', () => {
      const value: string = new intl.DateTimeFormat('en-US', { timeZone: 'UTC', year: 'numeric' })
        .format(new Date(winter));
      this.require(value === '2026');
      return [value];
    });
    this.check('permission.boundary', () => {
      const before: string = i18n.System.getSystemLanguage();
      let code: number = 0;
      try { (i18n.System as object as SystemPermissionProbe).setSystemLanguage(before); }
      catch (error) { code = (error as BusinessError).code; }
      const after: string = i18n.System.getSystemLanguage();
      if (!(typeof code === 'number' && (code === 201 || code === 202) && before.length > 0 && before === after)) {
        throw new Error('I18n permission boundary failed: ' +
          JSON.stringify({ code: code, before: before, after: after }));
      }
      return [code.toString(), typeof code, before, after];
    });
    this.check('parameter.type', () => {
      const before: string = i18n.System.getSystemLanguage();
      let code: number = 0;
      try { (i18n.System as object as WrongTypeProbe).setSystemLanguage(123); }
      catch (error) { code = (error as BusinessError).code; }
      const after: string = i18n.System.getSystemLanguage();
      if (!(typeof code === 'number' && code === 401 && before.length > 0 && before === after)) {
        throw new Error('I18n type boundary failed: ' + JSON.stringify({ code: code, before: before, after: after }));
      }
      return [code.toString(), typeof code, before, after];
    });
    this.check('parameter.missing', () => {
      const before: string = i18n.System.getSystemLanguage();
      let code: number = 0;
      try { (i18n.System as object as MissingParameterProbe).setSystemLanguage(); }
      catch (error) { code = (error as BusinessError).code; }
      const after: string = i18n.System.getSystemLanguage();
      if (!(typeof code === 'number' && code === 401 && before.length > 0 && before === after)) {
        throw new Error('I18n missing-argument boundary failed: ' +
          JSON.stringify({ code: code, before: before, after: after }));
      }
      return [code.toString(), typeof code, before, after];
    });
  }
  build() {
    Column({ space: 12 }) {
      Text('QEMU I18n bundled data audit').fontSize(18)
      Text(this.note).fontSize(12)
    }.width('100%').height('100%').justifyContent(FlexAlign.Center)
  }
}
