# 证据

## 2026-11-22 取证（无 IDA，自写 Mach-O 解析）

- IDA MCP 全程 `server is disconnected`，改用自写解析脚本读 `Payload/Gboard.app/PlugIns/Gboard.appex/Gboard`。
- 九键键位：`keyboard_body_pinyin_ninekeys.nib` / `_9key_digit.nib` / `_9key_symbol.nib` 均为 `GKB9KeysSoftKeyboardView`，都含 `key_pos_9keys_left_4`；`keyboard_body_pinyin.nib` / `keyboard_body_zhuyin.nib` 为 `GKBSoftKeyboardViewWithFixedLayout` + `GKBZhQwertySoftKeyboardView`，只有 `key_pos_candidate_right_1..5` 与 `key_pos_symbols`，没有 globe 键。
- 内联布局表：偏移 18022092 处 `'key_pos_9keys_left_4', 'normal', 'softkey_globe ', 'enableForceTouch'`；`'key_pos_globe', 'normal', 'softkey_globe ', 'normal+enableForceTouch'` 121 处全为 26 键表条目 → 两把键同一 softkey 语义。
- softkey 定义：`'softkey_globe', 'softkey_icon'` 与 `'softkey_globe', 'softkey_9keys_icon'`，无 label 条目 → 原生只有图标。
- 布局名不可用：`GKBKeyboardViewHelper` 有 `layoutName` / `_currentLayoutName`，但唯一持有者是 `GKBPopupKeyboardHelper`（私有 ivar），视图树拿不到；IPA 内也没有任何布局 `.pb`（全包唯一 `.pb` 是 `en.lproj/EmojiSuggestTrie.pb`）。
- 语言接口：appex 里 `primaryLanguage` 字符串出现 0 次（是 Foundation 协议属性），`currentLanguage` 3 次、`languageCode` 4 次、`isChinese` 1 次。

## 2026-11-22 实现

- `dylib/gkx.m` 新增「齿轮键『中/英』覆盖层」一节：`GXKLangKeyIDMatches`、`GXKFindLangKey`、`GXKLangCurrentIsChinese`、`GXKLangAttributedTitle`、`GXKDetachLangKey`、`GXKUpdateLangKey`、`gxk_lang_updateView`，以及全局 `gLangKeyButton`。
- 守卫接线：`gxk_key_updateView` 里 `gxk_lang_updateView(key)` 必须排在笑脸键早退之前，否则齿轮键永远轮不到（本轮已修正一次顺序错误）。
- 刷新接线：`gkx_textDidChange`、`gkx_viewDidLayoutSubviews`、`gkx_viewDidAppear`、`GXKBumpPolling` 四处调 `GXKUpdateLangKey`；`gkx_viewWillDisappear` 与 `gkx_viewWillAppear`（被别的控制器接管）两处调 `GXKDetachLangKey`。
- 切页宽限：`GXK_FLASH_GRACE_SECONDS 0.60`、`gFlashKey` / `gFlashDeadline`、`gxk_flash_grace_active`、`GXKClearFlashGrace`；`GXKDetachActionKey` 记录，`GXKUpdateActionKey` 到点还原，`gkx_viewWillDisappear` 作废。

## 2026-11-22 验证

- `python tests/test_lang_key.py`：12 项 OK（键 ID 唯一、定位器不按几何/顺序、九键与 26 键互不冒领、纯视觉覆盖、存档先于清除、撤键只还原同一身份、守卫顺序、不碰键帽外观、两字只差透明度、语言判据、四处刷新两处撤键、宽限有界且可还原）。
- `python tests/test_action_key.py`：26 项 OK；`python tests/test_perf.py`：42 项 OK。
- 未覆盖：本机无 iOS clang/SDK，未本地编译；未在真机安装。中/英两字的实际观感、切语言后高亮跟随、九键分页快速切换是否还闪，均需用户自签后验收。

## 2026-11-22 构建与出包

- CI run 44986819186（提交 dcf13a8）**失败**：`dylib/gkx.m:689:70: error: property 'primaryLanguage' not found on object of type 'id<UITextDocumentProxy>'` —— SDK 的 `UITextDocumentProxy` 协议没有声明该属性，直接点属性编译不过。
- 修法（提交 6a86c2c）：新增 `@protocol GXKPrimaryLanguageProviding` 只声明 `- (NSString *)primaryLanguage;`，先用 `respondsToSelector:@selector(primaryLanguage)` 探测再发消息；取不到时退回公开声明的 `vc.textInputMode.primaryLanguage`，仍取不到才沿用上次判定。契约测试同步锁住「不得出现 `textDocumentProxy.primaryLanguage` 点属性写法」。
- CI run 44988474911（提交 6a86c2c）**success**：build 与 publish 两个 job 都通过，macos-15-intel / arm64 / iOS 12+。
- 产物：builds 分支 `builds/libgkx-6a86c2c.dylib` 256992 bytes，SHA256 `dd19f4290bacf038b2578ba8f4c7c13a2d023d9f87bad95c16a7848bde71e76e`；`builds/LATEST` = 6a86c2cdd3315b878d98022ea93cb2f44c68b382。
- Release v1.0 资产 `gboard-ntr-1.0-unsigned.ipa` 35984372 bytes，digest `sha256:8e157b170bd6468a1bc5e1220a9443dd57bf8ec600c193b9e0c1dfd7108ef53e`，2026-11-22T05:14:39Z 发布。
- 推送方式说明：本机 `git push` 走 schannel 一直报 `SEC_E_NO_CREDENTIALS (0x8009030e)`（curl 直连也是 000，代理不可用）。改用 `/c/Program Files/Git/bin/git.exe -c http.sslBackend=openssl` + gh 凭据助手可正常 fetch/ls-remote；两次提交是通过 GitHub REST（blobs → tree → commit → PATCH ref）推上去的，推完再用同一 git 二进制 fetch 对齐本地。

