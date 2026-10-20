import common from '@ohos.app.ability.common';
import window from '@ohos.window';
import PiPWindow from '@ohos.PiPWindow';
import floatingBall from '@ohos.window.floatingBall';
import floatView from '@ohos.window.floatView';
import { BusinessError } from '@ohos.base';
import { Journal, RUN } from './Journal';

export class Driver {
  static stage?: window.WindowStage;
  static child?: window.Window;
  static main?: window.Window;
  static originalLimits?: window.WindowLimits;
  static xController: XComponentController = new XComponentController();
  static pip?: PiPWindow.PiPController;
  static ball?: floatingBall.FloatingBallController;
  static view?: floatView.FloatViewController;
  static pipId: string = 'lifecycle';
  static pipAction: string = 'lifecycle';
  static ballId: string = 'lifecycle';
  static ballAction: string = 'lifecycle';
  static viewId: string = 'lifecycle';
  static viewAction: string = 'lifecycle';

  static async userCancelBall(): Promise<void> {
    if (!Driver.ball) { throw new Error('actual floating ball controller missing'); }
    Journal.record('ball-user-cancel', 0, 'null', Driver.ballId, Driver.ballAction);
    await Driver.ball.stopFloatingBall();
  }

  static async execute(action: string, context: common.UIAbilityContext): Promise<void> {
    const id = Journal.requestId;
    if (!Driver.stage) { throw new Error('actual WindowStage missing'); }
    Driver.main = await Driver.stage.getMainWindow();
    if (action === 'identity') { await Journal.identity();
    } else if (action === 'probe') {
      Journal.record('capabilities', 0, JSON.stringify({
        session: canIUse('SystemCapability.Window.SessionManager'),
        pip: PiPWindow.isPiPEnabled(), ball: floatingBall.isFloatingBallEnabled(),
        view: floatView.isFloatViewEnabled(), main: Driver.main.getWindowProperties()}));
    } else if (action === 'window-create') {
      Driver.child = await Driver.stage.createSubWindow('s578_' + RUN.substring(0, 8));
      Driver.child.on('windowEvent', (event: window.WindowEventType) => {
        Journal.record('window-event', 0, event.toString());
      });
      await Driver.child.setUIContent('pages/Child');
      await Driver.child.resize(320, 240);
      await Driver.child.moveWindowTo(64, 96);
      await Driver.child.showWindow();
      Journal.record('window-created', 0, JSON.stringify(Driver.child.getWindowProperties()));
    } else if (action === 'window-properties') {
      if (!Driver.child) { throw new Error('window missing'); }
      Journal.record('window-properties', 0, JSON.stringify(Driver.child.getWindowProperties()));
    } else if (action === 'window-update') {
      if (!Driver.child) { throw new Error('window missing'); }
      await Driver.child.resize(400, 260);
      await Driver.child.moveWindowTo(96, 128);
      Driver.originalLimits = Driver.main.getWindowLimits();
      const applied = await Driver.main.setWindowLimits({minWidth: 200, minHeight: 160,
        maxWidth: 1200, maxHeight: 900});
      Journal.record('limits', 0, JSON.stringify({before: Driver.originalLimits, applied,
        readback: Driver.main.getWindowLimits()}));
      Journal.record('window-updated', 0, JSON.stringify(Driver.child.getWindowProperties()));
    } else if (action === 'window-hide' || action === 'window-show') {
      if (!Driver.child) { throw new Error('window missing'); }
      if (action === 'window-hide') { await Driver.child.hideWindow(); }
      else { await Driver.child.showWindow(); }
      Journal.record(action, 0, JSON.stringify(Driver.child.getWindowProperties()));
    } else if (action === 'window-destroy') {
      if (!Driver.child) { throw new Error('window missing'); }
      const props = Driver.child.getWindowProperties();
      await Driver.child.destroyWindow();
      Journal.record('window-destroyed', 0, JSON.stringify(props));
      try {
        Journal.record('destroyed-handle-returned', 0, JSON.stringify(Driver.child.getWindowProperties()));
      } catch (error) { Journal.fail('destroyed-handle', error as BusinessError); }
      Driver.child = undefined;
      if (Driver.originalLimits) {
        await Driver.main.setWindowLimits(Driver.originalLimits);
        Journal.record('limits-restored', 0, JSON.stringify(Driver.main.getWindowLimits()));
      }
    } else if (action === 'invalid-window') {
      const applied = await Driver.main.setWindowLimits({minWidth: -1, minHeight: 0,
        maxWidth: 1200, maxHeight: 900});
      Journal.record('invalid-window-returned', 0, JSON.stringify(applied));
    } else if (action === 'system-api') {
      await Driver.main.hideNonSystemFloatingWindows(true);
      await Driver.main.hideNonSystemFloatingWindows(false);
      Journal.record('system-api-restored');
    } else if (action === 'foreign-window') {
      const foreign = window.findWindow('s578_' + RUN.substring(0, 8));
      Journal.record('foreign-window-returned', 0, JSON.stringify(foreign.getWindowProperties()));
    } else if (action === 'pip-start') {
      Driver.pipId = id; Driver.pipAction = action;
      Driver.pip = await PiPWindow.create({context, componentController: Driver.xController,
        templateType: PiPWindow.PiPTemplateType.VIDEO_PLAY, contentWidth: 320, contentHeight: 180});
      Driver.pip.on('stateChange', (state: PiPWindow.PiPState, reason: string) => {
        Journal.record('pip-state', 0, JSON.stringify({state, reason}), Driver.pipId, Driver.pipAction);
      });
      await Driver.pip.startPiP();
      Journal.record('pip-start-requested');
    } else if (action === 'pip-stop') {
      if (!Driver.pip) { throw new Error('pip missing'); }
      Driver.pipId = id; Driver.pipAction = action;
      await Driver.pip.stopPiP();
      Journal.record('pip-stop-requested');
    } else if (action === 'pip-info') {
      if (!Driver.pip) { throw new Error('pip missing'); }
      Journal.record('feature-info', 0, JSON.stringify(await Driver.pip.getPiPWindowInfo()));
    } else if (action === 'ball-start' || action === 'ball-update') {
      Driver.ballId = id; Driver.ballAction = action;
      if (!Driver.ball) {
        Driver.ball = await floatingBall.create({context});
        Driver.ball.on('stateChange', (state: floatingBall.FloatingBallState) => {
          Journal.record('ball-state', 0, JSON.stringify({state}), Driver.ballId, Driver.ballAction);
        });
        Driver.ball.on('click', () => Journal.record('ball-click', 0, 'null', Driver.ballId, Driver.ballAction));
      }
      const params: floatingBall.FloatingBallParams = {template: floatingBall.FloatingBallTemplate.NORMAL,
        title: 'S578 ' + RUN.substring(0, 8), content: action === 'ball-start' ? 'START' : 'UPDATE',
        backgroundColor: '#157A40'};
      if (action === 'ball-start') { await Driver.ball.startFloatingBall(params); }
      else { await Driver.ball.updateFloatingBall(params); }
      Journal.record(action, 0, JSON.stringify(params));
    } else if (action === 'ball-stop') {
      if (!Driver.ball) { throw new Error('ball missing'); }
      Driver.ballId = id; Driver.ballAction = action;
      await Driver.ball.stopFloatingBall();
      Journal.record('ball-stop-requested');
    } else if (action === 'ball-info') {
      if (!Driver.ball) { throw new Error('ball missing'); }
      Journal.record('feature-info', 0, JSON.stringify(await Driver.ball.getFloatingBallWindowInfo()));
    } else if (action === 'view-start') {
      Driver.viewId = id; Driver.viewAction = action;
      Driver.view = await floatView.create({context,
        templateType: floatView.FloatViewTemplateType.ROUNDED_RECTANGLE});
      Driver.view.onStateChange((info: floatView.FloatViewStateChangeInfo) => {
        Journal.record('view-state', 0, JSON.stringify(info), Driver.viewId, Driver.viewAction);
      });
      Driver.view.onRectChange((info: floatView.FloatViewRectChangeInfo) => {
        Journal.record('view-rect', 0, JSON.stringify(info), Driver.viewId, Driver.viewAction);
      });
      await Driver.view.setUIContext('pages/Child');
      const limits = floatView.getFloatViewLimits(floatView.FloatViewTemplateType.ROUNDED_RECTANGLE);
      Journal.record('view-limits', 0, JSON.stringify(limits));
      await Driver.view.start();
      Journal.record('view-start-requested');
    } else if (action === 'view-stop') {
      if (!Driver.view) { throw new Error('view missing'); }
      Driver.viewId = id; Driver.viewAction = action;
      await Driver.view.stop();
      Journal.record('view-stop-requested');
    } else if (action === 'view-info') {
      if (!Driver.view) { throw new Error('view missing'); }
      Journal.record('feature-info', 0, JSON.stringify(Driver.view.getWindowProperties()));
    } else if (action === 'cleanup') {
      if (Driver.child) { await Driver.child.destroyWindow(); Driver.child = undefined; }
      if (Driver.pip) { try { await Driver.pip.stopPiP(); } catch (error) {
        Journal.fail('cleanup-pip', error as BusinessError); } }
      if (Driver.ball) { try { await Driver.ball.stopFloatingBall(); } catch (error) {
        Journal.fail('cleanup-ball', error as BusinessError); } }
      if (Driver.view) { try { await Driver.view.stop(); } catch (error) {
        Journal.fail('cleanup-view', error as BusinessError); } }
      if (Driver.originalLimits) { await Driver.main.setWindowLimits(Driver.originalLimits); }
      Journal.record('cleanup-returned');
    } else if (action === 'exit') {
      Journal.record('exit-request'); await context.terminateSelf();
    } else { throw new Error('unknown session action'); }
    Journal.record('done', 0, 'null', id, action);
  }
}
