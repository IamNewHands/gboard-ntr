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
    5. 中/英两字只改颜色透明度，不换字体族、不加背景色。

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

    def test_overlay_is_purely_visual_and_keeps_native_touch_path(self):
        update = function_body(self.source, "static void GXKUpdateLangKey(UIViewController *vc) {")
        self.assertIn("btn.userInteractionEnabled = NO", update)
        # 覆盖层不得挂任何手势或点击回调：切换语言必须继续由原生键处理。
        for retired in ("addGestureRecognizer", "addTarget", "touchesBegan", "hitTest"):
            self.assertNotIn(retired, update)
        self.assertIn("[UIColor clearColor]", update)

    def test_native_foreground_is_archived_before_clearing(self):
        update = function_body(self.source, "static void GXKUpdateLangKey(UIViewController *vc) {")
        self.assertLess(update.index("gLangNormalImage = icon.image"), update.index("icon.image = nil"))
        self.assertLess(update.index("gLangHighlightedImage = icon.highlightedImage"),
                        update.index("icon.highlightedImage = nil"))
        # 廉价路径同样要搬走原生重画的图，否则会盖在我们的文字上。
        cheap = update[:update.index("GXKFindLangKey(root)")]
        self.assertIn("gLangNormalImage = cheapIcon.image", cheap)
        self.assertIn("cheapIcon.image = nil", cheap)

    def test_detach_restores_only_the_same_native_identity(self):
        detach = function_body(self.source, "static void GXKDetachLangKey(void) {")
        identity = detach.index("GXKNativeIconForKey(oldKey) == oldIcon")
        self.assertLess(identity, detach.index("oldIcon.image = normalImage"))
        self.assertLess(identity, detach.index("oldIcon.highlightedImage = highlightedImage"))
        self.assertIn("softKeyDef == oldModel", detach)
        # 归属先释放再调原生 updateView：这次重画是还原，守卫不能再把图搬走。
        self.assertLess(detach.index("gGuardLangKey = nil"), detach.index("updateView]"))

    def test_guard_branch_runs_before_the_emoji_early_returns(self):
        guard = function_body(self.source, "static void gxk_key_updateView(id self, SEL _cmd) {")
        self.assertIn("gxk_lang_updateView(key)", guard)
        self.assertLess(guard.index("gxk_lang_updateView(key)"), guard.index("key != gGuardKey"))
        lang_guard = function_body(self.source, "static void gxk_lang_updateView(UIView *key) {")
        self.assertIn("key != gGuardLangKey", lang_guard)
        self.assertIn("GXKLangKeyIDMatches(key)", lang_guard)
        # 与笑脸键各自存档，互不覆盖。
        self.assertIn("gLangNormalImage = icon.image", lang_guard)
        for retired in ("gActionNormalImage", "gActionHighlightedImage"):
            self.assertNotIn(retired, lang_guard)

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

    def test_page_switch_grace_window_is_bounded_and_restores_native(self):
        """切页宽限按身份生效（重建出来的新实例也算），但必须到点交还原生。"""
        helper = function_body(self.source, "static BOOL gxk_flash_grace_active(UIView *key) {")
        # 旧实例直接命中；原生切页会重建表情键，新实例只能按「可见九键表情键」认。
        self.assertIn("key == gFlashKey", helper)
        self.assertIn("GXKNineKeyBodyForKey(key, gCurrentVC.view)", helper)
        # 有界：到点一律放行，绝不能变成长期接管。
        self.assertIn("CFAbsoluteTimeGetCurrent() >= gFlashDeadline", helper)
        self.assertIn("GXKEmojiKeyID", helper)
        # 宽限不能在空转 detach 里被清零：那会让守卫在刚建立的窗口上当场放行。
        detach_head = function_body(self.source, "static void GXKDetachActionKey(void) {")
        early = detach_head.index("if (!gEmojiSoftKeyView && !gActionKeyButton")
        self.assertLess(early, detach_head.index("gFlashDeadline = oldKey ?"))
        guard = function_body(self.source, "static void gxk_key_updateView(id self, SEL _cmd) {")
        self.assertIn("key != gGuardKey && !gxk_flash_grace_active(key)", guard)
        # 宽限不能变成第二条归属：守卫仍要求键 ID 是九键表情键。
        self.assertLess(guard.index("gxk_flash_grace_active(key)"),
                        guard.index("isEqualToString:GXKEmojiKeyID]"))
        detach = function_body(self.source, "static void GXKDetachActionKey(void) {")
        self.assertIn("gFlashDeadline = oldKey ?", detach)
        self.assertLess(detach.index("gFlashKey = oldKey"), detach.index("gGuardKey = nil"))
        # 到点还原必须自愈：轮询空闲会停表，只在更新路径里作废会让键停在空白前景。
        expire = function_body(self.source, "static void GXKExpireFlashGraceIfNeeded(void) {")
        self.assertIn("CFAbsoluteTimeGetCurrent() < gFlashDeadline", expire)
        self.assertIn("expired != gEmojiSoftKeyView", expire)
        self.assertLess(expire.index("gFlashKey = nil"), expire.index("updateView]"))
        for signature in (
            "static void gxk_key_updateView(id self, SEL _cmd) {",
            "static void GXKUpdateActionKey(UIViewController *vc) {",
        ):
            self.assertIn("GXKExpireFlashGraceIfNeeded()", function_body(self.source, signature), signature)
        gone = function_body(self.source, "static void gkx_viewWillDisappear(id self, SEL _cmd, BOOL animated) {")
        self.assertIn("GXKClearFlashGrace()", gone)
        self.assertLess(gone.index("GXKDetachActionKey()"), gone.index("GXKClearFlashGrace()"))

    def test_expiry_does_not_hand_the_key_back_while_rebind_is_pending(self):
        """宽限到点不能立刻还键：那一次 updateView 会把原生笑脸画回去。

        日志 4 的 1.17 秒圆圈就是这段空档——9390 宽限到点还原生、9391 守卫放行、
        补绑要等下一轮主队列才到。等待窗内改为继续拦，绑上或超时才还。
        """
        hold = function_body(self.source, "static BOOL gxk_rebind_hold(UIView *key) {")
        self.assertIn("gxk_rebind_pending()", hold)
        self.assertIn("GXKEmojiKeyID", hold)
        # 等待窗只认「可见九键布局体里的表情键」，不会变成第二条归属。
        self.assertIn("GXKNineKeyBodyForKey(key, gCurrentVC.view)", hold)
        expire = function_body(self.source, "static void GXKExpireFlashGraceIfNeeded(void) {")
        # 交还原生这一步必须被等待窗挡住，且挡在 updateView 之前。
        self.assertIn("!gxk_rebind_hold(expired)", expire)
        self.assertLess(expire.index("!gxk_rebind_hold(expired)"), expire.index("updateView]"))
        # 到点后仍要补绑，不能只拦不绑。
        self.assertIn("if (!gEmojiSoftKeyView) GXKScheduleActionKeyRebind();", expire)
        # 等待窗必须有界：超过上限一律还键，绝不长期接管。
        window = function_body(self.source, "static BOOL gxk_rebind_pending(void) {")
        self.assertIn("gRebindWaitDeadline > 0", window)
        self.assertIn("CFAbsoluteTimeGetCurrent() < gRebindWaitDeadline", window)
        # 写入拦截与守卫都必须认这条等待窗，否则原生图还是能进图层。
        guarded = function_body(self.source, "static UIView *GXKGuardedKeyForIcon(UIView *icon) {")
        self.assertIn("gxk_rebind_pending()", guarded)
        self.assertIn("gxk_rebind_hold(v)", guarded)
        guard = function_body(self.source, "static void gxk_key_updateView(id self, SEL _cmd) {")
        self.assertIn("!gxk_rebind_hold(key)", guard)
        # 绑定成功即结束等待；失败撤键也立即结束，键不会被空白挡到过期。
        update = function_body(self.source, "static void GXKUpdateActionKey(UIViewController *vc) {")
        self.assertLess(update.index("gGuardKey = currentKey"), update.index("GXKClearRebindPending()"))
        detach = function_body(self.source, "static void GXKDetachActionKey(void) {")
        self.assertLess(detach.index("GXKClearRebindPending()"), detach.index("if (!gEmojiSoftKeyView && !gActionKeyButton"))
        # 键盘撤走时窗口一并作废。
        clear = function_body(self.source, "static void GXKClearFlashGrace(void) {")
        self.assertIn("GXKClearRebindPending()", clear)



if __name__ == "__main__":
    unittest.main(verbosity=2)
