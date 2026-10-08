// SPDX-License-Identifier: Apache-2.0
// Test factory/callback contracts, not namespace constructors or media decoding.
import webview from '@ohos.web.webview';
import fs from '@ohos.file.fs';
import { BusinessError } from '@kit.BasicServicesKit';

webview.WebviewController.customizeSchemes([{ schemeName: 'auditweb', isSupportCORS: true,
  isSupportFetch: true, isStandard: true, isSecure: true }]);

interface Observation {
  name: string; runId: string; text: string; values: number[]; error: string;
}

// An application-side callback observer. This deliberately does NOT impersonate
// an AVPlayer, acknowledge playback, or manufacture any Chromium player state.
class MediaObserver implements webview.NativeMediaPlayerBridge {
  private notify: (name: string, values: number[]) => void;
  constructor(notify: (name: string, values: number[]) => void) { this.notify = notify; }
  updateRect(x: number, y: number, width: number, height: number): void {
    this.notify('rect', [x, y, width, height]);
  }
  play(): void { this.notify('play', []); }
  pause(): void { this.notify('pause', []); }
  seek(time: number): void { this.notify('seek', [time]); }
  setVolume(volume: number): void { this.notify('volume', [volume]); }
  setMuted(muted: boolean): void { this.notify('muted', [Number(muted)]); }
  setPlaybackRate(rate: number): void { this.notify('rate', [rate]); }
  release(): void { this.notify('release', []); }
  enterFullscreen(): void { this.notify('fullscreen.enter', []); }
  exitFullscreen(): void { this.notify('fullscreen.exit', []); }
}

@Entry
@Component
struct Index {
  private readonly runId: string = '__WEB_FACTORY_RUN_ID__';
  private readonly path: string = '/data/storage/el2/base/files/web-factory-__WEB_FACTORY_RUN_ID__-results.log';
  private controller: webview.WebviewController = new webview.WebviewController();
  private scheme: webview.WebSchemeHandler = new webview.WebSchemeHandler();
  private generation: number = 0;
  private finished: boolean = false;
  private failures: number = 0;
  private pageChecking: boolean = false;
  private record(name: string, text: string = '', values: number[] = [], error: string = ''): void {
    const row: Observation = { name, runId: this.runId, text, values, error };
    const file = fs.openSync(this.path, fs.OpenMode.WRITE_ONLY | fs.OpenMode.CREATE | fs.OpenMode.APPEND);
    fs.writeSync(file.fd, JSON.stringify(row) + '\n'); fs.closeSync(file);
  }
  private bytes(text: string): ArrayBuffer {
    const data = new Uint8Array(text.length);
    for (let i = 0; i < text.length; i++) { data[i] = text.charCodeAt(i); }
    return data.buffer;
  }
  private response(handler: webview.WebResourceHandler, text: string, mime: string): void {
    const response = new webview.WebSchemeHandlerResponse();
    // A non-empty response URL requests a redirect in ArkWeb/CEF, even when
    // equal to the request URL. A normal response must leave it unset.
    response.setStatus(200); response.setStatusText('OK');
    response.setMimeType(mime); response.setEncoding('utf-8');
    response.setHeaderByName('Access-Control-Allow-Origin', '*', true);
    response.setHeaderByName('Content-Length', text.length.toString(), true);
    handler.didReceiveResponse(response); handler.didReceiveResponseBody(this.bytes(text)); handler.didFinish();
  }
  private html(generation: number): string {
    const body = this.runId + ':' + generation + ':stream-body';
    return '<!doctype html><html><head><title>pending</title></head><body>' +
      '<video id="native-' + generation + '" preload="metadata" muted style="width:300px;height:120px">' +
      '<source src="auditweb://audit.local/media-' + generation + '.mp4" type="video/mp4"></video>' +
      '<script>document.getElementById("native-' + generation + '").play().catch(()=>{});' +
      'fetch("/echo?generation=' + generation + '",{method:"POST",body:"' + body +
      '",headers:{"Content-Type":"text/plain","X-Audit-Challenge":"' + this.runId +
      '"}}).then(r=>r.text()).then(t=>document.title="OK-"+t).catch(e=>document.title="ERROR-"+e);</script></body></html>';
  }
  private async echo(request: webview.WebSchemeHandlerRequest, handler: webview.WebResourceHandler,
    generation: number): Promise<void> {
    const prefix = 'stream.' + generation;
    try {
      const stream: webview.WebHttpBodyStream | null = request.getHttpBodyStream();
      if (stream === null) { throw new Error('POST did not produce a body stream'); }
      await stream.initialize();
      this.record(prefix + '.initial', '', [stream.getSize(), stream.getPosition(), Number(stream.isChunked()),
        Number(stream.isInMemory()), Number(stream.isEof())]);
      let boundary: number = 0;
      try { await stream.read(-1); }
      catch (error) { boundary = (error as BusinessError).code; }
      this.record(prefix + '.invalid-size', '', [boundary, stream.getPosition()]);
      let text: string = '';
      for (const size of [1, 7, 4096]) {
        const bytes = new Uint8Array(await stream.read(size));
        for (let i = 0; i < bytes.length; i++) { text += String.fromCharCode(bytes[i]); }
        this.record(prefix + '.read.' + size, '', [bytes.length, stream.getPosition(), Number(stream.isEof())]);
      }
      const eof = new Uint8Array(await stream.read(1));
      this.record(prefix + '.complete', text, [stream.getSize(), stream.getPosition(), Number(stream.isEof()), eof.length]);
      this.response(handler, text, 'text/plain');
      this.record('handler.' + generation + '.finish', text);
    } catch (error) {
      this.failures++; this.record(prefix + '.failed', '', [], (error as BusinessError).message || 'exception');
      handler.didFail(-2);
    }
  }
  private setup(): void {
    this.scheme.onRequestStart((request: webview.WebSchemeHandlerRequest,
      handler: webview.WebResourceHandler): boolean => {
      const url: string = request.getRequestUrl();
      if (url.includes('/main?')) {
        this.record('request.' + this.generation + '.main', url,
          [Number(request.isMainFrame()), request.getRequestResourceType(), Number(request.getHttpBodyStream() === null)]);
        this.response(handler, this.html(this.generation), 'text/html'); return true;
      }
      if (url.includes('/echo?')) {
        const header: webview.WebHeader | undefined = request.getHeader().find((value: webview.WebHeader) =>
          value.headerKey.toLowerCase() === 'x-audit-challenge');
        this.record('request.' + this.generation + '.post', request.getRequestMethod() + ':' +
          (header ? header.headerValue : ''), [Number(request.isMainFrame()), request.getRequestResourceType()]);
        this.echo(request, handler, this.generation); return true;
      }
      // The media observer does not decode or claim successful playback.
      // A real Chromium callback must still contain its actual source/surface.
      handler.didFail(-6); return true;
    });
    this.controller.setWebSchemeHandler('auditweb', this.scheme);
    this.controller.onCreateNativeMediaPlayer((_handler: webview.NativeMediaPlayerHandler,
      info: webview.MediaInfo): webview.NativeMediaPlayerBridge => {
      const generation = this.generation;
      const source: webview.MediaSourceInfo = info.mediaSrcList[0];
      const surface: webview.NativeMediaPlayerSurfaceInfo = info.surfaceInfo;
      this.record('media.' + generation + '.source', source.source + '|' + source.format,
        [source.type, info.mediaType, info.mediaSrcList.length]);
      this.record('media.' + generation + '.surface', surface.id,
        [surface.rect.x, surface.rect.y, surface.rect.width, surface.rect.height]);
      return new MediaObserver((name: string, values: number[]) => {
        this.record('media.' + generation + '.' + name, '', values);
      });
    });
    this.record('setup');
    // Install before the Web component performs its initial navigation. A
    // competing loadUrl here would be superseded by the component's src.
    setTimeout(() => { this.checkPage(); }, 250);
  }
  private async checkPage(): Promise<void> {
    if (this.pageChecking || this.finished) { return; }
    this.pageChecking = true;
    try {
      const expected: string = 'OK-' + this.runId + ':' + this.generation + ':stream-body';
      let title: string = '';
      for (let i = 0; i < 100; i++) {
        // This title is produced by the document's own fetch roundtrip. The
        // synchronous getter avoids testing an unrelated runJavaScript API
        // while native-media initialization intentionally awaits a decoder.
        title = this.controller.getTitle();
        if (title === expected || title.includes('ERROR-')) { break; }
        await new Promise<void>((resolve) => { setTimeout(resolve, 50); });
      }
      this.record('page.' + this.generation + '.title', title);
      if (title !== expected) { throw new Error('custom response did not reach the renderer'); }
      if (this.generation === 0) {
        this.generation = 1; this.pageChecking = false;
        this.controller.loadUrl('auditweb://audit.local/main?generation=1');
        setTimeout(() => { this.checkPage(); }, 250);
      } else {
        this.finished = true; this.controller.loadUrl('about:blank');
        setTimeout(() => { this.record('summary', '', [2, this.failures]); }, 1000);
      }
    } catch (error) {
      this.failures++; this.record('page.failed', '', [], (error as BusinessError).message || 'exception');
      this.finished = true; this.record('summary', '', [2, this.failures]);
    }
  }
  aboutToAppear(): void {
    const file = fs.openSync(this.path, fs.OpenMode.WRITE_ONLY | fs.OpenMode.CREATE | fs.OpenMode.TRUNC);
    fs.closeSync(file);
    setTimeout(() => {
      if (!this.finished) {
        this.finished = true; this.failures++;
        this.record('timeout', '', [], 'actual ArkWeb factory sequence timed out');
        this.record('summary', '', [0, this.failures]);
      }
    }, 90000);
  }
  build() {
    Column() {
      Web({ src: 'auditweb://audit.local/main?generation=0', controller: this.controller })
        .width('100%').height('100%')
        .javaScriptAccess(true).mediaPlayGestureAccess(false)
        .enableNativeMediaPlayer({ enable: true, shouldOverlay: false })
        .onControllerAttached(() => { this.setup(); })
        // The observer intentionally does not acknowledge a media decoder's
        // ready state; do not make DOM fetch proof depend on video onload.
        .onPageBegin(() => { setTimeout(() => { this.checkPage(); }, 500); })
        .onPageEnd(() => { this.checkPage(); })
    }.width('100%').height('100%')
  }
}
