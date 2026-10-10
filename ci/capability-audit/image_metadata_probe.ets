// SPDX-License-Identifier: Apache-2.0
// Public typed factory results, never invented metadata constructors.
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
  }
  private tiff(name: string, metadata: image.ImageMetadata): void {
    const value: image.TiffMetadata | undefined = metadata.tiffMetadata;
    if (value === undefined) { this.record(name, [], '', 'TiffMetadata absent'); return; }
    this.record(name, [value.compression ?? -1, value.photometricInterpretation ?? -1,
      value.orientation ?? -1, value.xResolution ?? -1, value.yResolution ?? -1,
      value.resolutionUnit ?? -1]);
  }
  private async dngTest(): Promise<void> {
    const source: image.ImageSource = await this.source('test_dng_mock.dng');
    try {
      this.dng('dng.selected', await source.readImageMetadataByType([image.MetadataType.DNG_METADATA], 0));
      this.dng('dng.default', await source.readImageMetadataByType());
      await this.invalid(source, image.MetadataType.DNG_METADATA, 'dng.negative', -1);
      this.dng('dng.after-invalid', await source.readImageMetadataByType([image.MetadataType.DNG_METADATA], 0));
    } finally { await source.release(); }
  }
  private async tiffTest(): Promise<void> {
    const source: image.ImageSource = await this.source('read_test.tiff');
    try {
      this.tiff('tiff.selected', await source.readImageMetadataByType([image.MetadataType.TIFF_METADATA], 0));
      this.tiff('tiff.default', await source.readImageMetadataByType());
      await this.invalid(source, image.MetadataType.TIFF_METADATA, 'tiff.negative', -1);
      await this.invalid(source, image.MetadataType.TIFF_METADATA, 'tiff.end', 1);
      this.tiff('tiff.after-invalid', await source.readImageMetadataByType([image.MetadataType.TIFF_METADATA], 0));
    } finally { await source.release(); }
  }
  private async avisTest(): Promise<void> {
    const source: image.ImageSource = await this.source('bird_8bit_I420_599x359_fps10.avif');
    try {
      this.record('avis.frames', [await source.getFrameCount()]);
      for (const index of [0, 45, 89]) {
        const metadata: image.ImageMetadata = await source.readImageMetadataByType([image.MetadataType.AVIS_METADATA], index);
        const value: image.AvisMetadata | undefined = metadata.avisMetadata;
        this.record('avis.frame.' + index, [value?.delayTime ?? -1]);
      }
      await this.invalid(source, image.MetadataType.AVIS_METADATA, 'avis.negative', -1);
      await this.invalid(source, image.MetadataType.AVIS_METADATA, 'avis.end', 90);
      const metadata: image.ImageMetadata = await source.readImageMetadataByType([image.MetadataType.AVIS_METADATA], 0);
      const value: image.AvisMetadata | undefined = metadata.avisMetadata;
      this.record('avis.after-invalid', [value?.delayTime ?? -1]);
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
    this.record('summary', [16, this.failures]);
  }
  aboutToAppear(): void {
    const file = fs.openSync(this.path, fs.OpenMode.WRITE_ONLY | fs.OpenMode.CREATE | fs.OpenMode.TRUNC);
    fs.closeSync(file); this.run();
  }
  build() { Column() { Text(this.note) }.width('100%').height('100%') }
}
