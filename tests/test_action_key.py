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
        cls.display = (ROOT / "dylib/action_key_display.h").read_text(encoding="utf-8")
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

    def test_queued_updates_are_bound_to_original_controller(self):
        tap = function_body(self.source, "- (void)onActionKeyTapped:(UIButton *)sender {")
        changed = function_body(self.source, "static void gkx_textDidChange(id self, SEL _cmd, id textInput)")
        self.assertIn("__weak UIViewController *weakVC = vc", tap)
        self.assertIn("currentVC == gCurrentVC", tap)
        self.assertIn("UIViewController *vc = weakVC", changed)
        self.assertIn("vc == gCurrentVC", changed)

    def test_per_native_key_binding_owns_visual_and_input_separately(self):
        self.assertIn("@interface GXKActionDisplayBinding", self.display)
        for owner in ("UILabel *label", "UIButton *inputButton", "UIView *key"):
            self.assertIn(owner, self.display)
        self.assertIn("objc_getAssociatedObject", self.display)
        self.assertIn("objc_setAssociatedObject", self.display)
        self.assertIn("GXKActionDisplayForKey", self.display)
        self.assertNotIn("gActionKeyButton", self.source + self.display)

    def test_native_key_is_weakly_registered_before_controller_readiness(self):
        reconcile = function_body(self.display, "static void GXKReconcileActionDisplay(UIView *key)")
        self.assertIn("[NSHashTable weakObjectsHashTable]", reconcile)
        self.assertLess(reconcile.index("[gActionDisplayKeys addObject:key]"),
                        reconcile.index("if (!domain)"))
        self.assertLess(reconcile.index("GXKEmojiKeyID"),
                        reconcile.index("[gActionDisplayKeys addObject:key]"))
        self.assertLess(reconcile.index("[key isKindOfClass:keyClass]"),
                        reconcile.index("[gActionDisplayKeys addObject:key]"))
        self.assertNotIn("GXKClearRebindPending", self.source + self.display)

    def test_no_cross_page_button_parking_grace_or_retarget_owner(self):
        for retired in ("GXK_FLASH_GRACE_SECONDS", "GXK_PARK_SECONDS", "GXK_REBIND_WAIT_SECONDS",
                        "gFlashKey", "gParkedButton", "gRebindWaitDeadline", "GXKTakeParkedButton",
                        "GXKKeepLiveBinding", "gxk_stale_emoji_key", "canRetarget", "retarget %@"):
            self.assertNotIn(retired, self.source + self.display)
        for callback in ("GXKReconcileActionDisplay", "GXKActionDisplayCoversIcon"):
            self.assertIn(callback, self.display)

    def test_input_requires_touch_down_generation_and_live_tap_validation(self):
        for required in ("capturedGeneration", "generation", "GXKCaptureActionKeyPress",
                         "GXKCancelActionKeyPress", "GXKValidateActionKeyPress", "cancelTrackingWithEvent:"):
            self.assertIn(required, self.display)
        validate = function_body(self.display, "static GXKActionDisplayBinding *GXKValidateActionKeyPress(")
        self.assertIn("capturedGeneration", validate)
        self.assertIn("generation", validate)
        self.assertIn("GXKFindNineKeyEmojiKey", validate)
        self.assertIn("GXKModelHasNativeActions", validate)
        self.assertIn("binding.key.userInteractionEnabled", validate)
        tap = function_body(self.source, "- (void)onActionKeyTapped:(UIButton *)sender {")
        self.assertLess(tap.index("GXKValidateActionKeyPress"), tap.index("GXKRefreshComposingState"))

    def test_label_is_noninteractive_and_not_a_native_content_identity(self):
        self.assertIn("userInteractionEnabled = NO", self.display)
        self.assertIn("[UILabel", self.display)
        self.assertNotRegex(self.display, r"(?:label|inputButton)\.restorationIdentifier\s*=\s*(?:GXKEmojiKeyID|@\"(?:image|label)\")")
        self.assertNotRegex(self.display, r"idToViewDict\s*\[.*?\]\s*=")
        self.assertNotRegex(self.source + self.display, r"\.softKeyDef\s*=(?!=)")

    def test_native_first_content_order_is_verified_before_label_is_attached(self):
        self.assertIn("nativeContent", self.display)
        self.assertIn("nativeHost", self.display)
        self.assertIn("firstObject", self.display)
        self.assertIn("GXKNativeIconForKey", self.display)
        self.assertIn("prepared", self.display)
        # Runtime reset/remount/native-firstObject assertions live in the UIKit fixture.
        fixture = ROOT / "tests/native/ActionDisplayTests.m"
        self.assertTrue(fixture.is_file())

    def test_coverage_is_exact_live_icon_and_an_attached_prepared_label(self):
        coverage = function_body(self.display, "static BOOL GXKActionDisplayCoversIcon(")
        for required in ("GXKActionDisplayForKey", "prepared", "label", "icon"):
            self.assertIn(required, coverage)
        self.assertIn("superview", coverage)
        self.assertNotIn("gGuardKey", coverage)
        self.assertNotIn("CFAbsoluteTimeGetCurrent", coverage)
        guard = function_body(self.source, "static UIView *GXKGuardedKeyForIcon(")
        self.assertIn("GXKActionDisplayCoversIcon", guard)
        self.assertIn("gGuardLangKey", guard)
        self.assertIn("gxk_icon_write_bypass", guard)
        current = function_body(self.display, "static BOOL GXKActionDisplayIsCurrent(")
        self.assertIn("isDescendantOfView:binding.root", current)
        self.assertIn("key.window != binding.root.window", current)
        self.assertNotIn("GXKKeyIsVisible", current, "Model visibility cannot retire an animating display owner")
        self.assertNotIn("userInteractionEnabled", current, "Native input capability cannot retire display ownership")
        reconcile = function_body(self.display, "static void GXKReconcileActionDisplay(")
        domain = reconcile[reconcile.index("BOOL domain"):reconcile.index("if (!domain)")]
        self.assertNotIn("GXKKeyIsVisible", domain)
        self.assertNotIn("userInteractionEnabled", domain)
        self.assertIn("BOOL clickAllowed = actions && key.userInteractionEnabled", reconcile)
        self.assertIn("GXKKeyIsVisible(key, root) && GXKKeyIsVisible(body, root)", reconcile)
        readiness = reconcile[reconcile.index("BOOL contentReady"):reconcile.index("BOOL titleFits")]
        self.assertNotIn("textSize", readiness, "Model bounds fit is not native structural readiness")
        self.assertIn("(!continuity && !titleFits)", reconcile)
        self.assertIn("binding.clickAllowed = clickAllowed", reconcile)
        self.assertIn("binding.clickAllowed && !clickAllowed", reconcile)

    def test_native_completed_update_reconciles_same_key_without_a_queue_handoff(self):
        guard = function_body(self.source, "static void gxk_key_updateView(id self, SEL _cmd)")
        self.assertIn("gOrigKeyUpdateView", guard)
        self.assertIn("GXKReconcileActionDisplay", guard)
        self.assertLess(guard.index("gOrigKeyUpdateView(self, _cmd)"), guard.rindex("GXKReconcileActionDisplay"))
        self.assertNotIn("dispatch_async", guard)
        self.assertNotIn("dispatch_after", guard)
        self.assertNotIn("return result;", guard)
        self.assertIn("static void (*gOrigKeyUpdateView)(id, SEL)", self.source)

    def test_completed_controller_layout_updates_action_display_before_async_work(self):
        layout = function_body(self.source, "static void gkx_viewDidLayoutSubviews(id self, SEL _cmd)")
        first = layout.index("GXKUpdateActionKey")
        self.assertLess(layout.index("gOrigViewDidLayoutSubviews(self, _cmd)"), first)
        self.assertLess(first, layout.index("dispatch_async"))

    def test_native_key_lifecycle_hooks_are_class_local_not_global_uikit_hooks(self):
        install = function_body(self.source, "static void GXKInstallIconWriteGuard(")
        self.assertIn('NSClassFromString(@"GKBSoftKeyView")', install)
        self.assertIn("class_addMethod", self.source + self.display)
        for callback in ("didMoveToSuperview", "didMoveToWindow", "setSoftKeyDef:"):
            self.assertIn(callback, self.source + self.display)
        for forbidden in ("contentRectForBounds:", "titleRectForContentRect:",
                          "intrinsicContentSize", "touchesBegan:", "touchesMoved:", "touchesEnded:"):
            self.assertNotIn(forbidden, self.display)

    def test_only_owned_overlays_are_styled_and_native_keycap_stays_read_only(self):
        self.assertIn("[UIColor clearColor]", self.display)
        self.assertIn("GXKNativeActionFont", self.display)
        self.assertIn("foregroundColor", self.display)
        self.assertNotRegex(self.display, r"(?:key|icon|body|root|nativeContent|nativeHost)\.(?:frame|bounds|backgroundColor|alpha|hidden)\s*=")
        for native_repaint in ("backgroundLayer.bgColor", "backgroundLayer.borderWidth", "cornerRadius"):
            self.assertNotIn(native_repaint, self.display)

    def test_title_owner_preserves_composing_suggesting_idle_priority(self):
        title = function_body(self.source, "static NSString *GXKActionTitle(")
        for text in ('return @"重输";', 'return @"收起";', 'return @"换行";'):
            self.assertIn(text, title)
        self.assertLess(title.index('return @"重输";'), title.index("gSuggestingActive"))
        self.assertIn("GXKActionTitle", self.display)
        self.assertNotIn("setTitle:", self.display, "Input-only buttons must never own the visible title")

    def test_native_nil_image_writes_are_not_confused_with_owned_clearing(self):
        clear = function_body(self.source, "static void GXKClearIconImages(")
        self.assertLess(clear.index("gxk_icon_write_bypass = YES"), clear.index("icon.image = nil"))
        self.assertIn("gxk_icon_write_bypass = bypass", clear)
        record = function_body(self.display, "static void GXKRecordActionImage(")
        self.assertNotIn("!image", record)
        self.assertIn("gxk_icon_write_bypass", record)
        for callback in ("gxk_icon_setImage", "gxk_icon_setHighlightedImage",
                         "gxk_layer_setImage", "gxk_layer_setHighlightedImage"):
            self.assertIn("GXKRecordActionIconWrite", function_body(self.source, "static void " + callback + "("))

    def test_model_with_empty_actions_never_authorizes_input(self):
        predicate = function_body(self.source, "static BOOL GXKModelHasNativeActions(")
        for check in ("respondsToSelector:@selector(actionsArray)", "isKindOfClass:[NSArray class]", "actions.count > 0"):
            self.assertIn(check, predicate)
        validate = function_body(self.display, "static GXKActionDisplayBinding *GXKValidateActionKeyPress(")
        self.assertIn("GXKModelHasNativeActions", validate)
        self.assertIn("clickAllowed", self.display)
        self.assertNotIn("setActions", self.display)

    def test_test_constructor_guard_does_not_change_production_initialization(self):
        self.assertRegex(self.source, r"#ifndef GXK_ACTION_DISPLAY_TESTING\s+__attribute__\(\(constructor\)\)\s+#endif\s+static void gkx_init")
        init = function_body(self.source, "static void gkx_init(")
        self.assertIn("GXKInstallIconWriteGuard", init)
        self.assertIn("GXKApplyTelemetryBlockIfNeeded", init)


if __name__ == "__main__":
    unittest.main(verbosity=2)
