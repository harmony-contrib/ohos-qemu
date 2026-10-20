import fs from '@ohos.file.fs';
import image from '@ohos.multimedia.image';
import crypto from '@ohos.security.cryptoFramework';
import media from '@ohos.multimedia.media';
import { Journal } from './Journal';

export class MediaBytes {
  static async read(uri: string, video: boolean): Promise<void> {
    const file = fs.openSync(uri, fs.OpenMode.READ_ONLY);
    try {
      const size = fs.statSync(file.fd).size;
      if (size <= 0 || size > 33554432) { throw new Error('actual media bytes outside finite capture bound'); }
      const bytes = new Uint8Array(size);
      const count = fs.readSync(file.fd, bytes.buffer);
      if (count !== size) { throw new Error('actual media read was short'); }
      const md = crypto.createMd('SHA256');
      await md.update({data: bytes});
      const digest = await md.digest();
      let hex: string = '';
      for (let i: number = 0; i < digest.data.length; i++) { hex += digest.data[i].toString(16).padStart(2, '0'); }
      const name = 'apps579-media-' + Journal.requestId + '.bin';
      const copy = fs.openSync('/data/storage/el2/base/files/' + name,
        fs.OpenMode.CREATE | fs.OpenMode.WRITE_ONLY | fs.OpenMode.TRUNC);
      try { fs.writeSync(copy.fd, bytes.buffer); } finally { fs.closeSync(copy); }
      Journal.record('media-bytes', JSON.stringify({uri, size, sha256: hex, file: name}));
      if (video) {
        const extractor = await media.createAVMetadataExtractor();
        try {
          extractor.fdSrc = {fd: file.fd, offset: 0, length: size};
          Journal.record('video-metadata', JSON.stringify(await extractor.fetchMetadata()));
        } finally { await extractor.release(); }
      } else {
        const source = image.createImageSource(bytes.buffer);
        try {
          const map = await source.createPixelMap({desiredPixelFormat: image.PixelMapFormat.RGBA_8888});
          try {
            const info = await map.getImageInfo();
            const rgba = new Uint8Array(info.size.width * info.size.height * 4);
            await map.readPixelsToBuffer(rgba.buffer);
            const at = ((Math.floor(info.size.height / 2) * info.size.width) + Math.floor(info.size.width / 2)) * 4;
            Journal.record('image-pixels', JSON.stringify({width: info.size.width, height: info.size.height,
              center: [rgba[at], rgba[at + 1], rgba[at + 2], rgba[at + 3]]}));
          } finally { await map.release(); }
        } finally { await source.release(); }
      }
    } finally { fs.closeSync(file); }
  }
}
