"""Offline contracts for the injected action key; no claim of UIKit execution.

Run exactly this file, not discovery over legacy gkx-test-* directories:
    python tests/test_action_key.py
"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "dylib/gkx.m"


def function_body(source, signature):
    """Read a bounded function implementation, including nested braces."""
    start = source.index(signature)
    start = source.index("{", start)
    level = 1
    end = start + 1
    while level and end < len(source):
        level += (source[end] == "{") - (source[end] == "}")
        end += 1
    if level:
        raise AssertionError(f"Unterminated function: {signature}")
    return source[start + 1:end - 1]


class ActionKeySourceContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = SOURCE.read_text(encoding="utf-8")
        cls.native_style = (ROOT / "dylib/native_key_style.h").read_text(encoding="utf-8")

    def test_newline_is_a_newline_not_backslash_n(self):
        self.assertIn('[proxy insertText:@"\\n"]', self.source)
        self.assertNotIn('[proxy insertText:@"\\\\n"]', self.source)

    def test_no_coordinate_or_dictionary_fallback_for_key_identity(self):
        finder = function_body(self.source, "static UIView *GXKFindNineKeyEmojiKey(UIView *root)")
        self.assertIn("restorationIdentifier", finder)
        self.assertIn("GXKEmojiKeyID", finder)
        for retired in ("allSoftKeys", "_allSoftKeys", "rightColX", "maxCandidateY", "99999", "bestCandidate"):
            self.assertNotIn(retired, self.source)

    def test_body_classification_checks_nine_before_qwerty(self):
        owner = function_body(self.source, "static UIView *GXKNineKeyBodyForKey(UIView *key, UIView *root)")
        self.assertLess(owner.index("GKB9KeysSoftKeyboardView"), owner.index("GKBZhQwertySoftKeyboardView"))
        self.assertIn("return nil", owner)

    def test_ambiguous_visible_emoji_is_not_chosen_by_tree_order(self):
        finder = function_body(self.source, "static UIView *GXKFindNineKeyEmojiKey(UIView *root)")
        self.assertRegex(finder, r"if\s*\(candidate\s*&&\s*candidate\s*!=\s*v\)\s*return nil")

    def test_layout_boundary_revalidates_key(self):
        layout = function_body(self.source, "static void gkx_viewDidLayoutSubviews(id self, SEL _cmd)")
        self.assertIn("gOrigViewDidLayoutSubviews", layout)
        self.assertIn("GXKUpdateActionKey", layout)

    def test_tap_revalidates_sender_identity_and_binding(self):
        tap = function_body(self.source, "- (void)onActionKeyTapped:(UIButton *)sender {")
        self.assertIn("sender != gActionKeyButton", tap)
        self.assertIn("GXKFindNineKeyEmojiKey", tap)
        self.assertIn("softKeyDef", tap)
        self.assertIn("gActionSoftKeyDef", tap)

    def test_tap_three_states_clear_newline_dismiss(self):
        """组字「重输」、联想「收起」、其余「换行」；收起走公开 dismissKeyboard。"""
        tap = function_body(self.source, "- (void)onActionKeyTapped:(UIButton *)sender {")
        self.assertIn("GXKRefreshComposingState(vc)", tap)
        self.assertIn("gComposingActive", tap)
        self.assertIn("gSuggestingActive", tap)
        self.assertIn("GXKPerformClearComposing(vc)", tap)
        self.assertIn("[ivc dismissKeyboard]", tap)
        self.assertIn('[proxy insertText:@"\\n"]', tap)
        # 顺序必须是 重输 > 收起 > 换行，联想分支不能吃掉组字分支。
        self.assertLess(tap.index("GXKPerformClearComposing(vc)"), tap.index("dismissKeyboard"))
        self.assertLess(tap.index("dismissKeyboard"), tap.index('[proxy insertText:@"\\n"]'))

    def test_candidate_state_is_scanned_once_and_invalidated(self):
        """候选态与组字态同一趟扫描产出，组字成立即作废，生命周期退出清空。"""
        scan = function_body(self.source, "static BOOL GXKComposingFullScan(UIViewController *vc) {")
        self.assertIn("GXKViewKindCandidates", scan)
        self.assertIn("GXKCandidateViewHasContent(v)", scan)
        self.assertIn("gSuggestingActive = YES", scan)
        self.assertIn("gSuggestingActive = NO", scan)
        self.assertNotIn("NSStringFromClass", scan)
        cached = function_body(self.source, "static BOOL GXKComposingStateCached(UIViewController *vc) {")
        self.assertIn("gSuggestingActive = NO", cached)
        gone = function_body(self.source, "static void gkx_viewWillDisappear(id self, SEL _cmd, BOOL animated)")
        self.assertIn("gSuggestingActive = NO", gone)

    def test_native_keycap_is_not_hidden_or_repainted(self):
        # 只扫动作键那一段：设置页的 toast 有自己的圆角，不属于键帽外观。
        start = self.source.index("#pragma mark - 动作键目标与更新")
        end = self.source.index("#pragma mark - 主 App：常用语维护入口")
        action = self.source[start:end]
        for retired in ("GXKRestoreKeySubviews", "sub.hidden = YES", "sub.hidden = NO", "cornerRadius", "colorWithWhite:0.35", "colorWithRed:0.82", "userInterfaceStyle"):
            self.assertNotIn(retired, action)
        update = function_body(self.source, "static void GXKUpdateActionKey(UIViewController *vc) {")
        self.assertIn("[UIColor clearColor]", update)

    def test_keyboard_touch_methods_are_not_swizzled(self):
        initialization = function_body(self.source, "static void gkx_init(void)")
        for event in ("touchesBegan", "touchesMoved", "touchesEnded", "hitTest"):
            self.assertNotIn(event, initialization)

    def test_disappearance_releases_controller_and_binding(self):
        disappear = function_body(self.source, "static void gkx_viewWillDisappear(id self, SEL _cmd, BOOL animated)")
        self.assertIn("GXKDetachActionKey", disappear)
        self.assertIn("gCurrentVC = nil", disappear)
        # 停表职责收敛到 GXKStopPolling：这里必须调用它，invalidate 在它体内。
        self.assertIn("GXKStopPolling()", disappear)
        stop = function_body(self.source, "static void GXKStopPolling(void) {")
        self.assertIn("invalidate", stop)
        self.assertLess(disappear.index("gCurrentVC = nil"), disappear.index("gOrigViewWillDisappear(self"))

    def test_incomplete_or_detached_tree_fails_closed(self):
        finder = function_body(self.source, "static UIView *GXKFindNineKeyEmojiKey(UIView *root)")
        visible = function_body(self.source, "static BOOL GXKKeyIsVisible(UIView *key, UIView *root)")
        self.assertIn("if (stack.count ||", finder)
        self.assertIn("GXKNineKeyBodyForKey(candidate, root) != visibleBody", finder)
        self.assertIn("v.window != root.window", finder)
        self.assertIn("key.window != root.window", visible)
        self.assertIn("CGRectIntersection", visible)
        self.assertIn("v.clipsToBounds", visible)

    def test_native_icon_uses_verified_content_not_generic_hidden_views(self):
        icon = function_body(self.source, "static UIView<GXKNativeIconContent> *GXKNativeIconForKey(UIView *key)")
        self.assertIn('contents[@"image"]', icon)
        self.assertIn("GKBImageViewWithBackground", icon)
        self.assertIn("isDescendantOfView:key", icon)
        self.assertIn("setHighlightedImage:", icon)
        self.assertNotIn("UIImageView", icon)
        self.assertNotIn("clearLabelAndIcons", self.source)
        self.assertIsNone(re.search(r"softKeyDef\s*=(?!=)", self.source), "Native softKeyDef must remain read-only")

    def test_saved_foregrounds_are_restricted_to_same_native_identity(self):
        detach = function_body(self.source, "static void GXKDetachActionKey(void)")
        identity = detach.index("oldKey.restorationIdentifier")
        normal_restore = detach.index("oldIcon.image = normalImage")
        highlight_restore = detach.index("oldIcon.highlightedImage = highlightedImage")
        self.assertLess(identity, normal_restore)
        self.assertLess(identity, highlight_restore)
        self.assertIn("softKeyDef == oldModel", detach)
        self.assertIn("GXKNativeIconForKey(oldKey) == oldIcon", detach)
        self.assertIn("oldKey.hidden = wasHidden", detach)
        self.assertIn("gActionNormalImage = nil", detach)
        # 归属只活到撤键结束：撤键后这把键完全回到原生，守卫不再清它的前景。
        # 且必须先释放归属再调原生 updateView——那次重画是还原，不能被守卫再搬走一次。
        self.assertIn("gGuardKey = nil", detach)
        self.assertLess(detach.index("gGuardKey = nil"),
                        detach.index("[(id<GXKNativeSoftKeyContent>)oldKey updateView]"))
        self.assertIn("gActionHighlightedImage = nil", detach)

    def test_rebinding_creates_fresh_button_after_detaching(self):
        update = function_body(self.source, "static void GXKUpdateActionKey(UIViewController *vc) {")
        create = update.index("[UIButton buttonWithType:UIButtonTypeCustom]")
        self.assertLess(update.index("GXKDetachActionKey();", update.index("gEmojiSoftKeyView != currentKey")), create)
        self.assertIn("gActionSoftKeyDef != model", update)
        self.assertIn("gActionKeyButton.superview != host", update)
        self.assertIn("GXKActionHostForKey(currentKey)", update)
        self.assertNotIn("[currentKey addSubview:btn]", update)
        self.assertIn("[currentKey convertRect:currentKey.bounds toView:host]", update)
        self.assertIn("gUpdatingActionKey", update)

    def test_native_theme_and_both_titles_keep_same_transparent_style(self):
        update = function_body(self.source, "static void GXKUpdateActionKey(UIViewController *vc) {")
        self.assertIn("icon.foregroundColor", update)
        self.assertIn("GXKNativeActionFont", update)
        self.assertIn("setTitleColor:color forState:UIControlStateNormal", update)
        self.assertIn("setTitleColor:color forState:UIControlStateHighlighted", update)
        self.assertIn("btn.accessibilityLabel = title", update)
        self.assertNotRegex(update, r"(?:currentKey|icon|root)\.(?:frame|bounds|backgroundColor)\s*=")
        self.assertNotIn("backgroundLayer", re.sub(r"//[^\n]*", "", update))

    def test_mixed_peer_bodies_fail_closed_but_nested_fixed_body_is_not_a_peer(self):
        finder = function_body(self.source, "static UIView *GXKFindNineKeyEmojiKey(UIView *root)")
        self.assertIn("GKB9KeysSoftKeyboardView", finder)
        self.assertIn("GKBZhQwertySoftKeyboardView", finder)
        self.assertIn("GKBSoftKeyboardViewWithFixedLayout", finder)
        self.assertIn("isPeerBody && GXKKeyIsVisible(v, root)", finder)
        self.assertIn("if (!visibleBody) visibleBody = v", finder)
        self.assertIn("else if (![v isDescendantOfView:visibleBody]) return nil", finder)
        self.assertIn("![visibleBody isKindOfClass:nineClass]", finder)
        self.assertIn("GXKNineKeyBodyForKey(candidate, root) != visibleBody", finder)

    def test_rebinding_rescans_controller_root_and_key_after_native_refresh(self):
        update = function_body(self.source, "static void GXKUpdateActionKey(UIViewController *vc) {")
        rebind = update[update.index("gEmojiSoftKeyView != currentKey"):]
        detach = rebind.index("GXKDetachActionKey();")
        controller = rebind.index("vc != gCurrentVC || !vc.isViewLoaded || vc.view != root", detach)
        select = rebind.index("currentKey = GXKFindNineKeyEmojiKey(root)", controller)
        content = rebind.index("icon = GXKNativeIconForKey(currentKey)", select)
        create = rebind.index("[UIButton buttonWithType:UIButtonTypeCustom]", content)
        self.assertLess(detach, controller)
        self.assertLess(controller, select)
        self.assertLess(select, content)
        self.assertLess(content, create)

    def test_empty_native_model_is_rejected_on_updates_and_taps(self):
        predicate = function_body(self.source, "static BOOL GXKModelHasNativeActions(id model)")
        self.assertIn("respondsToSelector:@selector(actionsArray)", predicate)
        self.assertIn("isKindOfClass:[NSArray class]", predicate)
        self.assertIn("actions.count > 0", predicate)
        self.assertNotIn("setActions", predicate)
        tap = function_body(self.source, "- (void)onActionKeyTapped:(UIButton *)sender {")
        update = function_body(self.source, "static void GXKUpdateActionKey(UIViewController *vc) {")
        self.assertIn("!GXKModelHasNativeActions(gActionSoftKeyDef)", tap)
        self.assertGreaterEqual(update.count("!GXKModelHasNativeActions(model)"), 2)

    def test_fresh_binding_requires_current_foreground_not_previous_images(self):
        update = function_body(self.source, "static void GXKUpdateActionKey(UIViewController *vc) {")
        fresh = update[update.index("gEmojiSoftKeyView != currentKey"):update.index("[UIButton buttonWithType:UIButtonTypeCustom]")]
        self.assertIn("[icon.image isKindOfClass:[UIImage class]]", fresh)
        self.assertIn("[icon.highlightedImage isKindOfClass:[UIImage class]]", fresh)
        self.assertIn("!hasForeground", fresh)
        self.assertNotIn("gActionNormalImage", fresh)
        self.assertNotIn("gActionHighlightedImage", fresh)

    def test_action_and_toolbar_fonts_share_identified_native_key_owner(self):
        self.assertIn('#import "native_key_style.h"', self.source)
        font = function_body(self.source, "static UIFont *GXKNativeActionFont(")
        self.assertIn("GXKNineKeyBodyForKey(key, root)", font)
        self.assertIn("return GXKNativeKeyFont(body, root);", font)
        self.assertNotIn("arrayWithObject:", font)
        toolbar = function_body(self.source, "static UIColor *GXKToolbarTextStyle(")
        self.assertIn("GXKNativeKeyStyleLabel(body, root)", toolbar)
        self.assertIn("label.font ?: GXKNativeKeyFont(body, root)", toolbar)
        self.assertNotIn("arrayWithObject:", toolbar)

    def test_native_icon_write_guard_clears_only_the_bound_key_in_the_same_pass(self):
        """原生 updateView 写完的同一轮清前景，否则下一拍清除前会闪一帧圆圈。"""
        guard = function_body(self.source, "static void gxk_key_updateView(id self, SEL _cmd) {")
        # 原方法是 void（v16@0:8）。包装必须同签名：按 id 接管会让 ARC retain 一个
        # 从未被赋值的返回寄存器，切键盘当场闪退。
        self.assertIn("static void (*gOrigKeyUpdateView)(id, SEL);", self.source)
        self.assertNotIn("return result;", guard)
        self.assertIn("if (gOrigKeyUpdateView) gOrigKeyUpdateView(self, _cmd);", guard)
        # 判据挂在「归属的九键表情键」上，不能挂按钮/图标对象同一性：切页这一拍原生会
        # 重建 icon，detach 又会先把按钮撤走，旧判据在这两种情况下都放行、笑脸照原样提交一帧。
        self.assertIn("key != gGuardKey", guard)
        self.assertIn("GXKNineKeyBodyForKey(key, gCurrentVC.view)", guard)
        self.assertNotIn("key != gEmojiSoftKeyView", guard)
        self.assertNotIn("icon != gActionNativeIcon", guard)
        self.assertNotIn("!gActionKeyButton", guard)
        # 图标必须每次现取：守卫里缓存的那一个在切页后已经不是图层上的那一个。
        self.assertLess(guard.index("GXKNativeIconForKey(key)"), guard.index("GXKClearIconImages(icon)"))
        # 原生重画的图要先存档再清，撤键时才还原得回来。
        self.assertLess(guard.index("gActionNormalImage = icon.image"), guard.index("GXKClearIconImages(icon)"))
        self.assertLess(guard.index("gActionHighlightedImage = icon.highlightedImage"),
                        guard.index("GXKClearIconImages(icon)"))
        # 清图必须瞬时：GKBImageLayer 实现了 actionForKey:，普通赋值会走隐式动画，
        # 前景图淡出那几帧就是用户看到的「闪一下圆圈」。
        clear = function_body(self.source, "static void GXKClearIconImages(UIView<GXKNativeIconContent> *icon) {")
        self.assertIn("[CATransaction begin]", clear)
        self.assertIn("[CATransaction setDisableActions:YES]", clear)
        self.assertIn("[CATransaction commit]", clear)
        self.assertLess(clear.index("setDisableActions:YES"), clear.index("icon.image = nil"))
        # 不碰键帽外观：不隐藏、不透明、不改背景层。
        for retired in ("hidden", "alpha", "backgroundLayer", "backgroundColor", "cornerRadius"):
            self.assertNotIn(retired, guard)

        install = function_body(self.source, "static void GXKInstallIconWriteGuard(void) {")
        self.assertIn("if (gxk_icon_guard_hooked) return;", install)
        self.assertIn('NSClassFromString(@"GKBSoftKeyView")', install)
        self.assertIn("class_getInstanceMethod(cls, @selector(updateView))", install)
        # 签名不符就不挂：宁可闪一帧，也不能让键盘崩。
        self.assertIn("const char *types = method_getTypeEncoding(m);", install)
        self.assertIn("if (!types || types[0] != 'v') return;", install)
        self.assertIn("method_getImplementation(m)", install)
        # 方法来自父类时用 class_addMethod，别改写父类波及其它键。
        self.assertIn("if (!class_addMethod(cls, @selector(updateView), (IMP)gxk_key_updateView, types)) {", install)
        self.assertIn("method_setImplementation(m, (IMP)gxk_key_updateView);", install)
        self.assertIn("gxk_icon_guard_hooked = YES;", install)

        # 构造期先挂，类晚加载时 viewWillAppear 补挂。
        init = function_body(self.source, "static void gkx_init(void)")
        self.assertIn("GXKInstallIconWriteGuard();", init)
        self.assertLess(init.index("GXKInstallIconWriteGuard();"),
                        init.index("GXKApplyTelemetryBlockIfNeeded()"))
        appear = function_body(self.source, "static void gkx_viewWillAppear(id self, SEL _cmd, BOOL animated)")
        self.assertIn("GXKInstallIconWriteGuard();", appear)
        self.assertLess(appear.index("GXKSymbolInstallHooks()"),
                        appear.index("GXKInstallIconWriteGuard();"))

    def test_native_typography_owner_is_return_key_dictionary_label_not_candidate(self):
        label = function_body(self.native_style, "static UILabel *GXKNativeReturnLabel(")
        for required in ('key.restorationIdentifier isEqualToString:@"key_pos_9keys_return"',
                         "isKindOfClass:keyClass", "isDescendantOfView:body", "GXKKeyIsVisible(key, root)",
                         "respondsToSelector:@selector(idToViewDict)", 'contents[@"label"]',
                         "isKindOfClass:[UILabel class]", "isDescendantOfView:key", "isKindOfClass:[UIFont class]"):
            self.assertIn(required, label)
        selection = function_body(self.native_style, "static UILabel *GXKNativeKeyStyleLabel(")
        self.assertIn("GXKNativeReturnLabel(view, body, root)", selection)
        self.assertIn("if (candidate && candidate != view) return nil;", selection)
        self.assertIn("if ([view isKindOfClass:[UICollectionView class]]) continue;", selection)
        self.assertIn("if (pending.count || !selected) return nil;", selection)
        self.assertLess(selection.index("if (!body || !root"), selection.index("arrayWithObject:body"))
        self.assertNotRegex(selection, r"(?:label|view)\.text(?:\b|\.)")

    def test_native_font_cache_revalidates_key_and_label_before_throttled_discovery(self):
        for weak in ("static __weak UIView *gNativeStyleBody;", "static __weak UIView *gNativeStyleKey;",
                     "static __weak UILabel *gNativeStyleLabel;"):
            self.assertIn(weak, self.native_style)
        selection = function_body(self.native_style, "static UILabel *GXKNativeKeyStyleLabel(")
        live = selection.index("GXKNativeReturnLabel(gNativeStyleKey, body, root)")
        reuse = selection.index("gNativeStyleBody == body && live && live == gNativeStyleLabel")
        throttle = selection.index("now - gNativeStyleScanAt < 0.25")
        self.assertLess(live, reuse)
        self.assertLess(reuse, throttle)
        self.assertIn("visited++ < 300", selection)
        self.assertIn("gNativeStyleKey = nil;", selection)
        self.assertIn("gNativeStyleLabel = nil;", selection)
        font = function_body(self.native_style, "static UIFont *GXKNativeKeyFont(")
        self.assertIn("GXKNativeKeyStyleLabel(body, root).font", font)
        self.assertIn('font ?: [UIFont fontWithName:@"Roboto-Regular" size:16.0] ?: [UIFont systemFontOfSize:16.0]', font)
        self.assertNotIn("systemFontOfSize:22", font)
        for hook in ("static void gkx_viewWillAppear(", "static void gkx_viewWillDisappear("):
            self.assertIn("GXKResetNativeKeyStyle();", function_body(self.source, hook))
        reset = function_body(self.native_style, "static void GXKResetNativeKeyStyle(")
        for binding in ("gNativeStyleBody = nil;", "gNativeStyleKey = nil;", "gNativeStyleLabel = nil;", "gNativeStyleScanAt = 0;"):
            self.assertIn(binding, reset)

    def test_both_action_update_paths_resample_native_font_and_keep_both_titles(self):
        update = function_body(self.source, "static void GXKUpdateActionKey(UIViewController *vc) {")
        fast, full = update.split("UIView *currentKey = GXKFindNineKeyEmojiKey(root);", 1)
        self.assertIn("GXKNativeActionFont(gEmojiSoftKeyView, root)", fast)
        self.assertIn("cheapBtn.titleLabel.font = cheapFont", fast)
        self.assertIn("GXKNativeActionFont(currentKey, root)", full)
        self.assertIn("btn.titleLabel.font = font", full)
        for body, variable in ((fast, "cheapTitle"), (full, "title")):
            self.assertIn(f"NSString *{variable} = GXKActionTitle(vc);", body)
            self.assertIn(f"setTitle:{variable} forState:UIControlStateNormal", body)
            self.assertIn(f"setTitle:{variable} forState:UIControlStateHighlighted", body)
        # 标题三态必须集中在一个函数里，两个更新路径不得各自复制判定逻辑。
        title = function_body(self.source, "static NSString *GXKActionTitle(UIViewController *vc) {")
        self.assertIn('return @"重输";', title)
        self.assertIn('return @"收起";', title)
        self.assertIn('return @"换行";', title)
        # 组字优先于联想：正在打的拼音不能被「收起」抢走。
        self.assertLess(title.index('return @"重输";'), title.index('gSuggestingActive'))
        sync = function_body(self.source, "static void GXKSyncToolbarStyle(")
        self.assertIn("GXKToolbarTextStyle(body, &font)", sync)
        self.assertIn("button.titleLabel.font = font", sync)
        self.assertIn("setTitleColor:tint forState:UIControlStateNormal", sync)

    def test_queued_updates_are_bound_to_original_controller(self):
        tap = function_body(self.source, "- (void)onActionKeyTapped:(UIButton *)sender {")
        changed = function_body(self.source, "static void gkx_textDidChange(id self, SEL _cmd, id textInput)")
        self.assertIn("__weak UIViewController *weakVC = vc", tap)
        self.assertIn("currentVC == gCurrentVC", tap)
        self.assertIn("UIViewController *vc = weakVC", changed)
        self.assertIn("vc == gCurrentVC", changed)


if __name__ == "__main__":
    unittest.main(verbosity=2)
