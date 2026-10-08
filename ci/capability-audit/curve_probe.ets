// Actual preset factories and interpolation, never a substitute native curve.
import curves from '@ohos.curves';
import fs from '@ohos.file.fs';
import probe from 'libruntimeenumprobe.so';
import { BusinessError } from '@kit.BasicServicesKit';

interface NativeEnum {
  values: (number | string)[]; statuses: number[]; types: number[]; own: boolean[]; exception: boolean;
}
interface Spec { name: string; curve: curves.Curve; points: number[]; }
interface Result {
  runId: string; name: string; typed: (number | string)[]; native: NativeEnum | null;
  values: number[]; reference: number[]; isolated: boolean; repeats: number; repeatError: number; error: string;
}
@Entry
@Component
struct Index {
  @State private note: string = 'Checking real Curve members and interpolation';
  private readonly runId: string = '__CURVE_RUN_ID__';
  private readonly path: string = '/data/storage/el2/base/files/curve-__CURVE_RUN_ID__-results.log';
  private failures: number = 0;
  private record(name: string, typed: (number | string)[] = [], native: NativeEnum | null = null,
    values: number[] = [], reference: number[] = [], isolated: boolean = false,
    repeats: number = 0, repeatError: number = 0, error: string = ''): void {
    const row: Result = { runId: this.runId, name, typed, native, values, reference,
      isolated, repeats, repeatError, error };
    const file = fs.openSync(this.path, fs.OpenMode.WRITE_ONLY | fs.OpenMode.CREATE | fs.OpenMode.APPEND);
    fs.writeSync(file.fd, JSON.stringify(row) + '\n'); fs.closeSync(file); this.note = name;
  }
  aboutToAppear(): void {
    const file = fs.openSync(this.path, fs.OpenMode.WRITE_ONLY | fs.OpenMode.CREATE | fs.OpenMode.TRUNC);
    fs.closeSync(file);
    let specs: Spec[] = [];
    try {
      specs = [
        { name: 'Linear', curve: curves.Curve.Linear, points: [] },
        { name: 'Ease', curve: curves.Curve.Ease, points: [0.25, 0.1, 0.25, 1] },
        { name: 'EaseIn', curve: curves.Curve.EaseIn, points: [0.42, 0, 1, 1] },
        { name: 'EaseOut', curve: curves.Curve.EaseOut, points: [0, 0, 0.58, 1] },
        { name: 'EaseInOut', curve: curves.Curve.EaseInOut, points: [0.42, 0, 0.58, 1] },
        { name: 'FastOutSlowIn', curve: curves.Curve.FastOutSlowIn, points: [0.4, 0, 0.2, 1] },
        { name: 'LinearOutSlowIn', curve: curves.Curve.LinearOutSlowIn, points: [0, 0, 0.2, 1] },
        { name: 'FastOutLinearIn', curve: curves.Curve.FastOutLinearIn, points: [0.4, 0, 1, 1] },
        { name: 'ExtremeDeceleration', curve: curves.Curve.ExtremeDeceleration, points: [0, 0, 0, 1] },
        { name: 'Sharp', curve: curves.Curve.Sharp, points: [0.33, 0, 0.67, 1] },
        { name: 'Rhythm', curve: curves.Curve.Rhythm, points: [0.7, 0, 0.2, 1] },
        { name: 'Smooth', curve: curves.Curve.Smooth, points: [0.4, 0, 0.4, 1] },
        { name: 'Friction', curve: curves.Curve.Friction, points: [0.2, 0, 0.2, 1] }
      ];
      this.record('members', specs.map((item: Spec) => item.curve),
        probe.inspect('@ohos.curves', 'Curve', specs.map((item: Spec) => item.name)));
    } catch (error) {
      this.failures++; this.record('members.failed', [], null, [], [], false, 0, 0,
        (error as BusinessError).message || 'exception');
    }
    const times: number[] = [-1, 0, 0.125, 0.25, 0.5, 0.75, 1, 2];
    for (let generation = 0; generation < 2; generation++) {
      for (const spec of specs) {
        try {
          const initial: curves.ICurve = curves.initCurve(spec.curve);
          const separate: curves.ICurve = curves.initCurve(spec.curve);
          const reference: curves.ICurve = spec.points.length === 0 ?
            curves.customCurve((fraction: number) => fraction) :
            curves.cubicBezierCurve(spec.points[0], spec.points[1], spec.points[2], spec.points[3]);
          const values: number[] = times.map((time: number) => initial.interpolate(time));
          const wanted: number[] = times.map((time: number) => reference.interpolate(time));
          let maxError: number = 0;
          let isolated: boolean = initial !== separate && initial !== reference && separate !== reference;
          for (let repeat = 0; repeat < 32; repeat++) {
            const fresh: curves.ICurve = curves.initCurve(spec.curve);
            isolated = isolated && fresh !== initial && fresh !== separate;
            for (let index = 0; index < times.length; index++) {
              maxError = Math.max(maxError, Math.abs(fresh.interpolate(times[index]) - values[index]),
                Math.abs(separate.interpolate(times[index]) - values[index]),
                Math.abs(initial.interpolate(times[index]) - values[index]));
            }
          }
          this.record('generation.' + generation + '.' + spec.name, [], null,
            values, wanted, isolated, 32, maxError);
        } catch (error) {
          this.failures++; this.record('generation.' + generation + '.' + spec.name + '.failed',
            [], null, [], [], false, 0, 0, (error as BusinessError).message || 'exception');
        }
      }
    }
    this.record('summary', [], null, [26, this.failures]);
  }
  build() { Column() { Text(this.note) }.width('100%').height('100%') }
}
