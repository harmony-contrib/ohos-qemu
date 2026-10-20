import common from '@ohos.app.ability.common';
import window from '@ohos.window';
import camera from '@ohos.multimedia.camera';
import cameraPicker from '@ohos.multimedia.cameraPicker';
import { Journal } from './Journal';
import { MediaBytes } from './MediaBytes';

export class Driver {
  static stage?: window.WindowStage;
  static async execute(action: string, context: common.UIAbilityContext): Promise<void> {
    const id = Journal.requestId;
    if (action === 'identity') { await Journal.identity();
    } else if (action === 'read-ungranted') {
      const uri = Journal.payload.uri as string;
      if (!uri.startsWith('file://media/Photo/')) { throw new Error('actual returned Photo URI required'); }
      await MediaBytes.read(uri, Journal.payload.video === true);
      Journal.record('ungranted-uri-read-returned');
    } else if (action === 'probe') {
      Journal.record('capabilities', JSON.stringify({camera: canIUse('SystemCapability.Multimedia.Camera.Core'),
        devices: camera.getCameraManager(context).getSupportedCameras()}));
    } else if (action === 'photo' || action === 'video' || action === 'cancel-photo' || action === 'cancel-video') {
      const video = action.endsWith('video');
      Journal.record('picker-request', JSON.stringify({video}));
      const result = await cameraPicker.pick(context,
        [video ? cameraPicker.PickerMediaType.VIDEO : cameraPicker.PickerMediaType.PHOTO],
        {cameraPosition: camera.CameraPosition.CAMERA_POSITION_BACK, videoDuration: 2});
      Journal.record('picker-result', JSON.stringify(result), 0, id, action);
      if (result.resultCode === 0 && result.resultUri.length > 0) { await MediaBytes.read(result.resultUri, video); }
    } else if (action === 'exit') { Journal.record('exit-request'); await context.terminateSelf();
    } else { throw new Error('unknown fixed camera action'); }
    Journal.record('done', 'null', 0, id, action);
  }
}
