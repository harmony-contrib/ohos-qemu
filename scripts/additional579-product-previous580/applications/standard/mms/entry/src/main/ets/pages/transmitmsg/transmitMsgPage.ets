import { SendDataAttachment } from '../../utils/SendDataAttachment';
/**
 * Copyright (c) 2022 Huawei Device Co., Ltd.
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */
import TransmitMsgController from './transmitMsgController';
import DeviceUtil from '../../utils/DeviceUtil';
import { TransmitMmsDialog, TransmitMsgDialog, TransmitThirdPartMsgDialog } from '../../views/MmsDialogs';
import WantUtil from '../../utils/WantUtil';
import { MmsAvatar } from '../../views/MmsAvatar/MmsAvatar';
import { messageType } from '../conversationlist/conversationListController';
import { GlobalContext } from '../../MainAbility/GlobalHelper';
import commonData from '../../data/commonData';
import LooseObject from '../../data/LooseObject';
import { CustomContentDialog } from '@ohos.arkui.advanced.Dialog';
import { SubHeader } from '@ohos.arkui.advanced.SubHeader';
import ResourceUtils from '../../utils/ResourceUtils';
import { LengthMetrics, SymbolGlyphModifier } from '@kit.ArkUI';
import FavoriteController from '../../pages/favoritepage/favoriteController'
import TransmitMessageUtil from '../../utils/TransmitMessageUtils'
import myCommon from '@ohos.app.ability.common';
import Configuration from '@system.configuration';
import { SplitInfoModel, SplitScreenManager } from '../../utils/SplitScreenManager';
import HiLog from '../../utils/HiLog';

const TAG = 'TransmitMsg';

@Builder
export function TransmitMsgLoader(param: LooseObject): void {
    TransmitMsg();
}

@Component
export default struct TransmitMsg {
    @StorageProp('fontSizeScale') fontSizeScale: number = 1;
    @Consume('pageInfos') pageInfos: NavPathStack
    private context = getContext(this) as myCommon.UIAbilityContext;
    @State mTransmitMsgCtrl: TransmitMsgController = TransmitMsgController.getInstance();
    @LocalStorageProp('fullScreenPadding') fullScreenPadding: Padding | null = null;
    @StorageProp('isShowContactHeadIcon') isShowHead: boolean = true;
    @State gridColumns: number = DeviceUtil.isTablet() ? 12 : 4;
    @State gridSizeType: SizeType = DeviceUtil.isTablet() ? SizeType.LG : SizeType.SM;
    @State gridGutter: string = '24vp';
    @State gridMargin: string = '24vp';
    /* 设备是否为pad */
    @State isPad: boolean = false;
    @StorageLink('mmsPadMargin') padMargin: number = DeviceUtil.padMargin();
    private dialogAlignment: DialogAlignment = DeviceUtil.isTablet() ? DialogAlignment.Center : DialogAlignment.Bottom;
    private dialogOffset: Offset = DeviceUtil.isTablet() ? { dx: 0, dy: 0 } : { dx: 0, dy: $r('app.float.dialog_bottom_margin')};
    scroller: Scroller = new Scroller();
    private textDirection: string = Configuration.getLocale().dir;
    @StorageLink('isVDEFoldPhoneAndFoldedState') @Watch('onFoldStatusChange') isVDEFoldPhoneAndFoldedState
        : boolean = false;
    @StorageLink('foldStatus') @Watch('getWallpaper') foldStatus: number = 0;
    @State isVDE: boolean = this.isVDEFoldPhoneAndFoldedState && this.foldStatus === 2 ? true : false;
    @State isPC: boolean = DeviceUtil.isPC()
    @State splitInfoModel: SplitInfoModel = SplitScreenManager.getInstance().infoModel;
    private onFoldStatusChange(): void {
        if (this.isVDEFoldPhoneAndFoldedState) {
            HiLog.i(TAG, 'onFoldStatusChange :' + this.isVDEFoldPhoneAndFoldedState);
        } else {
            HiLog.i(TAG, 'onFoldStatusChange :' + this.isVDEFoldPhoneAndFoldedState);
        }
    }

    getWallpaper() {
        if (this.isVDEFoldPhoneAndFoldedState) {
            HiLog.i(TAG, 'onFoldStatusChange: ' + this.isVDEFoldPhoneAndFoldedState);
            if (this.foldStatus === 2) {
                this.isVDE = true;
            } else {
                this.isVDE = false;
            }
            HiLog.i(TAG, 'isVDE: ' + this.isVDE);
        } else {
            this.isVDE = false;
            HiLog.i(TAG, 'onFoldStatusChange: ' + this.isVDEFoldPhoneAndFoldedState);
        }
    }
    @Styles
    pressedStyles() {
        .backgroundColor($r('sys.color.ohos_id_color_click_effect'))
    }

    @Styles
    pressedInfoItemStyles() {
        .backgroundColor(Color.Transparent)
    }

    transmitDialogController: CustomDialogController = new CustomDialogController({
        builder: CustomContentDialog({
            primaryTitle: TransmitMessageUtil.getMainTitle(this.mTransmitMsgCtrl),
            contentBuilder: () => {
                this.transmitDialogControllerBuildContent();
            },
            contentAreaPadding: {left: 0, right: 0, top: 0, bottom: 0}
        }),
        autoCancel: false,
    });

    @Builder
    transmitDialogControllerBuildContent(): void {
        TransmitMsgDialog({
            controller: this.transmitDialogController,
            cancel: () => {

            },
            confirm: (value) => {
                this.mTransmitMsgCtrl.saveDraftAndTransmit(value, this.pageInfos, true);
            },
            msg: this.mTransmitMsgCtrl.dialogMsg,
        });
    }

    transmitMmsDialogController: CustomDialogController = new CustomDialogController({
        builder: CustomContentDialog({
            primaryTitle: TransmitMessageUtil.getMainTitle(this.mTransmitMsgCtrl),
            contentBuilder: () => {
                this.transmitMmsDialogControllerBuildContent();
            },
            contentAreaPadding: {left: 0, right: 0, top: 0, bottom: 0}
        }),
        autoCancel: false,
    });

    @Builder
    transmitMmsDialogControllerBuildContent(): void {
        TransmitMmsDialog({
            controller: this.transmitMmsDialogController,
            cancel: () => {},
            confirm: (value, isTransmit) => {
                this.mTransmitMsgCtrl.saveDraftAndTransmit(value, this.pageInfos, isTransmit);
            },
            msg: this.mTransmitMsgCtrl.dialogMsg,
            isRcs: this.mTransmitMsgCtrl?.isRcs || false
        });
    }

    transmitThirdPartDialogController: CustomDialogController = new CustomDialogController({
        builder: CustomContentDialog({
            contentBuilder: () => {
                this.transmitThirdPartDialogControllerBuildContent();
            },
            contentAreaPadding: {left: 0, right: 0, top: 0, bottom: 0}
        }),
        autoCancel: false,
    });

    @Builder
    transmitThirdPartDialogControllerBuildContent(): void {
        TransmitThirdPartMsgDialog({
            controller: this.transmitThirdPartDialogController,
            cancel: () => {},
            confirm: (value) => {
                this.mTransmitMsgCtrl.transmit(value, true);
            },
            msg: this.mTransmitMsgCtrl.dialogMsg
        })
    }

    destinationAppear() {
        AppStorage.SetOrCreate('transmitSourceIsChecked', true);
        this.mTransmitMsgCtrl.onInit(this.pageInfos, this.transmitDialogController, this.transmitMmsDialogController,
            this.transmitThirdPartDialogController, getContext() as myCommon.UIAbilityContext);
        this.mTransmitMsgCtrl.onShow();
    }

    destinationDisappear() {
        // Search/contact overlays retain TransmitMsg in the stack.
        if (!this.pageInfos.getAllPathName().includes('TransmitMsg')) {
            SendDataAttachment.cancel(this.mTransmitMsgCtrl.sharedAttachmentLease);
        }
    }

    destinationShow() {
        WantUtil.getWant(this.context, this.pageInfos);
    }

    aboutToAppear() {
        this.isPad = DeviceUtil.isTablet();
    }

    onPageHide() {
    }

    destinationBackPress() {
        GlobalContext.getContext().setObject('notUpdateData', true)
        SendDataAttachment.cancel(this.mTransmitMsgCtrl.sharedAttachmentLease);
        this.pageInfos.pop();
    }

    build() {
        NavDestination() {
            Column() {
                if (this.mTransmitMsgCtrl.dialogMsg.transmitContent !== '') {
                    Text(this.mTransmitMsgCtrl.dialogMsg.transmitContent).id('mms-senddata-text')
                    Button('取消文本草稿').id('mms-senddata-text-cancel').onClick(() => this.destinationBackPress())
                }
                if (this.mTransmitMsgCtrl.sharedAttachmentLease !== '') {
                    Text(SendDataAttachment.description(this.mTransmitMsgCtrl.sharedAttachmentLease))
                        .id('mms-senddata-attachment')
                    Button('取消附件草稿').id('mms-senddata-cancel').onClick(() => this.destinationBackPress())
                }
                Row() {
                    Search({ value: '', placeholder: $r('app.string.searchHit') })
                        .width('100%')
                        .placeholderColor($r('sys.color.font_secondary'))
                        .placeholderFont({ size: $r('sys.float.Body_L'), weight: FontWeight.Regular })
                        .textFont({ size: $r('sys.float.Body_L'), weight: FontWeight.Regular })
                        .fontColor($r('sys.color.font_primary'))
                        .backgroundColor($r('sys.color.comp_background_tertiary'))
                        .accessibilityText(getContext(this).resourceManager.getStringSync($r('app.string.searchHit').id))
                        .onClick(() => {
                            this.mTransmitMsgCtrl.jumpToSearchContact();
                        })
                        .focusable(false)
                }
                .padding({
                    left: this.isPC ? 24 : this.isPad ? this.padMargin : 16,
                    right: this.isPC ? 24 : this.isPad ? this.padMargin : 16
                })
                .alignItems(VerticalAlign.Center)
                .height(56)
                .margin({ bottom: this.isPC ? 8 : '' })
                Column() {
                    //Select Contact
                    Flex({ direction: FlexDirection.Row, justifyContent: FlexAlign.SpaceBetween,
                        alignItems: ItemAlign.Center }) {
                        Text($r('app.string.selectContacts'))
                            .fontSize($r('sys.float.Subtitle_M'))
                            .fontColor($r('sys.color.font_primary'))
                            .fontWeight(FontWeight.Medium)
                        SymbolGlyph($r('sys.symbol.chevron_right'))
                            .width($r('app.float.settings_item_next_image_width'))
                            .height($r('app.float.settings_item_next_image_height'))
                            .draggable(false)
                            .fontSize('24vp')
                            .fontColor([$r('sys.color.icon_fourth')])
                    }
                    .constraintSize({ minHeight: '48vp' })
                    .onClick(() => {
                        //Go to Select Contact
                        this.mTransmitMsgCtrl.jumpToContactForResult(this.context);
                    })
                    .padding({
                        left: this.isPC ? 12 : this.isPad ? this.padMargin : 16,
                        right: this.isPC ? 12 : this.isPad ? this.padMargin : 16
                    })
                    .margin({
                        left: this.isPC ? 24 : '', right: this.isPC ? 24 : ''
                    })
                    .border(this.isPC ? {
                        radius: 16,
                        color: $r('sys.color.comp_background_list_card')
                    } : {})
                    .backgroundColor(this.isPC ? $r('sys.color.comp_background_list_card') : '')
                    SubHeader({
                        secondaryTitle: $r('app.string.recently')
                    }).margin({ left: this.isPC ? -28 : this.padMargin - 28 })
                    List() {
                        LazyForEach(this.mTransmitMsgCtrl.transmitMsgDataSource, (item: messageType, index: number) => {
                            ListItem() {
                                Column() {
                                    Row() {
                                        if (this.isShowHead) {
                                            MmsAvatar({ item: item })
                                        }
                                        Text(item.name !== '' ? item.name :
                                        item.telephone)
                                            .fontSize($r('sys.float.Subtitle_M'))
                                            .fontColor($r('sys.color.font_primary'))
                                            .fontWeight(FontWeight.Medium)
                                            .margin(
                                                {
                                                    start: this.isPC ? LengthMetrics.vp(8) :
                                                        this.isShowHead ? LengthMetrics.vp(16) : LengthMetrics.vp(0)
                                                })
                                            .maxLines(1)
                                            .textOverflow({ overflow: TextOverflow.Ellipsis })
                                            .layoutWeight(1)
                                    }
                                    .accessibilityGroup(true)
                                    .width('100%')
                                    .height(64)
                                    .padding({
                                        start: this.getCustomPadding(),
                                        end: this.getCustomPadding()
                                    })
                                    if (index !== this.mTransmitMsgCtrl.transmitMsgDataSource.mmsList.length - 1) {
                                        Divider()
                                            .strokeWidth('app.float.settings_divider_strokeWidth')
                                            .margin({
                                                start: this.isShowHead ? LengthMetrics.vp(56 + this.padMargin) :
                                                this.getCustomPadding(),
                                                end: this.getCustomPadding()
                                            })
                                            .color($r('sys.color.comp_divider'))
                                    }
                                }
                            }
                            .stateStyles({
                                normal: this.pressedInfoItemStyles,
                                pressed: this.pressedStyles
                            })
                            .onClick( () => {
                                this.mTransmitMsgCtrl.clickSendMessage(item)
                                if (this.isPC) {
                                    AppStorage.setOrCreate('isTransmitShow', false);
                                    AppStorage.setOrCreate('isFavoriteTransmitShow', false);
                                    AppStorage.setOrCreate('isTransmitSearch', false);
                                }
                                if (this.mTransmitMsgCtrl.dialogMsg.mmsStatus ===
                                    commonData.TRANSMIT_MSG_STATUS.NO_MMS) {
                                    this.transmitDialogController.open();
                                } else if (this.mTransmitMsgCtrl.dialogMsg.mmsStatus ===
                                commonData.TRANSMIT_MSG_STATUS.THIRD_PART_MMS ||
                                    this.mTransmitMsgCtrl.dialogMsg.mmsStatus ===
                                    commonData.TRANSMIT_MSG_STATUS.SHARE_MMS ||
                                    this.mTransmitMsgCtrl.dialogMsg.mmsStatus ===
                                    commonData.TRANSMIT_MSG_STATUS.SHARE_SMS) {
                                    this.transmitThirdPartDialogController.open();
                                } else {
                                    this.transmitMmsDialogController.open();
                                }
                            })
                        }, (item: messageType): string => item.threadId.toString())
                    }
                    .edgeEffect(EdgeEffect.Spring, {alwaysEnabled: true})
                    .scrollBar(BarState.Auto)
                    .layoutWeight(1)
                    .height(this.isVDE ? '47%' : '100%')
                    .nestedScroll({
                        scrollForward: NestedScrollMode.SELF_FIRST,
                        scrollBackward: NestedScrollMode.SELF_FIRST
                    })
                }
                .justifyContent(FlexAlign.Start)
                .width('100%')
                .height('calc(100% - 56vp)')
                .constraintSize({ minHeight: $r('app.float.transmitMsg_min_height') })
            }
            .justifyContent(FlexAlign.Start)
            .width('100%')
            .height('100%')
        }
        .onShown(() => {
            this.destinationShow();
        })
        .onAppear(() => {
            this.destinationAppear();
        })
        .onDisAppear(() => {
            this.destinationDisappear();
        })
        .onBackPressed(() => {
            this.destinationBackPress();
            return true;
        })
        .padding({top: this.fullScreenPadding ? (this.fullScreenPadding.top as number) : 0})
        .hideTitleBar(this.isPC || this.splitInfoModel.isSmall ? true : false)
        .backgroundColor(this.isPC ? '#19FFFFFF' : '')
        .backButtonIcon(new SymbolGlyphModifier($r('sys.symbol.xmark')))
        .title(ResourceUtils.getStringSync($r('app.string.transmitHeadText')), {paddingStart: LengthMetrics.vp(this.padMargin)})
    }

    private getCustomPadding(): LengthMetrics {
        return this.isPC ? LengthMetrics.vp(24) :
            this.isPad ? LengthMetrics.vp(this.padMargin) : LengthMetrics.vp(16);
    }
}