#!/usr/bin/env python3
"""齿轮键「中/英」覆盖层源码契约；不声称 UIKit 运行时行为。

本机没有 clang，真机行为靠 GitHub Actions 编译后再验；这里锁住几条硬约束：
    1. 只认两把已证键 ID（九键 key_pos_9keys_left_4、26 键 key_pos_globe），
       绝不按坐标、按键顺序或标题文字找键；
    2. 覆盖按钮是纯视觉层（userInteractionEnabled = NO），不改触摸链、
       不新增手势，切换语言仍走原生路径；
    3. 原生图标必须先存档再清，撤键时按原样还原，且只在同一把键、
       同一个 icon、同一个 model 上还原；
    4. 守卫分支必须排在笑脸键早退之前，否则齿轮键永远轮不到；
    5. 中/英两字只改颜色透明度，不换字体族、不加背景色；
    6. 覆盖层必须是**中英键自己的子视图**（与换行键同一条归属规则），
       挂在宿主容器上会被原生 bring-to-front 或重建键盖掉，露出一帧原生齿轮。

Run exactly this file:
    python tests/test_lang_key.py
"""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "dylib/gkx.m"


def function_body(source, signature):
    """按大括号配对截取函数体，包含嵌套块。"""
    start = source.index(signature)
    brace = source.index("{", start)
    depth = 0
    for i in range(brace, len(source)):
        ch = source[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return source[start:i + 1]
    raise AssertionError(f"unbalanced braces for {signature}")


RECONCILE = "static void GXKReconcileLangDisplay(UIView *key) {"


class LangKeySourceContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = SOURCE.read_text(encoding="utf-8")

    def test_only_the_two_verified_key_ids_are_used(self):
        self.assertIn('static NSString *const GXKLangKeyID9 = @"key_pos_9keys_left_4";', self.source)
        self.assertIn('static NSString *const GXKLangKeyID26 = @"key_pos_globe";', self.source)
        matcher = function_body(self.source, "static BOOL GXKLangKeyIDMatches(UIView *key) {")
        self.assertIn("restorationIdentifier", matcher)
        self.assertIn("GXKLangKeyID9", matcher)
        self.assertIn("GXKLangKeyID26", matcher)

    def test_finder_never_falls_back_to_geometry_or_tree_order(self):
        finder = function_body(self.source, "static UIView *GXKFindLangKey(UIView *root) {")
        self.assertIn("GXKLangKeyIDMatches", finder)
        # 两把键同时可见时必须放弃，不能按遍历顺序挑一个。
        self.assertRegex(finder, r"if\s*\(candidate\s*&&\s*candidate\s*!=\s*v\)\s*return nil")
        # 遍历不完整同样放弃。
        self.assertIn("if (stack.count) return nil", finder)
        for retired in ("frame", "center", "convertRect", "sortedArray", "indexOfObject"):
            self.assertNotIn(retired, finder)

    def test_nine_key_and_qwerty_key_do_not_claim_each_other(self):
        finder = function_body(self.source, "static UIView *GXKFindLangKey(UIView *root) {")
        self.assertIn("GXKNineKeyBodyForKey", finder)
        self.assertIn("isEqualToString:GXKLangKeyID9] ? (nineBody != nil) : (nineBody == nil)", finder)

    def test_overlay_is_owned_by_the_key_itself(self):
        """核心回归：按钮必须是键自己的子视图，且在同一拍提到最前。

        旧实现把按钮挂在 GXKActionHostForKey(key)（键的父容器）上，原生把键
        bring-to-front、或整批重建键内容时覆盖层就被盖住/丢失，露出原生齿轮，
        只能等 0.2 秒轮询补回来。
        """
        reconcile = function_body(self.source, RECONCILE)
        self.assertIn("if (btn.superview != key) [key addSubview:btn];", reconcile)
        self.assertIn("if (key.subviews.lastObject != btn) [key bringSubviewToFront:btn];", reconcile)
        # 不得再挂到宿主容器上：宿主是键的父视图，归属不对。
        self.assertNotIn("[host addSubview:btn]", reconcile)
        self.assertNotIn("GXKActionHostForKey", reconcile)

    def test_overlay_is_purely_visual_and_keeps_native_touch_path(self):
        reconcile = function_body(self.source, RECONCILE)
        self.assertIn("btn.userInteractionEnabled = NO", reconcile)
        # 覆盖层不得挂任何手势或点击回调：切换语言必须继续由原生键处理。
        for retired in ("addGestureRecognizer", "addTarget", "touchesBegan", "hitTest"):
            self.assertNotIn(retired, reconcile)
        self.assertIn("[UIColor clearColor]", reconcile)

    def test_native_foreground_is_archived_before_clearing(self):
        reconcile = function_body(self.source, RECONCILE)
        archive = reconcile.index("binding.normalImage = icon.image")
        clear = reconcile.index("GXKClearIconImages(icon)")
        self.assertLess(archive, clear)
        # 与换行键同一条顺序：先认领，再存档，最后无条件清。
        self.assertLess(reconcile.index("binding.prepared = YES"), clear)
        # 清空必须无条件执行：只在有图时才清会漏掉「原生刚画上又被搬走」的那一帧。
        self.assertNotRegex(reconcile, r"if \(icon\.image\) \{\s*binding\.normalImage[^}]*GXKClearIconImages")

    def test_detach_restores_only_the_same_native_identity(self):
        detach = function_body(self.source, "static void GXKDetachLangKey(void) {")
        identity = detach.index("GXKNativeIconForKey(key) == oldIcon")
        self.assertLess(identity, detach.index("oldIcon.image = normalImage"))
        self.assertLess(identity, detach.index("oldIcon.highlightedImage = highlightedImage"))
        self.assertIn("softKeyDef == oldModel", detach)
        # 归属先释放再调原生 updateView：这次重画是还原，守卫不能再把图搬走。
        self.assertLess(detach.index("binding.prepared = NO"), detach.index("updateView]"))
        # 没接管过的键不动：否则会触发多余重画。
        self.assertIn("if (!binding || !binding.prepared) continue;", detach)

    def test_guard_branch_runs_before_the_emoji_early_returns(self):
        guard = function_body(self.source, "static void gxk_key_updateView(id self, SEL _cmd) {")
        self.assertIn("gxk_lang_updateView(key)", guard)
        self.assertLess(guard.index("gxk_lang_updateView(key)"),
                        guard.index("GXKReconcileActionDisplay(key)"))
        lang_guard = function_body(self.source, "static void gxk_lang_updateView(UIView *key) {")
        self.assertIn("binding.prepared", lang_guard)
        self.assertIn("binding.normalImage = icon.image", lang_guard)
        # 与笑脸键各自存档，互不覆盖。
        for retired in ("gActionNormalImage", "gActionHighlightedImage"):
            self.assertNotIn(retired, lang_guard)
        # 原生重画后同一拍把按钮提回最前，否则原生内容会盖住我们的文字。
        self.assertIn("GXKReconcileLangDisplay(key)", lang_guard)

    def test_guard_does_not_touch_keycap_appearance(self):
        guard = function_body(self.source, "static void gxk_key_updateView(id self, SEL _cmd) {")
        for retired in ("hidden", "alpha", "backgroundLayer", "backgroundColor", "cornerRadius"):
            self.assertNotIn(retired, guard)

    def test_two_titles_differ_only_by_alpha(self):
        title = function_body(self.source, "static NSAttributedString *GXKLangAttributedTitle(BOOL chinese, UIColor *color, UIFont *font) {")
        self.assertIn('@"中英"', title)
        self.assertIn("GXK_LANG_DIM_ALPHA", title)
        self.assertIn("NSMakeRange(0, 1)", title)
        self.assertIn("NSMakeRange(1, 1)", title)
        self.assertIn("NSForegroundColorAttributeName", title)
        # 只用同一个前景色加透明度，不引入第二个颜色常量。
        self.assertEqual(title.count("colorWithAlphaComponent"), 1)

    def test_language_judgement_prefers_host_language_and_keeps_last(self):
        # SDK 的 UITextDocumentProxy 协议没有声明 primaryLanguage（CI 上直接点属性会编译失败），
        # 必须按协议探测后再发消息。
        probe = function_body(self.source, "static NSString *GXKLangCurrentLanguage(UIViewController *vc) {")
        self.assertIn("respondsToSelector:@selector(primaryLanguage)", probe)
        self.assertIn("GXKPrimaryLanguageProviding", probe)
        self.assertIn("textInputMode.primaryLanguage", probe)
        self.assertNotIn("textDocumentProxy.primaryLanguage", probe)
        judge = function_body(self.source, "static BOOL GXKLangCurrentIsChinese(UIViewController *vc) {")
        self.assertIn("GXKLangCurrentLanguage(vc)", judge)
        self.assertIn('hasPrefix:@"zh"', judge)
        # 取不到语言时沿用上次判定，避免无谓闪动。
        self.assertIn("return gLangChinese", judge)

    def test_every_refresh_entry_point_updates_and_teardown_detaches(self):
        for signature in (
            "static void gkx_textDidChange(id self, SEL _cmd, id textInput) {",
            "static void gkx_viewDidLayoutSubviews(id self, SEL _cmd) {",
            "static void gkx_viewDidAppear(id self, SEL _cmd, BOOL animated) {",
            "static void GXKBumpPolling(NSInteger ticks) {",
        ):
            self.assertIn("GXKUpdateLangKey", function_body(self.source, signature), signature)
        for signature in (
            "static void gkx_viewWillDisappear(id self, SEL _cmd, BOOL animated) {",
            "static void gkx_viewWillAppear(id self, SEL _cmd, BOOL animated) {",
        ):
            self.assertIn("GXKDetachLangKey", function_body(self.source, signature), signature)

    def test_action_display_timers_are_retired_not_language_dependencies(self):
        """Action drawing ownership must not leak into the language-key owner."""
        display = (ROOT / "dylib/action_key_display.h").read_text(encoding="utf-8")
        for retired in ("gxk_flash_grace_active", "GXKExpireFlashGraceIfNeeded",
                        "GXKClearFlashGrace", "GXKClearRebindPending", "gxk_rebind_hold",
                        "GXK_PARK_SECONDS", "GXK_FLASH_GRACE_SECONDS", "GXK_REBIND_WAIT_SECONDS"):
            self.assertNotIn(retired, self.source + display)
        lang = function_body(self.source, "static void GXKUpdateLangKey(UIViewController *vc) {")
        for action_owner in ("GXKActionDisplayBinding", "GXKReconcileActionDisplay",
                             "GXKDetachActionKey", "GXKCaptureActionKeyPress"):
            self.assertNotIn(action_owner, lang)

    def test_language_images_keep_independent_storage_from_per_key_action_display(self):
        """中英键有自己的逐键绑定，不借用换行键的存档，也不回到全局单例。"""
        binding = function_body(self.source, "@interface GXKLangDisplayBinding : NSObject")
        self.assertIn("normalImage", binding)
        self.assertIn("highlightedImage", binding)
        self.assertIn("prepared", binding)
        # 旧全局单例必须保持删除：它导致新键实例永远不认领，只能等轮询。
        for retired in ("gLangKeyView", "gGuardLangKey", "gLangNativeIcon", "gLangSoftKeyDef",
                        "gLangHost", "gLangKeyButton", "GXKLangRebindKey"):
            self.assertNotIn(retired, self.source)
        lang_guard = function_body(self.source, "static void gxk_lang_updateView(UIView *key) {")
        for action_storage in ("GXKActionDisplayForKey", "gActionNormalImage", "gActionHighlightedImage"):
            self.assertNotIn(action_storage, lang_guard)

    def test_language_guard_is_keyed_by_the_key_not_by_the_icon_instance(self):
        """原生换语言/换主题会重建 idToViewDict 里的 icon 实例，身份比对会漏帧。"""
        guard = function_body(self.source, "static UIView *GXKGuardedKeyForIcon(UIView *icon) {")
        lang = guard.index("GXKLangBindingFor(key).prepared")
        identity = guard.index("GXKNativeIconForKey(key) != icon")
        # 中英键分支必须排在 icon 身份比对之前，否则新实例上的原生写入不会被拦。
        self.assertLess(lang, identity)

    def test_key_lifecycle_callbacks_reconcile_the_language_overlay_in_place(self):
        for signature in (
            "static void gxk_key_setSoftKeyDef(id self, SEL _cmd, id model) {",
            "static void gxk_key_didMoveToSuperview(id self, SEL _cmd) {",
            "static void gxk_key_didMoveToWindow(id self, SEL _cmd) {",
        ):
            body = function_body(self.source, signature)
            self.assertIn("GXKReconcileLangDisplay", body, signature)
        reconcile = function_body(self.source, RECONCILE)
        # 轻量路径：不做全树扫描，也不改**键**的外观（按钮自己设 clearColor 是允许的）。
        for retired in ("GXKFindLangKey", "GXKUpdateLangKey", "key.hidden", "key.alpha", "key.backgroundColor"):
            self.assertNotIn(retired, reconcile)
        # 绑定按 key 查，所以键实例换了也由新实例自己认领，不需要全局单例比对。
        self.assertIn("GXKLangBindingFor(key)", reconcile)
        self.assertIn("GXKClearIconImages(icon)", reconcile)

    def test_action_and_language_teardown_remain_separate_on_disappearance(self):
        gone = function_body(self.source, "static void gkx_viewWillDisappear(id self, SEL _cmd, BOOL animated) {")
        self.assertIn("GXKDetachActionKey()", gone)
        self.assertIn("GXKDetachLangKey()", gone)
        self.assertIn("gCurrentVC = nil", gone)
        action = (ROOT / "dylib/action_key_display.h").read_text(encoding="utf-8")
        detach = function_body(action, "static void GXKDetachActionKey(void)")
        self.assertNotIn("GXKDetachLangKey", detach)
        self.assertNotIn("GXKLangDisplayBinding", detach)



if __name__ == "__main__":
    unittest.main(verbosity=2)
