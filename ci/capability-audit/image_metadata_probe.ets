// SPDX-License-Identifier: Apache-2.0
// Real typed factory values and the SDK's public metadata constructors.
import image from '@ohos.multimedia.image';
import fs from '@ohos.file.fs';
import { BusinessError } from '@kit.BasicServicesKit';

interface Observation { runId: string; name: string; values: number[]; text: string; error: string; }

@Entry
@Component
struct Index {
  @State private note: string = 'Reading real image metadata';
  private readonly runId: string = '__IMAGE_METADATA_RUN__';
  private readonly path: string = '/data/storage/el2/base/files/image-metadata-__IMAGE_METADATA_RUN__-results.log';
  private failures: number = 0;
  private record(name: string, values: number[] = [], text: string = '', error: string = ''): void {
    const row: Observation = { runId: this.runId, name, values, text, error };
    const file = fs.openSync(this.path, fs.OpenMode.WRITE_ONLY | fs.OpenMode.CREATE | fs.OpenMode.APPEND);
    fs.writeSync(file.fd, JSON.stringify(row) + '\n'); fs.closeSync(file); this.note = name;
  }
  private async source(name: string): Promise<image.ImageSource> {
    const bytes: Uint8Array = await getContext(this).resourceManager.getRawFileContent(name);
    const buffer: ArrayBuffer = bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength);
    return image.createImageSource(buffer);
  }
  private async invalid(source: image.ImageSource, type: image.MetadataType, name: string, index: number): Promise<void> {
    let code: number = 0;
    try { await source.readImageMetadataByType([type], index); }
    catch (error) { code = (error as BusinessError).code; }
    this.record(name, [index, code]);
  }
  private dng(name: string, metadata: image.ImageMetadata): void {
    const value: image.DngMetadata | undefined = metadata.dngMetadata;
    if (value === undefined) { this.record(name, [], '', 'DngMetadata absent'); return; }
    this.record(name, value.dngVersion || [], value.uniqueCameraModel || '');
    this.record(name + '.instance', [value instanceof image.DngMetadata ? 1 : 0]);
  }
  private tiff(name: string, metadata: image.ImageMetadata): void {
    const value: image.TiffMetadata | undefined = metadata.tiffMetadata;
    if (value === undefined) { this.record(name, [], '', 'TiffMetadata absent'); return; }
    this.record(name, [value.compression ?? -1, value.photometricInterpretation ?? -1,
      value.orientation ?? -1, value.xResolution ?? -1, value.yResolution ?? -1,
      value.resolutionUnit ?? -1]);
    this.record(name + '.instance', [value instanceof image.TiffMetadata ? 1 : 0]);
  }
  private async dngTest(): Promise<void> {
    const first: image.DngMetadata = new image.DngMetadata();
    const second: image.DngMetadata = new image.DngMetadata();
    this.record('dng.constructor', [first instanceof image.DngMetadata ? 1 : 0,
      second instanceof image.DngMetadata ? 1 : 0, first !== second ? 1 : 0,
      first.dngVersion === undefined ? 1 : 0, second.uniqueCameraModel === undefined ? 1 : 0]);
    const source: image.ImageSource = await this.source('test_dng_mock.dng');
    try {
      const selected: image.ImageMetadata =
        await source.readImageMetadataByType([image.MetadataType.DNG_METADATA], 0);
      this.dng('dng.selected', selected);
      this.dng('dng.default', await source.readImageMetadataByType());
      await this.invalid(source, image.MetadataType.DNG_METADATA, 'dng.negative', -1);
      this.dng('dng.after-invalid', await source.readImageMetadataByType([image.MetadataType.DNG_METADATA], 0));
      const fresh: image.DngMetadata = new image.DngMetadata();
      this.record('dng.constructor-after-read', [fresh.dngVersion === undefined ? 1 : 0,
        fresh !== selected.dngMetadata ? 1 : 0, first.dngVersion === undefined ? 1 : 0,
        second.uniqueCameraModel === undefined ? 1 : 0]);
    } finally { await source.release(); }
  }
  private async tiffTest(): Promise<void> {
    const first: image.TiffMetadata = new image.TiffMetadata();
    const second: image.TiffMetadata = new image.TiffMetadata();
    this.record('tiff.constructor', [first instanceof image.TiffMetadata ? 1 : 0,
      second instanceof image.TiffMetadata ? 1 : 0, first !== second ? 1 : 0,
      first.compression === undefined ? 1 : 0, second.orientation === undefined ? 1 : 0]);
    const source: image.ImageSource = await this.source('read_test.tiff');
    try {
      const selected: image.ImageMetadata =
        await source.readImageMetadataByType([image.MetadataType.TIFF_METADATA], 0);
      this.tiff('tiff.selected', selected);
      this.tiff('tiff.default', await source.readImageMetadataByType());
      await this.invalid(source, image.MetadataType.TIFF_METADATA, 'tiff.negative', -1);
      await this.invalid(source, image.MetadataType.TIFF_METADATA, 'tiff.end', 1);
      this.tiff('tiff.after-invalid', await source.readImageMetadataByType([image.MetadataType.TIFF_METADATA], 0));
      const fresh: image.TiffMetadata = new image.TiffMetadata();
      this.record('tiff.constructor-after-read', [fresh.compression === undefined ? 1 : 0,
        fresh !== selected.tiffMetadata ? 1 : 0, first.compression === undefined ? 1 : 0,
        second.orientation === undefined ? 1 : 0]);
    } finally { await source.release(); }
  }
  private async avisTest(): Promise<void> {
    const first: image.AvisMetadata = new image.AvisMetadata();
    const second: image.AvisMetadata = new image.AvisMetadata();
    this.record('avis.constructor', [first instanceof image.AvisMetadata ? 1 : 0,
      second instanceof image.AvisMetadata ? 1 : 0, first !== second ? 1 : 0,
      first.delayTime === undefined ? 1 : 0, second.delayTime === undefined ? 1 : 0]);
    const source: image.ImageSource = await this.source('bird_8bit_I420_599x359_fps10.avif');
    try {
      this.record('avis.frames', [await source.getFrameCount()]);
      for (const index of [0, 45, 89]) {
        const metadata: image.ImageMetadata = await source.readImageMetadataByType([image.MetadataType.AVIS_METADATA], index);
        const value: image.AvisMetadata | undefined = metadata.avisMetadata;
        this.record('avis.frame.' + index, [value?.delayTime ?? -1]);
        this.record('avis.instance.' + index, [value instanceof image.AvisMetadata ? 1 : 0]);
      }
      await this.invalid(source, image.MetadataType.AVIS_METADATA, 'avis.negative', -1);
      await this.invalid(source, image.MetadataType.AVIS_METADATA, 'avis.end', 90);
      const metadata: image.ImageMetadata = await source.readImageMetadataByType([image.MetadataType.AVIS_METADATA], 0);
      const value: image.AvisMetadata | undefined = metadata.avisMetadata;
      this.record('avis.after-invalid', [value?.delayTime ?? -1]);
      const fresh: image.AvisMetadata = new image.AvisMetadata();
      this.record('avis.constructor-after-read', [fresh.delayTime === undefined ? 1 : 0,
        fresh !== value ? 1 : 0, first.delayTime === undefined ? 1 : 0,
        second.delayTime === undefined ? 1 : 0]);
    } finally { await source.release(); }
  }
  private async run(): Promise<void> {
    try { await this.dngTest(); } catch (error) {
      this.failures++; this.record('dng.failed', [(error as BusinessError).code], '', (error as BusinessError).message);
    }
    try { await this.tiffTest(); } catch (error) {
      this.failures++; this.record('tiff.failed', [(error as BusinessError).code], '', (error as BusinessError).message);
    }
    try { await this.avisTest(); } catch (error) {
      this.failures++; this.record('avis.failed', [(error as BusinessError).code], '', (error as BusinessError).message);
    }
    this.record('summary', [31, this.failures]);
  }
  aboutToAppear(): void {
    const file = fs.openSync(this.path, fs.OpenMode.WRITE_ONLY | fs.OpenMode.CREATE | fs.OpenMode.TRUNC);
    fs.closeSync(file); this.run();
  }
  build() { Column() { Text(this.note) }.width('100%').height('100%') }
}
