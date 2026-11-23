// Current native contents outrank the toolbar. Discovery is event-scoped; reuse reads live views.
#ifndef GXK_TOOLBAR_VISIBILITY_H
#define GXK_TOOLBAR_VISIBILITY_H
static __weak UIView *gToolbarObstacleRoot;
static __weak UIView *gToolbarObstacleLogo;
static NSHashTable<UIView *> *gToolbarObstacles;
static NSHashTable<UIView *> *gToolbarKeyboardBodies;
static NSUInteger gToolbarContentEpoch;
static NSUInteger gToolbarObstacleEpoch;
static BOOL gToolbarObstacleComplete;
// 自家视图（诊断 HUD、标点弹层）不是原生内容。它们一旦被当成遮挡物，
// band 的右边界会被压到左边界，宽度判成 0，整条工具条静默消失。
// 用弱表按指针精确排除：tag 会和 gkx.m 里的 0x47584B5x 常量冲突。
static NSHashTable<UIView *> *gToolbarOwnViews;
static void GXKToolbarOwnViewRegister(UIView *view) {
    if (!view) return;
    if (!gToolbarOwnViews) gToolbarOwnViews = [NSHashTable weakObjectsHashTable];
    [gToolbarOwnViews addObject:view];
    // 已建好的遮挡表可能已经收录了这个视图，代次自增让下一次测量重建。
    gToolbarContentEpoch++;
}

// A successful empty rect means no visible content; NO means unproven geometry.
static BOOL GXKToolbarClippedViewRect(UIView *view, UIView *root, BOOL overflow, CGRect *outRect) {
    *outRect = CGRectZero;
    if (!view || !root.window || view.window != root.window ||
        (view != root && ![view isDescendantOfView:root])) return NO;
    CGRect visible = overflow ? root.layer.bounds : [view.layer convertRect:view.layer.bounds toLayer:root.layer];
    BOOL invisible = CGRectIsEmpty(visible);
    if (!invisible && !GXKToolbarFiniteRect(visible)) return NO;
    NSUInteger depth = 0;
    for (CALayer *ancestor = view.layer; ancestor && depth++ < 64; ancestor = ancestor.superlayer) {
        // Model bounds/opacity may already be empty while a presentation layer is still visible.
        // No empty-space success is allowed before the entire ancestry has been validated.
        if (ancestor.animationKeys.count || !CATransform3DIsIdentity(ancestor.transform) ||
            !CATransform3DIsIdentity(ancestor.sublayerTransform)) return NO;
        if (ancestor.hidden || ancestor.opacity < 0.05) invisible = YES;
        // A mask can only remove pixels, so its full bounds remain a conservative obstacle.
        if (ancestor.masksToBounds || ancestor == root.layer) {
            CGRect clip = [ancestor convertRect:ancestor.bounds toLayer:root.layer];
            if (CGRectIsEmpty(clip)) invisible = YES;
            else if (!GXKToolbarFiniteRect(clip)) return NO;
            if (!invisible) {
                visible = CGRectIntersection(visible, clip);
                invisible = CGRectIsEmpty(visible);
                if (!invisible && !GXKToolbarFiniteRect(visible)) return NO;
            }
        }
        if (ancestor == root.layer) { *outRect = invisible ? CGRectZero : visible; return YES; }
    }
    return NO;
}

static BOOL GXKToolbarContentRect(UIView *view, UIView *root, CGRect *outRect) {
    *outRect = CGRectZero;
    CGRect carrier = CGRectZero;
    // Even nil image/text/items must not bypass an active layer or ancestor animation.
    if (!GXKToolbarClippedViewRect(view, root, NO, &carrier)) return NO;
    Class keyClass = GXKClassCached(@"GKBSoftKeyView", &gCachedKeyClass);
    BOOL key = (keyClass && [view isKindOfClass:keyClass]) || [view isKindOfClass:[UIButton class]];
    if (!key && [view isKindOfClass:[UICollectionView class]]) {
        UICollectionView *collection = (UICollectionView *)view;
        BOOL populated = collection.visibleCells.count > 0;
        NSInteger sections = collection.numberOfSections;
        if (sections > 64) populated = YES;
        for (NSInteger section = 0; !populated && section < sections; section++)
            if ([collection numberOfItemsInSection:section] > 0) populated = YES;
        if (!populated) return YES; // Supplementary/custom descendants are registered separately.
    } else if (!key && [view isKindOfClass:[UILabel class]]) {
        UILabel *label = (UILabel *)view;
        if (!(label.text.length > 0 || label.attributedText.length > 0)) return YES;
    } else if (!key && [view respondsToSelector:@selector(image)]) {
        UIImage *image = [(id<GXKNativeIconContent>)view image];
        BOOL animated = [view isKindOfClass:[UIImageView class]] && [(UIImageView *)view isAnimating];
        if (![image isKindOfClass:[UIImage class]] && !animated) return YES;
        // Physical image geometry has no 8..64pt anchor-size authorization.
        if (GXKToolbarVisibleImageRect(view, root, outRect)) return YES;
        // Unsupported drawing may extend beyond an unclipped carrier. Never infer empty space.
        CALayer *layer = view.layer;
        BOOL bounded = layer.masksToBounds || [layer.contentsGravity isEqualToString:kCAGravityResize] ||
                       [layer.contentsGravity isEqualToString:kCAGravityResizeAspect];
        return GXKToolbarClippedViewRect(view, root, !bounded, outRect);
    }
    // Native keys/buttons own their complete clipped hit regions, even with empty title/image.
    *outRect = carrier;
    return YES;
}

static BOOL GXKToolbarContentBlocks(UIView *view, UIView *root, CGRect band) {
    CGRect rect = CGRectZero;
    if (!GXKToolbarContentRect(view, root, &rect)) return YES;
    return !CGRectIsEmpty(CGRectIntersection(rect, band));
}

static BOOL GXKToolbarPrepareNativeObstacles(UIView *root, UIView *logo) {
    if (!root || !logo || ![logo isDescendantOfView:root]) return NO;
    BOOL rebuild = gToolbarObstacleRoot != root || gToolbarObstacleLogo != logo ||
                   gToolbarObstacleEpoch != gToolbarContentEpoch ||
                   !gToolbarObstacleComplete;
    if (!rebuild) {
        for (UIView *view in gToolbarObstacles) {
            if (![view isDescendantOfView:root]) { rebuild = YES; break; }
        }
    }
    if (!rebuild) {
        for (UIView *body in gToolbarKeyboardBodies) {
            if (![body isDescendantOfView:root]) { rebuild = YES; break; }
        }
    }
    if (rebuild) {
        gToolbarObstacleRoot = root;
        gToolbarObstacleLogo = logo;
        gToolbarObstacleEpoch = gToolbarContentEpoch;
        gToolbarObstacleComplete = NO;
        gToolbarObstacles = [NSHashTable weakObjectsHashTable];
        gToolbarKeyboardBodies = [NSHashTable weakObjectsHashTable];
        Class keyClass = GXKClassCached(@"GKBSoftKeyView", &gCachedKeyClass);
        Class nineClass = GXKClassCached(@"GKB9KeysSoftKeyboardView", &gCachedNineKeyClass);
        Class qwertyClass = GXKClassCached(@"GKBZhQwertySoftKeyboardView", &gCachedQwertyClass);
        if (!keyClass || !nineClass || !qwertyClass) return NO;
        NSMutableArray<UIView *> *pending = [NSMutableArray arrayWithObject:root];
        NSUInteger visited = 0;
        while (pending.count && visited++ < 800) {
            UIView *view = pending.lastObject;
            [pending removeLastObject];
            if (view == logo || view == gToolbarStack || view.tag == GXK_ACTION_TAG ||
                [gToolbarOwnViews containsObject:view]) continue; // 自家视图不是原生遮挡。
            // Hidden keyboard owners are registered too: a 9→26 switch can reuse both objects.
            if ([view isKindOfClass:nineClass] || [view isKindOfClass:qwertyClass])
                [gToolbarKeyboardBodies addObject:view];
            // Include hidden objects in the registry: they may become visible without replacement.
            BOOL key = [view isKindOfClass:keyClass];
            BOOL collection = [view isKindOfClass:[UICollectionView class]];
            BOOL leaf = key || [view isKindOfClass:[UIButton class]];
            // Register the carrier even while its image is nil; contents can appear without an epoch change.
            BOOL icon = [view respondsToSelector:@selector(image)];
            // Supplementary/reusable cells can draw without a label or image child.
            BOOL reusable = [view isKindOfClass:[UICollectionReusableView class]];
            if (leaf || collection || icon || reusable || [view isKindOfClass:[UILabel class]]) [gToolbarObstacles addObject:view];
            if (!leaf) [pending addObjectsFromArray:view.subviews];
        }
        if (pending.count) return NO; // Partial traversal cannot authorize the registry.
        gToolbarObstacleComplete = YES;
    }
    // Revalidate owners on every reuse, independently of whether their keys overlap the band.
    Class nineClass = GXKClassCached(@"GKB9KeysSoftKeyboardView", &gCachedNineKeyClass);
    Class qwertyClass = GXKClassCached(@"GKBZhQwertySoftKeyboardView", &gCachedQwertyClass);
    BOOL nineVisible = NO;
    for (UIView *body in gToolbarKeyboardBodies) {
        if (!GXKKeyIsVisible(body, root)) continue;
        if ([body isKindOfClass:nineClass]) nineVisible = YES; // Nine-key inherits the QWERTY class.
        else if ([body isKindOfClass:qwertyClass]) return NO; // Independent 26-key body keeps native.
    }
    if (!nineVisible) return NO;
    return YES;
}

// Same live content owner as the final overlap check. No sibling-frame occupancy inference.
static BOOL GXKToolbarNativeRightBoundary(UIView *root, UIView *logo, CGRect strip, CGFloat *outRight) {
    if (!GXKToolbarPrepareNativeObstacles(root, logo)) return NO;
    CGFloat right = CGRectGetMaxX(strip);
    for (UIView *view in gToolbarObstacles) {
        CGRect rect = CGRectZero;
        if (!GXKToolbarContentRect(view, root, &rect)) return NO;
        if (CGRectIsEmpty(CGRectIntersection(rect, strip))) continue;
        CGFloat edge = MAX(CGRectGetMinX(strip), CGRectGetMinX(rect));
        if (edge < right) right = edge;
    }
    *outRight = right;
    return YES;
}

static BOOL GXKToolbarNativeSpaceClear(UIView *root, UIView *logo, CGRect band) {
    if (!root || !logo || !CGRectContainsRect(root.bounds, band)) return NO;
    if (!GXKToolbarPrepareNativeObstacles(root, logo)) return NO;
    for (UIView *view in gToolbarObstacles) {
        if (GXKToolbarContentBlocks(view, root, band)) return NO;
    }
    return YES;
}
#endif
