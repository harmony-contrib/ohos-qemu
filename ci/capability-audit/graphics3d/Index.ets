// SPDX-License-Identifier: Apache-2.0
import { Scene } from '@kit.ArkGraphics3D';
import { graphics3d } from '../graphics3d/GraphicsController';

@Entry
@Component
struct Index {
  @State private scene: Scene | undefined = undefined;
  aboutToAppear(): void {
    graphics3d.attach((scene: Scene | undefined): void => { this.scene = scene; });
  }
  aboutToDisappear(): void { graphics3d.detach(); }
  build() {
    Column() {
      if (this.scene !== undefined) {
        Component3D({ scene: this.scene, modelType: ModelType.TEXTURE })
          .id('graphics3d-audit-view')
          .width(256).height(256).renderWidth(256).renderHeight(256)
          .backgroundColor('#101820')
      }
    }.width('100%').height('100%').alignItems(HorizontalAlign.Start)
      .justifyContent(FlexAlign.Start).backgroundColor('#101820')
  }
}
