# Contacts full-build / image witness

本批新增独占 `scripts/qemu_contacts_build_witness.py` 与对应纯Python测试；没有修改产品源码、公共build/package/suite或任何agent文件。实际源码/out只读；没有运行GN/Ninja、编译器、SDK、签名、QEMU或HDC。18输出的移动只在临时测试目录演练，正式begin留给root构建写租约。

依赖 Apps 提交 `3fe292dab74715d61d82577247ed964bd3f7e88b` 的公开 `batch_apps_contact_payload.verify_payloads`。本工具直接调用它，不另写ELF blob、ABC或NAPI字节parser。独立的shared `read_elf`核实际机器、动态定义`__cfi_check`和产品`std::__h`，拒绝SDK`__n1`/Chromium`__Cr`。ABI覆盖arm64_virt、armv7a_virt、x86_64_virt；本批只读复放了真实ARM64图，其余两架构仅构造的命令合同反例，不能称为实际平台验证。

## 四阶段与root接线

### begin

在本次实际全构建前运行：

```sh
python3 scripts/qemu_contacts_build_witness.py begin \
  --source-root /Volumes/PSSD/qemu/openharmony --product arm64_virt
```

先核固定9份最终业务源码（含JS、picker回调、native_module注册、属性/类映射）+实际BUILD.gn/生成脚本/模板，再快照12份native源码与include/*.h。所有既有输出先逐一检查为非软链普通文件；之后只把18个输出及旧completion witness移入 `out/<product>/.qemu-contacts-witness/<nonce>/`，不删stamps、其他目标或源码。旧prepared快照仍留在各自nonce目录。

18输出合同与Apps完全相同：contact.abc、contact.o、contact_abc.o、12个native对象、linked libcontact、unstripped libcontact、staged system/module/libcontact。32位产品staged使用lib，其余lib64。输出名单可调用 `outputs(product)`。

新pending为 `out/<product>/qemu-contacts-build-pending.json`，包含唯一nonce、start_ns、完整source SHA和recipe。

### finish

root已约定把**实际正式images那次**Bash build_args原数组写成 `out/<product>/qemu-full-build-argv.json`；不是展示命令或只编contact目标的命令。真实pipefail构建/tee都成功后：

```sh
python3 scripts/qemu_contacts_build_witness.py finish \
  --source-root /Volumes/PSSD/qemu/openharmony --product arm64_virt \
  --build-log /absolute/full-images-build.log \
  --build-argv-json /Volumes/PSSD/qemu/openharmony/out/arm64_virt/qemu-full-build-argv.json \
  --build-exit-code 0
```

要求：

- pending源码/recipe没有变化，18个输出全部在start_ns至finish_ns内新写且非空；构建log本身也必须在本次窗口内更新。argv可在begin前准备，保留其真实SHA/长度/mtime，内容必须是唯一product、build-target=images、build-only-load=false、fast-rebuild=false，不接受冲突重复值。
- 真实 `toolchain.ninja`、`contact.ninja` 和 `args.gn`原字节保留。只用Python展开固定GN生成的选中规则，不执行Ninja。检查12个source→object边、3个生成action的完整依赖与绝对source/out路径、完整14对象的solink/rsp边。无法解析、未知/循环binding、重复边直接失败。
- 逐条检查真实选中命令：产品clang++/target/generated-musl sysroot、最终有效LTO、CFI-vcall/icall与cross-DSO、native无exceptions/RTTI；link本身连同实际rsp展开后的最终标志也须保留CFI/LTO，拒绝未保留的嵌套rsp、shell替换/注释/控制。先禁后启可接受，最后关闭必须失败。action锁定实际生成脚本、`--module`、真实es2abc工具目录与objcopy的对应产品arch。
- log中必须有12条强制CXX、3条ACTION、1条SOLINK，以及固定生成脚本实际打印的 `./ets_frontend/es2abc --output <freshABC> --module <currentJS> --target-api-sub-version=beta3 | execution_path: <out>/clang_x64/arkcompiler`。不能仅靠stamp或self-report pass。
- 固定hb `build/hb/modules/ohos_build_module.py:64–74`仅在super().run成功的else打印product build success；`log_util.py:86–95`加OHOS INFO前缀。GN/NINJA阶段清stage后，成功行是`[OHOS INFO]  arm64_virt build success`。工具锚定精确product的完整行且必须在所有强制工作之后，并核真实exit0，不接受任意build-success子串、早期load-only成功或失败日志。
- 保存实际clang++/llvm-objcopy/es2abc工具SHA与source内解析路径；这三份大工具不复制进包。完整命令/rsp是从保留的实际图展开的选择合同，不冒充另一次命令执行记录；actual es2abc执行另有log原行。
- 调用Apps parser，把当前JS/新ABC、两个blob对象、unstripped内实际VA blob范围、GetJS/GetABC真实可执行导出、linked/staged对应起来。CLI finish尚无image，不把staged代入的中间核对标为独立image提取成功；原parser的false能力字段保留。仅将临时目录的绝对path规范为稳定的证据角色路径，内容SHA/size/地址/代码校验结果原样保留，以便离线重放。

成功才写 `out/<product>/qemu-contacts-build-witness.json`。任一失败都保留pending/已归档旧产物，不产出completion witness。

### package

建议包目录为 `contacts-native/`，由root公共package接线选择：

```sh
python3 scripts/qemu_contacts_build_witness.py package \
  --source-root /Volumes/PSSD/qemu/openharmony --product arm64_virt \
  --directory /new/package/contacts-native --system-image /new/package/images/system.img
```

先在私有scratch重新核全部当前源码、18产物、图、实际argv/log与witness，再发布新专用目录。保留：raw图、args、commands、展开的link-response、完整源/headers/生成脚本、18原输出（含完整unstripped）、full-log、argv、witness与inventory。不能覆盖已有专用目录。

随后用共享 `ext_image_entries.dump_unique_file`从system.img的 `/lib64/module/libcontact.z.so` 与 `/system/lib64/module/libcontact.z.so`（32位lib）提取：必须存在且所有别名只指向一个真实regular inode。比真实提取DSO的hash与staged/linked，再以该独立提取文件重新调用Apps parser。没有单独安装contact.abc的假设。

### verify

```sh
python3 scripts/qemu_contacts_build_witness.py verify \
  --product arm64_virt --directory /archive/contacts-native \
  --system-image /archive/images/system.img --output /separate/verification.json
```

不需要原OHOS source/out、不执行GN/Ninja/编译器，只读包原证据重算所有SHA、固定source pins、raw graph→commands/rsp、fresh witness、完整log/argv、ELF/CFI/JS+ABC字节、真实image唯一inode和DSO身份。临时提取在包外；输出报告也应放在专用证据目录外。recipe需与当前仓库工具及四组件一致，必要依赖是Apps新parser和现有shared Python校验器。

## 明确的验收边界

所有阶段/报告都保留：

- `module_record_and_literal_binding_verified=false`：Panda header/size/Adler32与payload逐字节绑定不解ABC moduleRecordIdx或literal-array语义。
- `public_runtime_execution_verified=false`：CFI jump-table导出、完整源与build/image身份不证明普通调用方执行过LoadArkModule或picker回调。
- `first_artifact_behavior_gate_passed=false`：没有新guest行为验收，0项核销，余下5包仍不得越过首代表包门禁。

工具的full-build来源是root真实受控调用、原argv/log和强制fresh产物的一致性证据，不是可抵御伪造整个构建环境的远程attestation。归档内保留的mtime是原构建witness数值，不要求解包文件保留原mtime。

## 已运行轻检查与剩余工作

17项纯Pythonhost测试通过，覆盖：3ABI规则、缺失/重复native/blob边、最终CFI/LTO禁用、错误module/arch/old-root/action依赖、真实images argv、精确hb尾句及es2abc cwd、精确18输出保护、软链先验拒绝、旧/未来/空输出、stale callback/JS pin、原始包数据和rehash后的图篡改、伪造runtime字段及private scratch→archive路径稳定性。

metadata fixture测试显式mock ELF/parser来隔离元数据拒绝顺序；构造的bytes从不作为真实DSO/ABC验收。真正payload parser由Apps负责且没有复制；本批未声称新payload或新image实测通过。

`real-product-graph-replay.json`保留只读inspect原ARM64 contact.ninja（实际SHA）、toolchain中所需原始片段/行号及其16条展开命令；真实上下文是 `/Volumes/PSSD/qemu/openharmony`，不能把/ohos挂载别名代替实际GN绝对路径。其余无关graph没有加载/遍历。该复放只证明当前旧混合图的解析兼容，不证明fresh GN选择/新ABC/native link。

root待执行：两新工具纳入freeze/recipe、接三处shell；在同批真实全build后运行begin→finish；对新system.img做package/verify以及负向修改/双inode检查；最后才是新包普通API callback和完整首包行为门禁。
