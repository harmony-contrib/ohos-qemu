# Knowledge/Photos实际UI源码合同

本轮只读现有 `ohos-qemu-parallel-source-20261016-02` 的相关源码/资源，以及
Photos实际导入的ArkUI advanced Dialog实现。没有读取 `/ohos/out`，没有启动新容器、
编译、SDK、HDC或guest。首次发现查询UTC 20:20:56.696660，最后源码读取
2026-10-16 20:28:42.884383 UTC，约7分46秒；之后已向root归还RO租约。

`source-evidence.json`保留38份实际文件的完整SHA、项目revision、行号摘录和资源行。
`ui-contract.json`是给root/Apps的机读合同，包含下面全部标题、按钮资源和条件。
这些是源码合同，不是新guest真实树、BMS注册、权限或点击成功证据。

## READ/WRITE图片权限

`ImageAndVideosStrategy.ets`明确把READ_IMAGEVIDEO、WRITE_IMAGEVIDEO、MEDIA_LOCATION
放在同一个IMAGE_AND_VIDEOS组。默认按钮来自BasePermissionStrategy，为DENY、ALLOW。
两项都实际需要并允许申请时使用同组UI；已授权、政策拒绝或不可申请时是否出现弹窗
仍由真实权限流程决定，不能据分组就预造一次“允许”操作或authResults。

| 项目 | 资源 | zh_CN | base / en_GB |
| --- | --- | --- | --- |
| 标题 | `app.string.group_label_image_and_videos` | `允许“%s”访问图片和视频？` | `Allow %s to access images and videos on your device?` |
| 允许 | `app.string.allow` | `允许` | `Allow` |
| 拒绝 | `app.string.ban` | `禁止` | `Deny` |

PermissionManager bundle为`com.ohos.permissionmanager`。应用名来自真实caller的
资源label；`titleTrim`仅在长度超过1000个JS code unit时截断并追加`...`，普通
`Knowledge audit ROLE`标签不受影响。`dialogPlus.ets`没有为允许按钮设置固定唯一id。
运行时仍须核真实签名caller、label、对话框/窗口、唯一可见可点按钮、authResults和token。

## showAssetsCreationDialog的保存UI

真实链为公开JS wrapper取得self BMS bundle/appId/labelId、从相应module资源读取appName，
再交native `ShowAssetsCreationDialog`。native指定`com.ohos.photos/SaveUIExtensionAbility`、
`sysDialog/common`和读URI授权flag，在**调用者UIContent**创建ModalUIExtension。
phone manifest入口继承CommonSaveAbility，session加载SaveUIExtensionPage，最终构造
SaveUIExtensionComponent的CustomContentDialog。

这证明caller-hosted extension结构；它不能代替实际UITest树对bundle属性究竟显示
importer还是Photos的观测。选择器必须结合实际host窗口、AMS extension关系和可信节点，
不能只相信一个bundle字符串。

保存标题资源在 **`feature/extensions/src/main/resources`**，不是common下同名保存编辑页。
普通非shortTerm且全部类型为IMAGE时使用`app.plural.third_save_picture`，调用为
`$r(title, uris.length, appName, uris.length)`。

| 语言/数量 | 实际模板 |
| --- | --- |
| zh_CN other | `允许“%1$s”保存 %2$d 张图片？` |
| base one | `Allow %1$s to save %2$d image?` |
| base other | `Allow %1$s to save %2$d images?` |

若实际已安装label确为`Knowledge audit importer`且一次28张IMAGE，预期完整中文是
`允许“Knowledge audit importer”保存 28 张图片？`，英文是
`Allow Knowledge audit importer to save 28 images?`。数量两侧中文模板均含ASCII空格。
单图是`1 张图片` / `1 image`。示例不是抓到的guest标题。

视频/混合类型分别改用`third_save_video`和`third_save_picture_and_video`；完整中英文
one/other资源均在JSON。shortTerm分支使用另一资源，不能套此合同。
按钮数组第0项`app.string.dialog_ban`为`禁止`/`Deny`，调用setSaveResult(false)；
第1项`app.string.dialog_allow`为`允许`/`Allow`，调用setSaveResult(true)。
common资源`save_dialog_title_text=请选择保存方式`属于其他保存编辑UI，不能用于这里。

## advanced_dialog_button_1没有固定允许语义

Photos保存和删除都导入`@ohos.arkui.advanced.Dialog`。其真实source/dialog.ets、
dialog_v18.ets及shipping interfaces/dialog.js、dialog_v18.js用递增keyIndex生成
`.key(advanced_dialog_button_${keyIndex++})`，每组件初值0。

水平两按钮先构造数组0、再1；竖排两按钮反序构造1、再0。因此首次水平的允许/确认
可能是key1，首次竖排却可能是key0。key由builder调用递增，不能承诺重绘后的数字
稳定；`.key`到实际UITest属性的最终映射也必须在guest观测。保存或删除都不能盲点key1。

可执行选择合同是：先匹配真实可信对话框/窗口及精确源标题，再在其内部选唯一
visible/enabled/clickable且文本等于`允许`或`删除`的真实按钮，并记录selected_node的
实际ID、文本、bounds和原始前后树。缺少、重复或上下文不符就失败；点击后还须验证
真实保存URI/文件、删除资产状态或真实权限结果，不能只凭按钮消失判成功。

## 真正大图浏览器删除路径

这里必须保留 **`ToolBarButtonDelete`**，没有下划线。完整生产源码链是：

1. phone PhotoBrowserComponent导入并使用common PhotoBrowserToolBar。
2. PhotoBrowserToolBar导入`@ohos/browsercommon` ToolBar；实际文件是大小写敏感的
   `applications/standard/photos/browserCommon/src/main/ets/default/view/actionbar/ToolBar.ets`。
3. 该ToolBar第453/498/557行均生成`ToolBarButton${menu.componentKey}`。
4. Action.ets第173行`COMPONENT_KEY_DELETE='Delete'`，第452–458行Action.DELETE绑定它。

此前初查误跟到common通用ActionButton的`ToolBarButton_${prop.key}`路径，已在交付前
向root更正。那个通用组件和DeleteActionProp的`ActionButton_Delete`属于另一条actionbar，
不能据此修改已确认的大图browser selector。猜测的`feature/browsercommon`路径不存在，
随后实际解析到上述`browserCommon`并保留SHA。

DeleteMenuOperation普通单图IMAGE、非RecentlyDeleted、非特殊cleanup分支下：

| 项目 | 实际资源 | zh_CN | base |
| --- | --- | --- | --- |
| 标题 | `app.string.recycle_picture_tips` | `是否删除此图片？` | `Delete this photo?` |
| 确认 | `app.string.dialog_delete` | `删除` | `Delete` |
| 取消 | `app.string.dialog_cancel` | `取消` | `Cancel` |

`isTrash`默认true，表示本次走移入回收流程；albumInfo.isTrashAlbum时变false，进入
永久删除：标题`recycle_tips=是否删除？/Delete?`，确认
`dialog_delete_permanently=永久删除/Delete`。不要把永久删除分支悄悄当作普通清理正例。
保留期默认30天，content还区分cloud状态，不能猜固定全部正文。DeleteDialog用
AlertDialog(primaryTitle=dialogMessage, primaryButton=cancelButton,
secondaryButton=confirmButton)，同样没有Photos自有固定确认id。

此次没有修改任何shared/coordinator/fixture或既有报告。root负责后续统一修动态按钮
选择并在新包实际UITest/AMS/存储中验证；本轮firstgate保持false，0项核销。
