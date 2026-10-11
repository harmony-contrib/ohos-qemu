// SPDX-License-Identifier: Apache-2.0
// Real app-window density changes; no synthetic callbacks or root policy.
import observer from '@ohos.arkui.observer';
import fs from '@ohos.file.fs';
import window from '@ohos.window';
import { UIContext } from '@ohos.arkui.UIContext';

interface Row {
  runId: string; name: string; listener: string; generation: number; phase: number;
  step: number; target: number; density: number; width: number; height: number;
  instance: boolean; contextMatches: boolean; counts: number[]; error: string;
}

@Entry
@Component
struct Index {
  @State private note: string = 'Real density and layout breakpoint observer';
  private generation: number = 0;
  private phase: number = 0;
  private step: number = 0;
  private target: number = 0;
  private counts: number[] = [0, 0, 0, 0];
  private started: boolean = false;
  private readonly resultPath: string = '/data/storage/el2/base/files/observer-info-__RUN__-results.log';
  private record(name: string, listener: string = '', density: number = 0, width: number = -1,
    height: number = -1, instance: boolean = true, contextMatches: boolean = true, error: string = ''): void {
    const row: Row = { runId: '__RUN__', name, listener, generation: this.generation, phase: this.phase,
      step: this.step, target: this.target, density, width, height, instance, contextMatches,
      counts: this.counts.slice(), error };
    const file = fs.openSync(this.resultPath, fs.OpenMode.CREATE | fs.OpenMode.WRITE_ONLY | fs.OpenMode.APPEND);
    fs.writeSync(file.fd, JSON.stringify(row) + '\n'); fs.closeSync(file);
    this.note = name;
  }
  private density(listener: string, slot: number, info: observer.DensityInfo): void {
    this.counts[slot]++;
    try {
      const context = info.context as UIContext;
      const host = context.getHostContext();
      const ownHost = this.getUIContext().getHostContext();
      const matches = host !== undefined && ownHost !== undefined &&
        host.applicationInfo.name === ownHost.applicationInfo.name && host.filesDir === ownHost.filesDir &&
        Number(context.getRouter().getLength()) === 1;
      this.record('density', listener, info.density, -1, -1,
        info instanceof observer.DensityInfo, matches);
    } catch (error) { this.record('failed', listener, 0, -1, -1, false, false, String(error)); }
  }
  private breakpoint(listener: string, slot: number, info: observer.WindowSizeLayoutBreakpointInfo): void {
    this.counts[slot]++;
    const context = this.getUIContext();
    this.record('breakpoint', listener, 0, info.widthBreakpoint, info.heightBreakpoint,
      info instanceof observer.WindowSizeLayoutBreakpointInfo,
      info.widthBreakpoint === context.getWindowWidthBreakpoint() &&
      info.heightBreakpoint === context.getWindowHeightBreakpoint());
  }
  private delay(ms: number): Promise<void> {
    return new Promise<void>((resolve: () => void) => { setTimeout(resolve, ms); });
  }
  private async change(stage: window.WindowStage): Promise<void> {
    this.target = this.target === 0.5 ? 4 : 0.5;
    this.record('change');
    stage.setCustomDensity(this.target);
    await this.delay(1500);
    const main = stage.getMainWindowSync();
    const context = this.getUIContext();
    this.record('settled', '', main.getWindowDensityInfo().customDensity,
      context.getWindowWidthBreakpoint(), context.getWindowHeightBreakpoint());
  }
  private async run(): Promise<void> {
    const context = this.getUIContext();
    const firstDensity = (info: observer.DensityInfo): void => { this.density('a', 0, info); };
    const secondDensity = (info: observer.DensityInfo): void => { this.density('b', 1, info); };
    const firstBreakpoint = (info: observer.WindowSizeLayoutBreakpointInfo): void => {
      this.breakpoint('a', 2, info);
    };
    const secondBreakpoint = (info: observer.WindowSizeLayoutBreakpointInfo): void => {
      this.breakpoint('b', 3, info);
    };
    const stage = AppStorage.get<window.WindowStage>('qemuObserverInfoStage');
    let completed = false;
    let originalDensity = 0;
    try {
      if (stage === undefined) { throw new Error('real own WindowStage missing'); }
      await this.delay(500);
      const densityA = new observer.DensityInfo(); const densityB = new observer.DensityInfo();
      this.record('density.constructor', '', 0, -1, -1,
        densityA instanceof observer.DensityInfo && densityB instanceof observer.DensityInfo && densityA !== densityB);
      const breakA = new observer.WindowSizeLayoutBreakpointInfo();
      const breakB = new observer.WindowSizeLayoutBreakpointInfo();
      this.record('breakpoint.constructor', '', 0, -1, -1,
        breakA instanceof observer.WindowSizeLayoutBreakpointInfo &&
        breakB instanceof observer.WindowSizeLayoutBreakpointInfo && breakA !== breakB);
      this.target = stage.getMainWindowSync().getWindowDensityInfo().customDensity;
      originalDensity = this.target;
      for (this.generation = 0; this.generation < 2; this.generation++) {
        this.counts = [0, 0, 0, 0]; this.phase = 0; this.step = 0;
        observer.on('densityUpdate', context, firstDensity);
        observer.on('densityUpdate', context, secondDensity);
        context.getUIObserver().on('windowSizeLayoutBreakpointChange', firstBreakpoint);
        context.getUIObserver().on('windowSizeLayoutBreakpointChange', secondBreakpoint);
        this.record('registered');
        await this.change(stage); this.step = 1; await this.change(stage);
        observer.off('densityUpdate', context, firstDensity);
        context.getUIObserver().off('windowSizeLayoutBreakpointChange', firstBreakpoint);
        this.phase = 1; this.step = 2; this.record('first-removed'); await this.change(stage);
        observer.off('densityUpdate', context);
        context.getUIObserver().off('windowSizeLayoutBreakpointChange');
        this.phase = 2; this.step = 3; this.record('all-removed'); await this.change(stage);
      }
      completed = true;
    } catch (error) { this.record('failed', '', 0, -1, -1, false, false, String(error)); }
    finally {
      observer.off('densityUpdate', context);
      context.getUIObserver().off('windowSizeLayoutBreakpointChange');
      if (stage !== undefined && originalDensity > 0) {
        try {
          stage.setCustomDensity(originalDensity);
          await this.delay(1500);
          const own = this.getUIContext();
          this.record('restored', '', stage.getMainWindowSync().getWindowDensityInfo().customDensity,
            own.getWindowWidthBreakpoint(), own.getWindowHeightBreakpoint());
        } catch (error) {
          completed = false; this.record('failed', '', 0, -1, -1, false, false, String(error));
        }
      }
    }
    if (completed) { this.record('summary'); }
  }
  aboutToAppear(): void {
    if (this.started) { return; } this.started = true;
    const file = fs.openSync(this.resultPath, fs.OpenMode.CREATE | fs.OpenMode.WRITE_ONLY | fs.OpenMode.TRUNC);
    fs.closeSync(file); this.run();
  }
  build() { Column() { Text(this.note) }.width('100%').height('100%') }
}
