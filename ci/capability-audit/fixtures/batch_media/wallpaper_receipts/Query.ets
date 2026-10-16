/* Read-only real PhotoAccessHelper observer. Requests only READ_IMAGEVIDEO.
 * Root signs a separate legitimate query role; importer remains normal/zero.
 * Permission errors are errors, never synthesized empty query results. */
import photoAccessHelper from '@ohos.file.photoAccessHelper';
import predicates from '@ohos.data.dataSharePredicates';
import fs from '@ohos.file.fs';
import util from '@ohos.util';
import abilityAccessCtrl from '@ohos.abilityAccessCtrl';
import { common } from '@kit.AbilityKit';
import { BusinessError } from '@ohos.base';

interface QueryRequest { run_id: string; nonce: string; phase: string; uris: string[]; }
interface QueryEntry { uri: string; count: number; actualUri: string; }

@Entry
@Component
struct Index {
  @State private note: string = 'Wallpaper independent query __WALLPAPER_RUN__';
  @State private busy: boolean = false;
  private readonly run: string = '__WALLPAPER_RUN__';

  private request(): QueryRequest {
    const context = getContext(this) as common.UIAbilityContext;
    const request = JSON.parse(fs.readTextSync(context.filesDir + '/query-request.json')) as QueryRequest;
    if (request.run_id !== this.run || !/^[a-f0-9]{32}$/.test(request.nonce) ||
      !['before', 'after'].includes(request.phase) || request.uris.length !== 5 || new Set(request.uris).size !== 5 ||
      request.uris.some((uri: string) => !/^file:\/\/media\/Photo\/[1-9][0-9]*\//.test(uri))) {
      throw new Error('Invalid fresh query request');
    }
    return request;
  }

  private write(request: QueryRequest, text: string): void {
    const context = getContext(this) as common.UIAbilityContext;
    const path = context.filesDir + '/query-' + this.run + '-' + request.nonce + '.json';
    if (fs.accessSync(path)) { throw new Error('Query result already exists'); }
    // Public API26 FileIO exposes NOFOLLOW, not an exclusive-create mode.
    // This nonce path has one serialized writer inside the app's own sandbox;
    // both coordinator and caller reject a preexisting result.
    const file = fs.openSync(path, fs.OpenMode.CREATE | fs.OpenMode.NOFOLLOW | fs.OpenMode.WRITE_ONLY);
    try {
      const bytes = new util.TextEncoder().encodeInto(text + '\n');
      if (fs.writeSync(file.fd, bytes.buffer) !== bytes.byteLength) { throw new Error('Short query result write'); }
    } finally { fs.closeSync(file); }
  }

  private async permission(): Promise<void> {
    if (this.busy) { return; }
    this.busy = true;
    try {
      const result = await abilityAccessCtrl.createAtManager().requestPermissionsFromUser(
        getContext(this) as common.UIAbilityContext, ['ohos.permission.READ_IMAGEVIDEO']);
      this.note = 'READ_IMAGEVIDEO actual authResults ' + JSON.stringify(result.authResults);
    } catch (error) {
      const actual = error as BusinessError;
      this.note = 'Permission error ' + actual.code + ': ' + actual.message;
    } finally { this.busy = false; }
  }

  private async query(): Promise<void> {
    if (this.busy) { return; }
    this.busy = true;
    let request: QueryRequest | undefined;
    try {
      request = this.request();
      const helper = photoAccessHelper.getPhotoAccessHelper(getContext(this) as common.UIAbilityContext);
      const entries: QueryEntry[] = [];
      const active: string[] = [];
      const began = Date.now();
      for (const uri of request.uris) {
        const filter = new predicates.DataSharePredicates().equalTo(photoAccessHelper.PhotoKeys.URI, uri);
        const result = await helper.getAssets({ predicates: filter, fetchColumns: [] });
        try {
          const count = result.getCount();
          if (count !== 0 && count !== 1) { throw new Error('Nonunique URI query'); }
          let actual: string = '';
          if (count === 1) {
            actual = (await result.getFirstObject()).uri;
            if (actual !== uri) { throw new Error('Query returned another asset'); }
            active.push(actual);
          }
          entries.push({ uri: uri, count: count, actualUri: actual });
        } finally { result.close(); }
      }
      this.write(request, JSON.stringify({ run_id: this.run, nonce: request.nonce, phase: request.phase,
        queried_uris: request.uris, active_uris: active, entries: entries, began_ms: began, ended_ms: Date.now() }));
      this.note = 'Real query complete: ' + active.length;
    } catch (error) {
      const actual = error as BusinessError;
      if (request !== undefined) {
        this.write(request, JSON.stringify({ run_id: this.run, nonce: request.nonce, phase: request.phase,
          error_code: actual.code, error_message: actual.message }));
      }
      this.note = 'Query failed: ' + actual.code + ': ' + actual.message;
    } finally { this.busy = false; }
  }

  build() {
    Column({ space: 20 }) {
      Text(this.note).id('wallpaper_query_status')
      Button('Request actual photo read permission').id('wallpaper_query_permission').enabled(!this.busy)
        .onClick(() => { this.permission(); })
      Button('Query the five exact Photo URIs').id('wallpaper_query_run').enabled(!this.busy)
        .onClick(() => { this.query(); })
    }.width('100%').height('100%').padding(24)
  }
}
