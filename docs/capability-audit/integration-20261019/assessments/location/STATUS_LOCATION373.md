# Location当前缺口计数核对（373集成暂停）

按历史82原始ID，定位主账为9项；另有Apps的Location privacy UI和System的MSDP各1项，相关并集11，但不能跨agent重复计数。原parallel-work-plan的location agent还承担电话13项，原owner合计22；这13项不属于本次Location/native identity窄任务，没有因本次计数被删除或关闭。

定位9项是8个 `arkts_export:@ohos.geoLocationManager:` API：`addFusionFence`、`getCurrentDistrict`、`getLocationIconStatus`、`getPostProcessingTrack`、`isFusionFenceSupported`、`removeFusionFence`、`startBluetoothSearch`、`stopBluetoothSearch`，以及 `behavior:location-provider-backends-missing`。完整带前缀ID与原next_required保留在JSON。

8个API已有精确生产补丁路由，不能称为8个完全没有实现的API；实际provider可用性及完整新包行为尚未验收。定位后端广义finding仍open。`relativeStill`明确未支持，物理静止准确性未宣称，属于System/MSDP广义剩余范围，不是本批CFI阻断额外增加的API数量。

当前Location新F guest scoped通过0项，正式ID闭合0项。实际371只证明旧2f0/17-06的只读inventory及资源关闭：ArkUI原命令无CFI，AMS两命令有CFI；其ready/compiled/selected/fullgate均为false。368已备真实-s查询/64-platformsdk编译路径后继，372已备两个消费者路径覆盖，但尚不能当成完整可运行kit，更不是native/image/guest通过。373原生身份整合按主控要求暂停。CFI与路径是这些ID验收链的技术阻断，不是另外2个API。

原`parallel_runtime_suite.py:117–127`对external-inputs登记空ID集合；即使将来有限输入scoped通过，也不能自动关闭Location/MSDP广义finding。旧E闭环和host/单测均没有迁入当前F。JSON包含原始小文件pins和各计数归属，可与其他agent去重。
