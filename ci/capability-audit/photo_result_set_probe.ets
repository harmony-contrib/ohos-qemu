// Real PhotoAccessHelper.query factory and readonly SQLite/Photos queries.
// No module reflection, fake data provider, DB write, direct callback or permission bypass.
import photoAccessHelper from '@ohos.file.photoAccessHelper';
import fs from '@ohos.file.fs';
import process from '@ohos.process';
import common from '@ohos.app.ability.common';
import { BusinessError } from '@ohos.base';

interface Observation {
  runId: string; role: string; sequence: number; name: string; values: number[]; text: string; error: string;
}

@Entry
@Component
struct Index {
  @State private note: string = 'Real Photo ResultSet';
  private readonly nonce: string = '__RESULT_SET_RUN__';
  private readonly role: string = '__RESULT_SET_ROLE__';
  private readonly path: string = '/data/storage/el2/base/files/photo-result-set-__RESULT_SET_RUN__-results.log';
  private started: boolean = false;
  private sequence: number = 0;

  private record(name: string, values: number[] = [], text: string = '', error: string = ''): void {
    const row: Observation = { runId: this.nonce, role: this.role, sequence: ++this.sequence,
      name: name, values: values, text: text, error: error };
    const file = fs.openSync(this.path, fs.OpenMode.CREATE | fs.OpenMode.WRITE_ONLY | fs.OpenMode.APPEND);
    try { fs.writeSync(file.fd, JSON.stringify(row) + '\n'); } finally { fs.closeSync(file); }
    this.note = name;
  }

  private bounded<T>(pending: Promise<T>): Promise<T> {
    return new Promise<T>((resolve, reject) => {
      const timer: number = setTimeout(() => reject(new Error('Real query deadline exceeded')), 45000);
      pending.then(value => { clearTimeout(timer); resolve(value); })
        .catch((error: BusinessError) => { clearTimeout(timer); reject(error); });
    });
  }

  private requireError(error: BusinessError, code: number): void {
    if (typeof error.code !== 'number' || error.code !== code) {
      throw new Error('Numeric SDK error mismatch: ' + JSON.stringify(error));
    }
  }

  private sql(empty: boolean = false): string {
    const first: string = "SELECT 7 AS n, 1.25 AS r, '" + this.nonce + "' AS t, X'00117fff' AS b, NULL AS z";
    return empty ? first + ' FROM Photos WHERE 0' : first +
      " UNION ALL SELECT 8, 2.5, '" + this.nonce + "', X'00117fff', NULL";
  }

  private values(rs: photoAccessHelper.ResultSet, name: string): void {
    const n: photoAccessHelper.ValueType = rs.getValue(0);
    const r: photoAccessHelper.ValueType = rs.getValue(1);
    const t: photoAccessHelper.ValueType = rs.getValue(2);
    const b: photoAccessHelper.ValueType = rs.getValue(3);
    const z: photoAccessHelper.ValueType = rs.getValue(4);
    if (typeof n !== 'number' || typeof r !== 'number' || typeof t !== 'string' ||
      !(b instanceof Uint8Array) || b.length !== 4 || z !== null) throw new Error('Actual query value type mismatch');
    this.record(name, [n, r, b.length, b[0], b[1], b[2], b[3], z === null ? 1 : 0], t);
  }

  private row(rs: photoAccessHelper.ResultSet, name: string): void {
    const values: photoAccessHelper.ValuesBucket = rs.getRow();
    const b: photoAccessHelper.ValueType = values['b'];
    if (typeof values['n'] !== 'number' || typeof values['r'] !== 'number' ||
      typeof values['t'] !== 'string' || !(b instanceof Uint8Array) ||
      values['z'] !== null || !Object.keys(values).includes('z')) throw new Error('Actual row values/NULL key mismatch');
    this.record(name, [Object.keys(values).length, values['n'] as number, values['r'] as number,
      b.length, b[0], b[1], b[2], b[3], 1], values['t'] as string);
  }

  private indices(rs: photoAccessHelper.ResultSet, columns: boolean, name: string): void {
    const invalid: number[] = [-1, columns ? 5 : 2, 2147483648, 4294967296, 0.5, NaN, Infinity, -Infinity];
    let rejected: number = 0;
    for (const index of invalid) {
      let didThrow: boolean = false;
      try { if (columns) rs.getValue(index); else rs.goToRow(index); }
      catch (error) { this.requireError(error as BusinessError, 23800151); didThrow = true; rejected++; }
      if (!didThrow || !rs.goToRow(0) || rs.getValue(0) !== 7) throw new Error('Index rejection/recovery mismatch');
    }
    this.record(name, [invalid.length, rejected, rs.rowIndex, rs.getValue(0) as number]);
  }

  private async cycle(helper: photoAccessHelper.PhotoAccessHelper, cycle: number): Promise<void> {
    const suffix: string = '.' + cycle.toString();
    const rs: photoAccessHelper.ResultSet = await this.bounded(helper.query(this.sql()));
    try {
      this.record('factory' + suffix, [rs.columnCount, rs.rowCount, rs.rowIndex,
        rs instanceof photoAccessHelper.ResultSet ? 1 : 0]);
      this.record('first' + suffix, [rs.goToFirstRow() ? 1 : 0, rs.rowIndex, rs.isAtLastRow ? 1 : 0]);
      this.values(rs, 'values.first' + suffix); this.row(rs, 'row.first' + suffix);
      const bytes: photoAccessHelper.ValueType = rs.getValue(3);
      if (!(bytes instanceof Uint8Array)) throw new Error('Blob must be Uint8Array');
      bytes[0] = 255;
      const secondRead: photoAccessHelper.ValueType = rs.getValue(3);
      if (!(secondRead instanceof Uint8Array)) throw new Error('Blob reread must be Uint8Array');
      this.record('blob-copy' + suffix, [bytes[0], secondRead[0]]);
      this.record('last' + suffix, [rs.goToRow(1) ? 1 : 0, rs.rowIndex, rs.isAtLastRow ? 1 : 0]);
      this.values(rs, 'values.last' + suffix);
      this.record('past-last' + suffix, [rs.goToNextRow() ? 1 : 0]);
      if (!rs.goToFirstRow()) throw new Error('First-row recovery failed');
      this.indices(rs, true, 'invalid.column' + suffix);
      this.indices(rs, false, 'invalid.row' + suffix);
    } finally { rs.close(); }
    rs.close();
    let closed: boolean = false;
    try { rs.getValue(0); } catch (error) { this.requireError(error as BusinessError, 23800301); closed = true; }
    this.record('closed' + suffix, [2, closed ? 1 : 0]);
    const bare: photoAccessHelper.ResultSet = new photoAccessHelper.ResultSet();
    let bareRejected: boolean = false;
    try { bare.close(); } catch (error) { this.requireError(error as BusinessError, 23800301); bareRejected = true; }
    this.record('bare-close' + suffix, [bareRejected ? 1 : 0]);
    const empty: photoAccessHelper.ResultSet = await this.bounded(helper.query(this.sql(true)));
    try {
      this.record('empty' + suffix, [empty.columnCount, empty.rowCount,
        empty.goToFirstRow() ? 1 : 0, empty.goToNextRow() ? 1 : 0]);
    } finally { empty.close(); }
    let invalid: boolean = false;
    try { const unexpected = await this.bounded(helper.query('SELECT broken_' + this.nonce + ' FROM Photos')); unexpected.close(); }
    catch (error) { this.requireError(error as BusinessError, 23800151); invalid = true; }
    this.record('invalid.sql' + suffix, [invalid ? 1 : 0]);
    const media: photoAccessHelper.ResultSet = await this.bounded(helper.query('SELECT COUNT(*) AS count FROM Photos'));
    try {
      if (!media.goToFirstRow()) throw new Error('Actual Photos count query failed');
      const count: photoAccessHelper.ValueType = media.getValue(0);
      if (typeof count !== 'number' || !Number.isInteger(count) || count < 0) throw new Error('Real Photos count invalid');
      this.record('media-table' + suffix, [count, media.columnCount, media.rowCount]);
    } finally { media.close(); }
    const recovery: photoAccessHelper.ResultSet = await this.bounded(helper.query(this.sql()));
    try { if (!recovery.goToFirstRow()) throw new Error('Query recovery failed'); this.values(recovery, 'recovery' + suffix); }
    finally { recovery.close(); }
  }

  private async run(): Promise<void> {
    let helper: photoAccessHelper.PhotoAccessHelper | undefined = undefined;
    try {
      this.record('identity', [process.uid, process.euid, process.pid]);
      helper = photoAccessHelper.getPhotoAccessHelper(getContext(this) as common.UIAbilityContext);
      for (let cycle: number = 0; cycle < 2; cycle++) {
        if (this.role === 'system') await this.cycle(helper, cycle);
        else {
          let denied: boolean = false;
          try { const unexpected = await this.bounded(helper.query(this.sql())); unexpected.close(); }
          catch (error) { this.requireError(error as BusinessError, this.role === 'normal' ? 202 : 201); denied = true; }
          this.record('denied.' + cycle.toString(), [this.role === 'normal' ? 202 : 201, denied ? 1 : 0]);
        }
      }
      await helper.release(); helper = undefined;
      this.record('released', [1]); this.record('summary', [2]);
    } catch (error) { this.record('unexpected', [], '', JSON.stringify(error)); }
    finally { if (helper !== undefined) await helper.release(); }
  }

  aboutToAppear(): void {
    if (this.started) return;
    this.started = true;
    if (fs.accessSync(this.path)) throw new Error('Fresh ResultSet journal already exists');
    this.run();
  }

  build() { Column() { Text(this.note) }.width('100%').height('100%').justifyContent(FlexAlign.Center) }
}
