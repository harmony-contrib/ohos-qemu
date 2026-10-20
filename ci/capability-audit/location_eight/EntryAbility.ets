/* Real public calls only. Commands contain no expected result or injected callback. */
import UIAbility from '@ohos.app.ability.UIAbility';
import Want from '@ohos.app.ability.Want';
import window from '@ohos.window';
import geo from '@ohos.geoLocationManager';
import fs from '@ohos.file.fs';
import util from '@ohos.util';
import process from '@ohos.process';
import systemDateTime from '@ohos.systemDateTime';
import { BusinessError, Callback } from '@ohos.base';
import abilityAccessCtrl from '@ohos.abilityAccessCtrl';

interface Command {
  run_id: string; boot_id: string; operation_id: string; action: string;
  identifier: string; latitude: number; longitude: number; radius: number;
  expiration_ms: number; device_ids: string[]; rssi: number; wait_ms: number;
}

export default class EntryAbility extends UIAbility {
  private readonly run: string = '__LOCATION_EIGHT_RUN__';
  private sequence: number = 0;
  private used: string[] = [];
  private serial: Promise<void> = Promise.resolve();
  private fences: string[] = [];
  private tracking: boolean = false;
  private bleA: Callback<geo.BluetoothScanResult> | undefined;
  private bleB: Callback<geo.BluetoothScanResult> | undefined;
  private bleAActive: boolean = false;
  private bleBActive: boolean = false;
  private location: Callback<geo.Location> | undefined;

  private now(): number {
    return systemDateTime.getUptime(systemDateTime.TimeType.STARTUP, false);
  }

  private append(c: Command, kind: string, value: string, code: number = 0): void {
    const text = JSON.stringify({ schema: 1, run_id: this.run, boot_id: c.boot_id,
      operation_id: c.operation_id, action: c.action, seq: ++this.sequence,
      monotonic_ms: this.now(), pid: process.pid, uid: process.uid,
      kind: kind, code: code, value_json: value }) + '\n';
    const bytes = new util.TextEncoder().encodeInto(text);
    const file = fs.openSync(this.context.filesDir + '/location-eight-' + this.run + '.jsonl',
      fs.OpenMode.CREATE | fs.OpenMode.WRITE_ONLY | fs.OpenMode.APPEND | fs.OpenMode.NOFOLLOW);
    try {
      let done: number = 0;
      while (done < bytes.byteLength) {
        const n = fs.writeSync(file.fd, bytes.slice(done).buffer);
        if (n <= 0 || n > bytes.byteLength - done) { throw new Error('Raw journal short write'); }
        done += n;
      }
    } finally { fs.closeSync(file); }
  }

  private accept(want: Want): void {
    const value = want.parameters?.request;
    if (typeof value !== 'string' || value.length > 8192) { throw new Error('Missing bounded request'); }
    const c = JSON.parse(value) as Command;
    if (c.run_id !== this.run || !/^[a-f0-9-]{36}$/.test(c.boot_id) ||
      !/^[a-f0-9]{32}$/.test(c.operation_id) || this.used.includes(c.operation_id) || this.used.length >= 256 ||
      !['context', 'permissions', 'icon', 'supported', 'district', 'district-invalid', 'track-start', 'track-read', 'track-invalid',
        'track-stop', 'fence-add', 'fence-remove', 'fence-invalid', 'ble-start-a', 'ble-start-b',
        'ble-stop-a', 'ble-stop-all', 'quiet', 'cleanup'].includes(c.action)) { throw new Error('Invalid fresh command'); }
    this.used.push(c.operation_id);
    this.serial = this.serial.then((): Promise<void> => this.execute(c));
  }

  private async execute(c: Command): Promise<void> {
    this.append(c, 'begin', JSON.stringify(c));
    try {
      let result: string = 'null';
      switch (c.action) {
        case 'context': {
          const journalStat = fs.statSync(this.context.filesDir + '/location-eight-' + this.run + '.jsonl');
          const token = this.context.applicationInfo.accessTokenId;
          const manager = abilityAccessCtrl.createAtManager();
          result = JSON.stringify({ filesDir: this.context.filesDir, journalIno: journalStat.ino.toString(),
            journalUid: journalStat.uid, tokenId: token,
            permissionStatus: [manager.checkAccessTokenSync(token, 'ohos.permission.APPROXIMATELY_LOCATION'),
              manager.checkAccessTokenSync(token, 'ohos.permission.LOCATION')] });
          break;
        }
        case 'permissions': {
          const grant = await abilityAccessCtrl.createAtManager().requestPermissionsFromUser(this.context,
            ['ohos.permission.APPROXIMATELY_LOCATION', 'ohos.permission.LOCATION']);
          const journalStat = fs.statSync(this.context.filesDir + '/location-eight-' + this.run + '.jsonl');
          result = JSON.stringify({ permissions: grant.permissions, authResults: grant.authResults,
            filesDir: this.context.filesDir, journalIno: journalStat.ino.toString(), journalUid: journalStat.uid });
          break;
        }
        case 'icon': result = JSON.stringify(geo.getLocationIconStatus()); break;
        case 'supported': result = JSON.stringify(geo.isFusionFenceSupported()); break;
        case 'district': result = JSON.stringify(await geo.getCurrentDistrict({ locale: 'en', timeoutMs: 10000 })); break;
        case 'district-invalid': result = JSON.stringify(await geo.getCurrentDistrict({ timeoutMs: 0.5 })); break;
        case 'track-start': {
          if (this.tracking) { throw new Error('Stop previous tracking before start'); }
          this.location = (point: geo.Location): void => {
            this.append(c, 'location', JSON.stringify(point));
          };
          const request: geo.ContinuousLocationRequest = { interval: 1,
            locationScenario: geo.UserActivityScenario.SPORT, sportsType: geo.SportsType.SKIING };
          geo.on('locationChange', request, this.location);
          this.tracking = true;
          break;
        }
        case 'track-read': result = JSON.stringify(await geo.getPostProcessingTrack(geo.SportsType.SKIING)); break;
        case 'track-invalid': result = JSON.stringify(await geo.getPostProcessingTrack(geo.SportsType.WALKING)); break;
        case 'track-stop':
          if (this.location !== undefined) { geo.off('locationChange', this.location); }
          this.tracking = false;
          break;
        case 'fence-add': {
          if (!/^[a-zA-Z0-9_-]{1,64}$/.test(c.identifier) || !Number.isFinite(c.latitude) ||
            !Number.isFinite(c.longitude) || Math.abs(c.latitude) > 90 || Math.abs(c.longitude) > 180 ||
            !Number.isFinite(c.radius) || c.radius <= 0 || c.radius > 100000 ||
            !Number.isFinite(c.expiration_ms) || c.expiration_ms <= 0 || c.expiration_ms > 600000) {
            throw new Error('Measured fence parameters required');
          }
          const request: geo.FusionFenceRequestParams = { identifier: c.identifier,
            scene: geo.FusionFenceScene.SHOP, fenceType: geo.FusionFenceType.GNSS,
            poiLocation: { latitude: c.latitude, longitude: c.longitude },
            monitorTransitionEvents: 3, loiterTimeMs: 0, expirationMs: c.expiration_ms,
            gnssFences: [{ gnssFenceType: geo.GnssFenceType.CIRCULAR,
              circularFence: { latitude: c.latitude, longitude: c.longitude,
                radius: c.radius, expiration: c.expiration_ms } }],
            fenceTransitionCallback: (transition: geo.FusionFenceTransition): void => {
              // Intentionally still journals a native queued callback after remove/expiry.
              this.append(c, 'fence', JSON.stringify(transition));
            } };
          await geo.addFusionFence(request);
          if (!this.fences.includes(c.identifier)) { this.fences.push(c.identifier); }
          break;
        }
        case 'fence-remove':
          await geo.removeFusionFence(c.identifier);
          this.fences = this.fences.filter((id: string): boolean => id !== c.identifier);
          break;
        case 'fence-invalid': await geo.removeFusionFence(''); break;
        case 'ble-start-a': case 'ble-start-b': {
          if ((c.action === 'ble-start-a' && this.bleAActive) ||
            (c.action === 'ble-start-b' && this.bleBActive)) { throw new Error('Stop existing listener before replacement'); }
          if (!Array.isArray(c.device_ids) || c.device_ids.length < 1 || c.device_ids.length > 32 ||
            !c.device_ids.every((id: string): boolean => /^[a-fA-F0-9]{2}(:[a-fA-F0-9]{2}){5}$/.test(id)) ||
            !Number.isInteger(c.rssi) || c.rssi < -127 || c.rssi > 20) { throw new Error('Actual BLE identifiers required'); }
          const callback: Callback<geo.BluetoothScanResult> = (scan: geo.BluetoothScanResult): void => {
            this.append(c, 'ble', JSON.stringify(scan));
          };
          geo.startBluetoothSearch({ deviceIdArray: c.device_ids, rssiThreshold: c.rssi }, callback);
          if (c.action === 'ble-start-a') { this.bleA = callback; this.bleAActive = true; }
          else { this.bleB = callback; this.bleBActive = true; }
          break;
        }
        case 'ble-stop-a':
          if (this.bleA === undefined) { throw new Error('No A callback registered'); }
          geo.stopBluetoothSearch(this.bleA); this.bleAActive = false; break;
        case 'ble-stop-all':
          geo.stopBluetoothSearch(); this.bleAActive = false; this.bleBActive = false; break;
        case 'quiet':
          if (!Number.isInteger(c.wait_ms) || c.wait_ms < 1000 || c.wait_ms > 30000) { throw new Error('Invalid quiet interval'); }
          await new Promise<void>((resolve): void => { setTimeout(resolve, c.wait_ms); }); break;
        case 'cleanup': await this.cleanup(c); break;
      }
      this.append(c, 'return', result);
    } catch (error) {
      const e = error as BusinessError;
      this.append(c, 'throw', JSON.stringify({ message: e.message }), typeof e.code === 'number' ? e.code : -1);
    }
    this.append(c, 'end', 'null');
  }

  private async cleanup(c: Command): Promise<void> {
    let failed: boolean = false;
    // Attempt every owned resource even if an earlier release fails. Failed
    // handles remain owned for a later retry; the original Owner handles death.
    if (this.bleAActive || this.bleBActive) {
      try {
        geo.stopBluetoothSearch(); this.bleAActive = false; this.bleBActive = false;
        this.append(c, 'cleanup-step', JSON.stringify({ api: 'stopBluetoothSearch' }));
      } catch (error) {
        const e = error as BusinessError; failed = true;
        this.append(c, 'cleanup-step', JSON.stringify({ api: 'stopBluetoothSearch' }), e.code || -1);
      }
    }
    if (this.tracking && this.location !== undefined) {
      try {
        geo.off('locationChange', this.location); this.tracking = false;
        this.append(c, 'cleanup-step', JSON.stringify({ api: 'off(locationChange)' }));
      } catch (error) {
        const e = error as BusinessError; failed = true;
        this.append(c, 'cleanup-step', JSON.stringify({ api: 'off(locationChange)' }), e.code || -1);
      }
    }
    for (const id of this.fences.slice()) {
      try {
        await geo.removeFusionFence(id);
        this.fences = this.fences.filter((owned: string): boolean => owned !== id);
        this.append(c, 'cleanup-step', JSON.stringify({ api: 'removeFusionFence', identifier: id }));
      } catch (error) {
        const e = error as BusinessError; failed = true;
        this.append(c, 'cleanup-step', JSON.stringify({ api: 'removeFusionFence', identifier: id }), e.code || -1);
      }
    }
    if (failed) { throw new Error('At least one actual release failed'); }
  }

  onCreate(want: Want): void { this.accept(want); }
  onNewWant(want: Want): void { this.accept(want); }
  onWindowStageCreate(stage: window.WindowStage): void { stage.loadContent('pages/Index'); }
}
