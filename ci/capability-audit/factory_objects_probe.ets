// SPDX-License-Identifier: Apache-2.0
// Factory-returned SDK classes are exercised as typed values, never fabricated constructors.
import resourceManager from '@ohos.resourceManager';
import taskpool from '@ohos.taskpool';
import fs from '@ohos.file.fs';
import { BusinessError } from '@kit.BasicServicesKit';

interface Result {
  name: string; values: number[]; text: string; tasks: taskpool.TaskInfo[];
  threads: taskpool.ThreadInfo[]; error: string; runId: string;
}

@Concurrent
function transform(seed: number): number {
  // A finite worker-side interval makes live diagnostics observable without
  // blocking the UI/Binder thread or relying on an external keepalive.
  const end: number = Date.now() + 1500;
  let result: number = seed;
  for (let i = 0; i < 256; i++) { result = (result + i) & 0xffff; }
  while (Date.now() < end) { /* bounded by the worker's actual clock */ }
  return result;
}

@Entry
@Component
struct Index {
  @State private note: string = 'Checking real factory-returned values';
  private readonly runId: string = '__FACTORY_RUN_ID__';
  private readonly path: string = '/data/storage/el2/base/files/factory-objects-__FACTORY_RUN_ID__-results.log';
  private failures: number = 0;
  private record(name: string, values: number[] = [], text: string = '',
    tasks: taskpool.TaskInfo[] = [], threads: taskpool.ThreadInfo[] = [], error: string = ''): void {
    const row: Result = { name, values, text, tasks, threads, error, runId: this.runId };
    const file = fs.openSync(this.path, fs.OpenMode.WRITE_ONLY | fs.OpenMode.CREATE | fs.OpenMode.APPEND);
    fs.writeSync(file.fd, JSON.stringify(row) + '\n'); fs.closeSync(file); this.note = name;
  }
  private configuration(name: string, value: resourceManager.Configuration): void {
    this.record(name, [value.direction, value.deviceType, value.screenDensity,
      value.colorMode, value.mcc, value.mnc], value.locale);
  }
  private capability(name: string, value: resourceManager.DeviceCapability): void {
    this.record(name, [value.deviceType, value.screenDensity]);
  }
  private delay(milliseconds: number): Promise<void> {
    return new Promise<void>((resolve) => { setTimeout(resolve, milliseconds); });
  }
  private async resources(): Promise<void> {
    const manager: resourceManager.ResourceManager = getContext(this).resourceManager;
    this.configuration('configuration.sync', manager.getConfigurationSync());
    this.capability('capability.sync', manager.getDeviceCapabilitySync());
    this.configuration('configuration.promise', await manager.getConfiguration());
    this.capability('capability.promise', await manager.getDeviceCapability());
    const configuration: resourceManager.Configuration = await new Promise<resourceManager.Configuration>(
      (resolve, reject) => { manager.getConfiguration((error, value) => {
        if (error) { reject(error); } else { resolve(value); }
      }); });
    this.configuration('configuration.callback', configuration);
    const capability: resourceManager.DeviceCapability = await new Promise<resourceManager.DeviceCapability>(
      (resolve, reject) => { manager.getDeviceCapability((error, value) => {
        if (error) { reject(error); } else { resolve(value); }
      }); });
    this.capability('capability.callback', capability);
    // Returned snapshots must not mutate ResourceManager or the next result.
    const original: resourceManager.Configuration = manager.getConfigurationSync();
    original.locale = 'qemu-factory-isolation'; original.mcc = 987;
    const device: resourceManager.DeviceCapability = manager.getDeviceCapabilitySync();
    device.deviceType = resourceManager.DeviceType.DEVICE_TYPE_CAR;
    this.configuration('configuration.isolation', manager.getConfigurationSync());
    this.capability('capability.isolation', manager.getDeviceCapabilitySync());
  }
  private async generation(generation: number): Promise<void> {
    const seed: number = parseInt(this.runId.substring(0, 4), 16) + generation * 8;
    const tasks: taskpool.Task[] = [];
    const pending: Promise<Object>[] = [];
    for (let i = 0; i < 4; i++) {
      const task: taskpool.Task = new taskpool.Task('factory-' + generation + '-' + i, transform, seed + i);
      tasks.push(task); pending.push(taskpool.execute(task, taskpool.Priority.MEDIUM));
    }
    const ids: number[] = tasks.map((task: taskpool.Task) => task.taskId);
    let snapshot: taskpool.TaskPoolInfo = taskpool.getTaskPoolInfo();
    for (let attempt = 0; attempt < 80; attempt++) {
      if (snapshot.taskInfos.some((task: taskpool.TaskInfo) => ids.includes(task.taskId) &&
          task.state === taskpool.State.RUNNING) &&
          snapshot.threadInfos.some((thread: taskpool.ThreadInfo) =>
            thread.taskIds !== undefined && thread.taskIds.some((id: number) => ids.includes(id)))) { break; }
      await this.delay(10); snapshot = taskpool.getTaskPoolInfo();
    }
    this.record('taskpool.live.' + generation, ids, '', snapshot.taskInfos, snapshot.threadInfos);
    const output: Object[] = await Promise.all(pending);
    this.record('taskpool.complete.' + generation, output.map((value: Object) => value as number));
    // Poll only our IDs: framework-internal tasks cannot manufacture closure.
    let after: taskpool.TaskPoolInfo = taskpool.getTaskPoolInfo();
    for (let attempt = 0; attempt < 80 && after.taskInfos.some((task: taskpool.TaskInfo) =>
      ids.includes(task.taskId)); attempt++) { await this.delay(10); after = taskpool.getTaskPoolInfo(); }
    this.record('taskpool.idle.' + generation, ids, '', after.taskInfos, after.threadInfos);
  }
  private async run(): Promise<void> {
    try { await this.resources(); }
    catch (error) { this.failures++; this.record('resources.failed', [], '', [], [],
      (error as BusinessError).message || 'exception'); }
    for (let generation = 0; generation < 2; generation++) {
      try { await this.generation(generation); }
      catch (error) { this.failures++; this.record('taskpool.failed.' + generation, [], '', [], [],
        (error as BusinessError).message || 'exception'); }
    }
    this.record('summary', [14, this.failures]);
  }
  aboutToAppear(): void {
    const file = fs.openSync(this.path, fs.OpenMode.WRITE_ONLY | fs.OpenMode.CREATE | fs.OpenMode.TRUNC);
    fs.closeSync(file); this.run();
  }
  build() { Column() { Text(this.note) }.width('100%').height('100%') }
}
