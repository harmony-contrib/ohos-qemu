# QEMU 的实际 WPA 扫描后端

补丁栈保留 chip HDI 路径，为 non-chip 产品接通现有 WPA HDI。回调注册、
派发和注销共用原有同步路径；接口必须是实际主 STA，不能忽略接口参数。

SCAN 使用已有通用请求/回复接口，校验参数边界、十六进制编码 SSID，检查
实际 OK 回复。非默认 chip 扫描调度类型明确返回 NOT_SUPPORT，不丢弃参数。

频率查询解析实际 `GET_CAPABILITY freq` 文档，分别返回 2.4 GHz、非 DFS
5 GHz、DFS 及其既有组合。允许真实 B/G 重复和空模式块；去重、拒绝坏格式、
超长/截断回复与未知标记；6/60 GHz 不冒充 5 GHz。输出仅在完整解析成功后
替换。NO_IR 信道可以被动扫描，返回其频率不改变 WPA/内核的发射限制。

`ci/capability-audit/fixtures/wpa_frequency_capabilities.txt` 是 R27 原归档
真实只读结果，来源和校验和记录在缺口文档中；不是生产信道表，也不用于
镜像默认值。ASan/UBSan 边界和三架构完整 TU 编译不是客体 WLAN 验收。
