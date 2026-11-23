# 最新续跑状态

> 文末为本轮状态；历次根因/零闪推断不是本轮真机验收。

## 笑脸键写入守卫（2026-11-20；源码/回归/CI/出包完成，真机待验收）

- 提交 `c86e7cb` 已推送 main；改动 4 处：`dylib/gkx.m`（新增守卫段 + 两处安装调用）、`tests/test_action_key.py`（新增 1 项契约测试）、`README.md`（新增一条说明）、`docs/aegis/work/2026-11-20-emoji-icon-guard/`。
- 守卫实现要点：`static void (*gOrigKeyUpdateView)(id, SEL);` 先透传原实现；只对 `key == gEmojiSoftKeyView`、`icon == gActionNativeIcon`、`GXKModelHasNativeActions` 成立的那一个键生效；清空前先把图存档进 `gActionNormalImage`／`gActionHighlightedImage`，撤键仍可还原。
- 返回类型处理（**已修正，首版判断错误**）：首版按 `id` 接管并回传返回值，真机切键盘即闪退。事后从 `Payload/Gboard.app/PlugIns/Gboard.appex/Gboard` 的 `__objc_const` 解出方法类型编码为 `v16@0:8`，即返回 void；按 `id` 包装会让 ARC 对从未被赋值的返回寄存器做 retain，故崩溃。现改为 `void` 包装、不读返回寄存器，并在安装时用 `method_getTypeEncoding` 校验首字符为 `v`，签名不符则不挂（宁可闪一帧也不崩键盘）；方法若来自父类则用 `class_addMethod` 新增而不改写父类。
- 安装时机：`gkx_init` 中在 `GXKApplyTelemetryBlockIfNeeded()` 之前挂一次（不影响 privacy 的 index 断言），`gkx_viewWillAppear` 中在 `GXKSymbolInstallHooks()` 之后补挂，幂等旗标 `gxk_icon_guard_hooked`。
- 回归：bundled Python 逐个文件跑 tests，10 个文件全 OK，共 134 项（test_action_key 26 项）；`git diff --check` exit 0。
- CI：run 44733139902 success（macos-15-intel，arm64/iOS12+/QuartzCore/ldid），artifact libgkx 239184 bytes，SHA256 `9caff9c2071eccf12b0c90b331f8387a4ac25762979975814875c46c0e1e2347`。
- 产物：`dist/gboard-ntr-1.0-unsigned.ipa` 35980293 bytes，SHA256 `09c3976561e5435c1c4ae739842c1cce9e09cad871e824832a97b0702de053a8`；输入原包 SHA256 `c011730153df537f226052e766bbbf71834b5afcfeb13cba12f365d049719731`。
- 验包：ZIP CRC OK；2050 条目，仅新增 dylib 与词库、移除 3 个旧 CodeResources；2045 个原生文件逐字节未变；允许差异仅共享框架／主 exe／appex 三个二进制；两个可执行文件各 1 条 `@rpath/libgkx.dylib`，rpath 未移动；框架 8 处 app group 改写为 `group.zunbengege.top`。
- 待真机：LCSign 自签安装后验证九键拼音↔符号页切换时换行键不再闪圆圈，以及三态切换、9↔26 切换、滑行输入无回归。

## 本轮：键内文字归属修复（2026-11-22，进行中）

- 需求：九键拼音↔123↔符号切页瞬间，动作键文字连续、无原生圆圈；重输/收起/换行、原生return、26键、键帽、主题与中英指示不变。第五版仍闪；用户说明是切页瞬间，约0.61秒到期日志不能解释此时刻。
- TaskStartSnapshot：main，HEAD 4dc86035d88928b50af905232280282141e0b87a；开始时tracked/untracked工作树为空，仅项目_scratch/2026-11-22-action-display生成临时物。开始时只授权本地分析修复；2026-11-22 23:11用户明确批准本轮回归通过后推送IamNewHands/gboard-ntr main、Actions编译并更新既有v1.0安装包，不建新tag/PR、不force-push。
- 证据：原包IPA c011730153df537f226052e766bbbf71834b5afcfeb13cba12f365d049719731；appex 711bc3dbeaec7cce6551d48286a7e5322b460e78aaaafa580e2ccd7fafb86566。GKBImageLayer actionForKey: 0x100295d50为mov x0,#0; ret，否定必然隐式淡出的历史解释。原生initView在内容addSubview/initSubViewsIDs后updateView，key可能尚未入root；当前guard未绑定会直接放行，文字依赖异步补齐。
- 因果等级：首帧显示归属缺口/跨键复用旧点击是源码可构造的proximate机制；没有新方案真机presentation帧，不能宣称全部实际闪烁根因闭合。风险反例：双可见实例、空动作新模型、原生子树重建、9↔26、旧TouchDown新TouchUp。
- Change Necessity：code-change。定时器延长不能拥有原生key物理生命周期。ArchitectureReviewRequired：yes；已独立复核，实施后规格→质量审查。
- 设计：每个原生目标key associated binding，非交互UILabel放在本key内继承隐藏/alpha/transform/祖先动画；透明sibling UIButton仅输入，不设文字/背景。不同key永不共享label/button。输入未授权时吞旧/歧义触摸，不透传原生表情。原生模型/idToViewDict只读，不冒用内容ID。
- 接线：native updateView同栈reconcile；仅GKBSoftKeyView局部didMoveToSuperview/didMoveToWindow确认九键归属后同步挂接；controller原layout返回后同步完成动作显示，其他扫描仍异步合并。前景阻挡仅exact live icon且本key label已准备时生效，背景不拦。子树重建恢复本key自己的label。
- 输入generation：model/icon/body/host/root/controller/session变化cancelTracking，TouchDown旧generation失效；点击复核唯一live目标及三态。空动作同ID过渡保留文字不执行输入。离场/native return/26先停止拦截，再撤自有label/button，按当前原生模型恢复。
- Pre-Edit Complexity：gkx.m 4170行、多owner，move-out/extract-first；动作显示提取dylib/action_key_display.h，gkx保留共享hook/生命周期/输入执行。删除park/grace/rebind/stale-shell第二归属，无新timer/fallback。语言owner不移植。Existence Check：复用现有动作职责的提取，不是并行owner。预算exceeded-and-governed，降低多时间窗和跨键交接责任。
- TDD Mode off / Route skipped（会话配置），无强制RED；真实生产seam+静态回归按比例验证。
- ADR Backfill：skip。逐键owner提取有真实取舍、无上下文会意外，但可直接版本回退，不涉及外部API/存储迁移，未满足hard-to-reverse；采用现有checkpoint/源码注释/README轻记录，落盘后同步事实。结构check exit1：当前仅有轻量work目录，缺docs/aegis/adr、baseline、specs、plans及README.md/INDEX.md/BASELINE-GOVERNANCE.md；这是workspace结构缺口，不是代码/测试失败。为不扩任务范围，不新建整套Aegis目录，不把结构工具当验收。

### 实施计划（历史记录；当前状态见下）

1. 2026-11-23 00:29恢复读回：production子agent已停止，交接确认无技术/权限阻断、此前没有落盘；lead接管单一源码写入。Slice Goal=落实既有逐键设计；Files=dylib/gkx.m及dylib/action_key_display.h；Boundary=不改原生模型/键帽/语言owner、不新增timer；Verification=静态全套+same-TU UIKit CI+两阶段审查；Stop=授权范围内交付或需要外部验证。header已创建、接线尚待gkx原子修改，不计为可编译实现。
   原计划：实现agent仅改dylib/gkx.m及新dylib/action_key_display.h：逐键label/input binding、同步native生命周期、退役旧显示窗口；不做Git/网络/递归委派。
2. lead维护独立测试文件，不覆盖实现文件：替换失效timer-string断言，保留三态/ABI/键帽/26边界；新增same-TU生产UIKit fixture，覆盖首帧、模型/图标替换、双实例、旧TouchUp/禁止透传、隐藏/拆树/退出。Windows执行全部Python回归，Simulator只能交付fixture不能在本机执行。
3. 规格审查先核需求/边界，修完后质量审查核生命周期/ARC/ABI/子树/identity；lead审完整diff及fresh结果，更新证据边界。已将生产UIKit fixture的tests/native/run_tests.sh接入现有build job、置于arm64编译前且无continue-on-error，失败不发布。
   - 本轮已执行未触碰相邻功能57项回归（输入/常用语/隐私/标点/toolbar/打包）通过；Release契约13项、原包资源/ABI8项通过。生产新代码全量回归/Simulator尚未执行，不能加总成新方案验收。
   - 接续核验：原会话推送授权逐字读回（session-680c500a-9334-4087-8854-5c7a7798ea34，seq957/962）；复核时生产gkx.m仍为4170行旧版，新header尚未写入，故此前计划/README不视为已实现。lead已补齐same-TU生产UIKit fixture（23用例，未执行），14项native-runner离线门禁与bash -n通过；CI固定已安装Xcode16.4+对应runtime、15分钟上限、失败日志/xcresult保留、严格核对当前单fixture target全部23用例passed且0skip。xcodebuild退出与最终门禁退出单独存档，verify-result.log保留。summary计数尚无真实Xcode输出验证，不冒充逐method身份核验。模型树/离屏raster测试不能替代presentation或真机零闪。
   - native-scaffold-audit已完成805行fixture/Xcode/runner静态审阅，无新确定编译/门禁阻断；未编译。待生产writer ready后再核最终API/生命周期/constructor。Release前驱已读回：v1.0/published_at=2026-11-22T14:19:44Z，35991603 bytes，SHA256 da167ef815c87b1804167261072d442b08a5c698d7fdb15b8993b839b8ead19a；与当前dist逐哈希一致。此为旧包，不是本轮交付。
4. 本次main推送/Actions编译/自动替换v1.0已获明确批准；本地回归与独立审查通过后执行、读取CI/新包验证。真机切页结果仍由用户验收，无新包真机证据不能称零闪已解决。

### 08:24快照（历史；08:48修正进度见下）

- 生产已落盘：dylib/gkx.m 3644行，动作显示提取到dylib/action_key_display.h 332行；已接updateView/setSoftKeyDef/didMoveToSuperview/didMoveToWindow及controller完成layout同步收口。冷启动先弱登记物理键、控制器就绪后补齐本键显示；toolbar旧全局消费者已改读逐键binding。此前“生产未接线”是恢复时事实，不是当前状态。
- 显示与输入归属：每key独立label/button；确认过的同key/body/root/controller/session空动作过渡保留文字但拒绝输入，新空动作key保持原生。旧TouchDown generation作废，点击强制当前树唯一性；背景和普通mask不拦，语言owner独立。park/grace/rebind/stale-shell旧owner已退役。
- 必要本地回归已执行一次：31 action + 7 diag + 14 language + 43 perf + 8原包资源/ABI + 14 native-runner + 13 release + 8 toolbar几何 = 138项全部通过、0skip，exit0；bash -n与git diff --check通过。此结果只覆盖源码契约/原包/工具门禁，不证明UIKit或真机零闪。
- Native fixture最终26用例、848行，直接include生产TU；CI只跑这组已存在fixture后编译arm64，再发布既有v1.0。计数由源码提取，不写死23；当前尚未执行Simulator/本轮CI/新包。
- 当前main仍为4dc86035d88928b50af905232280282141e0b87a，remote main同SHA；无新commit/push。规格审查进行中，随后质量审查；通过后执行已授权构建发布。
- Complexity Closure：exceeded-and-governed。gkx动作显示的跨键全局/时间窗owner撤掉，header成为唯一逐键owner；gkx保留共享native hook/生命周期与既有输入三态。新增same-TU fixture是单一native测试责任，避免复制生产算法；不为800行阈值拆散它。无新增display timer/fallback，无额外治理目录。
- 交付边界：工程修复/新包交付与真机验收分开；iOS27 Gboard切页presentation、真实UITouch、滑行输入仍须安装后验收。

### 本轮复审修正：显示结构归属与输入可见性分离（2026-11-23 08:48，已落盘/待独立复审与CI）

- Slice Goal：修正已确认物理键在祖先alpha→0或移出root动画期间过早摘字/恢复笑脸的源码反例。Parent=既有逐键实施计划；Files=dylib/action_key_display.h、tests/test_action_key.py、tests/native/ActionDisplayTests.m；不改原生模型/键帽/语言owner、无timer/fallback、新测试框架或重复全量测试。
- Change Necessity：code-change；不改或只改文档不能让文字随祖先连续退场。PatchShape=已有归属判据修正；CanonicalOwner=逐键display binding；UpwardDrillSignal=exact-icon守卫与输入消费者共享Current，误把模型可见性当显示归属。Ripple=守卫保持结构current，点击资格独立读可见性并取消旧generation；真实拆树/native return/26/session退出仍退役。
- Minimality Check：sufficient repair；复用现有owner，撤销可见性负责display retirement的无效职责，保留其输入安全职责。Pre-Edit Owner-Fit=local-fix-without-new-responsibility/edit-in-place；header已提取，仍为同一逐键职责，不再次拆分。ArchitectureReviewRequired仍yes；按既有规格→质量顺序复审。
- TDD Mode off / Route skipped保持；只扩展已有alpha/transform fixture与exact-icon源码契约，运行受影响action契约一次；既有138项结果保留历史，不重跑全套。原生26用例仍由既有CI验证；不把模型终态/sendActions当presentation或真机零闪。
- 已修正规格复审的1项Important：display domain/Current只按真实key/root/window/body/native identity判断；alpha/transform模型不可见只撤clickAllowed并cancel旧generation，不摘label或提前恢复原生圆圈；真拆树/native return/26/session退出仍退役。dylib/action_key_display.h 339行；既有26项native fixture 883行，仅扩展原alpha/transform用例。
- 修正后受影响action契约31项一次通过（exit0，0skip），git diff --check通过；此前138项离线通过不重复计数/不重跑全套。规格复核已送出，质量审查随后；原生fixture与arm64需已授权CI，本轮仍无commit/push/new IPA。
- 08:54独立spec-review复核通过：原唯一Important / Implementation Drift（scope: both）已关闭，指定return/26/拆树/session/空动作邻近边界无新规格阻断；未执行测试/编译。质量审查quality-review已启动，只读、无新增测试范围。
- 09:02质量审查进行中，业务源码已冻结；既有commit/push/watch/download/验包脚本已读回并就绪，尚未执行本轮Git mutation或CI。原包/前驱/当前dist哈希已核对，remote main仍4dc86035d88928b50af905232280282141e0b87a。dylib生产8文件旧park/grace/rebind/stale-shell/globalbutton符号扫描0命中、完整扫描。
- 临时清理许可未获得：此前针对两task scratch目录的提问超时，没有答案；08:44前置审批策略关闭不是对删除既有数据的授权。暂停scratch删除，不跨项目清理；dist最终只更新当前两个binary，保留原始IPA。
- 09:13 quality-review发现Important / Implementation Drift（scope: both）：TouchDown后native key.userInteractionEnabled=NO，而sibling input不随key禁用；当前clickAllowed和TouchUp没有重读能力，仍可能执行。lead已按当前源码核实，推送暂停。Change Necessity=code-change；CanonicalOwner=逐键input资格；MinimumBoundary=clickAllowed/TouchUp纳入native交互能力、现有允许→禁止generation取消复用，不纳入display Current/domain，不disable overlay破坏空actions吞触摸。TDD off/skipped，不重跑全套；最终报告的fit边界待收齐后一并做受影响修正。
- 09:20 quality-review最终报告2项Important / Implementation Drift（scope: both），另1项为已确认同key原生16pt文字在bounds动画至1×1时，contentReady的fit门槛触发retire/恢复笑脸。lead已核对原生font、bounds与退役路径，属于源码反例而非已观察Gboard根因。
- 本slice修复两条既有owner判据：native input capability进入clickAllowed和TouchUp现取复核；原生结构ready与first-fit admission分离，已确认同树归属不因临时bounds不足退役。Change Necessity=code-change（docs/no-change不足）；PatchShape=已有owner判据补全；CanonicalOwner=逐键display/input binding；UpwardDrillSignal=display admission与输入资格混为content readiness；Decision=fix owner，Minimality=sufficient repair，OwnerFit=edit-in-place/no-new-responsibility，保留结构缺失/native return/26/拆树/session退役、原生字体/几何/中英owner不改。
- 验证边界：扩展既有native输入generation与alpha/transform用例，不增加26 fixture数量/新套件；受影响31action源码契约一次复跑，既有138结果不重复执行/累加。TDD Mode off / Route skipped保持；两项需质量定点复核后进入已授权CI。
- 09:24两项修正已落盘：header343行，input native capability独立纳入clickAllowed/TouchUp；contentReady与titleFits分离，首次fit门槛保留。native fixture937行/26项未增数量；最新action31项一次exit0/0skip、git diff --check exit0，未重复138全套。源码冻结；09:29 spec-review定点spec pass，两项源码反例闭合，指定相邻有效边界无削弱。09:36原quality-review最终定点复核通过：原两项Important均关闭，无新增Critical/Important/Minor；未增timer/fallback/owner、指定原生边界保持。进入既有授权的main提交/推送与CI；原生26/arm64/新IPA仍待执行，不能宣称发布或真机零闪完成。
- 已明确动画反例不是Gboard真机已命中根因。Stop=质量问题修正与复核通过后执行原有构建发布授权，真机presentation/UITouch/滑行结果仍待用户。
- 09:38提交并正常推送main：7c2079e95266eaa3b3b64faea50516f49afaf190，message=fix: bind nine-key action display to each native key；仅21个已审本任务文件，提交后工作树为空，remote main已读回同SHA。现有push触发CI run45095613124（https://github.com/IamNewHands/gboard-ntr/actions/runs/45095613124），已失败；唯一watcher job=bash-b3aed6260fe34b64已收集，detail exit code:1，结果存当前scratch/ci-result.json。Simulator目标实际编译/link后26个test开始均SIGSEGV(signal11)，被Xcode重启换case，最终15分钟超时；arm64/build/publish未执行，新IPA未发布。
- 10:08当前slice=定位既有native gate共同crash，不新增测试工程/用例/生产fallback，不放宽门禁或盲目重跑。证据=ci-failure.log:936-1283及failure-native-evidence内首Session-GXKActionDisplayTests-2026-11-23_014740-4eBZiA.log:284/302；retained日志无调用栈/.ips。原生hook/fixture shared setUp:299-324/控制器host仍未排除，根因未知；quality-review复用为只读定点诊断。quality-review静态诊断收口：未确证共同nil/递归/void ABI根因，平台controller/window host seam只是疑点。10:14仅在现有fixture加[DEBUG-native-ci] C phase标记，未装信号handler；hook/images/controller/root/window/returnkey前后定位，26方法/所有断言/runner/15min失败门禁不变。14项既有native-runner offline contracts一次exit0、diff-check0；quality-review定点复核通过，未见副作用阻断；仅允许一次诊断CI定位，不能称崩溃已修复。临时probe在定位修复后全部移除，再交最终门禁；生产源码保持不动，TDD off/skipped、此前138/31不重复累计。

## 切键盘闪退修复（2026-11-20，同批次）

- 现象：装 09c39765 包后切到 Gboard 键盘即闪退。
- 根因：守卫按 `id` 接管 `-[GKBSoftKeyView updateView]`，但该方法类型编码是 `v16@0:8`（void）。ARC 下 `id` 返回值会对返回寄存器做 `objc_retainAutoreleasedReturnValue`，void 方法没有赋值该寄存器，首次布局调用即崩。
- 修复提交 `5b6bd55`：`static void (*gOrigKeyUpdateView)(id, SEL);`、`static void gxk_key_updateView(...)` 不再读返回寄存器；安装前用 `method_getTypeEncoding` 校验首字符为 `v`，不符则不挂；方法若继承自父类用 `class_addMethod` 新增。
- CI：run 44735557750 success；dylib 239232 bytes，SHA256 `df495d715023fc05273fe736cb9d3ffe71cee186607d4f0a04a16a7d67a20e9c`。
- 产物：`dist/gboard-ntr-1.0-unsigned.ipa` 35980290 bytes，SHA256 `11df7f9fa60bee2a0057c590381f0cec164a9bc9c624c7d60196591cb1118ccc`；验包 CRC OK、2050 条目、新增 dylib 与词库（1688094 bytes）、移除 3 个 CodeResources、包内 dylib 与 CI 产物同哈希。
- 教训：从二进制方法表解类型编码，不要凭「取不到编码串」推断签名；包装未知签名方法一律先校验。

## 切页仍闪一帧的二次修复（2026-11-20，同批次）

- 现场：11df7f9f 包不闪退，但九键「拼音」↔「符号」反复切页时换行键仍闪一帧笑脸。
- 根因：首版守卫判据是对象同一性（`key != gEmojiSoftKeyView`、`icon != gActionNativeIcon`）且入口先看 `!gActionKeyButton`。切页那一拍原生对旧布局调 `updateView`，此时按钮已被 detach 摘掉、icon 已被原生重建，两条都放行 → 笑脸提交一帧。
- 修复：新增 `static __weak UIView *gGuardKey` 作归属；绑定建立时赋值，撤键时先清空再调还原用的原生 `updateView`；守卫改判「归属键 + emoji id + 九键 body + 同 window + 有原生 action」，图标每次现取。
- 回归：tests 10 文件全 OK；test_action_key 26 项，新增断言锁定「判据不得引用按钮/图标同一性」「图标先现取再清空」「gGuardKey = nil 先于原生 updateView」。
- 发布（补做）：本次三包（c86e7cb / 5b6bd55 / 61b8d32）都只重打了 `dist/`，Release 资产一直是旧的，用户两次追问「为什么又没发布 release」。已补 `tools/publish_release.py` 并把「第 6 步 发布」写进 README 与 agent.md 速查。最终 Release：tag `v1.0`，资产 `gboard-ntr-1.0-unsigned.ipa` 35980398 bytes，远端 digest `sha256:0c330dc4…cd0ee`，`published_at` 刷新为 2026-11-20T12:55:56Z，正文 SHA-256 已同步。
- 发布自动化（提交 `5980876`）：CI 新增 `publish` job（needs: build，contents: write）。仓库不含 Google 二进制，CI 不从原始包重新 inject，而是下载 Release 上那份成品 IPA，用新增的 `tools/swap_dylib.py` 替换 `Frameworks/libgkx.dylib`（复用 inject.py 的 unpack/repack/权限逻辑），再调 `tools/publish_release.py --refresh-sha` 覆盖上传并改正文哈希。`publish_release.py` 同时加了上传重试（`--clobber` 先删后传，断线会留空资产列表）。新增 `tests/test_release.py` 12 项锁定契约。验证 run 44740644479 全绿（build + publish），Release `published_at` 刷新为 2026-11-20T13:02:08Z，资产 35980398 bytes、digest 不变（本次 dylib 未变）。

