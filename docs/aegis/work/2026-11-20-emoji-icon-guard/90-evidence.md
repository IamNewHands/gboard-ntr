# 证据

## 2026-11-20 源码阶段

- 目标症状：九键拼音页／符号页切换时，换行键上先出现原生笑脸（带圆圈），随后才被替换成「换行／重输／收起」文字。
- 根因依据（既有证据）：`docs/aegis/work/2026-11-18-toolbar-repair/90-evidence.md:57` 记录 `GKBImageViewWithBackground` 的 `layerClass` 为 `GKBImageLayer`、`setImage:` 转发 `self.layer`；`docs/aegis/work/2026-11-14-action-key/90-evidence.md:22` 记录该视图自有独立 image/highlightedImage 前景。原生每次 `updateView` 都会把笑脸重新写进前景图层，而 `GXKUpdateActionKey` 的清除发生在轮询／布局的下一拍。
- 修复：`static void gxk_key_updateView(id self, SEL _cmd)` 先调用 `gOrigKeyUpdateView`，再对已绑定的那一个表情键清 `image`／`highlightedImage`，清前把两张图存进 `gActionNormalImage`／`gActionHighlightedImage` 供 `GXKDetachActionKey` 还原。
- 刻意不做：不隐藏视图、不改 alpha、不碰 backgroundLayer／backgroundColor／cornerRadius；不清未绑定的键（`GXKUpdateActionKey` 的 `hasForeground` 要求新绑定必须有当前原生前景，先清会让新布局绑不上）。
- 方法签名（首版误判，真机闪退后已证伪）：首版按 `id` 接管并原样回传返回值，理由是「取不到类型编码串」。真机切键盘即闪退。
- 签名实证：解析 `Payload/Gboard.app/PlugIns/Gboard.appex/Gboard` 的 `__objc_classlist` → `class_ro_t` → `method_list_t`（entsize 24，sel/type 均为指针），得到 `GKBSoftKeyView` 的 `-updateView` 类型编码 `v16@0:8`，即 `void (^)(id, SEL)`；同表 `GKBImageViewWithBackground` 的 `-setImage:` 为 `v24@0:8@16`，说明解析路径正确。全包仅 `GKBSoftKeyView` 声明了 `updateView`。
- 崩溃机制：ARC 下 `id` 返回值的包装函数会对返回寄存器做 `objc_retainAutoreleasedReturnValue`；原方法返回 void 时该寄存器内容不确定，切键盘（首次布局调用 updateView）即崩。
- 回归：`python -B -m unittest <每个 tests/test_*.py>`，10 个文件全 OK，共 134 项；新增契约测试覆盖透传返回值、只处理绑定键、存档先于清除、不碰外观字段、幂等安装与两处安装点顺序。

## 2026-11-20 构建与验包

- CI run 44733139902（提交 c86e7cb）success，macos-15-intel，arm64 / iOS 12+ / QuartzCore / ldid；artifact libgkx.dylib 239184 bytes，SHA256 9caff9c2071eccf12b0c90b331f8387a4ac25762979975814875c46c0e1e2347。
- 出包：`tools/inject.py --ipa ../ipa/Gboard_2.3.19.ipa --dylib <CI dylib> --app-group group.zunbengege.top --dict dist/user_dictionary.db`，输出 `dist/gboard-ntr-1.0-unsigned.ipa` 35980293 bytes，SHA256 09c3976561e5435c1c4ae739842c1cce9e09cad871e824832a97b0702de053a8。
- 独立验包：ZIP CRC OK；条目 2050（原 3633，原包含大量目录条目）；新增 `Frameworks/libgkx.dylib` 与 `Frameworks/user_dictionary.db`；移除 3 个 `_CodeSignature/CodeResources`；变更仅 `gboard_framework`、主 `Gboard`、`Gboard.appex/Gboard`；其余 2045 个原生文件 SHA256 逐字节相同；包内 dylib SHA256 与 CI artifact 一致。
- 加载命令：主 exe ncmds=50 各 1 条 `@rpath/libgkx.dylib`、rpath `@executable_path/Frameworks`；appex ncmds=48、rpath `@executable_path/../../Frameworks`；框架 8 处 app group 已改写为 `group.zunbengege.top`。
- 未覆盖：本机无 iOS clang/SDK，未做本地编译；未在真机上安装。闪烁是否消失、切页与 9↔26 切换、滑行输入是否回归均需用户自签后验收。

## 2026-11-20 切页仍闪一帧（二次修复）

- 现场：装 11df7f9f 包后不再闪退，但九键下反复点「拼音」↔「符号」分页时，换行键上仍闪一下带圆圈的笑脸。
- 根因：首版守卫的判据挂在对象同一性上（`key != gEmojiSoftKeyView`、`icon != gActionNativeIcon`），且入口先看 `!gActionKeyButton`。切页这一拍原生会对旧布局的 `GKBSoftKeyView` 调 `updateView`：此时 `GXKDetachActionKey` 已把按钮置空、原生又重建了 icon，两条判据都放行 → 笑脸写进图层并提交一帧，下一拍轮询才清。
- 修复：新增归属引用 `static __weak UIView *gGuardKey`，绑定建立时赋值（gkx.m:1233），撤键时**先于**还原用的原生 `updateView` 清空（gkx.m:589 附近）。守卫判据改为 `key == gGuardKey` + `restorationIdentifier == GXKEmojiKeyID` + `GXKNineKeyBodyForKey(key, gCurrentVC.view)` + 同 window + `GXKModelHasNativeActions`，图标每次 `GXKNativeIconForKey(key)` 现取，不再与按钮或图标对象同一性比较。
- 撤键顺序的理由：撤键里那次 `updateView` 是「还原」，若归属仍指向该键，守卫会把原生刚写回的图再搬走一次；本地存档为空时键会停在无前景状态。
- 回归：tests 10 个文件逐个跑全 OK（test_action_key 26 项，新增/改写 4 条断言：判据不得引用 `gEmojiSoftKeyView`／`gActionNativeIcon`／`!gActionKeyButton`、图标须先于清空现取、detach 内 `gGuardKey = nil` 先于原生 updateView）。
- 未覆盖：仍未真机验收；本机无 iOS clang/SDK。

## 2026-11-20 发布补做（Release 资产落后）

- 现场：本地 `dist/gboard-ntr-1.0-unsigned.ipa` 三次重打、CI 三次出新 dylib，但 `gh release view v1.0` 的资产一直是 35980290 bytes / SHA `11df7f9f…`，正文也写着旧哈希；用户第二次问「为什么又没发布 release」。
- 根因：流程缺步，不是操作失误。README 第 3 步止于「本地注入打包」，agent.md 速查止于「校验产物」，两处都没有「上传 Release」。
- 补做：新增 `tools/publish_release.py`（`gh release upload --clobber` → 置草稿再发布重置 `published_at` → 读回校验 size → 打印固定下载地址与远端 digest）；README 增「4. 发布到 GitHub Release」，agent.md 速查增第 6 步并新增避坑 11。
- 结果：`v1.0` 资产 35980398 bytes，远端 digest `sha256:0c330dc44d51cdc89e5185b720839ece35f63fd9b7722da19c1c61a5012cd0ee`，`published_at=2026-11-20T12:55:56Z`（原 11:04:15Z），正文 SHA-256 已同步。
- 注意：`--clobber` 会把旧资产先删再传，网络中断会留下空资产列表（本次即遇到一次，重跑即恢复）；`publish_release.py` 因此带了读回校验与 3 次重试。

## 2026-11-20 发布接入 CI（提交 5980876）

- 需求：让 push 之后自动发版，不再依赖人记得跑最后一步。
- 约束：仓库不含 Google 二进制（免责声明写明），CI 拿不到原始 `Gboard_2.3.19.ipa`，无法从头 `inject.py`。
- 解法：Release 上那份 IPA 已经是注入完成的成品（app group 已改写、词库已内嵌、`LC_LOAD_DYLIB` 已写入），重建只改变 `Payload/Gboard.app/Frameworks/libgkx.dylib` 一个文件。新增 `tools/swap_dylib.py` 只换这一个文件，并复用 `inject.py` 的 `unpack`/`repack`/`strip_signatures`，保证 CI 产物与本地手工产物在权限（0o755）与时间戳上一致。
- 工作流：`build` 之后新增 `publish`（ubuntu-latest、`contents: write`）：下载 artifact → `gh release download v1.0 --pattern gboard-ntr-1.0-unsigned.ipa` 取当前成品 → swap → `publish_release.py --refresh-sha`。
- `publish_release.py` 增强：上传 3 次重试（`--clobber` 先删后传，断线会留空资产列表，本次手工发版时真实遇到一次）；`--refresh-sha` 用正则改写正文的体积与 64 位 SHA-256；`--skip-upload` 供只刷新元数据时用。
- 本地验证 swap：用同一 dylib 换 → 包内 2050 条目、无增删、无字节变化（CRC OK）；换一个不同内容的 dylib → 只有 `Payload/Gboard.app/Frameworks/libgkx.dylib` 变化，条目数不变，CRC OK。
- 契约测试：新增 `tests/test_release.py` 12 项（swap 只换 dylib、保留 0o755、换后校验字节、拒绝无 dylib 的包；publish 上传重试、先 `--draft` 后 `--draft=false`、大小不符即失败；workflow 的 publish job `needs: build`、有 `contents: write`、调用两个工具）。
- 全量回归：11 个测试文件逐个 `python -B <file>` 全 OK。
- CI 验证：run 44740644479 success（build + publish 两个 job），publish 日志显示 `包内 libgkx.dylib 校验通过 (1 处)`、`published_at=2026-11-20T13:02:08Z`、资产 35980398 bytes。
- 未覆盖：本次 dylib 内容与上一版相同（仅工作流与脚本变化），因此产物哈希未变；真正「换 dylib 后 Release 自动更新」的验证要等下一次改 `dylib/` 的提交。仍未真机验收。

## 2026-11-22：第五版仍闪，重新核对原生显示生产链（本轮未出新包）

- 用户当前验收：拼音↔123↔符号切页瞬间仍闪圆圈；文字应像原生一样连续，不切换/消失。新建 文本文档 (10).txt 是第五版反馈，307行环形缓冲；保留6次retarget和6次grce exp，约606–618ms到期，但用户确认症状在切页瞬间。不能据此把到期还键升级为直接原因。
- 日志限制：没有UIView/model/icon/host/source-target身份、提交SHA或presentation帧；punct attach/detach是标点键计数，绝非动作键计数；gd/blk为0不证明没有绘制。过去按相同ID判断旧壳/未抓到update即无原生重画的解释撤回。
- 当前基线main 4dc86035d88928b50af905232280282141e0b87a已经包含第五版。源码实证：未绑定键的native updateView先绘制而guard返回，文字靠后续异步动作刷新；唯一文字UIButton跨host迁移，不属于物理nativekey。可构造旧TouchDown后跨键retarget，TouchUp复核新身份仍通过；GXKKeepLiveBinding读取保存的旧actions而不是live新model。属于可复现源码机制，不是新方案真机零闪证明。

### 原包固定事实与反证

- 原始IPA SHA256 c011730153df537f226052e766bbbf71834b5afcfeb13cba12f365d049719731；原始appex SHA256 711bc3dbeaec7cce6551d48286a7e5322b460e78aaaafa580e2ccd7fafb86566，cryptid=0。只在项目_scratch提取分析，原包未改。
- existing tools/objc_probe.py格式解析和类本地方法表核对：GKBSoftKeyView -updateView v16@0:8 VM0x10027ca3c；-setSoftKeyDef: v24@0:8@16 VM0x10027b944；GKBImageLayer -actionForKey: @24@0:8@16 VM0x100295d50，完整8字节 000080d2c0035fd6 = mov x0,#0; ret（下一方法VM0x100295d58）。方法恒返回nil。此前“实现actionForKey就会隐式淡出”的注释和强制测试是错误因果解释，已用原包断言替代。不能据此断言其他mask/presentation/显式动画不存在。
- 原生initView VM0x10027c530顺序：内容addSubview VM0x10027c7e4→内容frame→initSubViewsIDs VM0x10027c81c→updateView VM0x10027c82c。此时key可能尚未属于控制器root。initSubViewsIDs VM0x10027c858–0x10027ca3c递归按restorationIdentifier建表；自有UILabel不占用label/image ID，也不写此表。
- resetView VM0x10027c314–0x10027c518遍历native host全部subviews remove；hostView getter VM0x10027e17c–0x10027e1e0可返回self。原生layoutSublayersOfLayer VM0x10027b62c–0x10027b760使用hostView.subviews.firstObject当nativecontent。必须保留关联记录、在内容重建之后追加自有label，不能让label成为firstObject。
- setSoftKeyDef分支：同layout先clearLabelAndIcons、存model、updateView；布局重建reset、存model、initView；同指针可早退。hook要在模型替换前撤输入世代，完成原生链后验证并同步自己的label。仅靠keymove无法覆盖祖先同window移动，需controller完成layout同步收口。
- 工具覆盖：REA6.5.0 Windows adapter拒绝Mach-O（只接native PE/raw6502）；未修系统配置/安装engine。现有Ghidra12.1.4通过项目限定XDG_CONFIG_HOME/XDG_CACHE_HOME运行scoped headless Mach-O import，selected methods离线反汇编/反编译。证据是普通Ghidra原包分析，不伪标REA/MCP运行时证据。

### 本轮验证进度（2026-11-22恢复阶段历史；当前读回见末尾）

- 结构核验：aegis-workspace.py check --root D:/GitHub_Clone/gboard-ntr exit1，missing workspace directory: docs/aegis/adr；docs/aegis/baseline；docs/aegis/specs；docs/aegis/plans；missing workspace file: docs/aegis/README.md；docs/aegis/INDEX.md；docs/aegis/BASELINE-GOVERNANCE.md。项目当前采用既有轻量work载体，不为此bug扩建治理结构。ADR Gate hard-to-reverse=no，选择skip/轻记录；结构核验不证明语义或产物验收。

- tests/test_native_resources.py原包资源+ABI/constant-nil反证：8项通过，2026-11-22 23:05前执行，exit0，无skip。验证原包身份/字节与模型签名，不验证新dylib或真机帧。
- 正在实施：每物理key自有child UILabel + input-only transparent siblingbutton，native完成链同步reconcile；删除park/grace/rebind/stale-shell第二绘制归属。接续核验时生产仍是4170行旧实现、header缺失，不能把待实施设计说成已完成。已创建tests/native/ActionDisplayTests.m：23项same-TU生产UIKit用例，使用真实window/tree/hitTest/layer、仅fake原生模型接口；包含两host/native-first/reset/模型图标替换/触摸世代/空动作吞触摸/双可见key/return和26退出/三态/前景vs背景mask/离屏raster正负对照。Windows未执行UIKit。14项native-runner离线门禁及bash -n通过；这些结果仅证明离线门禁/接线，不验证新dylib或presentation。runner分别留xcodebuild exit-status.txt与最终final-exit-status.txt，门禁输出写verify-result.log并上传。计数仅适用于当前单fixture target；实际Xcode16 summary schema/真实运行仍需CI读回。
- native-scaffold-audit静态审阅805行/23用例及Xcode工程/runner，无新确定编译阻断；未编译/未跑UIKit。highlighted仅setter/model，sendActions不是UITouch，controller直接C wrapper不是已安装swizzle集成；offscreen model-layer raster不是presentation。最终生产交叉检查待writer落盘。前驱Release v1.0已读回：2026-11-22T14:19:44Z，35991603 bytes，digest=sha256:da167ef815c87b1804167261072d442b08a5c698d7fdb15b8993b839b8ead19a，当前本地IPA一致；不是本轮新包。
- 授权进展：2026-11-22 23:11用户明确批准回归通过后推送IamNewHands/gboard-ntr main→Actions arm64编译→覆盖既有v1.0安装包。尚未执行本轮生产编译、Simulator fixture、Remote CI、IPA、新真机首帧验收。任何源码/离线测试绿不等于用户零闪结果已实现。
- 前景边界复核：GKBImageViewWithBackground backgroundLayer getter VM0x1002962e0 / @16@0:8，setter VM0x100296a24；backgroundImage/highlightedBackgroundImage setter VM0x10029643c / 0x1002964c4。getter返回类/懒创建未证实。GKBImageLayer currentLayerForImage VM0x100295e20–0x100296080可返回自身或新普通CALayer mask并复制delegate；因此delegate/superlayer不能授权抑制，只认当前native icon.layer指针。背景setter始终透传，不宣称截获普通mask直接contents或presentation。

### 08:24读回（历史；复审修正见下）

- 源码：dylib/gkx.m:625引入逐键owner；dylib/action_key_display.h:169-291同栈挂本key UILabel与透明sibling input；:174-181冷启动先弱登记，不提前授权显示/输入；:293-318捕获/取消/校验generation与强制当前树唯一性；:328-332离场逐键退役。原生model/idToViewDict不写，native-firstObject校验先于自有label添加。
- Hooks：dylib/gkx.m:747-770保留真实void ABI、先native完成后reconcile；model变化先invalidate。:785-814仅目标class局部安装且检查参数编码。:1230-1235 toolbar样式从当前binding取，不再读旧全局；:1675同步controller完成layout收口，后续全树扫描仍合并异步。
- 执行：一次8套必要回归138项全通过，0skip；31 action/7 diag/14 language/43 perf/8原包/14 runner/13 release/8 toolbar几何；bash -n和git diff --check exit0。Windows bundled Python，未安装本地原生工具链。
- 凭据与发布：gh认证IamNewHands，origin=https://github.com/IamNewHands/gboard-ntr.git；remote main读回4dc86035d88928b50af905232280282141e0b87a。已有明确main→CI→既有v1.0覆盖授权，尚无本轮commit/push/new IPA。
- Native当前26用例（tests/native/ActionDisplayTests.m，848行），不是恢复时23。未执行；XCTest/UI树、模型layer离屏raster、sendActions和wrapper均不能升级成真机presentation/UITouch/swizzle全链证明。
- 继承误判已纠正：GKBImageLayer actionForKey恒nil，不能用“隐式淡出”解释闪烁；0.61s到期日志不对应用户切页瞬间；源码机制与已执行本地回归不等于实际零闪。工程交付结束后保留此真机验收缺口。

### 复审修正与受影响验证（2026-11-23 08:48）

- spec-review指出同key/body/root/session的alpha→0或移出root动画：模型先到终点，presentation仍可能可见；旧domain/Current误用GXKKeyIsVisible使label早退并恢复圆圈。这是源码反例，不是原生Gboard已命中链。
- 修正唯一逐键owner：dylib/action_key_display.h:119-138结构current不读模型可见性；:189-195结构domain不按alpha/geometry退役；:203-206可见性只决定clickAllowed；:256-266可见→不可见取消held generation。原生前景setter仍只守exact-current icon+已准备label，背景/模型不写。
- 仅扩展现有tests/test_action_key.py exact-icon契约与tests/native/ActionDisplayTests.m alpha/transform用例，native仍26项。0.3s动画块内检查model端点、reconcile前后label/图标守卫保持、旧TouchUp无输入；这是模型/UI树断言，不冒充presentation帧。
- Windows修正后action契约31项exit0/0skip、git diff --check exit0；此前138项保持历史，未重复全套。08:54独立spec-review给spec pass，原唯一Important源码反例关闭，指定邻近边界无新阻断；结论仅静态证据。

### 质量复审修正与定点验证（2026-11-23 09:24）

- quality-review最终报告2项Important / Implementation Drift（scope: both）：TouchDown后同key.userInteractionEnabled=NO，旧TouchUp仍可执行；同key原生16pt标题在bounds缩至1×1时，fit混入contentReady使confirmed label退役并恢复原生图像。两者为源码seam反例，不是已观察Gboard真机根因。
- dylib/action_key_display.h:203-204 clickAllowed现取native输入能力，:322-324 TouchUp再次复核，既有允许→不允许取消generation；display Current/domain不受交互能力影响，空actions覆盖按钮仍吞触摸。:211-218把native content结构ready与titleFits分开，未确认first admission仍要求fit，confirmed连续绑定不因临时bounds不足退役。缺内容/native return/26/拆树/session仍走原有退役。未改模型、字体、原生几何或language owner。
- tests/native/ActionDisplayTests.m既有输入generation、missing-content/first-fit和alpha/transform用例扩展，仍26项/937行；检查无layout的disabled TouchUp、禁用后再启用不复活旧touch、bounds1×1模型端点label及exact-icon守卫保留、未确认小键不能首次准备。程序sendActions/model动画断言不是presentation/UITouch证明。
- 09:24最新受影响tests/test_action_key.py 31项一次通过，exit0/0skip；git diff --check exit0。此前138结果保持历史，不重复全量、不叠加数字。业务源码343行header已冻结；09:29 spec-review定点spec pass，两项源码反例闭合、指定相邻valid case无削弱，09:36原quality-review最终定点复核通过：两项Important关闭、无新增Critical/Important/Minor；源码冻结状态可交既有CI。两审查均未执行测试，UIKit、arm64编译和新IPA尚待本轮CI，presentation/UITouch/真机未验证。
