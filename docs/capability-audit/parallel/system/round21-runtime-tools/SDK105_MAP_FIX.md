# SDK105 Calendar QA map 类型修复

Root 的 QA01 三角色真实编译均在同一 map 对象触发 10605038；原始 producer/observer/denied 项目和日志只读保留。

仅修改 CalendarAudit.ets：声明 CalendarAccountObservation 接口（id:number、account:calendarManager.CalendarAccount），并显式标注 calendars.map 回调返回类型。字段、序列化结果、公开 API、权限及验收判据均未改变；三个角色共用此 fixture。

11 项已有轻量 host checks 通过。未执行 SDK/Docker/native/签名/BMS/VM，也未修改生产、共享文件、Git index 或 HEAD。实际 SDK 修复后重编译仍由 root 批量执行，不能把 host 通过当成编译/运行通过。

源码 SHA、SDK105 声明 SHA、三个历史失败日志 SHA 及完整诊断位置见 sdk105-map-fix.json；host 原始结果见 sdk105-map-fix-host-check.log。旧 result.json 记录的是本次窄修复前的交付快照，本次以增量记录为准，未覆盖旧证据。

Root 后续在新输出生成三角色 source project/manifest 并真实编译，保留新的完整 inventory/receipt；不要改 QA01 项目使旧失败日志失去对应源码。文件租约已释放。
