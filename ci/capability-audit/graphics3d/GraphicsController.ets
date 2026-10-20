// SPDX-License-Identifier: Apache-2.0
// Only real public Scene/Camera/Node calls. No replacement renderer or pixels.
import { Scene, Node as SceneNode, NodeType } from '@kit.ArkGraphics3D';
import fs from '@ohos.file.fs';
import util from '@ohos.util';
import process from '@ohos.process';
import systemDateTime from '@ohos.systemDateTime';
import { BusinessError } from '@ohos.base';

interface Command {
  run_id: string; boot_id: string; operation_id: string; action: string;
  translate_x: number; wait_ms: number;
}
type SceneSink = (scene: Scene | undefined) => void;

class GraphicsController {
  filesDir: string = '';
  private readonly run: string = '__GRAPHICS3D_RUN__';
  private sequence: number = 0;
  private used: string[] = [];
  private pending: Command[] = [];
  private sink: SceneSink | undefined = undefined;
  private serial: Promise<void> = Promise.resolve();
  private ownedScene: Scene | undefined = undefined;
  private group: SceneNode | undefined = undefined;
  private generation: number = 0;

  private now(): number {
    return systemDateTime.getUptime(systemDateTime.TimeType.STARTUP, false);
  }
  private append(c: Command, kind: string, value: string, code: number = 0): void {
    const line = JSON.stringify({ schema: 1, run_id: this.run, boot_id: c.boot_id,
      operation_id: c.operation_id, action: c.action, seq: ++this.sequence,
      monotonic_ms: this.now(), pid: process.pid, uid: process.uid,
      kind: kind, code: code, value_json: value }) + '\n';
    const bytes = new util.TextEncoder().encodeInto(line);
    const file = fs.openSync(this.filesDir + '/graphics3d-' + this.run + '.jsonl',
      fs.OpenMode.CREATE | fs.OpenMode.WRITE_ONLY | fs.OpenMode.APPEND | fs.OpenMode.NOFOLLOW);
    try {
      let done: number = 0;
      while (done < bytes.byteLength) {
        const count = fs.writeSync(file.fd, bytes.slice(done).buffer);
        if (count <= 0 || count > bytes.byteLength - done) { throw new Error('Raw journal short write'); }
        done += count;
      }
    } finally { fs.closeSync(file); }
  }
  accept(text: string): void {
    if (text.length > 4096 || this.filesDir.length === 0) { throw new Error('Bounded original request required'); }
    const c = JSON.parse(text) as Command;
    if (c.run_id !== this.run || !/^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/.test(c.boot_id) ||
      !/^[a-f0-9]{32}$/.test(c.operation_id) || this.used.includes(c.operation_id) || this.used.length >= 32 ||
      !['load', 'translate', 'frame', 'destroy', 'invalid', 'cleanup', 'quiet'].includes(c.action) ||
      !Number.isFinite(c.translate_x) || c.translate_x < 0.55 || c.translate_x > 0.65 ||
      !Number.isInteger(c.wait_ms) || c.wait_ms < 1500 || c.wait_ms > 5000) {
      throw new Error('Invalid fresh original request');
    }
    this.used.push(c.operation_id);
    this.pending.push(c);
    this.drain();
  }
  attach(sink: SceneSink): void {
    if (this.sink !== undefined) { throw new Error('Duplicate view attachment'); }
    this.sink = sink;
    this.drain();
  }
  detach(): void {
    // The original Owner requires explicit cleanup acknowledgement before stop.
    // A premature window death is not silently converted into a release proof.
    this.sink = undefined;
  }
  private drain(): void {
    if (this.sink === undefined) { return; }
    while (this.pending.length > 0) {
      const c = this.pending.shift();
      if (c !== undefined) { this.serial = this.serial.then((): Promise<void> => this.execute(c)); }
    }
  }
  private wait(milliseconds: number): Promise<void> {
    return new Promise<void>((resolve): void => { setTimeout(resolve, milliseconds); });
  }
  private find(root: SceneNode, name: string, depth: number = 0): SceneNode | undefined {
    if (depth > 16 || root.children.count() > 64) { throw new Error('Unexpected asset node bounds'); }
    if (root.name === name) { return root; }
    let found: SceneNode | undefined = undefined;
    for (let index: number = 0; index < root.children.count(); index++) {
      const child = root.children.get(index);
      if (child === null) { throw new Error('Missing actual child'); }
      const candidate = this.find(child, name, depth + 1);
      if (candidate !== undefined) {
        if (found !== undefined) { throw new Error('Duplicate asset node'); }
        found = candidate;
      }
    }
    return found;
  }
  private async load(c: Command): Promise<string> {
    if (this.ownedScene !== undefined || this.sink === undefined) { throw new Error('Release previous scene and attach window first'); }
    const scene = await Scene.load($rawfile('graphics3d-audit.glb'));
    this.ownedScene = scene;
    this.append(c, 'api-return', JSON.stringify({ api: 'Scene.load', asset: 'graphics3d-audit.glb' }));
    const root = scene.root;
    if (root === null) { throw new Error('Loaded scene has no actual root'); }
    const group = this.find(root, 'AuditAsset');
    const red = this.find(root, 'AuditRed');
    const green = this.find(root, 'AuditGreen');
    if (group === undefined || red === undefined || green === undefined ||
      red.nodeType !== NodeType.GEOMETRY || green.nodeType !== NodeType.GEOMETRY) {
      throw new Error('Real loaded mesh nodes missing');
    }
    const camera = await scene.getResourceFactory().createCamera({ name: 'AuditCamera' });
    root.children.append(camera);
    camera.position = { x: 0, y: 0, z: 3 };
    camera.rotation = { x: 0, y: 0, z: 0, w: 1 };
    camera.fov = Math.PI / 3;
    camera.nearPlane = 0.1;
    camera.farPlane = 10;
    camera.clearColor = { r: 16 / 255, g: 24 / 255, b: 32 / 255, a: 1 };
    camera.postProcess = null;
    camera.enabled = true;
    this.group = group;
    this.generation++;
    this.sink(scene);
    return JSON.stringify({ generation: this.generation, root_children: root.children.count(),
      group_name: group.name, red_name: red.name, red_type: red.nodeType,
      green_name: green.name, green_type: green.nodeType,
      camera_name: camera.name, camera_position: camera.position, camera_rotation: camera.rotation,
      camera_enabled: camera.enabled, camera_fov: camera.fov, group_position: group.position });
  }
  private async destroy(c: Command): Promise<void> {
    const scene = this.ownedScene;
    if (this.sink === undefined) { throw new Error('Window detached before explicit release'); }
    this.sink(undefined);
    await this.wait(200);
    if (scene !== undefined) {
      scene.destroy();
      this.append(c, 'api-return', JSON.stringify({ api: 'Scene.destroy', generation: this.generation }));
      this.ownedScene = undefined;
      this.group = undefined;
    }
  }
  private async execute(c: Command): Promise<void> {
    this.append(c, 'begin', JSON.stringify(c));
    try {
      let result: string = 'null';
      switch (c.action) {
        case 'load': result = await this.load(c); break;
        case 'translate': {
          if (this.group === undefined || this.ownedScene === undefined) { throw new Error('No actual loaded group'); }
          this.group.position = { x: c.translate_x, y: 0, z: 0 };
          result = JSON.stringify({ generation: this.generation, position: this.group.position });
          break;
        }
        case 'frame': {
          const scheduled = this.ownedScene?.renderFrame({ alwaysRender: true });
          await this.wait(c.wait_ms);
          result = JSON.stringify({ generation: this.generation, scene_present: this.ownedScene !== undefined,
            scheduled: scheduled === undefined ? null : scheduled });
          break;
        }
        case 'destroy':
          if (this.ownedScene === undefined) { throw new Error('No scene to destroy'); }
          await this.destroy(c); break;
        case 'invalid': {
          if (this.ownedScene !== undefined) { throw new Error('Release scene before invalid load'); }
          let unexpected: Scene | undefined = undefined;
          try {
            unexpected = await Scene.load($rawfile('graphics3d-invalid.glb'));
            this.append(c, 'api-return', JSON.stringify({ api: 'Scene.load', asset: 'graphics3d-invalid.glb' }));
          } catch (error) {
            const e = error as BusinessError;
            this.append(c, 'api-throw', JSON.stringify({ api: 'Scene.load', asset: 'graphics3d-invalid.glb',
              message: typeof e.message === 'string' ? e.message : String(error) }),
              typeof e.code === 'number' ? e.code : -1);
          }
          if (unexpected !== undefined) {
            this.ownedScene = unexpected;
            await this.destroy(c);
          }
          break;
        }
        case 'cleanup': await this.destroy(c); break;
        case 'quiet': await this.wait(c.wait_ms); break;
      }
      this.append(c, 'return', result);
    } catch (error) {
      const e = error as BusinessError;
      this.append(c, 'throw', JSON.stringify({ message: typeof e.message === 'string' ? e.message : String(error) }),
        typeof e.code === 'number' ? e.code : -1);
    }
    this.append(c, 'end', 'null');
  }
}
export const graphics3d: GraphicsController = new GraphicsController();
