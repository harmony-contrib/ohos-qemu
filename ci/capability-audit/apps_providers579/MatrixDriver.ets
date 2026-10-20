import common from '@ohos.app.ability.common';
import window from '@ohos.window';
import matrix from '@ohos.matrix4';
import { BusinessError } from '@ohos.base';
import { Journal } from './Journal';

type MissingTranslate = () => matrix.Matrix4Transit | null;
type ScalarTranslate = (value: number) => matrix.Matrix4Transit | null;
type ShortPoint = (value: number[]) => number[] | null;

export class Driver {
  static stage?: window.WindowStage;
  static failures: number = 0;
  static reset(): void { matrix.combine(matrix.copy().invert()); }
  static check(name: string, action: () => number[]): void {
    try { Journal.record('matrix-case', JSON.stringify({name, values: action()})); }
    catch (error) { Driver.failures++; Journal.record('matrix-case-name', JSON.stringify(name));
      Journal.fail('matrix-case-error', error as BusinessError); }
  }
  static async execute(action: string, context: common.UIAbilityContext): Promise<void> {
    const id = Journal.requestId;
    if (action === 'identity') { await Journal.identity();
    } else if (action === 'matrix-modern') {
      const t = matrix.identity().translate({x: 5, y: -6});
      Journal.record('matrix-values', JSON.stringify({point: [2, 3], copy: matrix.identity().copy().transformPoint([2, 3]),
        translate: t.copy().transformPoint([2, 3]), invert: t.copy().invert().transformPoint([2, 3]),
        combine: t.copy().combine(t.copy().invert()).transformPoint([2, 3]),
        scale: matrix.identity().scale({x: 2, y: 3}).transformPoint([2, 3]),
        rotate: matrix.identity().rotate({z: 1, angle: 90}).transformPoint([2, 3]),
        transformPoint: matrix.identity().transformPoint([2, 3])}));
    } else if (action === 'matrix-legacy') {
      Driver.failures = 0;
    Driver.check('identity.init', () => {
      const initial = matrix.identity().transformPoint([3, -2]);
      const translated = matrix.init([1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 10, -20, 0, 1]);
      return initial.concat(translated.transformPoint([3, -2]), matrix.transformPoint([3, -2]));
    });
    Driver.check('root.copy', () => {
      Driver.reset(); matrix.translate({ x: 4, y: -5 });
      const copied = matrix.copy();
      const before = copied.transformPoint([3, -2]);
      copied.scale({ x: 2, y: 3 });
      return before.concat(copied.transformPoint([3, -2]), matrix.transformPoint([3, -2]));
    });
    Driver.check('root.invert', () => {
      Driver.reset(); matrix.translate({ x: 4, y: -5 });
      const original = matrix.copy(); matrix.invert();
      const inverse = matrix.transformPoint([3, -2]); matrix.combine(original);
      return inverse.concat(matrix.transformPoint([3, -2]));
    });
    Driver.check('root.combine', () => {
      Driver.reset(); matrix.translate({ x: 4, y: -5 });
      matrix.combine(matrix.identity().scale({ x: 2, y: 3 }));
      return matrix.transformPoint([3, -2]);
    });
    Driver.check('root.translate', () => {
      Driver.reset(); matrix.translate({ x: 4, y: -5, z: 0 });
      const first = matrix.transformPoint([3, -2]); matrix.translate({});
      const second = matrix.transformPoint([3, -2]); matrix.translate({ x: 0, y: 0 });
      return first.concat(second, matrix.transformPoint([3, -2]));
    });
    Driver.check('root.scale', () => {
      Driver.reset(); matrix.scale({ x: 2, y: 3 }); const first = matrix.transformPoint([3, -2]);
      Driver.reset(); matrix.scale({ x: 2, y: 3, centerX: 1, centerY: 2 });
      const center = matrix.transformPoint([3, -2]);
      Driver.reset(); matrix.scale({ x: -1, y: -1 }); const negative = matrix.transformPoint([3, -2]);
      Driver.reset(); matrix.scale({});
      return first.concat(center, negative, matrix.transformPoint([3, -2]));
    });
    Driver.check('root.rotate', () => {
      Driver.reset(); matrix.rotate({ z: 1, angle: 90 }); const quarter = matrix.transformPoint([1, 0]);
      Driver.reset(); matrix.rotate({ z: 1, angle: 90, centerX: 2, centerY: 3 });
      const center = matrix.transformPoint([3, 3]);
      Driver.reset(); matrix.rotate({ z: 1, angle: 0 }); const zero = matrix.transformPoint([3, -2]);
      Driver.reset(); matrix.rotate({ z: 1, angle: -90 });
      return quarter.concat(center, zero, matrix.transformPoint([1, 0]));
    });
    Driver.check('root.transformPoint', () => {
      Driver.reset(); return matrix.transformPoint([3, -2]).concat(
        matrix.transformPoint([0, 0]), matrix.transformPoint([-8, 11]));
    });
    Driver.check('root.boundary.missing', () => {
      Driver.reset(); const call: MissingTranslate = matrix.translate as MissingTranslate;
      const result = call();
      return [result === null ? 1 : 0].concat(matrix.transformPoint([3, -2]));
    });
    Driver.check('root.boundary.type', () => {
      Driver.reset(); const call: ScalarTranslate = matrix.translate as ScalarTranslate;
      const result = call(123);
      return [result === null ? 1 : 0].concat(matrix.transformPoint([3, -2]));
    });
    Driver.check('root.boundary.point', () => {
      Driver.reset(); const call: ShortPoint = matrix.transformPoint as object as ShortPoint;
      const result = call([1]);
      return [result === null ? 1 : 0].concat(matrix.transformPoint([3, -2]));
    });
    Driver.check('object.copy', () => {
      const original = matrix.identity().translate({ x: 4, y: -5 });
      const copied = original.copy(); const before = copied.transformPoint([3, -2]);
      copied.scale({ x: 2, y: 3 });
      return before.concat(copied.transformPoint([3, -2]), original.transformPoint([3, -2]));
    });
    Driver.check('object.invert', () => {
      const original = matrix.identity().translate({ x: 4, y: -5 });
      const inverse = original.copy().invert(); const point = inverse.transformPoint([3, -2]);
      inverse.combine(original); return point.concat(inverse.transformPoint([3, -2]));
    });
    Driver.check('object.combine', () => {
      const original = matrix.identity().translate({ x: 4, y: -5 });
      original.combine(matrix.identity().scale({ x: 2, y: 3 })); return original.transformPoint([3, -2]);
    });
    Driver.check('object.transforms', () => {
      return matrix.identity().scale({ x: 2, y: 3 }).transformPoint([3, -2]).concat(
        matrix.identity().translate({ x: 4, y: -5 }).transformPoint([3, -2]),
        matrix.identity().rotate({ z: 1, angle: 90 }).transformPoint([1, 0]),
        matrix.identity().scale({ x: 0, y: 0 }).transformPoint([3, -2]),
        matrix.identity().transformPoint([3, -2]));
    });
    Driver.check('repeat.isolation', () => {
      let maximum: number = 0;
      for (let i = 0; i < 64; i++) {
        Driver.reset(); matrix.translate({ x: i + 1, y: -(i + 2) });
        const original = matrix.copy(); const transformed = matrix.transformPoint([3, -2]);
        maximum = Math.max(maximum, Math.abs(transformed[0] - (i + 4)),
          Math.abs(transformed[1] + i + 4));
        matrix.invert(); matrix.combine(original); const restored = matrix.transformPoint([3, -2]);
        maximum = Math.max(maximum, Math.abs(restored[0] - 3), Math.abs(restored[1] + 2));
      }
      return [64, maximum];
    });
      Journal.record('matrix-summary', JSON.stringify({count: 16, failures: Driver.failures}));
    } else if (action === 'exit') { Journal.record('exit-request'); await context.terminateSelf();
    } else { throw new Error('unknown fixed matrix action'); }
    Journal.record('done', 'null', 0, id, action);
  }
}
