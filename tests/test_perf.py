#!/usr/bin/env python3
"""性能改动源码契约：轮询必须走廉价路径，全树扫描不得留在定时器里。"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "dylib/gkx.m"


def function_body(source: str, signature: str) -> str:
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


class PerfContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = SOURCE.read_text(encoding="utf-8")
        cls.layout = (ROOT / "dylib/toolbar_layout.h").read_text(encoding="utf-8")
        cls.visibility = (ROOT / "dylib/toolbar_visibility.h").read_text(encoding="utf-8")

    def test_timer_body_never_scans_full_tree(self):
        """定时器只在按需窗口内跑，且体内绝不做全树扫描。"""
        pump = function_body(self.source, "static void GXKBumpPolling(NSInteger ticks) {")
        self.assertIn("scheduledTimerWithTimeInterval", pump)
        body = pump[pump.index("scheduledTimerWithTimeInterval"):]
        self.assertNotIn("GXKFindNineKeyEmojiKey", body)
        self.assertNotIn("GXKComposingFullScan", body)
        self.assertIn("GXKUpdateActionKey(vc)", body)
        # 生命周期入口只抬计数，不直接建表；建表只在 GXKBumpPolling 里发生一次。
        appear = function_body(self.source, "static void gkx_viewWillAppear(id self, SEL _cmd, BOOL animated)")
        self.assertIn("GXKBumpPolling(GXK_POLL_BURST)", appear)
        self.assertNotIn("scheduledTimerWithTimeInterval", appear)

    def test_key_lookup_reuses_the_verified_instance(self):
        """定位缓存：同一个布局里键实例是稳定的，不能每拍都从 root 扫 1500 个节点。"""
        finder = function_body(self.source, "static UIView *GXKFindNineKeyEmojiKey(UIView *root) {")
        # 命中缓存必须排在全树扫描之前。
        self.assertLess(finder.index("GXKCachedEmojiKeyValid(root)"), finder.index("NSMutableArray"))
        valid = function_body(self.source, "static BOOL GXKCachedEmojiKeyValid(UIView *root) {")
        # 命中判据与全树扫描一致：同一 root、ID 相符、可见、owner 是可见九键体。
        for required in ("gCachedEmojiRoot != root", "GXKEmojiKeyID",
                         "isDescendantOfView:root", "GXKKeyIsVisible(key, root)",
                         "GXKNineKeyBodyForKey(key, root)"):
            self.assertIn(required, valid)
        # 「两把同时可见就不猜」不能因缓存被绕过：命中前必须在九键体子树里复核唯一性。
        self.assertIn("return found == key && !stack.count", valid)
        self.assertLess(valid.index("NSMutableArray"), valid.index("return found == key"))
        # 只缓存完整扫描确认过的实例：半途放弃（stack 未空）不写缓存。
        self.assertLess(finder.index("if (stack.count ||"), finder.index("gCachedEmojiKey = candidate"))
        # 缓存必须是 weak：键被重建时自动失效，不拿旧实例冒充当前布局。
        self.assertIn("static __weak UIView *gCachedEmojiKey;", self.source)
        self.assertIn("static __weak UIView *gCachedLangKey;", self.source)
        # 世代：布局/撤键一变缓存立刻失效，结构性歧义一定落回全树扫描。
        self.assertIn("gCachedEmojiEpoch != gKeyCacheEpoch", valid)
        lang_valid = function_body(self.source, "static BOOL GXKCachedLangKeyValid(UIView *root) {")
        self.assertIn("gCachedLangEpoch != gKeyCacheEpoch", lang_valid)
        layout = function_body(self.source, "static void gkx_viewDidLayoutSubviews(id self, SEL _cmd) {")
        self.assertIn("GXKBumpKeyCacheEpoch()", layout)
        # 撤键即作废，下次从头认当前布局。
        display = (ROOT / "dylib/action_key_display.h").read_text(encoding="utf-8")
        detach = function_body(display, "static void GXKDetachActionKey(void)")
        self.assertIn("GXKClearEmojiKeyCache()", detach)
        detach_lang = function_body(self.source, "static void GXKDetachLangKey(void) {")
        self.assertIn("GXKClearLangKeyCache()", detach_lang)

    def test_polling_stops_when_idle(self):
        """空闲必须停表：计数归零后 invalidate，隐藏时也停表。"""
        pump = function_body(self.source, "static void GXKBumpPolling(NSInteger ticks) {")
        self.assertIn("gPollTicks <= 0", pump)
        self.assertIn("GXKStopPolling()", pump)
        self.assertIn("gPollTicks--", pump)
        stop = function_body(self.source, "static void GXKStopPolling(void) {")
        self.assertIn("[gStatePollTimer invalidate]", stop)
        self.assertIn("gStatePollTimer = nil", stop)
        self.assertIn("gPollTicks = 0", stop)
        gone = function_body(self.source, "static void gkx_viewWillDisappear(id self, SEL _cmd, BOOL animated)")
        self.assertIn("GXKStopPolling()", gone)
        # 旧的无条件常驻表必须消失，否则空闲仍每秒唤醒 5 次。
        self.assertNotIn("if (!gStatePollTimer) {", self.source)

    def test_action_refresh_uses_existing_key_bindings_not_a_cross_page_button(self):
        display = (ROOT / "dylib/action_key_display.h").read_text(encoding="utf-8")
        update = function_body(display, "static void GXKUpdateActionKey(UIViewController *vc)")
        self.assertIn("GXKReconcileActionDisplay", update)
        self.assertNotIn("GXKFindNineKeyEmojiKey", update,
                         "Unique input validation is for taps, not each polling frame")
        for retired in ("gActionKeyButton", "gActionHost", "GXKKeepLiveBinding", "canRetarget"):
            self.assertNotIn(retired, self.source + display)

    def test_per_key_reconcile_does_not_scan_the_controller_tree(self):
        display = (ROOT / "dylib/action_key_display.h").read_text(encoding="utf-8")
        reconcile = function_body(display, "static void GXKReconcileActionDisplay(UIView *key)")
        self.assertNotIn("GXKFindNineKeyEmojiKey", reconcile)
        self.assertNotIn("GXKComposingFullScan", reconcile)
        self.assertNotIn("NSStringFromClass", reconcile)
        self.assertNotIn("dispatch_after", reconcile)
        self.assertIn("GXKNativeIconForKey", reconcile)
        self.assertIn("GXKActionDisplayForKey", reconcile)

    def test_no_new_display_timer_or_deadline_repeats_native_work(self):
        display = (ROOT / "dylib/action_key_display.h").read_text(encoding="utf-8")
        for retired in ("scheduledTimer", "dispatch_after", "CFAbsoluteTimeGetCurrent", "gFlashDeadline",
                        "GXK_FLASH_GRACE_SECONDS", "GXK_REBIND_WAIT_SECONDS", "GXK_PARK_SECONDS"):
            self.assertNotIn(retired, display)
        coverage = function_body(display, "static BOOL GXKActionDisplayCoversIcon(")
        self.assertNotIn("GXKFindNineKeyEmojiKey", coverage)
        self.assertNotIn("GXKComposingFullScan", coverage)
        self.assertNotIn("NSStringFromClass", coverage)

    def test_composing_scan_is_event_driven_not_polled(self):
        self.assertIn("static void GXKRefreshComposingState(UIViewController *vc)", self.source)
        self.assertIn("static BOOL GXKComposingStateCached(UIViewController *vc)", self.source)
        refresh = function_body(self.source, "static void GXKRefreshComposingState(UIViewController *vc)")
        self.assertIn("GXKComposingFromProxy(vc)", refresh)
        self.assertIn("GXKComposingFullScan(vc)", refresh)
        cached = function_body(self.source, "static BOOL GXKComposingStateCached(UIViewController *vc)")
        self.assertNotIn("GXKComposingFullScan", cached)
        for hook in (
            "static void gkx_textDidChange(id self, SEL _cmd, id textInput)",
            "static void gkx_viewDidLayoutSubviews(id self, SEL _cmd)",
        ):
            body = function_body(self.source, hook)
            self.assertIn("GXKRefreshComposingState", body, hook)

    def test_dictionary_deploy_is_once_per_process(self):
        deploy = function_body(self.source, "static void GXKEnsureUserDictionaryDeployed(void)")
        first = deploy.index("gDictDeploySettled")
        self.assertLess(first, deploy.index("defaultManager"))
        self.assertIn("if (gDictDeploySettled) return;", deploy)
        self.assertGreaterEqual(deploy.count("gDictDeploySettled = YES"), 2)

    def test_haptics_are_reused_and_released(self):
        impact = function_body(self.source, "static void GXKImpact(UIImpactFeedbackStyle style)")
        self.assertIn("if (!gFbMedium)", impact)
        self.assertIn("if (!gFbLight)", impact)
        self.assertIn("[gFbMedium prepare]", impact)
        self.assertIn("[gFbLight prepare]", impact)
        self.assertEqual(impact.count("initWithStyle:"), 2, "generators must be created at most once each")
        tap = function_body(self.source, "- (void)onActionKeyTapped:(UIButton *)sender")
        self.assertNotIn("initWithStyle:", tap, "tap must not allocate a generator")
        release = function_body(self.source, "static void GXKReleaseHaptics(void)")
        self.assertIn("gFbMedium = nil", release)
        self.assertIn("gFbLight = nil", release)
        gone = function_body(self.source, "static void gkx_viewWillDisappear(id self, SEL _cmd, BOOL animated)")
        self.assertIn("GXKReleaseHaptics()", gone)
        self.assertIn("gComposingActive = NO", gone)

    def test_view_kind_cache_avoids_per_node_class_strings(self):
        """类名判定必须按类指针缓存，不能在每个节点上重新拼字符串。"""
        cache = function_body(self.source, "static NSInteger GXKViewKind(UIView *view) {")
        self.assertIn("gViewKindCache", cache)
        self.assertIn("NSValue valueWithPointer", cache)
        self.assertIn("NSStringFromClass", cache)
        # 缓存命中必须提前返回，否则缓存没有意义。
        self.assertLess(cache.index("if (cached) return cached.integerValue;"),
                        cache.index("NSStringFromClass"))
        scan = function_body(self.source, "static BOOL GXKComposingFullScan(UIViewController *vc) {")
        self.assertIn("GXKViewKind(v)", scan)
        self.assertNotIn("NSStringFromClass", scan, "scan must not format class names per node")
        self.assertNotIn("containsString:@\"Composing\"", scan)
        # 候选子树判定完立即剪枝，不把成百上千个 cell 压进栈。
        self.assertIn("continue", scan)
        self.assertLess(scan.index("GXKViewKindCandidates"), scan.index("[stack addObjectsFromArray:v.subviews]"))

    def test_composing_scan_is_throttled_with_trailing_pass(self):
        """全树扫描必须节流，且被跳过的那次要有尾随扫描兜住状态。"""
        self.assertIn("#define GXK_COMPOSING_SCAN_MIN_INTERVAL 0.25", self.source)
        refresh = function_body(self.source, "static void GXKRefreshComposingState(UIViewController *vc)")
        self.assertIn("CFAbsoluteTimeGetCurrent()", refresh)
        self.assertIn("GXK_COMPOSING_SCAN_MIN_INTERVAL", refresh)
        self.assertIn("GXKScheduleComposingScan()", refresh)
        # 代理已明确有 mark 时仍然走 O(1) 路径，不受节流影响。
        self.assertLess(refresh.index("GXKComposingFromProxy(vc)"),
                        refresh.index("CFAbsoluteTimeGetCurrent()"))
        trailing = function_body(self.source, "static void GXKScheduleComposingScan(void) {")
        self.assertIn("dispatch_after", trailing)
        self.assertIn("gComposingScanScheduled", trailing)
        self.assertIn("GXKComposingFullScan(vc)", trailing)
        # 状态没翻转时不得触发界面刷新；联想态与组字态同趟产出，任一变化都要刷新。
        self.assertIn("BOOL wasSuggesting = gSuggestingActive;", trailing)
        self.assertIn("if (composing == gComposingActive && gSuggestingActive == wasSuggesting) return;", trailing)
        self.assertLess(trailing.index("BOOL wasSuggesting"), trailing.index("GXKComposingFullScan(vc)"))

    def test_plain_typing_uses_short_settle_window(self):
        """普通打字只补两帧；只有组字状态翻转才拉起完整补帧窗口。"""
        self.assertIn("#define GXK_POLL_BURST 5", self.source)
        self.assertIn("#define GXK_POLL_SETTLE 2", self.source)
        typed = function_body(self.source, "static void gkx_textDidChange(id self, SEL _cmd, id textInput)")
        self.assertIn("BOOL wasComposing = gComposingActive;", typed)
        self.assertIn("GXKBumpPolling((wasComposing != gComposingActive) ? GXK_POLL_BURST : GXK_POLL_SETTLE);", typed)

    def test_native_obstacle_registry_is_weak_event_scoped_and_complete(self):
        """Discovery is event-scoped; hidden carriers remain eligible for live changes."""
        registry = function_body(self.visibility, "static BOOL GXKToolbarPrepareNativeObstacles(")
        for required in ("gToolbarObstacleRoot != root", "gToolbarObstacleLogo != logo",
                         "gToolbarObstacleEpoch != gToolbarContentEpoch", "!gToolbarObstacleComplete",
                         "[NSHashTable weakObjectsHashTable]", "visited++ < 800",
                         "if (pending.count) return NO;", "gToolbarObstacleComplete = YES;"):
            self.assertIn(required, registry)
        discover = registry[registry.index("if (rebuild) {"):registry.index("gToolbarObstacleComplete = YES;")]
        self.assertNotRegex(discover, r"view\.(?:hidden|isHidden|alpha)")
        self.assertIn("[view isDescendantOfView:root]", registry)
        for signature in ("static void gkx_textDidChange(", "static void gkx_viewDidLayoutSubviews(",
                          "static void gkx_viewWillAppear("):
            self.assertIn("gToolbarContentEpoch++;", function_body(self.source, signature))
        detach = function_body(self.source, "static void GXKDetachToolbar(void) {")
        self.assertIn("gToolbarObstacleComplete = NO;", detach)

    def test_keyboard_owner_registry_shares_complete_discovery_without_hidden_pruning(self):
        registry = function_body(self.visibility, "static BOOL GXKToolbarPrepareNativeObstacles(")
        discover = registry[registry.index("if (rebuild) {"):registry.index("gToolbarObstacleComplete = YES;")]
        self.assertIn("static NSHashTable<UIView *> *gToolbarKeyboardBodies;", self.visibility)
        self.assertIn("gToolbarKeyboardBodies = [NSHashTable weakObjectsHashTable];", discover)
        self.assertIn("if (!keyClass || !nineClass || !qwertyClass) return NO;", discover)
        self.assertIn("if ([view isKindOfClass:nineClass] || [view isKindOfClass:qwertyClass])", discover)
        self.assertIn("[gToolbarKeyboardBodies addObject:view];", discover)
        self.assertEqual(1, registry.count("NSMutableArray<UIView *> *pending"))
        self.assertNotIn("GXKKeyIsVisible(", discover)
        self.assertNotRegex(discover, r"view\.(?:hidden|alpha)")
        self.assertLess(discover.index("[gToolbarKeyboardBodies addObject:view]"),
                        discover.index("if (!leaf)"))
        self.assertIn("if (pending.count) return NO;", discover)

    def test_reuse_requires_live_nine_owner_and_rejects_independent_qwerty_without_band_overlap(self):
        registry = function_body(self.visibility, "static BOOL GXKToolbarPrepareNativeObstacles(")
        live = registry[registry.index("gToolbarObstacleComplete = YES;") + len("gToolbarObstacleComplete = YES;"):]
        owners = live[live.index("BOOL nineVisible = NO;"):]
        self.assertIn("for (UIView *body in gToolbarKeyboardBodies)", owners)
        self.assertIn("if (!GXKKeyIsVisible(body, root)) continue;", owners)
        code = re.sub(r"//[^\n]*", "", owners)
        self.assertIn("if ([body isKindOfClass:nineClass]) nineVisible = YES;", code)
        self.assertIn("else if ([body isKindOfClass:qwertyClass]) return NO;", code)
        self.assertIn("if (!nineVisible) return NO;", owners)
        for band_condition in ("band", "CGRect", "GXKToolbarContentBlocks", "convertRect:"):
            self.assertNotIn(band_condition, owners)
        self.assertNotIn("if (rebuild)", live)
        self.assertIn("GXKToolbarPrepareNativeObstacles(root, logo)", function_body(self.visibility, "static BOOL GXKToolbarNativeSpaceClear("))

    def test_native_content_is_checked_live_not_alpha_masked(self):
        content = function_body(self.visibility, "static BOOL GXKToolbarContentRect(")
        for required in ("collection.visibleCells.count", "numberOfItemsInSection:section",
                         "label.text.length > 0", "label.attributedText.length > 0"):
            self.assertIn(required, content)
        blocks = function_body(self.visibility, "static BOOL GXKToolbarContentBlocks(")
        self.assertIn("GXKToolbarContentRect(view, root, &rect)", blocks)
        self.assertIn("CGRectIntersection(rect, band)", blocks)
        self.assertIn("if (!GXKToolbarContentRect(view, root, &rect)) return YES;", blocks)
        final = function_body(self.visibility, "static BOOL GXKToolbarNativeSpaceClear(")
        self.assertIn("CGRectContainsRect(root.bounds, band)", final)
        self.assertIn("GXKToolbarPrepareNativeObstacles(root, logo)", final)
        self.assertIn("GXKToolbarContentBlocks(view, root, band)", final)
        toolbar = self.source[self.source.index("#pragma mark - 顶部工具条"):self.source.index("#pragma mark - 按需轮询")]
        code = re.sub(r"//[^\n]*", "", toolbar + self.visibility)
        self.assertNotRegex(code, r"\.alpha\s*=(?!=)")
        for retired in ("GXKSyncToolbarDecorations", "GXKRestoreToolbarDecorations", "gToolbarDecorations"):
            self.assertNotIn(retired, code)

    def test_native_image_carrier_is_registered_empty_and_contents_checked_live(self):
        registry = function_body(self.visibility, "static BOOL GXKToolbarPrepareNativeObstacles(")
        discover = registry[registry.index("if (rebuild) {"):registry.index("gToolbarObstacleComplete = YES;")]
        self.assertIn("BOOL icon = [view respondsToSelector:@selector(image)];", discover)
        self.assertIn("BOOL reusable = [view isKindOfClass:[UICollectionReusableView class]];", discover)
        self.assertIn("if (leaf || collection || icon || reusable || [view isKindOfClass:[UILabel class]]) [gToolbarObstacles addObject:view];", discover)
        self.assertNotIn("[(id<GXKNativeIconContent>)view image]", discover)
        content = function_body(self.visibility, "static BOOL GXKToolbarContentRect(")
        self.assertIn("UIImage *image = [(id<GXKNativeIconContent>)view image];", content)
        self.assertIn("GXKToolbarVisibleImageRect(view, root, outRect)", content)
        self.assertNotIn("GXKToolbarIconSized", content)
        self.assertIn("GXKToolbarClippedViewRect(view, root, !bounded, outRect)", content)
        self.assertIn("BOOL key = (keyClass && [view isKindOfClass:keyClass]) || [view isKindOfClass:[UIButton class]];", content)
        self.assertIn("else if (!key && [view respondsToSelector:@selector(image)])", content)

    def test_boundary_reads_same_live_rect_owner_before_cache_and_handles_left_crossing(self):
        band = function_body(self.layout, "static BOOL GXKToolbarBand(")
        self.assertLess(band.index("GXKToolbarNativeRightBoundary("), band.index("if (gToolbarBandCacheValid &&"))
        self.assertIn("CGRectEqualToRect(gToolbarBandCacheCandidateRoot, candidateInRoot)", band)
        self.assertNotIn("sibling.frame", band)
        boundary = function_body(self.visibility, "static BOOL GXKToolbarNativeRightBoundary(")
        self.assertIn("GXKToolbarContentRect(view, root, &rect)", boundary)
        self.assertIn("CGRectIntersection(rect, strip)", boundary)
        self.assertIn("MAX(CGRectGetMinX(strip), CGRectGetMinX(rect))", boundary)
        self.assertIn("if (!GXKToolbarContentRect(view, root, &rect)) return NO;", boundary)

    def test_clipping_owner_rejects_complex_geometry_and_preserves_overflow_conservatively(self):
        clip = function_body(self.visibility, "static BOOL GXKToolbarClippedViewRect(")
        for required in ("overflow ? root.layer.bounds", "ancestor.hidden", "ancestor.opacity < 0.05",
                         "ancestor.animationKeys.count", "CATransform3DIsIdentity(ancestor.transform)",
                         "CATransform3DIsIdentity(ancestor.sublayerTransform)", "depth++ < 64",
                         "ancestor.masksToBounds || ancestor == root.layer", "CGRectIntersection(visible, clip)"):
            self.assertIn(required, clip)
        anchor = function_body(self.layout, "static BOOL GXKToolbarImageRect(")
        self.assertIn("GXKToolbarVisibleImageRect(view, base, &measured)", anchor)
        self.assertIn("if (!GXKToolbarIconSized(measured)) {", anchor)
        # A clipped header G keeps its drawn rect as the last resort; the drawn rect is still measured.
        self.assertIn("CGRect drawn = root ? [root.layer convertRect:gToolbarImageDrawnRoot toLayer:base.layer] : CGRectZero;", anchor)
        self.assertIn("if (!GXKToolbarIconSized(drawn)) return NO;", anchor)
        self.assertNotIn("gToolbarImageGate", self.layout)
        physical = function_body(self.layout, "static BOOL GXKToolbarVisibleImageRect(")
        self.assertNotIn("GXKToolbarIconSized", physical)
        registry = function_body(self.visibility, "static BOOL GXKToolbarPrepareNativeObstacles(")
        self.assertIn("BOOL leaf = key || [view isKindOfClass:[UIButton class]];", registry)
        self.assertIn("for (UIView *body in gToolbarKeyboardBodies)", registry)
        self.assertIn("![body isDescendantOfView:root]", registry)

    def test_empty_content_never_bypasses_animated_layer_ancestry(self):
        """Model opacity/bounds/nil contents cannot prove presentation pixels are absent."""
        clip = function_body(self.visibility, "static BOOL GXKToolbarClippedViewRect(")
        self.assertEqual(clip.count("return YES;"), 1)
        self.assertIn("*outRect = invisible ? CGRectZero : visible; return YES;", clip)
        self.assertLess(clip.index("ancestor.animationKeys.count"), clip.index("ancestor.opacity < 0.05"))
        self.assertLess(clip.index("ancestor.animationKeys.count"), clip.index("if (ancestor == root.layer)"))
        self.assertNotIn("if (CGRectIsEmpty(visible)) return YES;", clip)
        self.assertNotIn("if (CGRectIsEmpty(clip)) return YES;", clip)
        content = function_body(self.visibility, "static BOOL GXKToolbarContentRect(")
        validation = content.index("GXKToolbarClippedViewRect(view, root, NO, &carrier)")
        for empty_check in ("if (!populated) return YES;", "if (!(label.text.length", "if (![image isKindOfClass"):
            self.assertLess(validation, content.index(empty_check))

    def test_toolbar_reuses_root_host_stack_and_replaces_constraints(self):
        """Same row/logo/root may reuse; only the patch stack receives constraints."""
        self.assertIn("static NSArray<NSLayoutConstraint *> *gToolbarConstraints;", self.source)
        update = function_body(self.source, "static void GXKUpdateToolbar(UIViewController *vc) {")
        reuse = update[update.index("BOOL reuse ="):update.index("if (!reuse)")]
        for identity in ("gToolbarRow == row", "gToolbarLogoView == logo", "gToolbarHost == root",
                         "gToolbarStack.superview == root"):
            self.assertIn(identity, reuse)
        self.assertIn("UIStackView *stack = reuse ? gToolbarStack : GXKMakeToolbar(root, tint);", update)
        self.assertIn("if (!reuse) GXKDetachToolbar();", update)
        self.assertLess(update.index("deactivateConstraints:gToolbarConstraints"),
                        update.index("gToolbarConstraints = @["))
        self.assertLess(update.index("gToolbarConstraints = @["),
                        update.index("[NSLayoutConstraint activateConstraints:gToolbarConstraints"))
        detach = function_body(self.source, "static void GXKDetachToolbar(void) {")
        for cleanup in ("deactivateConstraints:gToolbarConstraints", "gToolbarConstraints = nil;",
                        "gToolbarHost = nil;", "gToolbarBandCacheValid = NO;"):
            self.assertIn(cleanup, detach)

    def test_haptics_released_after_idle(self):
        """Taptic 引擎不能一直预热：停手 2 秒就释放 generator。"""
        self.assertIn("#define GXK_HAPTIC_IDLE_SECONDS 2.0", self.source)
        self.assertIn("static NSTimer *gHapticIdleTimer;", self.source)
        impact = function_body(self.source, "static void GXKImpact(UIImpactFeedbackStyle style) {")
        self.assertIn("GXKScheduleHapticRelease();", impact)
        schedule = function_body(self.source, "static void GXKScheduleHapticRelease(void) {")
        self.assertIn("[gHapticIdleTimer invalidate]", schedule)
        self.assertIn("GXK_HAPTIC_IDLE_SECONDS", schedule)
        self.assertIn("repeats:NO", schedule)
        # 释放必须真的把两个 generator 置空。
        self.assertIn("gFbMedium = nil;", schedule)
        self.assertIn("gFbLight = nil;", schedule)
        release = function_body(self.source, "static void GXKReleaseHaptics(void) {")
        self.assertIn("[gHapticIdleTimer invalidate]", release)

    def test_pin_toggle_skips_forced_sync(self):
        """钉子状态只有键盘自己读，不跨进程，不必强制落盘；常用语正文必须保留。"""
        pinned = function_body(self.source, "static void GXKPhrasesSetPinned(BOOL pinned) {")
        # 只看真实调用，注释里提到 synchronize 不算。
        self.assertNotIn("[defaults synchronize];", pinned)
        self.assertIn("setBool:pinned forKey:GXKPhrasesPinnedKey", pinned)
        save = function_body(self.source, "static void GXKPhraseSave(NSArray<NSString *> *list) {")
        self.assertIn("[defaults synchronize];", save)

    def test_dictionary_ships_once_and_is_found_from_both_processes(self):
        """词库只随包放一份；扩展进程要能沿 bundle 往上找到主 App 的 Frameworks。"""
        inject = (ROOT / "tools/inject.py").read_text(encoding="utf-8")
        self.assertNotIn("dict_dst_appex", inject)
        self.assertIn('dict_dst_fw = os.path.join(fw, "user_dictionary.db")', inject)
        deploy = function_body(self.source, "static void GXKEnsureUserDictionaryDeployed(void) {")
        # 候选路径必须逐个 fileExistsAtPath 验证，不能拿到第一个非 nil 就用。
        self.assertIn("for (NSString *candidate in candidates)", deploy)
        self.assertIn("[fm fileExistsAtPath:candidate]", deploy)
        self.assertIn("../../Frameworks/user_dictionary.db", deploy)

    def test_polling_never_joins_common_modes(self):
        """0.2 秒轮询只挂默认模式：挂 CommonModes 会在滚动/动画期间继续抢主线程。"""
        pump = function_body(self.source, "static void GXKBumpPolling(NSInteger ticks) {")
        self.assertIn("scheduledTimerWithTimeInterval", pump)
        self.assertNotIn("NSRunLoopCommonModes", pump)
        self.assertNotIn("addTimer:", pump)
        self.assertNotIn("NSRunLoopCommonModes", self.source)

    def test_high_frequency_callbacks_coalesce_to_last_one(self):
        """同一帧内多次文本/布局回调只让最后一次刷新，前面排队的直接丢弃。"""
        typed = function_body(self.source, "static void gkx_textDidChange(id self, SEL _cmd, id textInput)")
        self.assertIn("NSUInteger seq = ++gTextChangeSeq;", typed)
        self.assertIn("if (seq != gTextChangeSeq) return;", typed)
        # 丢弃判定必须在真正的刷新之前，否则合并没有意义。
        self.assertLess(typed.index("if (seq != gTextChangeSeq) return;"),
                        typed.index("GXKRefreshComposingState(vc)"))
        layout = function_body(self.source, "static void gkx_viewDidLayoutSubviews(id self, SEL _cmd)")
        self.assertIn("NSUInteger seq = ++gLayoutSeq;", layout)
        self.assertIn("if (seq != gLayoutSeq) return;", layout)
        self.assertLess(layout.index("if (seq != gLayoutSeq) return;"),
                        layout.index("GXKRefreshComposingState(vc)"))
        # 全树发现仍合并异步；已登记的逐键显示必须在原生 layout 返回后同栈完成。
        sync_part = layout[:layout.index("dispatch_async")]
        self.assertNotIn("GXKUpdateToolbar", sync_part)
        self.assertNotIn("GXKRefreshComposingState", sync_part)
        self.assertNotIn("GXKFindNineKeyEmojiKey", sync_part)
        self.assertIn("GXKUpdateActionKey((UIViewController *)self)", sync_part)

    def test_hot_scan_paths_cache_class_pointers(self):
        """扫描热路径只解析一次类指针，不在每个软键上重复 NSClassFromString。"""
        self.assertIn("static Class GXKClassCached(NSString *name, Class *slot)", self.source)
        helper = function_body(self.source, "static Class GXKClassCached(NSString *name, Class *slot)")
        # 解析失败（类还没加载）不能写缓存，否则永远补不上。
        self.assertIn("if (*slot) return *slot;", helper)
        self.assertIn("if (cls) *slot = cls;", helper)
        for signature in (
            "static UIView *GXKNineKeyBodyForKey(UIView *key, UIView *root)",
            "static UIView *GXKActionHostForKey(UIView *key)",
            "static UIView *GXKFindNineKeyEmojiKey(UIView *root)",
            "static BOOL GXKToolbarScan(UIView *root, UIView **outRow, UIView **outLogo, UIView **outBody, CGRect *outBand)",
            "static UIView<GXKNativeIconContent> *GXKNativeIconForKey(UIView *key)",
        ):
            owner = self.layout if "GXKToolbarScan" in signature else self.source
            body = function_body(owner, signature)
            self.assertNotIn("NSClassFromString", body, signature)
            self.assertIn("GXKClassCached(", body, signature)

    def test_toolbar_hit_band_stays_in_row_without_moving_glyph_center(self):
        """The native hit carrier and title anchor are separate, including cache hits."""
        band = function_body(self.layout, "static BOOL GXKToolbarBand(")
        self.assertLess(band.index("GXKToolbarGlyphRect(logo, row, &glyph)"),
                        band.index("if (gToolbarBandCacheValid &&"))
        for geometry in ("CGFloat left = CGRectGetMaxX(glyph) + 4.0;",
                         "GXKToolbarContentRect(logo, root, &logoCarrierRoot)",
                         "BOOL carrierIsRow = !CGRectIsEmpty(logoCarrier) &&",
                         "CGRectGetWidth(logoCarrier) >= CGRectGetWidth(row.bounds) - 8.0;",
                         "if (!CGRectIsEmpty(logoCarrier) && !carrierIsRow) left = MAX(left, CGRectGetMaxX(logoCarrier));",
                         "CGFloat barHeight = glyph.size.height;",
                         "if (barHeight < 28.0) barHeight = 28.0;",
                         "if (barHeight > row.bounds.size.height) barHeight = row.bounds.size.height;",
                         "if (barHeight < 18.0)",
                         "top = MAX(CGRectGetMinY(row.bounds), MIN(top, CGRectGetMaxY(row.bounds) - barHeight));",
                         "GXKToolbarNativeRightBoundary(root, logo, strip, &rightInRoot)",
                         "right - left >= 200.0", "CGRectContainsRect(row.bounds, candidate)",
                         "CGRectContainsRect(root.bounds, candidateInRoot)"):
            self.assertIn(geometry, band)
        self.assertEqual(1, band.count("gToolbarGlyphRoot = CGRectZero;"))
        self.assertIn("if (gToolbarBandCacheHit) gToolbarGlyphRoot = [row convertRect:glyph toView:root];", band)
        self.assertIn("if (hit) gToolbarGlyphRoot = [row convertRect:glyph toView:root];", band)
        self.assertNotIn("gToolbarGlyphRoot", function_body(self.layout, "static BOOL GXKToolbarVisibleImageRect("))

    def test_title_alignment_is_absolute_bounded_and_refreshed_before_fast_return(self):
        # 覆写 UIKit 的布局矩形会在键盘扩展的布局循环里闪退：标题内边距只用公开 API 调。
        self.assertNotIn("- (CGRect)contentRectForBounds:", self.source)
        self.assertNotIn("- (CGRect)titleRectForContentRect:", self.source)
        self.assertIn("button.titleEdgeInsets = UIEdgeInsetsMake(-6.0, 0.0, -6.0, 0.0);", self.source)
        self.assertNotIn("titleLabel.frame =", self.source)
        geometry = function_body(self.source, "static BOOL GXKSyncToolbarGeometry(")
        self.assertNotIn("titleRectForContentRect", geometry)
        for required in ("CGFloat anchorY = CGRectGetMidY(gToolbarGlyphRoot) - CGRectGetMinY(hostBand);",
                         "centerY = MAX(textHeight * 0.5, MIN(centerY, slot.size.height - textHeight * 0.5));",
                         "button.gxkContentCenterY = centerY;", "[button setNeedsLayout]",
                         "MAX(font.lineHeight, textSize.height)", "textHeight > slot.size.height",
                         "textSize.width > slot.size.width"):
            self.assertIn(required, geometry)
        update = function_body(self.source, "static void GXKUpdateToolbar(UIViewController *vc) {")
        self.assertLess(update.index("GXKSyncToolbarGeometry(gToolbarStack, hostBand)"),
                        update.index("if (CGRectEqualToRect(band, gToolbarBand)"))
        self.assertLess(update.index("GXKSyncToolbarStyle(body);"),
                        update.index("GXKSyncToolbarGeometry(stack, hostBand)"))
        self.assertIn("adjustsFontSizeToFitWidth = NO", self.source)
        self.assertNotIn("minimumScaleFactor = 0.75", self.source)

    def test_no_uikit_layout_rect_override_anywhere_in_the_dylib(self):
        """覆写 UIKit 的布局矩形会让键盘扩展在布局循环里闪退：整个 dylib 都不许有。"""
        banned = re.compile(
            r"-\s*\(\s*(?:CGRect|CGSize)\s*\)\s*"
            r"(?:contentRectForBounds|titleRectForContentRect|titleRectForBounds|"
            r"backgroundRectForBounds|imageRectForContentRect|intrinsicContentSize)\b")
        for path in sorted((ROOT / "dylib").glob("*")):
            if path.suffix not in (".m", ".h"):
                continue
            text = path.read_text(encoding="utf-8")
            found = banned.findall(text)
            self.assertEqual([], found, f"{path.name} overrides a UIKit layout rect: {found}")
        # 标题偏移只能用公开的内边距属性，不能用布局矩形回调。
        self.assertIn("button.titleEdgeInsets = UIEdgeInsetsMake(-6.0, 0.0, -6.0, 0.0);", self.source)

    def test_image_measurement_requires_identified_original_foreground_layer(self):
        image = function_body(self.layout, "static BOOL GXKToolbarVisibleImageRect(")
        for required in ('NSClassFromString(@"GKBImageLayer")', "isKindOfClass:imageLayerClass",
                         "isKindOfClass:[UIImage class]", "respondsToSelector:@selector(image)",
                         "[(id<GXKNativeIconContent>)layer image] != image",
                         "layer.contents != (__bridge id)image.CGImage", "!image.CGImage",
                         "image.imageOrientation != UIImageOrientationUp", "image.images.count",
                         "UIEdgeInsetsEqualToEdgeInsets(image.capInsets, UIEdgeInsetsZero)", "layer.mask",
                         "CGRectEqualToRect(layer.contentsRect, CGRectMake(0, 0, 1, 1))",
                         "CGRectEqualToRect(layer.contentsCenter, CGRectMake(0, 0, 1, 1))"):
            self.assertIn(required, image)
        self.assertNotIn("view.contentMode", image)
        self.assertNotIn("view.frame", image)
        self.assertNotIn("view.bounds", image)
        self.assertNotIn("image.size", image)
        self.assertNotIn("renderInContext", image)

    def test_image_geometry_uses_layer_pixel_scale_and_only_proven_gravity(self):
        image = function_body(self.layout, "static BOOL GXKToolbarVisibleImageRect(")
        for required in ("!isfinite(layer.contentsScale)", "layer.contentsScale <= 0.0",
                         "CGImageGetWidth(image.CGImage) / layer.contentsScale",
                         "CGImageGetHeight(image.CGImage) / layer.contentsScale",
                         "layer.contentsGravity isEqualToString:kCAGravityCenter",
                         "if (![layer.contentsGravity isEqualToString:kCAGravityResizeAspect]) return NO;",
                         "MIN(bounds.size.width / size.width, bounds.size.height / size.height)",
                         "CGRectGetMidX(bounds) - size.width * 0.5", "CGRectGetMidY(bounds) - size.height * 0.5",
                         "[layer convertRect:drawn toLayer:root.layer]"):
            self.assertIn(required, image)
        self.assertNotIn("kCAGravityResizeAspectFill", image)
        finite = function_body(self.layout, "static BOOL GXKToolbarFiniteRect(")
        for required in ("!CGRectIsNull(rect)", "!CGRectIsInfinite(rect)", "!CGRectIsEmpty(rect)",
                         "isfinite(rect.origin.x)", "isfinite(rect.origin.y)",
                         "isfinite(rect.size.width)", "isfinite(rect.size.height)"):
            self.assertIn(required, finite)

    def test_image_measurement_clips_live_ancestors_and_rejects_complex_or_detached_geometry(self):
        image = function_body(self.layout, "static BOOL GXKToolbarVisibleImageRect(")
        for required in ("!root.window", "view.window != root.window", "![base isDescendantOfView:root]",
                         "![view isDescendantOfView:root]", "depth++ < 64", "ancestor = ancestor.superlayer",
                         "ancestor.hidden", "ancestor.opacity < 0.05", "ancestor.mask", "ancestor.animationKeys.count",
                         "!CATransform3DIsIdentity(ancestor.transform)",
                         "!CATransform3DIsIdentity(ancestor.sublayerTransform)",
                         "if (ancestor.masksToBounds)", "[ancestor convertRect:ancestor.bounds toLayer:root.layer]",
                         "visible = CGRectIntersection(visible, clip)", "if (!GXKToolbarFiniteRect(visible)) return NO;",
                         "if (ancestor == root.layer)", "CGRectIntersection(visible, root.layer.bounds)",
                         "[root.layer convertRect:visible toLayer:base.layer]"):
            self.assertIn(required, image)
        success = image.index("return YES;")
        self.assertLess(image.index("visible = CGRectIntersection(visible, clip)"), success)
        self.assertLess(image.index("if (ancestor == root.layer)"), success)
        self.assertEqual(image.count("return YES;"), 1)
        self.assertIn("if (outRect) *outRect = CGRectZero;", image)
        self.assertIn("if (outRect) *outRect = measured;", image)
        code = re.sub(r"//[^\n]*", "", image)
        self.assertNotRegex(code, r"\.(?:bounds|frame|hidden|opacity|transform|sublayerTransform|mask|contentsScale|contentsGravity)\s*=(?!=)")
        self.assertRegex(code, r"return NO;\s*}\s*$")

    def test_glyph_requires_live_measured_image_and_complete_bounded_scan(self):
        collect = function_body(self.layout, "static void GXKToolbarGlyphCollect(")
        for required in ("GXKToolbarImageRect(sub, base, &rect)", "visited++ < 128",
                         "[out addObject:[NSValue valueWithCGRect:rect]]", "if (pending.count) [out removeAllObjects]"):
            self.assertIn(required, collect)
        self.assertNotIn("convertRect:sub.bounds", collect)
        glyph = function_body(self.layout, "static BOOL GXKToolbarGlyphRect(")
        for required in ("GXKToolbarGlyphCollect(view, base, found)", "CGFloat bottom = CGRectGetMaxY(rect);",
                         "bottom > bestBottom + 0.5", "if (better)", "if (bestArea <= 0.0) return NO;"):
            self.assertIn(required, glyph)
        self.assertNotIn("CGRectUnion", glyph)
        self.assertNotIn("if (area > bestArea)", glyph)
        self.assertNotIn("view.bounds", glyph)
        self.assertNotIn("fallback-square", re.sub(r"//[^\n]*", "", glyph))
        sized = function_body(self.layout, "static BOOL GXKToolbarIconSized(")
        for limit in ("size.width >= 8.0", "size.height >= 8.0", "size.width <= 64.0", "size.height <= 64.0"):
            self.assertIn(limit, sized)

    def test_logo_selection_requires_complete_nine_key_scan_not_tree_order(self):
        scan = function_body(self.layout, "static BOOL GXKToolbarScan(")
        for required in ("NSMutableArray<NSArray *> *logoCandidates",
                         "if (stack.count || !body || qwertyVisible || !logoCandidates.count) return NO;",
                         "if (!GXKToolbarGlyphRect(view, root, &glyph) || CGRectIsEmpty(glyph))",
                         "CGRect bodyRect = [body convertRect:body.bounds toView:root];",
                         "CGFloat gap = CGRectGetMinY(bodyRect) - CGRectGetMaxY(glyph);",
                         "BOOL better = (!logo || gap < bestGap - 0.5)"):
            self.assertIn(required, scan)
        self.assertLess(scan.index("isKindOfClass:nineClass"), scan.index("isKindOfClass:qwertyClass"))
        self.assertNotIn("if (!logo && [view isKindOfClass:logoClass]", scan)

    def test_root_host_coordinates_do_not_grow_or_repaint_native_keyboard(self):
        update = function_body(self.source, "static void GXKUpdateToolbar(UIViewController *vc) {")
        for required in ("[row convertRect:band toView:root]", "gToolbarHost = root;",
                         "[root addSubview:stack]", "gToolbarBand = band;",
                         "constraintEqualToAnchor:root.leadingAnchor constant:hostBand.origin.x - root.bounds.origin.x",
                         "constraintEqualToAnchor:root.topAnchor constant:hostBand.origin.y - root.bounds.origin.y",
                         "[stack.heightAnchor constraintEqualToConstant:hostBand.size.height]"):
            self.assertIn(required, update)
        self.assertNotIn("[row addSubview:stack]", update)
        self.assertNotRegex(update, r"\[(?:root|row|body|logo)\.heightAnchor\s+constraint")
        self.assertNotRegex(update, r"(?:root|row|body|logo)\.(?:frame|bounds|alpha|hidden|backgroundColor)\s*=(?!=)")
        self.assertNotIn("GXKToolbarSurface", self.source)
        make = function_body(self.source, "static UIStackView *GXKMakeToolbar(")
        self.assertIn("stack.backgroundColor = [UIColor clearColor];", make)
        self.assertIn("stack.backgroundColor = [UIColor clearColor];", update)

    def test_toolbar_cache_includes_fresh_glyph_and_root_geometry(self):
        band = function_body(self.layout, "static BOOL GXKToolbarBand(")
        for required in ("CGRectEqualToRect(gToolbarBandCacheCandidateRoot, candidateInRoot)", "gToolbarBandCacheEpoch == gToolbarBandEpoch",
                         "CGSizeEqualToSize(gToolbarBandCacheRowSize, row.bounds.size)",
                         "CGRectEqualToRect(gToolbarBandCacheGlyph, glyph)",
                         "CGRectEqualToRect(gToolbarBandCacheRowInRoot, rowInRoot)",
                         "CGRectEqualToRect(gToolbarBandCacheRootBounds, root.bounds)",
                         "gToolbarBandCacheGlyph = glyph;", "gToolbarBandCacheRowInRoot = rowInRoot;",
                         "gToolbarBandCacheRootBounds = root.bounds;", "return gToolbarBandCacheHit;"):
            self.assertIn(required, band)
        self.assertLess(band.index("GXKToolbarGlyphRect(logo, row, &glyph)"), band.index("if (gToolbarBandCacheValid &&"))
        self.assertLess(band.index("GXKToolbarNativeRightBoundary(root, logo, strip, &rightInRoot)"),
                        band.index("if (gToolbarBandCacheValid &&"))
        detach = function_body(self.source, "static void GXKDetachToolbar(void) {")
        self.assertIn("gToolbarBandEpoch++;", detach)
        self.assertIn("gToolbarBandCacheValid = NO;", detach)

    def test_own_overlay_views_never_register_as_native_obstacles(self):
        """诊断 HUD 与标点弹层压在同一条 G 行上：当成遮挡会把 band 宽度压成 0，工具条整条消失。"""
        self.assertIn("static NSHashTable<UIView *> *gToolbarOwnViews;", self.visibility)
        register = function_body(self.visibility, "static void GXKToolbarOwnViewRegister(UIView *view) {")
        for required in ("[gToolbarOwnViews addObject:view]", "gToolbarContentEpoch++"):
            self.assertIn(required, register)
        registry = function_body(self.visibility, "static BOOL GXKToolbarPrepareNativeObstacles(")
        self.assertIn("[gToolbarOwnViews containsObject:view]", registry)
        diag = (ROOT / "dylib/punct_diag.h").read_text(encoding="utf-8")
        self.assertIn("GXKToolbarOwnViewRegister(label)", diag)
        popup = (ROOT / "dylib/punct_popup.h").read_text(encoding="utf-8")
        self.assertIn("GXKToolbarOwnViewRegister(panel)", popup)

    def test_fast_toolbar_reuse_rechecks_style_band_and_native_content(self):
        update = function_body(self.source, "static void GXKUpdateToolbar(UIViewController *vc) {")
        fast = update[:update.index("UIView *row = nil")]
        for required in ("gToolbarHost == root", "gToolbarStack.superview == root",
                         "GXKSyncToolbarStyle(gToolbarNineBody)", "GXKToolbarBand(gToolbarRow, gToolbarLogoView, root, &band)",
                         "GXKToolbarNativeSpaceClear(root, gToolbarLogoView, hostBand)",
                         "if (composing || !clear)", "gToolbarStack.hidden = YES;"):
            self.assertIn(required, fast)
        self.assertLess(fast.index("GXKToolbarNativeSpaceClear"), fast.index("if (CGRectEqualToRect(band, gToolbarBand)"))
        self.assertIn("stack.hidden = composing || !clear;", update)

    def test_geometry_only_invalidates_layout_when_center_moves(self):
        """中心没变就不要 setNeedsLayout：五个按钮每拍各失效一次会白排整棵子树。"""
        geometry = function_body(self.source, "static BOOL GXKSyncToolbarGeometry(")
        self.assertIn("if (button.gxkContentCenterY != centerY) {", geometry)
        guard = geometry[geometry.index("if (button.gxkContentCenterY != centerY) {"):]
        self.assertLess(guard.index("button.gxkContentCenterY = centerY;"), guard.index("[button setNeedsLayout]"))
        self.assertLess(guard.index("[button setNeedsLayout]"), guard.index("}"))

    def test_missing_bundled_dictionary_settles_instead_of_rescanning(self):
        """包里没有词库时也要 settle：否则每次弹键盘都再摸三次磁盘。"""
        deploy = function_body(self.source, "static void GXKEnsureUserDictionaryDeployed(void) {")
        missing = deploy[deploy.index("if (!bundlePath) {"):]
        body = missing[:missing.index("}")]
        self.assertIn("gDictDeploySettled = YES;", body)
        self.assertLess(body.index("gDictDeploySettled = YES;"), body.index("return;"))

    def test_punct_popup_does_not_rebuild_an_unchanged_gesture(self):
        """键没换就别 detach+attach：白删白挂一次手势，还多扫一遍全树。"""
        popup = (ROOT / "dylib/punct_popup.h").read_text(encoding="utf-8")
        update = function_body(popup, "static void GXKPunctPopupUpdate(UIViewController *vc) {")
        fast = update[:update.index("UIView *found = GXKPunctFindKey(root);")]
        self.assertIn("if (GXKPunctGestureIsAttached(key, root)) {", fast)
        self.assertIn("return;", fast)
        self.assertNotIn("GXKPunctDetach();", fast)
        recovery = update[update.index("UIView *found = GXKPunctFindKey(root);"):]
        self.assertLess(recovery.index("GXKPunctDetach();"), recovery.index("GXKPunctAttach(found, root);"))
        self.assertNotIn("if (gPunctKey == found", recovery)

    def test_punct_diag_bookkeeping_is_off_by_default(self):
        """诊断关闭时不能建 ident 数组、不能 containsObject、不能拼日志字符串。"""
        popup = (ROOT / "dylib/punct_popup.h").read_text(encoding="utf-8")
        find = function_body(popup, "static UIView *GXKPunctFindKey(UIView *root) {")
        self.assertIn("BOOL diag = GXKPunctDiagEnabled();", find)
        self.assertIn("NSMutableArray<NSString *> *seenIdents = diag ? [NSMutableArray array] : nil;", find)
        self.assertIn("if (diag && ident.length && ![seenIdents containsObject:ident])", find)
        # 无 ident 的数字键只记录原生模型 ID；不再递归收集不可读的键帽文字。
        self.assertIn("NSMutableArray<NSString *> *seenDefs = diag ? [NSMutableArray array] : nil;", find)
        self.assertIn("if (diag && ident.length == 0) {", find)
        self.assertIn("GXKPunctKeyDefinitionID(v)", find)
        self.assertIn("if (![seenDefs containsObject:entry]) [seenDefs addObject:entry];", find)
        self.assertLess(find.index("if (diag && ident.length == 0) {"), find.index("GXKPunctKeyDefinitionID(v)"))
        self.assertNotIn("GXKPunctCollectTexts", find)
        # 拼日志字符串只能发生在 if (diag) 里面。
        self.assertLess(find.index("if (diag) {"), find.index("gDiagFindMiss++"))
        report = find[find.index("if (diag) {"):]
        self.assertIn("componentsJoinedByString", report)


if __name__ == "__main__":
    unittest.main(verbosity=2)
