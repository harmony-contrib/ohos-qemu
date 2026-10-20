import common from '@ohos.app.ability.common';
import window from '@ohos.window';
import generation from '@ohos.arkui.intelligence.imageGeneration';
import { BusinessError } from '@ohos.base';
import { Journal } from './Journal';

export class Driver {
  static stage?: window.WindowStage;
  static async execute(action: string, context: common.UIAbilityContext): Promise<void> {
    const id = Journal.requestId;
    if (action === 'identity') { await Journal.identity();
    } else if (action === 'exit') { Journal.record('exit-request'); await context.terminateSelf();
    } else {
      if (!Driver.stage) { throw new Error('actual caller WindowStage required'); }
      const main = await Driver.stage.getMainWindow();
      const ui = main.getUIContext();
      Journal.record('imagegen-request', JSON.stringify({action, windowId: main.getWindowProperties().id}), 0, id, action);
      if (action === 'boundaries') {
        for (const method of ['openGeneratorNodeGraph', 'hideGeneratorNodeGraph', 'restoreGeneratorNodeGraph',
          'closeGeneratorNodeGraph', 'hideGeneratorDialog', 'restoreGeneratorDialog', 'closeGeneratorDialog']) {
          Journal.record('imagegen-boundary-method', JSON.stringify(method), 0, id, action);
          try {
            if (method === 'openGeneratorNodeGraph') { await generation.openGeneratorNodeGraph(ui); }
            else if (method === 'hideGeneratorNodeGraph') { await generation.hideGeneratorNodeGraph(ui); }
            else if (method === 'restoreGeneratorNodeGraph') { await generation.restoreGeneratorNodeGraph(ui); }
            else if (method === 'closeGeneratorNodeGraph') { await generation.closeGeneratorNodeGraph(ui); }
            else if (method === 'hideGeneratorDialog') { await generation.hideGeneratorDialog(ui); }
            else if (method === 'restoreGeneratorDialog') { await generation.restoreGeneratorDialog(ui); }
            else { await generation.closeGeneratorDialog(ui); }
            Journal.record('imagegen-boundary-returned', JSON.stringify(method), 0, id, action);
          } catch (error) { Journal.fail('imagegen-boundary-error', error as BusinessError, id, action); }
        }
      } else if (action === 'graph-open') { await generation.openGeneratorNodeGraph(ui); }
      else if (action === 'graph-hide') { await generation.hideGeneratorNodeGraph(ui); }
      else if (action === 'graph-restore') { await generation.restoreGeneratorNodeGraph(ui); }
      else if (action === 'graph-close') { await generation.closeGeneratorNodeGraph(ui); }
      else if (action === 'dialog-open') {
        // Real framework/provider setup only. Never supply a fake model,
        // generated image, completion callback or host image as AI output.
        const result = await generation.showGeneratorDialog(ui);
        Journal.record('imagegen-dialog-result', JSON.stringify({result, resultType: typeof result}), 0, id, action);
      } else if (action === 'dialog-hide') { await generation.hideGeneratorDialog(ui); }
      else if (action === 'dialog-restore') { await generation.restoreGeneratorDialog(ui); }
      else if (action === 'dialog-close') { await generation.closeGeneratorDialog(ui); }
      else { throw new Error('unknown fixed real ImageGeneration action'); }
      Journal.record('imagegen-resolved', JSON.stringify(action), 0, id, action);
    }
    Journal.record('done', 'null', 0, id, action);
  }
}
