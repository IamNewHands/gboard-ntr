// action_key_display.h — same-TU action display owner for pinned Gboard 2.3.19.
// Included after native identity/style helpers in gkx.m; UIKit fixture includes that TU.
// A physical key owns its label and input-only sibling. No timer or cross-key reuse.

@interface GXKActionDisplayBinding : NSObject
@property(nonatomic, weak) UIView *key;
@property(nonatomic, weak) UIView<GXKNativeIconContent> *icon;
@property(nonatomic, weak) UIView *body;
@property(nonatomic, weak) UIView *host;
@property(nonatomic, weak) UIView *root;
@property(nonatomic, weak) UIView *nativeHost;
@property(nonatomic, weak) UIView *nativeContent;
@property(nonatomic, weak) UIViewController *controller;
@property(nonatomic, strong) UILabel *label;
@property(nonatomic, strong) UIButton *inputButton;
@property(nonatomic, strong) id model;
@property(nonatomic, strong) UIImage *normalImage;
@property(nonatomic, strong) UIImage *highlightedImage;
@property(nonatomic) NSUInteger generation;
@property(nonatomic) NSUInteger session;
@property(nonatomic) NSUInteger capturedGeneration;
@property(nonatomic) BOOL prepared;
@property(nonatomic) BOOL clickAllowed;
@property(nonatomic) BOOL confirmed;
@property(nonatomic) BOOL reconciling;
@end
@implementation GXKActionDisplayBinding @end

static char GXKActionDisplayAssociation;
// Enumeration for refresh/exit only, not a second visual or identity owner.
static NSHashTable<UIView *> *gActionDisplayKeys;
static NSUInteger gActionDisplaySession = 1;
static BOOL gUpdatingActionDisplays;

static GXKActionDisplayBinding *GXKActionDisplayForKey(UIView *key) {
    return key ? objc_getAssociatedObject(key, &GXKActionDisplayAssociation) : nil;
}

static UIView *GXKActionNativeHost(UIView *key) {
    if (![key respondsToSelector:@selector(hostView)]) return nil;
    UIView *host = ((id<GXKNativeSoftKeyContent>)key).hostView;
    return [host isKindOfClass:[UIView class]] &&
           (host == key || [host isDescendantOfView:key]) ? host : nil;
}

static void GXKCancelActionKeyPress(UIButton *sender);

@interface GXKActionInputButton : UIButton
@property(nonatomic, weak) GXKActionDisplayBinding *binding;
@end
@implementation GXKActionInputButton
- (BOOL)pointInside:(CGPoint)point withEvent:(UIEvent *)event {
    GXKActionDisplayBinding *binding = self.binding;
    UIView *key = binding.key;
    // Semantic rejection must still swallow a visible confirmed key. Never use
    // clickAllowed to disable this control and expose the native emoji beneath.
    if (![super pointInside:point withEvent:event] || !binding.prepared ||
        self.superview != binding.host || !key.userInteractionEnabled ||
        !GXKKeyIsVisible(key, binding.root)) return NO;
    CGPoint local = [self convertPoint:point toView:key];
    return [key pointInside:local withEvent:event];
}
@end

static GXKActionDisplayBinding *GXKActionBindingForInput(UIButton *sender) {
    if (![sender isKindOfClass:[GXKActionInputButton class]]) return nil;
    GXKActionDisplayBinding *binding = ((GXKActionInputButton *)sender).binding;
    return binding.inputButton == sender && GXKActionDisplayForKey(binding.key) == binding ? binding : nil;
}

static void GXKAdvanceActionGeneration(GXKActionDisplayBinding *binding) {
    binding.generation++;
    binding.capturedGeneration = 0;
    [binding.inputButton cancelTrackingWithEvent:nil];
    binding.inputButton.highlighted = NO;
}

static void GXKInvalidateActionDisplay(UIView *key) {
    GXKActionDisplayBinding *binding = GXKActionDisplayForKey(key);
    if (!binding) return;
    binding.prepared = NO; // Stop guarding before native setter/model changes.
    binding.clickAllowed = NO;
    GXKAdvanceActionGeneration(binding);
}

static void GXKRetireActionDisplay(GXKActionDisplayBinding *binding, BOOL preserveConfirmation) {
    if (!binding) return;
    BOOL active = binding.prepared || binding.label.superview || binding.inputButton.superview ||
                  binding.capturedGeneration;
    binding.prepared = NO;
    binding.clickAllowed = NO;
    if (active) GXKAdvanceActionGeneration(binding);
    [binding.label removeFromSuperview];
    [binding.inputButton removeFromSuperview];
    UIView *key = binding.key;
    UIView<GXKNativeIconContent> *icon = GXKNativeIconForKey(key);
    // Only the current native identity may receive these images. Reused return
    // models and replacement icons already repaint through their native update.
    if (icon && icon == binding.icon && ((id<GXKNativeSoftKeyContent>)key).softKeyDef == binding.model) {
        BOOL bypass = gxk_icon_write_bypass;
        gxk_icon_write_bypass = YES;
        [CATransaction begin];
        [CATransaction setDisableActions:YES];
        if (!icon.image && binding.normalImage) icon.image = binding.normalImage;
        if (!icon.highlightedImage && binding.highlightedImage) icon.highlightedImage = binding.highlightedImage;
        [CATransaction commit];
        gxk_icon_write_bypass = bypass;
    }
    if (!preserveConfirmation) {
        binding.confirmed = NO;
        binding.normalImage = nil;
        binding.highlightedImage = nil;
    }
    if (active) GXKPunctDiagLog(@"action retire key=%p model=%p icon=%p gen=%lu",
        (__bridge void *)key, (__bridge void *)binding.model,
        (__bridge void *)binding.icon, (unsigned long)binding.generation);
}

// Display ownership follows the live native tree, not model alpha/geometry.
// During an exit animation its presentation can still be visible at model zero.
static BOOL GXKActionDisplayIsCurrent(GXKActionDisplayBinding *binding) {
    UIView *key = binding.key;
    UIViewController *vc = gCurrentVC;
    if (!binding.prepared || !key || !vc || !vc.isViewLoaded ||
        binding.controller != vc || binding.root != vc.view || binding.session != gActionDisplaySession ||
        ![key.restorationIdentifier isEqualToString:GXKEmojiKeyID] ||
        GXKNineKeyBodyForKey(key, binding.root) != binding.body ||
        ![key isDescendantOfView:binding.root] || !binding.root.window ||
        key.window != binding.root.window ||
        GXKActionHostForKey(key) != binding.host || GXKNativeIconForKey(key) != binding.icon ||
        ((id<GXKNativeSoftKeyContent>)key).softKeyDef != binding.model ||
        GXKActionNativeHost(key) != binding.nativeHost ||
        binding.nativeHost.subviews.firstObject != binding.nativeContent ||
        !binding.nativeContent || ![binding.icon isDescendantOfView:binding.nativeContent] ||
        binding.label.superview != key || binding.label.hidden || binding.label.alpha < 0.05 ||
        !binding.label.text.length || !CGRectEqualToRect(binding.label.frame, key.bounds)) return NO;
    return YES;
}

static BOOL GXKActionDisplayCoversIcon(UIView *icon) {
    Class keyClass = GXKClassCached(@"GKBSoftKeyView", &gCachedKeyClass);
    for (UIView *key = icon.superview; key; key = key.superview) {
        if (![key isKindOfClass:keyClass]) continue;
        GXKActionDisplayBinding *binding = GXKActionDisplayForKey(key);
        return binding.prepared && binding.icon == icon && binding.label.superview == key &&
               GXKActionDisplayIsCurrent(binding);
    }
    return NO;
}

static void GXKRecordActionImage(UIView *key, UIImage *image, BOOL highlighted) {
    GXKActionDisplayBinding *binding = GXKActionDisplayForKey(key);
    if (gxk_icon_write_bypass || (!binding.prepared && !binding.confirmed) ||
        binding.icon != GXKNativeIconForKey(key) ||
        binding.model != ((id<GXKNativeSoftKeyContent>)key).softKeyDef) return;
    if (highlighted) binding.highlightedImage = image;
    else binding.normalImage = image;
}

// Native nil is a real state too. Observe it independently of whether a label
// currently covers the icon; invalidation may precede a same-model repaint.
static void GXKRecordActionIconWrite(UIView *icon, UIImage *image, BOOL highlighted) {
    if (gxk_icon_write_bypass || !icon) return;
    Class keyClass = GXKClassCached(@"GKBSoftKeyView", &gCachedKeyClass);
    for (UIView *key = icon.superview; key; key = key.superview) {
        if (![key isKindOfClass:keyClass]) continue;
        if (GXKNativeIconForKey(key) == icon) GXKRecordActionImage(key, image, highlighted);
        return;
    }
}

// Temporary CI-only depth probe shared by reconcile diagnostics.
static NSUInteger GXKDebugSubtreeDepth(UIView *view) {
    NSUInteger deepest = 0, visited = 0;
    NSMutableArray *stack = [NSMutableArray arrayWithObject:@[view, @0]];
    NSMutableSet *seen = [NSMutableSet set];
    while (stack.count && visited++ < 4000) {
        NSArray *item = stack.lastObject;
        [stack removeLastObject];
        UIView *v = item[0];
        NSUInteger d = [item[1] unsignedIntegerValue];
        if ([seen containsObject:v]) {
            fprintf(stderr, "[DEBUG-native-ci] CYCLE view=%p at depth %lu\n",
                (__bridge void *)v, (unsigned long)d);
            fflush(stderr);
            return 9999;
        }
        [seen addObject:v];
        if (d > deepest) deepest = d;
        for (UIView *s in v.subviews) [stack addObject:@[s, @(d + 1)]];
    }
    return deepest;
}

static void GXKReconcileActionDisplay(UIView *key) {
    if (!key) return;
    GXKActionDisplayBinding *binding = GXKActionDisplayForKey(key);
    if (binding.reconciling) return;
    Class keyClass = GXKClassCached(@"GKBSoftKeyView", &gCachedKeyClass);
    // Native construction/attachment can finish before viewWillAppear assigns
    // gCurrentVC. Remember that physical key weakly, without preparing a label
    // or granting input, so completed controller layout can reconcile it.
    if (keyClass && [key isKindOfClass:keyClass] &&
        [key.restorationIdentifier isEqualToString:GXKEmojiKeyID]) {
        if (!gActionDisplayKeys) gActionDisplayKeys = [NSHashTable weakObjectsHashTable];
        [gActionDisplayKeys addObject:key];
    }
    UIViewController *vc = gCurrentVC;
    UIView *root = vc.isViewLoaded ? vc.view : nil;
    UIView *body = GXKNineKeyBodyForKey(key, root);
    UIView *host = GXKActionHostForKey(key);
    BOOL domain = root && [key isKindOfClass:keyClass] &&
        [key.restorationIdentifier isEqualToString:GXKEmojiKeyID] && body && host &&
        [key isDescendantOfView:root] && root.window && key.window == root.window;
    if (!domain) {
        GXKRetireActionDisplay(binding, NO);
        return;
    }
    // Confirmation is physical-key/body/session continuity, not a timeout or a
    // global current button. Empty-actions newcomers never acquire this role.
    BOOL continuity = binding.confirmed && binding.body == body && binding.root == root &&
        binding.controller == vc && binding.session == gActionDisplaySession;
    UIView<GXKNativeIconContent> *icon = GXKNativeIconForKey(key);
    id model = icon ? ((id<GXKNativeSoftKeyContent>)key).softKeyDef : nil;
    BOOL actions = GXKModelHasNativeActions(model);
    BOOL clickAllowed = actions && key.userInteractionEnabled &&
        GXKKeyIsVisible(key, root) && GXKKeyIsVisible(body, root);
    UIView *nativeHost = GXKActionNativeHost(key);
    UIView *nativeContent = nativeHost.subviews.firstObject;
    UIColor *color = icon.foregroundColor;
    UIFont *font = GXKNativeActionFont(key, root);
    NSString *title = GXKActionTitle(vc);
    CGSize textSize = font ? [title sizeWithAttributes:@{NSFontAttributeName:font}] : CGSizeZero;
    BOOL contentReady = icon && model && nativeContent && nativeContent != binding.label &&
        [nativeContent isKindOfClass:[UIView class]] &&
        [icon isDescendantOfView:nativeContent] && [color isKindOfClass:[UIColor class]] && font;
    BOOL titleFits = textSize.width <= CGRectGetWidth(key.bounds) + 0.5 &&
        textSize.height <= CGRectGetHeight(key.bounds) + 0.5;
    // Fit admits the first label; a confirmed structural owner follows native
    // bounds animation even while its model size cannot contain the text.
    if (!contentReady || (!continuity && !titleFits) || (!actions && !continuity)) {
        GXKRetireActionDisplay(binding, continuity);
        return; // Never install our label as the missing native firstObject.
    }
    if (!binding) {
        binding = [[GXKActionDisplayBinding alloc] init];
        binding.key = key;
        binding.label = [[UILabel alloc] initWithFrame:key.bounds];
        binding.label.userInteractionEnabled = NO;
        binding.label.isAccessibilityElement = NO;
        binding.label.backgroundColor = [UIColor clearColor];
        binding.label.textAlignment = NSTextAlignmentCenter;
        binding.label.numberOfLines = 1;
        binding.label.autoresizingMask = UIViewAutoresizingFlexibleWidth | UIViewAutoresizingFlexibleHeight;
        GXKActionInputButton *input = [GXKActionInputButton buttonWithType:UIButtonTypeCustom];
        input.binding = binding;
        input.tag = GXK_ACTION_TAG;
        input.backgroundColor = [UIColor clearColor];
        input.adjustsImageWhenHighlighted = NO;
        input.showsTouchWhenHighlighted = NO;
        input.autoresizingMask = UIViewAutoresizingNone;
        if (!gActionTarget) gActionTarget = [[GXKActionKeyTarget alloc] init];
        [input addTarget:gActionTarget action:@selector(onActionKeyTouchDown:) forControlEvents:UIControlEventTouchDown];
        [input addTarget:gActionTarget action:@selector(onActionKeyCancelled:)
         forControlEvents:UIControlEventTouchCancel | UIControlEventTouchUpOutside];
        [input addTarget:gActionTarget action:@selector(onActionKeyTapped:) forControlEvents:UIControlEventTouchUpInside];
        binding.inputButton = input;
        objc_setAssociatedObject(key, &GXKActionDisplayAssociation, binding, OBJC_ASSOCIATION_RETAIN_NONATOMIC);
    }
    binding.reconciling = YES;
    BOOL changed = binding.model != model || binding.icon != icon || binding.body != body || binding.host != host ||
        binding.root != root || binding.controller != vc || binding.session != gActionDisplaySession ||
        binding.nativeHost != nativeHost || binding.nativeContent != nativeContent;
    if (changed) {
        binding.prepared = NO;
        GXKAdvanceActionGeneration(binding);
        if (binding.model != model || binding.icon != icon) {
            binding.normalImage = nil;
            binding.highlightedImage = nil;
        }
    }
    // Losing visibility or native input capability cancels a held touch without
    // retiring text or restoring the native icon during unfinished animation.
    if (!changed && binding.clickAllowed && !clickAllowed) GXKAdvanceActionGeneration(binding);
    binding.icon = icon;
    binding.model = model;
    binding.body = body;
    binding.host = host;
    binding.root = root;
    binding.nativeHost = nativeHost;
    binding.nativeContent = nativeContent;
    binding.controller = vc;
    binding.session = gActionDisplaySession;
    binding.clickAllowed = clickAllowed;
    binding.confirmed = actions || continuity;
    [CATransaction begin];
    [CATransaction setDisableActions:YES];
    if (![binding.label.font isEqual:font]) binding.label.font = font;
    if (![binding.label.textColor isEqual:color]) binding.label.textColor = color;
    if (![binding.label.text isEqualToString:title]) binding.label.text = title;
    if (!CGRectEqualToRect(binding.label.frame, key.bounds)) binding.label.frame = key.bounds;
    binding.label.hidden = NO;
    // Native content is already first. Append to key, not the native dictionary.
    if (binding.label.superview != key) {
        fprintf(stderr, "[DEBUG-native-ci] bind label add key=%p(%s) subviews=%lu depth=%lu\n",
            (__bridge void *)key, class_getName(object_getClass(key)),
            (unsigned long)key.subviews.count, (unsigned long)GXKDebugSubtreeDepth(key));
        fflush(stderr);
        [key addSubview:binding.label];
    }
    if (key.subviews.lastObject != binding.label) [key bringSubviewToFront:binding.label];
    CGRect inputRect = [key convertRect:key.bounds toView:host];
    if (!CGRectEqualToRect(binding.inputButton.frame, inputRect)) binding.inputButton.frame = inputRect;
    if (binding.inputButton.superview != host) {
        fprintf(stderr, "[DEBUG-native-ci] bind input add host=%p(%s) key=%p subviews=%lu depth=%lu\n",
            (__bridge void *)host, class_getName(object_getClass(host)), (__bridge void *)key,
            (unsigned long)host.subviews.count, (unsigned long)GXKDebugSubtreeDepth(host));
        fflush(stderr);
        [host addSubview:binding.inputButton];
    }
    if (host.subviews.lastObject != binding.inputButton) [host bringSubviewToFront:binding.inputButton];
    binding.inputButton.accessibilityLabel = title;
    binding.inputButton.accessibilityTraits = UIAccessibilityTraitKeyboardKey |
        (clickAllowed ? UIAccessibilityTraitNone : UIAccessibilityTraitNotEnabled);
    binding.prepared = YES;
    // Our previously cleared nil getters are not new native writes. Initial or
    // replacement identities already start with nil snapshots; setters capture
    // explicit native nil updates for existing identities.
    if (icon.image) GXKRecordActionImage(key, icon.image, NO);
    if (icon.highlightedImage) GXKRecordActionImage(key, icon.highlightedImage, YES);
    GXKClearIconImages(icon);
    [CATransaction commit];
    binding.reconciling = NO;
    if (changed) GXKPunctDiagLog(@"action bind key=%p model=%p icon=%p gen=%lu click=%d",
        (__bridge void *)key, (__bridge void *)model, (__bridge void *)icon,
        (unsigned long)binding.generation, binding.clickAllowed);
}

static void GXKCaptureActionKeyPress(UIButton *sender) {
    GXKActionDisplayBinding *binding = GXKActionBindingForInput(sender);
    if (!binding) return;
    GXKReconcileActionDisplay(binding.key);
    binding.capturedGeneration = GXKActionDisplayIsCurrent(binding) && binding.clickAllowed &&
        sender.superview == binding.host && GXKModelHasNativeActions(binding.model) ? binding.generation : 0;
}

static void GXKCancelActionKeyPress(UIButton *sender) {
    GXKActionBindingForInput(sender).capturedGeneration = 0;
}

static GXKActionDisplayBinding *GXKValidateActionKeyPress(UIButton *sender, UIViewController *vc) {
    GXKActionDisplayBinding *binding = GXKActionBindingForInput(sender);
    NSUInteger capturedGeneration = binding.capturedGeneration;
    binding.capturedGeneration = 0; // Each TouchDown authorizes at most one action.
    if (!binding || !capturedGeneration || capturedGeneration != binding.generation || vc != gCurrentVC) return nil;
    GXKReconcileActionDisplay(binding.key);
    if (capturedGeneration != binding.generation || !binding.clickAllowed ||
        !binding.key.userInteractionEnabled || !GXKActionDisplayIsCurrent(binding) || sender.superview != binding.host ||
        !GXKModelHasNativeActions(binding.model)) return nil;
    // A peer can attach without a key callback. Low-frequency taps must force
    // current whole-tree uniqueness; do not trust the body-local cached epoch.
    GXKBumpKeyCacheEpoch();
    if (GXKFindNineKeyEmojiKey(vc.view) != binding.key) return nil;
    return capturedGeneration == binding.generation && GXKActionDisplayIsCurrent(binding) ? binding : nil;
}

static void GXKUpdateActionKey(UIViewController *vc) {
    if (!vc || vc != gCurrentVC || !vc.isViewLoaded || gUpdatingActionDisplays) return;
    gUpdatingActionDisplays = YES;
    for (UIView *key in gActionDisplayKeys.allObjects) GXKReconcileActionDisplay(key);
    gUpdatingActionDisplays = NO;
}

static void GXKDetachActionKey(void) {
    for (UIView *key in gActionDisplayKeys.allObjects) GXKRetireActionDisplay(GXKActionDisplayForKey(key), NO);
    gActionDisplaySession++;
    GXKClearEmojiKeyCache();
}
