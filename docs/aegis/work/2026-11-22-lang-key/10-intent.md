# 齿轮键「中/英」覆盖层 + 切页闪图收口

- 用户目标（m00002、m00130）：把九键左列第 4 键与 26 键右上角的齿轮键（切语言键）从「只有图标」改成「中/英」双字覆盖层：中文态高亮「中」、英文态高亮「英」，外观原生、切换不闪；同时修掉九键在拼音↔123↔符号分页快速切换时换行键仍闪原生小圆圈的问题。
- 证据基础（无 IDA）：IPA 内 appex 二进制内联布局表实证——`key_pos_9keys_left_4` 条目紧跟 `softkey_globe`，`key_pos_globe` 121 次出现全部为 26 键表条目；`softkey_globe` 定义只有 `softkey_icon` / `softkey_9keys_icon`，没有文字标签。布局名在 IPA 里只有文件名列表字符串，没有对应 `.pb` 文件，因此不按语言读表。
- 判据：键身份只认 `restorationIdentifier`（`key_pos_9keys_left_4` / `key_pos_globe`）+ 所在键盘体类（九键体内 / 非九键体内），两把键同时可见即放弃，遍历不完整即放弃。语言判据取 `textDocumentProxy.primaryLanguage`，取不到沿用上次判定。
- 方案：把原生图标存档后置 nil，在键的宿主容器上叠一个 `userInteractionEnabled = NO` 的按钮，画「中英」两字，当前语言那一字满不透明、另一字 `GXK_LANG_DIM_ALPHA`（0.35）透明度。触摸继续落到底下的原生键，切换语言完全走原生路径，不新增手势、不拦截触摸、不改键盘高度。
- 切页闪图收口：`GXKDetachActionKey` 记录刚撤的那把键与 0.60 秒宽限；窗口内 `gxk_key_updateView` 继续把原生圆圈搬走，窗口一到立刻放行并调一次原生 `updateView` 还原前景。扩展隐藏时宽限当场作废。
- 边界：只碰这两把键；不改 alpha/hidden/背景层/键帽样式；不碰其它键；不改输入逻辑。
- 成功证据：源码契约测试（`tests/test_lang_key.py`）、既有全量回归、CI arm64 编译、注入包结构校验；真机外观与闪烁需用户验收。
