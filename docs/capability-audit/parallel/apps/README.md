# apps 第一轮交接

34 项分配逐项列于 `result.json` 的 `requirements_review`。本轮没有核销完整账本。
新增修复只修改 Settings 的 `IgnoreRepeatClickService.ets`：等待真实无障碍设置
Promise 完成后才更新缓存和成功事件，捕获异步拒绝并串行处理后续请求。主机回归
执行完整补丁类体，原文件可重现提前成功，候选通过 10 个场景。完整编译、真实
通知动作、权限拒绝及服务销毁/重启由主 agent 在集中代表包中验收。

两个 notification preference helper 经固定源复核是同步 `Settings.setValueSync`。
service生命周期继续由现有framework管理，候选不调用无条件 `terminateSelf`：
固定native实现只传token和-1，未提供startId条件，异步停止期间新请求会有竞态。
安全idle-stop/销毁闭环保留为主agent后续工作，不能宣称本轮已修复服务退出。

`static-evidence.json` 是只读查询固定源容器所得的源码和构建暂存元数据。
暂存 `/ohos/out/arm64_virt/packages/phone/system` 同时含 SceneBoard、旧 phone
payload、Picker 等多种配置产物；目录名不证明设备画像，也不证明最新归档内容。
它只能帮助区分已有源码/候选实现与缺 provider，不能证明 BMS 注册或运行。
Settings、Photos、Camera、Contacts 均有比历史 R49 描述更多的入口；后续仍必须
在新包解包、BMS 查询和真实调用层复核。六项 phone minimum 声明仍未见于这份
暂存 syscap，AVInputCast 已声明；两者都不能据此修改账本。

未完成的主要类别：真实 ScreenReader/Caption/分享/翻译/实体识别后端缺失；
AdminProvisioning、Wallpaper、Contacts/Camera 等provider源码构建、签名、设备
配置和预装链需独立准备；网络、定位、通知、媒体调用者与UI协议须按原契约验证，
不能只改包名或伪造响应。具体拆分和下一步见逐项记录。
