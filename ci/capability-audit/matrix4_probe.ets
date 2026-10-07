// SPDX-License-Identifier: Apache-2.0
// Real module-level helpers and existing factory-object arithmetic, no native shim.
import matrix4 from '@ohos.matrix4';
import fs from '@ohos.file.fs';
import { BusinessError } from '@kit.BasicServicesKit';

interface Result { name: string; values: number[]; error: string; runId: string; }
type MissingTranslate = () => matrix4.Matrix4Transit | null;
type ScalarTranslate = (value: number) => matrix4.Matrix4Transit | null;
type ShortPoint = (value: number[]) => number[] | null;

@Entry
@Component
struct Index {
  @State private note: string = 'Checking real Matrix4 helpers';
  private readonly runId: string = '__MATRIX_RUN_ID__';
  private readonly path: string = '/data/storage/el2/base/files/matrix4-__MATRIX_RUN_ID__-results.log';
  private failures: number = 0;
  private record(name: string, values: number[], error: string = ''): void {
    const row: Result = { name: name, values: values, error: error, runId: this.runId };
    const file = fs.openSync(this.path, fs.OpenMode.WRITE_ONLY | fs.OpenMode.CREATE | fs.OpenMode.APPEND);
    fs.writeSync(file.fd, JSON.stringify(row) + '\n');
    fs.closeSync(file);
    this.note = name;
  }
  private check(name: string, action: () => number[]): void {
    try { this.record(name, action()); }
    catch (error) { this.failures++; this.record(name, [], (error as BusinessError).message || 'exception'); }
  }
  private reset(): void {
    // identity()/init() return independent objects; do not pretend they reset
    // the module. Multiplying its actual inverse restores the module in place.
    matrix4.combine(matrix4.copy().invert());
  }
  aboutToAppear(): void {
    const file = fs.openSync(this.path, fs.OpenMode.WRITE_ONLY | fs.OpenMode.CREATE | fs.OpenMode.TRUNC);
    fs.closeSync(file);
    this.check('identity.init', () => {
      const initial = matrix4.identity().transformPoint([3, -2]);
      const translated = matrix4.init([1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 10, -20, 0, 1]);
      return initial.concat(translated.transformPoint([3, -2]), matrix4.transformPoint([3, -2]));
    });
    this.check('root.copy', () => {
      this.reset(); matrix4.translate({ x: 4, y: -5 });
      const copied = matrix4.copy();
      const before = copied.transformPoint([3, -2]);
      copied.scale({ x: 2, y: 3 });
      return before.concat(copied.transformPoint([3, -2]), matrix4.transformPoint([3, -2]));
    });
    this.check('root.invert', () => {
      this.reset(); matrix4.translate({ x: 4, y: -5 });
      const original = matrix4.copy(); matrix4.invert();
      const inverse = matrix4.transformPoint([3, -2]); matrix4.combine(original);
      return inverse.concat(matrix4.transformPoint([3, -2]));
    });
    this.check('root.combine', () => {
      this.reset(); matrix4.translate({ x: 4, y: -5 });
      matrix4.combine(matrix4.identity().scale({ x: 2, y: 3 }));
      return matrix4.transformPoint([3, -2]);
    });
    this.check('root.translate', () => {
      this.reset(); matrix4.translate({ x: 4, y: -5, z: 0 });
      const first = matrix4.transformPoint([3, -2]); matrix4.translate({});
      const second = matrix4.transformPoint([3, -2]); matrix4.translate({ x: 0, y: 0 });
      return first.concat(second, matrix4.transformPoint([3, -2]));
    });
    this.check('root.scale', () => {
      this.reset(); matrix4.scale({ x: 2, y: 3 }); const first = matrix4.transformPoint([3, -2]);
      this.reset(); matrix4.scale({ x: 2, y: 3, centerX: 1, centerY: 2 });
      const center = matrix4.transformPoint([3, -2]);
      this.reset(); matrix4.scale({ x: -1, y: -1 }); const negative = matrix4.transformPoint([3, -2]);
      this.reset(); matrix4.scale({});
      return first.concat(center, negative, matrix4.transformPoint([3, -2]));
    });
    this.check('root.rotate', () => {
      this.reset(); matrix4.rotate({ z: 1, angle: 90 }); const quarter = matrix4.transformPoint([1, 0]);
      this.reset(); matrix4.rotate({ z: 1, angle: 90, centerX: 2, centerY: 3 });
      const center = matrix4.transformPoint([3, 3]);
      this.reset(); matrix4.rotate({ z: 1, angle: 0 }); const zero = matrix4.transformPoint([3, -2]);
      this.reset(); matrix4.rotate({ z: 1, angle: -90 });
      return quarter.concat(center, zero, matrix4.transformPoint([1, 0]));
    });
    this.check('root.transformPoint', () => {
      this.reset(); return matrix4.transformPoint([3, -2]).concat(
        matrix4.transformPoint([0, 0]), matrix4.transformPoint([-8, 11]));
    });
    this.check('root.boundary.missing', () => {
      this.reset(); const call: MissingTranslate = matrix4.translate as MissingTranslate;
      const result = call();
      return [result === null ? 1 : 0].concat(matrix4.transformPoint([3, -2]));
    });
    this.check('root.boundary.type', () => {
      this.reset(); const call: ScalarTranslate = matrix4.translate as ScalarTranslate;
      const result = call(123);
      return [result === null ? 1 : 0].concat(matrix4.transformPoint([3, -2]));
    });
    this.check('root.boundary.point', () => {
      this.reset(); const call: ShortPoint = matrix4.transformPoint as object as ShortPoint;
      const result = call([1]);
      return [result === null ? 1 : 0].concat(matrix4.transformPoint([3, -2]));
    });
    this.check('object.copy', () => {
      const original = matrix4.identity().translate({ x: 4, y: -5 });
      const copied = original.copy(); const before = copied.transformPoint([3, -2]);
      copied.scale({ x: 2, y: 3 });
      return before.concat(copied.transformPoint([3, -2]), original.transformPoint([3, -2]));
    });
    this.check('object.invert', () => {
      const original = matrix4.identity().translate({ x: 4, y: -5 });
      const inverse = original.copy().invert(); const point = inverse.transformPoint([3, -2]);
      inverse.combine(original); return point.concat(inverse.transformPoint([3, -2]));
    });
    this.check('object.combine', () => {
      const original = matrix4.identity().translate({ x: 4, y: -5 });
      original.combine(matrix4.identity().scale({ x: 2, y: 3 })); return original.transformPoint([3, -2]);
    });
    this.check('object.transforms', () => {
      return matrix4.identity().scale({ x: 2, y: 3 }).transformPoint([3, -2]).concat(
        matrix4.identity().translate({ x: 4, y: -5 }).transformPoint([3, -2]),
        matrix4.identity().rotate({ z: 1, angle: 90 }).transformPoint([1, 0]),
        matrix4.identity().scale({ x: 0, y: 0 }).transformPoint([3, -2]),
        matrix4.identity().transformPoint([3, -2]));
    });
    this.check('repeat.isolation', () => {
      let maximum: number = 0;
      for (let i = 0; i < 64; i++) {
        this.reset(); matrix4.translate({ x: i + 1, y: -(i + 2) });
        const original = matrix4.copy(); const transformed = matrix4.transformPoint([3, -2]);
        maximum = Math.max(maximum, Math.abs(transformed[0] - (i + 4)),
          Math.abs(transformed[1] + i + 4));
        matrix4.invert(); matrix4.combine(original); const restored = matrix4.transformPoint([3, -2]);
        maximum = Math.max(maximum, Math.abs(restored[0] - 3), Math.abs(restored[1] + 2));
      }
      return [64, maximum];
    });
    this.record('summary', [16, this.failures]);
  }
  build() { Column() { Text(this.note) }.width('100%').height('100%') }
}
