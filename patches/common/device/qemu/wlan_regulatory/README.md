# QEMU 的签名无线监管数据库

共用的三个 Linux 6.6 产品配置均要求 cfg80211 验证监管数据库签名，
但原 firmware 目标没有安装 regulatory.db。复用固定 7.0 manifest 中
device/soc/unisoc 的两份原始二进制；不生成自签数据库，不修改国家码或信道。

apply.sh 在任何补丁或幂等跳过前验证数据库、签名与内核 wens.hex 的固定
SHA-256，执行二进制 CMS 签名验证，再将签名者 DER 与内核内置信任证书
逐字节比较。openssl 的 -noverify 只排除宿主系统 CA 库，其信任判断不能
替代后续精确 DER 比较。三个产品仍必须启用签名要求、内核密钥和固件加载器。

GN 将数据库及签名安装到 system/lib/firmware，并预装独立的 vendor init
配置。pre-init 指定 /system/lib/firmware 固件查找路径，早于 boot 阶段加载
cfg80211/mac80211/hwsim。原有固件默认回退路径和所有权限保持不变。

`ci/capability-audit/check_wlan_regulatory.py` 在私有副本验证实际签名、两次
应用及损坏依赖拒绝。它不是新包行为验收：还需验证实际镜像文件校验和、
加载路径、内核无数据库加载失败，并通过真实 WLAN 扫描/关联边界测试。
