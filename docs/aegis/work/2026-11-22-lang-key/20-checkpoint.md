# 最新续跑状态

## 中英判据根因修复 + 闪烁埋点（2026-11-22；源码/回归完成，CI 与真机待办）

### 根因（已由产物实证，不再是猜测）

扩展 `Payload/Gboard.app/PlugIns/GboardExtension.appex/Info.plist` 里：

```
NSExtensionAttributes.PrimaryLanguage = "mul"
NSExtensionPointIdentifier = "com.apple.keyboard-service"
NSExtensionPrincipalClass = "GKBUIInputViewController"
```

"mul" 是「多语言」占位值。所以宿主回给扩展的语言恒为 `mul`，
`GXKLangCurrentLanguage(vc)` 拿到 `"mul"`，`hasPrefix:@"zh"` 永远为假
→ **中文输入法下也永远高亮「英」**。这不是时序问题，靠补帧修不好。

### 修法：改问 Gboard 自己的语言对象

- 新增 `@protocol GXKLangIDProbe`（`+ (id)currentLanguage` / `- (BOOL)isChinese`）
  与 `static NSInteger GXKLangReflectedState(void)`：`NSClassFromString(@"GKBLanguageID")`
  + `respondsToSelector` 双重校验，命中返回 1/0，类或方法不在返回 -1。
  静态量只解析一次，之后每拍只调一次类方法。
- 为什么是 `GKBLanguageID` 而不是 `GKBLanguageManager`：前者有类方法 `+currentLanguage`，
  零实例依赖；后者只有实例方法且没有公开共享实例入口，反射成本高得多。
- 为什么一定加载得到：appex 的 LC_LOAD_DYLIB 里非系统依赖只有
  `@rpath/gboard_framework.framework/gboard_framework`（rpath = `@executable_path/../../Frameworks`），
  扩展进程必然已加载该 framework。
- 兜底语义保留：反射不可用 → 退回原宿主语言判据；再取不到 → 保持 `gLangChinese`（不闪）。

### 闪烁埋点（全部走「设置 → 诊断日志」开关，关态零成本）

| 埋点 | 位置 | 行格式 |
|---|---|---|
| 布局每拍 | `gxk_key_updateView`，仅两把接管键 | `upd <id> own=0/1 grace=0/1` |
| 原生重画表情键 | 同上，`icon.image/highlightedImage` 非空才算 | `gd emoji g=own/grace` |
| 原生重画齿轮键 | `gxk_lang_updateView` | `gd lang <id>` |
| 撤键 | `GXKDetachActionKey` | `det emoji <id>` |
| 宽限作废 | `GXKExpireFlashGraceIfNeeded` | `grce exp <id>` |
| 语言判据 | `GXKLangCurrentIsChinese`，仅状态变化时 | `lang src=<src> state=1/0/-1` |

- `gd` 两行只在原生**真的**把圆圈画回来时写：正常帧不进 300 行环形缓冲，闪的那几拍才看得见。
- `lang` 只在状态翻转时写：0.2 秒一拍，不变化就一行不写。
- 原型 `static void GXKPunctDiagLog(NSString *fmt, ...);` 放在 `dylib/gkx.m:35` 附近：
  `punct_diag.h` 到 1907 行才 import，而埋点最早在 574 行。
- 守卫顺序保持不变：`GXKIsOverlayKey(key)` 是单独函数，守卫主体里
  `gxk_flash_grace_active(key)` 仍排在 `isEqualToString:GXKEmojiKeyID]` 之前
  （`tests/test_lang_key.py::test_page_switch_grace_window_is_bounded_and_restores_native` 盯着这条）。

### 验证

- `cd gboard-ntr && python -m unittest discover -s tests -p 'test_*.py'` → **Ran 161 tests, OK**。
- 新增 2 项契约（`tests/test_diag.py`）：
  `test_language_decision_prefers_gboard_language_object`（反射优先于宿主语言、保留 zh 兜底）、
  `test_flash_instrumentation_stays_behind_the_switch`（埋点全走 GXKPunctDiagLog、守卫顺序不乱、原型早于使用）。

### CI 与产物（已完成）

- 提交 `8c8582e`，run [44993577002](https://github.com/IamNewHands/gboard-ntr/actions/runs/44993577002) → **success**（编译 + 换 dylib + 发 Release 全绿）。
- Release `v1.0` 的 `gboard-ntr-1.0-unsigned.ipa`（35985267 字节）已刷新。
- 把该 IPA 里的 `Payload/Gboard.app/Frameworks/libgkx.dylib`（257296 字节）抽出来做字符串核对，
  全部命中：`GKBLanguageID`、`lang src=%@ state=%ld`、`upd %@ own=%d grace=%d`、
  `gd emoji g=%@`、`gd lang %@`、`det emoji %@`、`grce exp %@`、`lang=language decision`、`isChinese`。
  → 说明这次改动真的进了安装包，不是只改了源码。

### 未完成

- 真机验收（唯一剩余项）：装 Release IPA → 设置里打开「诊断日志」→ 切中英、切页 → 长按 HUD 复制日志回传。

### 真机验收步骤

1. 装包 → 设置 → 诊断日志（开）。
2. 键盘上切换中文/英文各两次，观察齿轮键高亮是否跟随。
3. 切页（九键↔26 键）几次，看是否还闪小圆圈。
4. 长按 HUD 复制，粘回聊天。
5. 判读：`lang src=GKBLanguageID state=1` 应随中英翻转；若出现 `state=-1` 说明反射没命中，
   若出现 `src=mul` 说明退回了宿主判据（即修复未生效）。
   闪圆圈看 `gd emoji`/`gd lang` 是否出现在 `own=0 grace=0` 的 `upd` 之后 —— 那就是漏网的一帧。
