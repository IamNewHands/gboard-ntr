# 最新续跑状态

## 齿轮键「中/英」覆盖层 + 切页闪图收口（2026-11-22；源码/回归完成，CI 与真机待办）

- 改动面：`dylib/gkx.m`（新增覆盖层一节 + 守卫接线 + 宽限窗口）、`tests/test_lang_key.py`（新增 12 项契约）、`README.md`（第 8 条功能）、`docs/aegis/work/2026-11-22-lang-key/`。
- 键身份：只认 `restorationIdentifier` 的 `key_pos_9keys_left_4`（九键）与 `key_pos_globe`（26 键），再叠加「必须在九键体内 / 必须不在九键体内」；两把键同时可见即放弃，遍历不完整即放弃，绝不按坐标或遍历顺序猜。
- 覆盖方式：原生前景存档后置 nil，在键宿主上叠 `userInteractionEnabled = NO` 的按钮画「中英」；当前语言那一字满色、另一字 `GXK_LANG_DIM_ALPHA`(0.35)。不新增手势、不拦触摸、不改键盘高度。
- 守卫顺序（**本轮修正过一次**）：`gxk_key_updateView` 里 `gxk_lang_updateView(key)` 必须排在笑脸键早退 `if (key != gGuardKey ...) return;` 之前，否则齿轮键永远轮不到。
- 切页宽限：`GXK_FLASH_GRACE_SECONDS` 0.60 秒；`GXKDetachActionKey` 记录刚撤的键，`GXKExpireFlashGraceIfNeeded` 在守卫与更新路径各自兜底（轮询空闲会停表，只在更新路径作废会让键停在空白前景），扩展隐藏时 `GXKClearFlashGrace` 当场作废。
- 验证：`tests/test_lang_key.py` 12 项 OK、`tests/test_action_key.py` 26 项 OK、`tests/test_perf.py` 42 项 OK，其余 9 个套件同样全绿。
- 未完成：本机无 iOS clang/SDK，未本地编译；`git push` 因 schannel 无凭据失败（`gh auth status` 显示已登录 IamNewHands，token 具备 repo/workflow 权限，可用 `gh` 走 HTTPS 推送）；真机验收未做。
