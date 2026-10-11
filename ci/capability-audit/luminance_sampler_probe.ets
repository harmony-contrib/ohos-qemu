// Public SDK factory contract, not a synthetic exported constructor.
import { LuminanceSampler } from '@ohos.arkui.UIContext';
import fs from '@ohos.file.fs';
import process from '@ohos.process';
import { BusinessError } from '@ohos.base';

interface SampleRow { runId: string; name: string; values: number[]; error: string; }

@Entry
@Component
struct Index {
  @State private color: string = '#000000';
  @State private note: string = 'Luminance factory regression';
  private running: boolean = false;
  private readonly runId: string = '__LUMINANCE_RUN__';
  private readonly path: string = '/data/storage/el2/base/files/luminance-__LUMINANCE_RUN__-results.log';
  private samples: number[] = [];
  private phase: string = 'idle';

  private record(name: string, values: number[], error: string = ''): void {
    const row: SampleRow = { runId: this.runId, name, values, error };
    const file = fs.openSync(this.path, fs.OpenMode.CREATE | fs.OpenMode.WRITE_ONLY | fs.OpenMode.APPEND);
    try { fs.writeSync(file.fd, JSON.stringify(row) + '\n'); } finally { fs.closeSync(file); }
    this.note = name;
  }

  private pause(ms: number): Promise<void> {
    return new Promise<void>((resolve) => { setTimeout(() => { resolve(); }, ms); });
  }

  private async expectSample(bright: boolean, begin: number): Promise<void> {
    for (let attempt = 0; attempt < 100; attempt++) {
      for (let index = begin; index < this.samples.length; index++) {
        const value = this.samples[index];
        if (bright ? value >= 215 && value <= 255 : value >= 0 && value <= 40) { return; }
      }
      await this.pause(100);
    }
    throw new Error('actual RS luminance callback did not match rendered background');
  }

  private async run(): Promise<void> {
    if (this.running) { return; }
    this.running = true;
    let sampler: LuminanceSampler | undefined = undefined;
    let complete = false;
    let boundariesOk = true;
    const file = fs.openSync(this.path, fs.OpenMode.CREATE | fs.OpenMode.WRITE_ONLY | fs.OpenMode.TRUNC);
    fs.closeSync(file);
    try {
      this.record('identity', [process.uid, process.euid, process.pid]);
      const context = this.getUIContext();
      sampler = context.getLuminanceSampler({ id: 'luminance-target' });
      this.record('factory', [sampler === undefined ? 0 : 1,
        context.getLuminanceSampler({ id: 'luminance-target' }) === sampler ? 1 : 0,
        context.getLuminanceSampler({ id: 'missing-' + this.runId }) === undefined ? 1 : 0]);
      if (sampler === undefined) { throw new Error('actual attached target factory failed'); }
      for (const invalid of [256, -1]) {
        let code: number = 0;
        let numeric: number = 0;
        try { sampler.setBackgroundLuminanceSamplingConfigs({ brightThreshold: invalid }); }
        catch (error) {
          code = (error as BusinessError).code;
          numeric = typeof code === 'number' ? 1 : 0;
        }
        this.record('invalid.bright.' + invalid.toString(), [code, numeric]);
        // Preserve the failed boundary observation but still exercise the
        // independent real rendering path in this batch. Never turn it green.
        if (code !== 100001 || numeric !== 1) { boundariesOk = false; }
      }
      sampler.setBackgroundLuminanceSamplingConfigs({ samplingInterval: 180, darkThreshold: 50, brightThreshold: 200 });
      for (let cycle = 0; cycle < 2; cycle++) {
        this.samples = [];
        this.phase = 'dark.' + cycle.toString();
        this.color = '#000000';
        const listener = (value: number): void => {
          this.samples.push(value);
          this.record('sample.' + this.phase, [value, typeof value === 'number' ? 1 : 0]);
        };
        sampler.onBackgroundLuminanceChange(listener);
        await this.expectSample(false, 0);
        this.record('dark.' + cycle.toString(), [this.samples.length]);
        const begin = this.samples.length;
        this.phase = 'bright.' + cycle.toString();
        this.color = '#ffffff';
        await this.expectSample(true, begin);
        this.record('bright.' + cycle.toString(), [this.samples.length]);
        sampler.offBackgroundLuminanceChange(listener);
        const stopped = this.samples.length;
        this.phase = 'off.' + cycle.toString();
        this.color = '#000000';
        await this.pause(1500);
        this.record('off.' + cycle.toString(), [stopped, this.samples.length]);
        if (stopped !== this.samples.length) { throw new Error('removed callback still delivered'); }
        sampler.offBackgroundLuminanceChange();
      }
      complete = boundariesOk;
    } catch (error) {
      this.record('failed', [], (error as Error).message || 'luminance failure');
    } finally {
      if (sampler !== undefined) {
        try { sampler.offBackgroundLuminanceChange(); this.record('cleanup', [1]); }
        catch (error) { complete = false; this.record('cleanup.failed', [], (error as Error).message); }
      }
      this.color = '#000000';
      this.record('summary', [complete ? 1 : 0]);
    }
  }

  build() {
    Column({ space: 12 }) {
      Text(this.note)
      Button('Run').id('luminance-run').onClick(() => { this.run(); })
      Stack() {
        Column().width(300).height(300).backgroundColor(this.color)
        Column().id('luminance-target').width(200).height(200).backgroundColor('#00000000')
      }.width(300).height(300)
    }.width('100%').height('100%').backgroundColor('#808080')
  }
}
