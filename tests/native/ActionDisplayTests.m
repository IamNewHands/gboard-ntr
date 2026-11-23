// Production action-display regression fixture for an installed iOS Simulator.
// Run: bash tests/native/run_tests.sh (macOS/Xcode only).
// UIKit owns attachment, layout, hit testing and layers. Fakes below model only
// pinned upstream content/model behavior; all display/input policy comes from gkx.m.
#import <XCTest/XCTest.h>
#import <UIKit/UIKit.h>
#import <QuartzCore/QuartzCore.h>
#import <objc/runtime.h>
#import <stdio.h>

// Temporary CI-only boundary probe. Remove after the shared SIGSEGV is located.
static void GXKDebugNativePhase(const char *phase) {
    fprintf(stderr, "[DEBUG-native-ci] %s\n", phase);
    fflush(stderr);
}

// Bounded subtree walk: a parent cycle surfaces as CYCLE instead of a hang.
static NSUInteger GXKDebugDepth(UIView *view) {
    if (!view) return 0;
    NSMutableArray *stack = [NSMutableArray arrayWithObject:@[view, @0]];
    NSMutableSet *seen = [NSMutableSet set];
    NSUInteger deepest = 0, visited = 0;
    while (stack.count && visited++ < 4000) {
        NSArray *item = stack.lastObject;
        [stack removeLastObject];
        UIView *v = item[0];
        NSUInteger d = [item[1] unsignedIntegerValue];
        if ([seen containsObject:v]) {
            fprintf(stderr, "[DEBUG-native-ci] CYCLE %s at depth %lu class=%s\n",
                "subtree", (unsigned long)d, class_getName(object_getClass(v)));
            fflush(stderr);
            return 9999;
        }
        [seen addObject:v];
        if (d > deepest) deepest = d;
        for (UIView *s in v.subviews) [stack addObject:@[s, @(d + 1)]];
    }
    return deepest;
}

static void GXKDebugDepthPhase(const char *phase, UIView *view) {
    fprintf(stderr, "[DEBUG-native-ci] %s depth=%lu subviews=%lu\n",
        phase, (unsigned long)GXKDebugDepth(view), (unsigned long)view.subviews.count);
    fflush(stderr);
}

@interface GKBImageLayer : CALayer {
    UIImage *_fixtureImage;
    UIImage *_fixtureHighlightedImage;
}
@property(nonatomic, strong) UIImage *image;
@property(nonatomic, strong) UIImage *highlightedImage;
@property(nonatomic) NSUInteger normalWrites;
@property(nonatomic) NSUInteger highlightedWrites;
@end

@implementation GKBImageLayer
- (UIImage *)image { return _fixtureImage; }
- (void)setImage:(UIImage *)image {
    self.normalWrites++;
    _fixtureImage = image;
    self.contents = image ? (__bridge id)image.CGImage : nil;
}
- (UIImage *)highlightedImage { return _fixtureHighlightedImage; }
- (void)setHighlightedImage:(UIImage *)image {
    self.highlightedWrites++;
    _fixtureHighlightedImage = image;
}
- (id<CAAction>)actionForKey:(NSString *)key { return nil; } // Pinned stock implementation.
@end

@interface GKBImageViewWithBackground : UIView
@property(nonatomic, strong) UIImage *image;
@property(nonatomic, strong) UIImage *highlightedImage;
@property(nonatomic, strong) UIImage *backgroundImage;
@property(nonatomic, strong) UIImage *highlightedBackgroundImage;
@property(nonatomic, strong) UIColor *foregroundColor;
@property(nonatomic, strong) GKBImageLayer *backgroundLayer;
@property(nonatomic, strong) GKBImageLayer *fixtureMaskLayer;
@property(nonatomic) NSUInteger normalWrites;
@property(nonatomic) NSUInteger highlightedWrites;
@property(nonatomic) NSUInteger backgroundWrites;
@property(nonatomic) NSUInteger highlightedBackgroundWrites;
@end

@implementation GKBImageViewWithBackground
+ (Class)layerClass { return GKBImageLayer.class; }
- (instancetype)initWithFrame:(CGRect)frame {
    self = [super initWithFrame:frame];
    if (self) {
        _foregroundColor = UIColor.darkGrayColor;
        _backgroundLayer = [[GKBImageLayer alloc] init];
        _backgroundLayer.delegate = self;
        [self.layer addSublayer:_backgroundLayer];
        _fixtureMaskLayer = [[GKBImageLayer alloc] init];
        _fixtureMaskLayer.delegate = self;
        // Keep the default icon unmasked so raster positive controls are meaningful.
        // Only the layer-identity test installs this separate mask.
        self.userInteractionEnabled = NO;
    }
    return self;
}
- (UIImage *)image { return ((GKBImageLayer *)self.layer).image; }
- (void)setImage:(UIImage *)image {
    self.normalWrites++;
    ((GKBImageLayer *)self.layer).image = image;
}
- (UIImage *)highlightedImage { return ((GKBImageLayer *)self.layer).highlightedImage; }
- (void)setHighlightedImage:(UIImage *)image {
    self.highlightedWrites++;
    ((GKBImageLayer *)self.layer).highlightedImage = image;
}
- (UIImage *)backgroundImage { return self.backgroundLayer.image; }
- (void)setBackgroundImage:(UIImage *)image {
    self.backgroundWrites++;
    self.backgroundLayer.image = image;
}
- (UIImage *)highlightedBackgroundImage { return self.backgroundLayer.highlightedImage; }
- (void)setHighlightedBackgroundImage:(UIImage *)image {
    self.highlightedBackgroundWrites++;
    self.backgroundLayer.highlightedImage = image;
}
@end

@interface GKBSoftKeyboardViewWithFixedLayout : UIView @end
@implementation GKBSoftKeyboardViewWithFixedLayout @end
@interface GKBZhQwertySoftKeyboardView : GKBSoftKeyboardViewWithFixedLayout @end
@implementation GKBZhQwertySoftKeyboardView @end
@interface GKB9KeysSoftKeyboardView : GKBZhQwertySoftKeyboardView @end
@implementation GKB9KeysSoftKeyboardView @end
@interface GXKFixtureCandidateView : UIView @end
@implementation GXKFixtureCandidateView @end

@interface GXKFixtureSoftKeyDef : NSObject
@property(nonatomic, copy) NSArray *actionsArray;
@property(nonatomic, strong) UIImage *normalImage;
@property(nonatomic, strong) UIImage *highlightedImage;
@property(nonatomic, copy) NSString *layout;
@end
@implementation GXKFixtureSoftKeyDef @end

@interface GKBSoftKeyView : UIView {
    GXKFixtureSoftKeyDef *_fixtureDef;
}
@property(nonatomic, copy) NSDictionary *idToViewDict;
@property(nonatomic, strong) GXKFixtureSoftKeyDef *softKeyDef;
@property(nonatomic, strong) UIView *separateHost;
@property(nonatomic, readonly) UIView *hostView;
@property(nonatomic, weak) UIView *nativeLayoutFirstObject;
@property(nonatomic) NSUInteger nativeUpdateCount;
@property(nonatomic) NSUInteger nativeTouchEnds;
- (void)resetView;
- (void)buildNativeContents;
- (void)replaceNativeIcon;
- (void)updateView;
@end

@implementation GKBSoftKeyView
- (instancetype)initWithFrame:(CGRect)frame {
    self = [super initWithFrame:frame];
    if (self) _idToViewDict = @{};
    return self;
}
- (UIView *)hostView { return self.separateHost ?: self; }
- (GXKFixtureSoftKeyDef *)softKeyDef { return _fixtureDef; }
- (void)setSoftKeyDef:(GXKFixtureSoftKeyDef *)model {
    if (model == _fixtureDef) return;
    BOOL rebuild = !_fixtureDef || ![_fixtureDef.layout isEqualToString:model.layout];
    GXKDebugNativePhase("setter: before reset");
    if (rebuild) [self resetView];
    GXKDebugDepthPhase("setter: after reset", self);
    _fixtureDef = model;
    if (rebuild) [self buildNativeContents];
    GXKDebugDepthPhase("setter: after build", self);
    GXKDebugNativePhase("setter: before updateView");
    [self updateView];
    GXKDebugDepthPhase("setter: after updateView", self);
}
- (void)resetView {
    // Stock resetView removes every child of hostView, including foreign children.
    for (UIView *view in self.hostView.subviews.copy) [view removeFromSuperview];
    self.idToViewDict = @{};
}
- (void)buildNativeContents {
    GXKDebugNativePhase("build: before content alloc");
    UIView *content = [[UIView alloc] initWithFrame:self.hostView.bounds];
    content.userInteractionEnabled = NO;
    GXKDebugNativePhase("build: after content alloc");
    GKBImageViewWithBackground *icon = [[GKBImageViewWithBackground alloc] initWithFrame:content.bounds];
    icon.restorationIdentifier = @"image";
    GXKDebugNativePhase("build: after icon alloc");
    [content addSubview:icon];
    GXKDebugNativePhase("build: after content addSubview icon");
    [self.hostView addSubview:content]; // Native content must be first, before GXK's label.
    GXKDebugNativePhase("build: after host addSubview content");
    NSMutableDictionary *contents = [@{@"image": icon} mutableCopy];
    if ([self.restorationIdentifier isEqualToString:@"key_pos_9keys_return"]) {
        UILabel *label = [[UILabel alloc] initWithFrame:content.bounds];
        label.restorationIdentifier = @"label";
        label.text = @"换行";
        label.font = [UIFont systemFontOfSize:16.0];
        label.textColor = UIColor.darkGrayColor;
        [content addSubview:label];
        contents[@"label"] = label;
    }
    self.idToViewDict = contents;
}
- (void)replaceNativeIcon {
    UIView *content = self.hostView.subviews.firstObject;
    [self.idToViewDict[@"image"] removeFromSuperview];
    GKBImageViewWithBackground *icon = [[GKBImageViewWithBackground alloc] initWithFrame:content.bounds];
    icon.restorationIdentifier = @"image";
    [content addSubview:icon];
    NSMutableDictionary *contents = [self.idToViewDict mutableCopy];
    contents[@"image"] = icon;
    self.idToViewDict = contents;
    [self updateView];
}
- (void)updateView {
    GXKDebugDepthPhase("updateView: entry", self);
    self.nativeUpdateCount++;
    GKBImageViewWithBackground *icon = self.idToViewDict[@"image"];
    UIView *native = self.hostView.subviews.firstObject;
    NSAssert(!icon || native == icon || [icon isDescendantOfView:native],
             @"Native update must find the real content in hostView.subviews.firstObject.");
    GXKDebugNativePhase("updateView: before normalImage");
    icon.image = self.softKeyDef.normalImage;
    GXKDebugNativePhase("updateView: after normalImage");
    icon.highlightedImage = self.softKeyDef.highlightedImage;
    GXKDebugNativePhase("updateView: after highlightedImage");
}
- (void)layoutSubviews {
    [super layoutSubviews];
    UIView *content = self.hostView.subviews.firstObject;
    self.nativeLayoutFirstObject = content;
    content.frame = self.hostView.bounds;
    ((UIView *)self.idToViewDict[@"image"]).frame = content.bounds;
}
- (UIView *)hitTest:(CGPoint)point withEvent:(UIEvent *)event {
    // Pinned native key does not descend into children. Production input must be a sibling.
    return !self.hidden && self.alpha >= 0.05 && self.userInteractionEnabled &&
           [self pointInside:point withEvent:event] ? self : nil;
}
- (void)touchesEnded:(NSSet<UITouch *> *)touches withEvent:(UIEvent *)event {
    self.nativeTouchEnds++;
    [super touchesEnded:touches withEvent:event];
}
@end

@interface GXKFixtureProxy : NSObject
@property(nonatomic, copy) NSString *markedText;
@property(nonatomic, copy) NSString *documentContextBeforeInput;
@property(nonatomic, copy) NSString *documentContextAfterInput;
@property(nonatomic, copy) NSString *selectedText;
@property(nonatomic, strong) NSMutableArray<NSString *> *insertions;
@property(nonatomic) NSUInteger unmarkCalls;
- (void)insertText:(NSString *)text;
- (void)unmarkText;
@end
@implementation GXKFixtureProxy
- (instancetype)init {
    self = [super init];
    if (self) {
        _markedText = @"";
        _documentContextBeforeInput = @"";
        _documentContextAfterInput = @"";
        _insertions = [NSMutableArray array];
    }
    return self;
}
- (void)insertText:(NSString *)text { [self.insertions addObject:text]; }
- (void)unmarkText { self.unmarkCalls++; self.markedText = @""; }
@end

@interface GXKFixtureKeyboardController : UIInputViewController
@property(nonatomic, strong) GXKFixtureProxy *fixtureProxy;
// Legacy clear-composing enumerates controller ivars with object_getIvar.
// Keep fixture storage object-only; counters expose scalar getters, not scalar ivars.
@property(nonatomic, strong) NSNumber *fixtureDismissCalls;
@property(nonatomic, strong) NSNumber *fixtureResetCalls;
@property(nonatomic, strong) NSNumber *fixtureAbortCalls;
@property(nonatomic, readonly) NSUInteger dismissCalls;
@property(nonatomic, readonly) NSUInteger resetCalls;
@property(nonatomic, readonly) NSUInteger abortCalls;
@end
@implementation GXKFixtureKeyboardController
- (void)loadView { self.view = [[UIView alloc] initWithFrame:CGRectMake(0, 0, 390, 844)]; }
- (id<UITextDocumentProxy>)textDocumentProxy { return (id<UITextDocumentProxy>)self.fixtureProxy; }
- (NSUInteger)dismissCalls { return self.fixtureDismissCalls.unsignedIntegerValue; }
- (NSUInteger)resetCalls { return self.fixtureResetCalls.unsignedIntegerValue; }
- (NSUInteger)abortCalls { return self.fixtureAbortCalls.unsignedIntegerValue; }
- (void)dismissKeyboard { self.fixtureDismissCalls = @(self.dismissCalls + 1); }
- (void)resetKeyboard { self.fixtureResetCalls = @(self.resetCalls + 1); self.fixtureProxy.markedText = @""; }
- (void)abortComposing { self.fixtureAbortCalls = @(self.abortCalls + 1); self.fixtureProxy.markedText = @""; }
@end

#ifndef GXK_ACTION_DISPLAY_TESTING
#define GXK_ACTION_DISPLAY_TESTING 1
#endif
#include "../../dylib/gkx.m"

static UIImage *GXKFixtureImage(UIColor *color) {
    UIGraphicsBeginImageContextWithOptions(CGSizeMake(4, 4), NO, 1.0);
    [color setFill];
    UIRectFill(CGRectMake(0, 0, 4, 4));
    UIImage *image = UIGraphicsGetImageFromCurrentImageContext();
    UIGraphicsEndImageContext();
    return image;
}

// Offscreen raster controls inspect model-layer output, not render-server presentation.
static NSData *GXKFixtureRaster(UIView *view) {
    size_t width = (size_t)ceil(CGRectGetWidth(view.bounds));
    size_t height = (size_t)ceil(CGRectGetHeight(view.bounds));
    NSMutableData *data = [NSMutableData dataWithLength:width * height * 4];
    CGColorSpaceRef space = CGColorSpaceCreateDeviceRGB();
    CGContextRef context = CGBitmapContextCreate(data.mutableBytes, width, height, 8, width * 4,
        space, kCGImageAlphaPremultipliedLast | kCGBitmapByteOrder32Big);
    CGColorSpaceRelease(space);
    NSCAssert(context != NULL, @"Raster control requires a nonempty bitmap.");
    CGContextTranslateCTM(context, 0, (CGFloat)height);
    CGContextScaleCTM(context, 1, -1);
    [view.layer renderInContext:context];
    CGContextRelease(context);
    return data;
}
static NSUInteger GXKFixtureVisiblePixels(NSData *data) {
    const unsigned char *bytes = data.bytes;
    NSUInteger count = 0;
    for (NSUInteger i = 0; i + 3 < data.length; i += 4) if (bytes[i + 3] > 10) count++;
    return count;
}
static NSUInteger GXKFixtureBluePixels(NSData *data) {
    const unsigned char *bytes = data.bytes;
    NSUInteger count = 0;
    for (NSUInteger i = 0; i + 3 < data.length; i += 4)
        if (bytes[i + 3] > 10 && bytes[i + 2] > 100 && bytes[i] < 20 && bytes[i + 1] < 20) count++;
    return count;
}

@interface GXKActionDisplayTests : XCTestCase
@property(nonatomic, strong) UIWindow *fixtureWindow;
@property(nonatomic, strong) GXKFixtureKeyboardController *controller;
@property(nonatomic, strong) GKB9KeysSoftKeyboardView *body;
@property(nonatomic, strong) GKBSoftKeyView *returnKey;
@property(nonatomic, strong) UIImage *normalImage;
@property(nonatomic, strong) UIImage *highlightedImage;
@end

@implementation GXKActionDisplayTests
- (void)setUp {
    [super setUp];
    XCTAssertTrue(NSThread.isMainThread, @"UIKit fixture must execute on the main thread.");
    // Bisect 1: identical fixture construction with NO dylib hooks installed.
    // Surviving here means the dylib hook path owns the crash.
    GXKDebugNativePhase("pre-hook probe: before alloc");
    GKBSoftKeyView *probeKey = [GKBSoftKeyView alloc];
    GXKDebugNativePhase("pre-hook probe: after alloc");
    probeKey = [probeKey initWithFrame:CGRectMake(0, 0, 48, 44)];
    GXKDebugNativePhase("pre-hook probe: after init");
    probeKey.restorationIdentifier = @"key_pos_9keys_return";
    GXKFixtureSoftKeyDef *probeModel = [[GXKFixtureSoftKeyDef alloc] init];
    probeModel.actionsArray = @[@"native-action"];
    probeModel.layout = @"pre-hook-probe";
    GXKDebugNativePhase("pre-hook probe: before model assignment");
    probeKey.softKeyDef = probeModel;
    GXKDebugNativePhase("pre-hook probe: after model assignment");
    probeKey = nil;
    GXKDebugNativePhase("before hook installation");
    GXKInstallIconWriteGuard(); // Install the actual production native/key/layer hooks.
    GXKDebugNativePhase("after hook installation");
    gCurrentVC = nil;
    GXKDetachActionKey();
    GXKStopPolling();
    GXKClearEmojiKeyCache();
    GXKResetNativeKeyStyle();
    gComposingActive = NO;
    gSuggestingActive = NO;
    gComposingScanAt = 0;
    GXKDebugNativePhase("before fixture images");
    self.normalImage = GXKFixtureImage(UIColor.blueColor);
    self.highlightedImage = GXKFixtureImage(UIColor.orangeColor);
    GXKDebugNativePhase("before controller initialization");
    self.controller = [[GXKFixtureKeyboardController alloc] init];
    GXKDebugNativePhase("after controller initialization");
    self.controller.fixtureProxy = [[GXKFixtureProxy alloc] init];
    self.fixtureWindow = [[UIWindow alloc] initWithFrame:CGRectMake(0, 0, 390, 844)];
    GXKDebugNativePhase("before root controller assignment");
    self.fixtureWindow.rootViewController = self.controller;
    GXKDebugNativePhase("after root controller assignment / before window display");
    [self.fixtureWindow makeKeyAndVisible];
    GXKDebugNativePhase("after window display");
    gCurrentVC = self.controller;
    self.body = [[GKB9KeysSoftKeyboardView alloc] initWithFrame:CGRectMake(0, 120, 390, 260)];
    [self.controller.view addSubview:self.body];
    GXKDebugNativePhase("before native return key construction");
    self.returnKey = [self makeKey:@"key_pos_9keys_return" separateHost:NO attach:NO];
    GXKDebugNativePhase("after native return key construction");
    self.returnKey.frame = CGRectMake(330, 200, 48, 44);
    [self.body addSubview:self.returnKey];
    GXKDebugNativePhase("after native return key attachment / setup complete");
}
- (void)tearDown {
    gCurrentVC = nil;
    GXKDetachActionKey();
    GXKStopPolling();
    GXKDetachLangKey();
    GXKDetachToolbar();
    GXKResetNativeKeyStyle();
    GXKReleaseHaptics();
    self.fixtureWindow.hidden = YES;
    self.fixtureWindow.rootViewController = nil;
    self.returnKey = nil;
    self.body = nil;
    self.controller = nil;
    self.fixtureWindow = nil;
    [super tearDown];
}
- (GXKFixtureSoftKeyDef *)modelWithActions:(NSArray *)actions layout:(NSString *)layout {
    GXKFixtureSoftKeyDef *model = [[GXKFixtureSoftKeyDef alloc] init];
    model.actionsArray = actions;
    model.layout = layout;
    model.normalImage = self.normalImage;
    model.highlightedImage = self.highlightedImage;
    return model;
}
- (GKBSoftKeyView *)makeKey:(NSString *)identity separateHost:(BOOL)separate attach:(BOOL)attach {
    GXKDebugNativePhase("before key alloc");
    GKBSoftKeyView *key = [GKBSoftKeyView alloc];
    GXKDebugNativePhase("after key alloc");
    key = [key initWithFrame:CGRectMake(330, 145, 48, 44)];
    GXKDebugNativePhase("after key init");
    key.restorationIdentifier = identity;
    GXKDebugNativePhase("after identity assignment");
    if (separate) {
        key.separateHost = [[UIView alloc] initWithFrame:key.bounds];
        key.separateHost.userInteractionEnabled = NO;
        [key addSubview:key.separateHost];
    }
    GXKFixtureSoftKeyDef *model = [self modelWithActions:@[@"native-action"] layout:@"icon"];
    GXKDebugNativePhase("after model creation");
    key.softKeyDef = model;
    GXKDebugNativePhase("after model assignment");
    if (attach) [self.body addSubview:key];
    return key;
}
- (GKBSoftKeyView *)emoji { return [self makeKey:GXKEmojiKeyID separateHost:NO attach:YES]; }
- (GKBImageViewWithBackground *)icon:(GKBSoftKeyView *)key { return key.idToViewDict[@"image"]; }
- (void)press:(UIButton *)input {
    [input sendActionsForControlEvents:UIControlEventTouchDown];
    [input sendActionsForControlEvents:UIControlEventTouchUpInside];
    GXKStopPolling(); // Existing production refresh polling is not this fixture's clock.
}
- (void)assertPrepared:(GKBSoftKeyView *)key {
    GXKActionDisplayBinding *binding = GXKActionDisplayForKey(key);
    XCTAssertNotNil(binding);
    XCTAssertTrue(binding.prepared);
    XCTAssertEqual(binding.key, key);
    XCTAssertEqual(binding.label.superview, key);
    XCTAssertFalse(binding.label.userInteractionEnabled);
    XCTAssertEqualObjects(binding.label.text, @"换行");
    XCTAssertEqual(binding.inputButton.superview, GXKActionHostForKey(key));
    XCTAssertEqual(binding.inputButton.tag, GXK_ACTION_TAG);
    XCTAssertNil([binding.inputButton titleForState:UIControlStateNormal]);
    XCTAssertTrue(CGRectEqualToRect(binding.label.frame, key.bounds));
    XCTAssertNotEqual(key.hostView.subviews.firstObject, binding.label);
    XCTAssertEqual(binding.nativeContent, key.hostView.subviews.firstObject);
    XCTAssertTrue([[self icon:key] isDescendantOfView:binding.nativeContent]);
    XCTAssertTrue(GXKActionDisplayCoversIcon([self icon:key]));
    XCTAssertNil([self icon:key].image);
    XCTAssertNil([self icon:key].highlightedImage);
}

- (void)testFirstAttachmentCompletesProductionDisplayBeforeAQueueTurn {
    GKBSoftKeyView *key = [self makeKey:GXKEmojiKeyID separateHost:NO attach:NO];
    XCTAssertFalse(GXKActionDisplayForKey(key).prepared);
    XCTAssertEqual([self icon:key].image, self.normalImage); // Pre-root native initView/updateView.
    [self.body addSubview:key]; // Real UIKit didMove hooks, no manual reconcile or dispatch wait.
    [self assertPrepared:key];
    XCTAssertEqual(GXKFindNineKeyEmojiKey(self.controller.view), key);
    CGPoint p = [key convertPoint:CGPointMake(24, 22) toView:self.body];
    XCTAssertEqual([self.body hitTest:p withEvent:nil], GXKActionDisplayForKey(key).inputButton);
    XCTAssertEqual([key hitTest:CGPointMake(24, 22) withEvent:nil], key);
}
- (void)testIndependentNativeHostKeepsNativeFirstObjectAndKeyOwnedLabel {
    GKBSoftKeyView *key = [self makeKey:GXKEmojiKeyID separateHost:YES attach:YES];
    [self assertPrepared:key];
    GXKActionDisplayBinding *binding = GXKActionDisplayForKey(key);
    XCTAssertEqual(binding.nativeHost, key.separateHost);
    XCTAssertEqual(key.subviews.firstObject, key.separateHost);
    [key layoutSubviews];
    XCTAssertEqual(key.nativeLayoutFirstObject, binding.nativeContent);
    XCTAssertNotEqual(key.nativeLayoutFirstObject, binding.label);
}
- (void)testSelfHostResetRemountsSamePhysicalLabelAfterNativeContent {
    GKBSoftKeyView *key = [self emoji];
    GXKActionDisplayBinding *binding = GXKActionDisplayForKey(key);
    UILabel *label = binding.label;
    NSUInteger generation = binding.generation;
    [key resetView];
    XCTAssertNil(label.superview);
    XCTAssertFalse(GXKActionDisplayCoversIcon(binding.icon));
    GXKReconcileActionDisplay(key);
    XCTAssertFalse(binding.prepared);
    XCTAssertNil(label.superview, @"Never install a label as missing native firstObject.");
    [key buildNativeContents];
    [key updateView];
    [self assertPrepared:key];
    XCTAssertEqual(GXKActionDisplayForKey(key).label, label);
    XCTAssertGreaterThan(binding.generation, generation);
    [key layoutSubviews];
    XCTAssertEqual(key.nativeLayoutFirstObject, binding.nativeContent);
    XCTAssertNotEqual(key.nativeLayoutFirstObject, label);
}
- (void)testIndependentHostResetChangesContentButRetainsPhysicalKeyLabel {
    GKBSoftKeyView *key = [self makeKey:GXKEmojiKeyID separateHost:YES attach:YES];
    GXKActionDisplayBinding *binding = GXKActionDisplayForKey(key);
    UILabel *label = binding.label;
    UIView *content = binding.nativeContent;
    [key resetView];
    GXKReconcileActionDisplay(key);
    XCTAssertFalse(binding.prepared);
    XCTAssertEqual(key.separateHost.subviews.count, 0u);
    [key buildNativeContents];
    [key updateView];
    [self assertPrepared:key];
    XCTAssertEqual(binding.label, label);
    XCTAssertNotEqual(binding.nativeContent, content);
    XCTAssertEqual(key.separateHost.subviews.firstObject, binding.nativeContent);
}
- (void)testLayoutChangingModelSetterRemountsBeforeAnyManualRepair {
    GKBSoftKeyView *key = [self emoji];
    GXKActionDisplayBinding *binding = GXKActionDisplayForKey(key);
    UILabel *label = binding.label;
    UIView *content = binding.nativeContent;
    GKBImageViewWithBackground *icon = [self icon:key];
    [binding.inputButton sendActionsForControlEvents:UIControlEventTouchDown];
    NSUInteger generation = binding.generation;
    key.softKeyDef = [self modelWithActions:@[@"native-symbol-action"] layout:@"symbols"];
    // Real model setter traverses reset/build/update and production hooks in one stack.
    // There is no intervening GXKReconcileActionDisplay or runloop/layout repair.
    [self assertPrepared:key];
    XCTAssertEqual(binding.label, label);
    XCTAssertNotEqual(binding.nativeContent, content);
    XCTAssertNotEqual([self icon:key], icon);
    XCTAssertGreaterThan(binding.generation, generation);
    XCTAssertEqual(key.hostView.subviews.firstObject, binding.nativeContent);
    [binding.inputButton sendActionsForControlEvents:UIControlEventTouchUpInside];
    XCTAssertEqual(self.controller.fixtureProxy.insertions.count, 0u);
}
- (void)testOffscreenRasterControlsShowNativeImageAndSynchronousReplacementText {
    GKBSoftKeyView *key = [self makeKey:GXKEmojiKeyID separateHost:NO attach:NO];
    XCTAssertNil([self icon:key].layer.mask, @"A default empty mask must not hide native controls.");
    NSData *native = GXKFixtureRaster(key);
    XCTAssertGreaterThan(GXKFixtureBluePixels(native), 0u, @"Positive control must render the native blue image.");
    [self.body addSubview:key];
    [self assertPrepared:key]; // Assert synchronous mount before raster or transaction flush.
    NSData *first = GXKFixtureRaster(key);
    XCTAssertEqual(GXKFixtureBluePixels(first), 0u);
    XCTAssertGreaterThan(GXKFixtureVisiblePixels(first), 0u, @"Replacement text must not be a blank raster.");
    GXKActionDisplayBinding *binding = GXKActionDisplayForKey(key);
    key.softKeyDef = [self modelWithActions:@[@"native-symbol-action"] layout:@"symbols"];
    [self assertPrepared:key];
    NSData *rebuilt = GXKFixtureRaster(key);
    XCTAssertEqual(GXKFixtureBluePixels(rebuilt), 0u);
    XCTAssertGreaterThan(GXKFixtureVisiblePixels(rebuilt), 0u);
    binding.label.hidden = YES;
    NSData *blank = GXKFixtureRaster(key);
    XCTAssertEqual(GXKFixtureVisiblePixels(blank), 0u, @"Without native foreground or our label, negative control is blank.");
    binding.label.hidden = NO;
    [CATransaction flush];
    XCTAssertTrue(GXKActionDisplayCoversIcon([self icon:key]));
    // No claim about Gboard animations, Simulator presentation, or actual iPhone first frame.
}
- (void)testMissingNativeContentNeverBecomesAPreparedFirstObject {
    GKBSoftKeyView *key = [self makeKey:GXKEmojiKeyID separateHost:NO attach:NO];
    [key resetView];
    [self.body addSubview:key];
    GXKActionDisplayBinding *binding = GXKActionDisplayForKey(key);
    XCTAssertFalse(binding.prepared);
    XCTAssertFalse([key.subviews containsObject:binding.label]);
    XCTAssertEqual(key.subviews.count, 0u);
    CGRect normalBounds = key.bounds;
    CGRect tinyBounds = normalBounds;
    tinyBounds.size = CGSizeMake(1, 1);
    key.bounds = tinyBounds;
    [key buildNativeContents];
    [key updateView];
    XCTAssertFalse(GXKActionDisplayForKey(key).prepared, @"First admission still requires title fit.");
    XCTAssertFalse(GXKActionDisplayCoversIcon([self icon:key]));
    key.bounds = normalBounds;
    [key updateView];
    [self assertPrepared:key];
}
- (void)testModelReplacementCancelsCapturedTouchAndNeverPassesToNativeEmoji {
    GKBSoftKeyView *key = [self emoji];
    GXKActionDisplayBinding *binding = GXKActionDisplayForKey(key);
    UIButton *input = binding.inputButton;
    [input sendActionsForControlEvents:UIControlEventTouchDown];
    NSUInteger generation = binding.generation;
    XCTAssertEqual(binding.capturedGeneration, generation);
    key.softKeyDef = [self modelWithActions:@[@"new-native-action"] layout:@"icon"];
    XCTAssertGreaterThan(binding.generation, generation);
    [input sendActionsForControlEvents:UIControlEventTouchUpInside];
    XCTAssertEqual(self.controller.fixtureProxy.insertions.count, 0u);
    XCTAssertEqual(key.nativeTouchEnds, 0u);
    CGPoint p = [key convertPoint:CGPointMake(24, 22) toView:self.body];
    XCTAssertEqual([self.body hitTest:p withEvent:nil], binding.inputButton);
    [self press:binding.inputButton];
    XCTAssertEqualObjects(self.controller.fixtureProxy.insertions, (@[@"\n"]));
    [self.controller.fixtureProxy.insertions removeAllObjects];
    UILabel *label = binding.label;
    [input sendActionsForControlEvents:UIControlEventTouchDown];
    generation = binding.generation;
    XCTAssertEqual(binding.capturedGeneration, generation);
    key.userInteractionEnabled = NO;
    XCTAssertTrue(GXKActionDisplayCoversIcon([self icon:key]));
    // No intervening layout callback: TouchUp must read the current capability.
    [input sendActionsForControlEvents:UIControlEventTouchUpInside];
    XCTAssertGreaterThan(binding.generation, generation);
    XCTAssertEqual(binding.capturedGeneration, 0u);
    XCTAssertFalse(binding.clickAllowed);
    XCTAssertEqual(binding.label, label);
    XCTAssertEqual(label.superview, key);
    XCTAssertTrue(binding.prepared);
    XCTAssertEqual(self.controller.fixtureProxy.insertions.count, 0u);
    [input sendActionsForControlEvents:UIControlEventTouchDown];
    XCTAssertEqual(binding.capturedGeneration, 0u);
    key.userInteractionEnabled = YES;
    GXKUpdateActionKey(self.controller);
    [input sendActionsForControlEvents:UIControlEventTouchUpInside];
    XCTAssertEqual(self.controller.fixtureProxy.insertions.count, 0u);
    [self press:input];
    XCTAssertEqualObjects(self.controller.fixtureProxy.insertions, (@[@"\n"]));
    XCTAssertEqual(key.nativeTouchEnds, 0u);
}
- (void)testIconReplacementInvalidatesOldTouchAndOnlyCoversCurrentIcon {
    GKBSoftKeyView *key = [self emoji];
    GXKActionDisplayBinding *binding = GXKActionDisplayForKey(key);
    GKBImageViewWithBackground *oldIcon = [self icon:key];
    UILabel *label = binding.label;
    [binding.inputButton sendActionsForControlEvents:UIControlEventTouchDown];
    NSUInteger generation = binding.generation;
    [key replaceNativeIcon];
    XCTAssertGreaterThan(binding.generation, generation);
    XCTAssertEqual(binding.label, label);
    XCTAssertFalse(GXKActionDisplayCoversIcon(oldIcon));
    XCTAssertTrue(GXKActionDisplayCoversIcon([self icon:key]));
    oldIcon.image = self.normalImage;
    XCTAssertEqual(oldIcon.image, self.normalImage);
    [binding.inputButton sendActionsForControlEvents:UIControlEventTouchUpInside];
    XCTAssertEqual(self.controller.fixtureProxy.insertions.count, 0u);
    [self assertPrepared:key];
}
- (void)testDifferentPhysicalKeysNeverShareLabelsOrInputAndAmbiguityRejectsTap {
    GKBSoftKeyView *first = [self emoji];
    GXKActionDisplayBinding *a = GXKActionDisplayForKey(first);
    [a.inputButton sendActionsForControlEvents:UIControlEventTouchDown];
    GKBSoftKeyView *second = [self emoji];
    GXKActionDisplayBinding *b = GXKActionDisplayForKey(second);
    XCTAssertNotEqual(a, b);
    XCTAssertNotEqual(a.label, b.label);
    XCTAssertNotEqual(a.inputButton, b.inputButton);
    XCTAssertEqual(a.label.superview, first);
    XCTAssertEqual(b.label.superview, second);
    XCTAssertTrue(GXKActionDisplayCoversIcon([self icon:first]));
    XCTAssertTrue(GXKActionDisplayCoversIcon([self icon:second]));
    XCTAssertNil(GXKFindNineKeyEmojiKey(self.controller.view));
    [a.inputButton sendActionsForControlEvents:UIControlEventTouchUpInside];
    [self press:b.inputButton];
    XCTAssertEqual(self.controller.fixtureProxy.insertions.count, 0u);
    XCTAssertEqual(first.nativeTouchEnds + second.nativeTouchEnds, 0u);
    CGPoint p = [second convertPoint:CGPointMake(24, 22) toView:self.body];
    UIView *hit = [self.body hitTest:p withEvent:nil];
    XCTAssertTrue(hit == a.inputButton || hit == b.inputButton, @"Ambiguous overlay swallows, never native passthrough.");
}
- (void)testMixedPeerBodiesKeepVisualPerKeyButNeverAuthorizeAnAmbiguousTap {
    GKBSoftKeyView *key = [self emoji];
    GKBZhQwertySoftKeyboardView *peer = [[GKBZhQwertySoftKeyboardView alloc] initWithFrame:self.body.frame];
    [self.controller.view addSubview:peer];
    GXKBumpKeyCacheEpoch();
    XCTAssertNil(GXKFindNineKeyEmojiKey(self.controller.view));
    [self press:GXKActionDisplayForKey(key).inputButton];
    XCTAssertEqual(self.controller.fixtureProxy.insertions.count, 0u);
    XCTAssertTrue(GXKActionDisplayCoversIcon([self icon:key]));
}
- (void)testEmptyActionsTransitionKeepsConfirmedTextButNeverExecutesInput {
    GKBSoftKeyView *key = [self emoji];
    GXKActionDisplayBinding *binding = GXKActionDisplayForKey(key);
    UILabel *label = binding.label;
    [binding.inputButton sendActionsForControlEvents:UIControlEventTouchDown];
    key.softKeyDef = [self modelWithActions:@[] layout:@"icon"];
    XCTAssertEqual(binding.label, label);
    XCTAssertEqual(label.superview, key);
    XCTAssertEqualObjects(label.text, @"换行");
    XCTAssertFalse(binding.clickAllowed);
    CGPoint p = [key convertPoint:CGPointMake(24, 22) toView:self.body];
    XCTAssertEqual([self.body hitTest:p withEvent:nil], binding.inputButton,
                   @"Confirmed empty-actions transition must swallow, not fall through to native emoji.");
    [binding.inputButton sendActionsForControlEvents:UIControlEventTouchUpInside];
    [self press:binding.inputButton];
    XCTAssertEqual(self.controller.fixtureProxy.insertions.count, 0u);
    XCTAssertEqual(key.nativeTouchEnds, 0u);
}
- (void)testNeverConfirmedEmptyActionKeyStaysNative {
    GKBSoftKeyView *key = [[GKBSoftKeyView alloc] initWithFrame:CGRectMake(330, 145, 48, 44)];
    key.restorationIdentifier = GXKEmojiKeyID;
    key.softKeyDef = [self modelWithActions:@[] layout:@"icon"];
    [self.body addSubview:key];
    XCTAssertFalse(GXKActionDisplayForKey(key).prepared);
    XCTAssertFalse(GXKActionDisplayCoversIcon([self icon:key]));
    XCTAssertEqual([self icon:key].image, self.normalImage);
}
- (void)testNativeReturnReuseRetiresOverlayBeforeRepaintingCurrentModel {
    GKBSoftKeyView *key = [self emoji];
    GXKActionDisplayBinding *binding = GXKActionDisplayForKey(key);
    UILabel *oldLabel = binding.label;
    UIButton *oldInput = binding.inputButton;
    UIImage *returnImage = GXKFixtureImage(UIColor.greenColor);
    UIImage *returnHighlighted = GXKFixtureImage(UIColor.purpleColor);
    GXKFixtureSoftKeyDef *model = [self modelWithActions:@[@"return"] layout:@"return"];
    model.normalImage = returnImage;
    model.highlightedImage = returnHighlighted;
    key.restorationIdentifier = @"key_pos_9keys_return";
    key.softKeyDef = model;
    XCTAssertFalse(GXKActionDisplayForKey(key).prepared);
    XCTAssertNil(oldLabel.superview);
    XCTAssertNil(oldInput.superview);
    XCTAssertFalse(GXKActionDisplayCoversIcon([self icon:key]));
    XCTAssertEqual([self icon:key].image, returnImage);
    XCTAssertEqual([self icon:key].highlightedImage, returnHighlighted);
    XCTAssertEqual(key.softKeyDef, model);
}
- (void)testNineToQwertyKeyMoveReturnsCurrentNativeImagesAndInput {
    GKBSoftKeyView *key = [self emoji];
    GXKActionDisplayBinding *binding = GXKActionDisplayForKey(key);
    UILabel *oldLabel = binding.label;
    UIButton *oldInput = binding.inputButton;
    [oldInput sendActionsForControlEvents:UIControlEventTouchDown];
    GKBZhQwertySoftKeyboardView *qwerty = [[GKBZhQwertySoftKeyboardView alloc] initWithFrame:self.body.frame];
    self.body.hidden = YES;
    [self.controller.view addSubview:qwerty];
    [qwerty addSubview:key];
    XCTAssertNil(GXKNineKeyBodyForKey(key, self.controller.view));
    XCTAssertNil(oldLabel.superview);
    XCTAssertNil(oldInput.superview);
    XCTAssertFalse(GXKActionDisplayCoversIcon([self icon:key]));
    XCTAssertEqual([self icon:key].image, self.normalImage);
    XCTAssertEqual([self icon:key].highlightedImage, self.highlightedImage);
    [oldInput sendActionsForControlEvents:UIControlEventTouchUpInside];
    XCTAssertEqual(self.controller.fixtureProxy.insertions.count, 0u);
    XCTAssertEqual([key hitTest:CGPointMake(24, 22) withEvent:nil], key);
}
- (void)testKeyOwnedLabelInheritsNativeAlphaAndTransformWithoutStylingKeycap {
    GKBSoftKeyView *key = [self emoji];
    GXKActionDisplayBinding *binding = GXKActionDisplayForKey(key);
    key.backgroundColor = UIColor.cyanColor;
    [self icon:key].backgroundColor = UIColor.yellowColor;
    CGRect originalBounds = key.bounds;
    key.alpha = 0.40;
    key.transform = CGAffineTransformMakeTranslation(-4, 3);
    GXKReconcileActionDisplay(key);
    XCTAssertEqual(binding.label.superview, key);
    XCTAssertEqualWithAccuracy(binding.label.alpha, 1.0, 0.0001);
    XCTAssertTrue(CGAffineTransformIsIdentity(binding.label.transform));
    XCTAssertTrue(CGRectEqualToRect(key.bounds, originalBounds));
    XCTAssertEqualObjects(key.backgroundColor, UIColor.cyanColor);
    XCTAssertEqualObjects([self icon:key].backgroundColor, UIColor.yellowColor);
    XCTAssertTrue(CGRectEqualToRect(binding.label.frame, key.bounds));
    XCTAssertTrue(CGRectEqualToRect(binding.inputButton.frame, [key convertRect:key.bounds toView:binding.host]));
    // Model endpoints occur before an ancestor's presentation has finished.
    // Check ownership synchronously; this is not a presentation-frame oracle.
    UILabel *label = binding.label;
    for (NSUInteger endpoint = 0; endpoint < 2; endpoint++) {
        self.body.alpha = 1;
        self.body.transform = CGAffineTransformIdentity;
        GXKUpdateActionKey(self.controller);
        [binding.inputButton sendActionsForControlEvents:UIControlEventTouchDown];
        NSUInteger generation = binding.generation;
        XCTAssertEqual(binding.capturedGeneration, generation);
        [UIView animateWithDuration:0.3 animations:^{
            if (endpoint == 0) self.body.alpha = 0;
            else self.body.transform = CGAffineTransformMakeTranslation(1000, 0);
            XCTAssertFalse(GXKKeyIsVisible(key, self.controller.view));
            XCTAssertTrue(GXKActionDisplayCoversIcon([self icon:key])); // Even before reconcile.
            [self icon:key].image = self.normalImage;
            [self icon:key].highlightedImage = self.highlightedImage;
            XCTAssertNil([self icon:key].image);
            XCTAssertNil([self icon:key].highlightedImage);
            gkx_viewDidLayoutSubviews(self.controller, @selector(viewDidLayoutSubviews));
            XCTAssertEqual(binding.label, label);
            XCTAssertEqual(label.superview, key);
            XCTAssertTrue(binding.prepared);
            XCTAssertTrue(GXKActionDisplayCoversIcon([self icon:key]));
            XCTAssertFalse(binding.clickAllowed);
            XCTAssertGreaterThan(binding.generation, generation);
            XCTAssertEqual(binding.capturedGeneration, 0u);
        }];
        [binding.inputButton sendActionsForControlEvents:UIControlEventTouchUpInside];
        XCTAssertEqual(self.controller.fixtureProxy.insertions.count, 0u);
        [self.body.layer removeAllAnimations];
    }
    self.body.alpha = 1;
    self.body.transform = CGAffineTransformIdentity;
    key.alpha = 1;
    key.transform = CGAffineTransformIdentity;
    GXKUpdateActionKey(self.controller);
    CGRect shrinkingBounds = originalBounds;
    shrinkingBounds.size = CGSizeMake(1, 1);
    [UIView animateWithDuration:0.3 animations:^{
        key.bounds = shrinkingBounds;
        gkx_viewDidLayoutSubviews(self.controller, @selector(viewDidLayoutSubviews));
        XCTAssertEqual(binding.label, label);
        XCTAssertEqual(label.superview, key);
        XCTAssertTrue(binding.prepared);
        XCTAssertTrue(CGRectEqualToRect(label.frame, key.bounds));
        XCTAssertTrue(GXKActionDisplayCoversIcon([self icon:key]));
        [self icon:key].image = self.normalImage;
        [self icon:key].highlightedImage = self.highlightedImage;
        XCTAssertNil([self icon:key].image);
        XCTAssertNil([self icon:key].highlightedImage);
    }];
    [key.layer removeAllAnimations];
    key.bounds = originalBounds;
    GXKUpdateActionKey(self.controller);
    key.hidden = YES;
    XCTAssertTrue(GXKActionDisplayCoversIcon([self icon:key]));
    GXKUpdateActionKey(self.controller);
    XCTAssertFalse(binding.clickAllowed);
    XCTAssertNil(GXKValidateActionKeyPress(binding.inputButton, self.controller));
    XCTAssertEqual(binding.label.superview, key);
}
- (void)testHostMoveInvalidatesCapturedGenerationWithoutCrossKeyReuse {
    GKBSoftKeyView *key = [self emoji];
    GXKActionDisplayBinding *binding = GXKActionDisplayForKey(key);
    UILabel *label = binding.label;
    [binding.inputButton sendActionsForControlEvents:UIControlEventTouchDown];
    NSUInteger generation = binding.generation;
    UIView *newHost = [[UIView alloc] initWithFrame:self.body.bounds];
    [self.body addSubview:newHost];
    [newHost addSubview:key];
    XCTAssertGreaterThan(binding.generation, generation);
    XCTAssertEqual(binding.label, label);
    XCTAssertEqual(binding.label.superview, key);
    XCTAssertEqual(binding.inputButton.superview, newHost);
    [binding.inputButton sendActionsForControlEvents:UIControlEventTouchUpInside];
    XCTAssertEqual(self.controller.fixtureProxy.insertions.count, 0u);
}
- (void)testExitCancelsOldTouchAndRestoresBothCurrentNativeImages {
    GKBSoftKeyView *key = [self emoji];
    GXKActionDisplayBinding *binding = GXKActionDisplayForKey(key);
    UILabel *label = binding.label;
    UIButton *input = binding.inputButton;
    [input sendActionsForControlEvents:UIControlEventTouchDown];
    gCurrentVC = nil;
    GXKDetachActionKey();
    XCTAssertFalse(binding.prepared);
    XCTAssertNil(label.superview);
    XCTAssertNil(input.superview);
    XCTAssertFalse(GXKActionDisplayCoversIcon([self icon:key]));
    XCTAssertEqual([self icon:key].image, self.normalImage);
    XCTAssertEqual([self icon:key].highlightedImage, self.highlightedImage);
    [input sendActionsForControlEvents:UIControlEventTouchUpInside];
    XCTAssertEqual(self.controller.fixtureProxy.insertions.count, 0u);
    gCurrentVC = self.controller;
    [key updateView];
    [self assertPrepared:key];
    XCTAssertNil(GXKValidateActionKeyPress(input, self.controller), @"An old session's TouchDown cannot authorize the new one.");
}
- (void)testNativeViewNilWritesRemainNilAfterRetirement {
    GKBSoftKeyView *key = [self emoji];
    GXKActionDisplayBinding *binding = GXKActionDisplayForKey(key);
    XCTAssertEqual(binding.normalImage, self.normalImage);
    XCTAssertEqual(binding.highlightedImage, self.highlightedImage);
    [self icon:key].image = nil;
    [self icon:key].highlightedImage = nil;
    XCTAssertNil(binding.normalImage);
    XCTAssertNil(binding.highlightedImage);
    GXKUpdateActionKey(self.controller);
    XCTAssertTrue(binding.prepared);
    gCurrentVC = nil;
    GXKDetachActionKey();
    XCTAssertNil([self icon:key].image);
    XCTAssertNil([self icon:key].highlightedImage);
}
- (void)testNativeLayerNilWritesRemainNilAfterInvalidationAndRetirement {
    GKBSoftKeyView *key = [self emoji];
    GXKActionDisplayBinding *binding = GXKActionDisplayForKey(key);
    GXKInvalidateActionDisplay(key);
    GKBImageLayer *foreground = (GKBImageLayer *)[self icon:key].layer;
    foreground.image = nil;
    foreground.highlightedImage = nil;
    XCTAssertNil(binding.normalImage);
    XCTAssertNil(binding.highlightedImage);
    GXKUpdateActionKey(self.controller);
    XCTAssertTrue(binding.prepared);
    gCurrentVC = nil;
    GXKDetachActionKey();
    XCTAssertNil([self icon:key].image);
    XCTAssertNil([self icon:key].highlightedImage);
}
- (void)testDetachedNativeTreeCannotValidateOldTap {
    GKBSoftKeyView *key = [self emoji];
    GXKActionDisplayBinding *binding = GXKActionDisplayForKey(key);
    UIButton *input = binding.inputButton;
    [input sendActionsForControlEvents:UIControlEventTouchDown];
    [key removeFromSuperview];
    XCTAssertFalse(GXKActionDisplayCoversIcon([self icon:key]));
    XCTAssertFalse(binding.prepared);
    XCTAssertNil(binding.label.superview);
    XCTAssertNil(input.superview);
    [input sendActionsForControlEvents:UIControlEventTouchUpInside];
    XCTAssertEqual(self.controller.fixtureProxy.insertions.count, 0u);
}
- (void)testOnlyExactLiveForegroundLayerIsBlockedNotBackgroundOrMask {
    GKBSoftKeyView *key = [self emoji];
    GKBImageViewWithBackground *icon = [self icon:key];
    GKBImageLayer *foreground = (GKBImageLayer *)icon.layer;
    NSUInteger normal = foreground.normalWrites;
    NSUInteger highlighted = foreground.highlightedWrites;
    icon.image = self.normalImage;
    icon.highlightedImage = self.highlightedImage;
    foreground.image = self.normalImage;
    foreground.highlightedImage = self.highlightedImage;
    XCTAssertNil(icon.image);
    XCTAssertNil(icon.highlightedImage);
    XCTAssertEqual(foreground.normalWrites, normal);
    XCTAssertEqual(foreground.highlightedWrites, highlighted);
    // These share the same UIView delegate and layer class, but are not icon.layer.
    icon.fixtureMaskLayer.frame = icon.bounds;
    icon.layer.mask = icon.fixtureMaskLayer;
    icon.backgroundImage = self.normalImage;
    icon.highlightedBackgroundImage = self.highlightedImage;
    icon.fixtureMaskLayer.image = self.normalImage;
    icon.fixtureMaskLayer.highlightedImage = self.highlightedImage;
    XCTAssertEqual(icon.backgroundLayer.image, self.normalImage);
    XCTAssertEqual(icon.backgroundLayer.highlightedImage, self.highlightedImage);
    XCTAssertEqual(icon.fixtureMaskLayer.image, self.normalImage);
    XCTAssertEqual(icon.fixtureMaskLayer.highlightedImage, self.highlightedImage);
    XCTAssertEqual(icon.backgroundWrites, 1u);
    XCTAssertEqual(icon.highlightedBackgroundWrites, 1u);
    foreground.image = nil;
    foreground.highlightedImage = nil;
    XCTAssertEqual(foreground.normalWrites, normal + 1);
    XCTAssertEqual(foreground.highlightedWrites, highlighted + 1);
    GKBImageViewWithBackground *unrelated = [[GKBImageViewWithBackground alloc] initWithFrame:key.bounds];
    [key addSubview:unrelated];
    unrelated.image = self.normalImage;
    unrelated.highlightedImage = self.highlightedImage;
    XCTAssertEqual(unrelated.image, self.normalImage);
    XCTAssertEqual(unrelated.highlightedImage, self.highlightedImage);
}
- (void)testNativeFontAndForegroundThemeFollowCurrentVerifiedOwners {
    GKBSoftKeyView *key = [self emoji];
    GXKActionDisplayBinding *binding = GXKActionDisplayForKey(key);
    UILabel *nativeLabel = self.returnKey.idToViewDict[@"label"];
    UIFont *font = [UIFont systemFontOfSize:19.0 weight:UIFontWeightMedium];
    nativeLabel.font = font;
    [self icon:key].foregroundColor = UIColor.whiteColor;
    GXKResetNativeKeyStyle();
    GXKUpdateActionKey(self.controller);
    XCTAssertEqualObjects(binding.label.font, font);
    XCTAssertEqualObjects(binding.label.textColor, UIColor.whiteColor);
    XCTAssertEqualObjects(binding.label.backgroundColor, UIColor.clearColor);
    XCTAssertEqualObjects(binding.inputButton.backgroundColor, UIColor.clearColor);
    XCTAssertEqual(key.softKeyDef.normalImage, self.normalImage, @"Native model images remain read-only.");
}
- (void)testThreeStateProductionTapPreservesClearDismissAndNewlinePriority {
    GKBSoftKeyView *key = [self emoji];
    GXKActionDisplayBinding *binding = GXKActionDisplayForKey(key);
    [self press:binding.inputButton];
    XCTAssertEqualObjects(self.controller.fixtureProxy.insertions, (@[@"\n"]));
    [self.controller.fixtureProxy.insertions removeAllObjects];
    self.controller.fixtureProxy.markedText = @"ni";
    gSuggestingActive = YES;
    GXKUpdateActionKey(self.controller);
    XCTAssertEqualObjects(binding.label.text, @"重输");
    [self press:binding.inputButton];
    XCTAssertGreaterThan(self.controller.resetCalls, 0u);
    XCTAssertGreaterThan(self.controller.abortCalls, 0u);
    XCTAssertEqual(self.controller.dismissCalls, 0u);
    XCTAssertEqual(self.controller.fixtureProxy.insertions.count, 0u);
    GXKFixtureCandidateView *candidates = [[GXKFixtureCandidateView alloc] initWithFrame:CGRectMake(0, 40, 300, 40)];
    UILabel *candidate = [[UILabel alloc] initWithFrame:candidates.bounds];
    candidate.text = @"联想词";
    [candidates addSubview:candidate];
    [self.controller.view addSubview:candidates];
    gComposingScanAt = 0;
    GXKRefreshComposingState(self.controller);
    GXKUpdateActionKey(self.controller);
    XCTAssertEqualObjects(binding.label.text, @"收起");
    [self press:binding.inputButton];
    XCTAssertEqual(self.controller.dismissCalls, 1u);
    XCTAssertEqual(self.controller.fixtureProxy.insertions.count, 0u);
    candidates.hidden = YES;
    gComposingScanAt = 0;
    GXKRefreshComposingState(self.controller);
    GXKUpdateActionKey(self.controller);
    XCTAssertEqualObjects(binding.label.text, @"换行");
}
- (void)testColdControllerLayoutPreparesAlreadyAttachedNativeKeySynchronously {
    gCurrentVC = nil;
    GKBSoftKeyView *key = [self emoji];
    XCTAssertNil(GXKActionDisplayForKey(key));
    XCTAssertTrue([gActionDisplayKeys containsObject:key]);
    XCTAssertEqual([self icon:key].image, self.normalImage);
    XCTAssertEqual([self icon:key].highlightedImage, self.highlightedImage);
    gCurrentVC = self.controller;
    gkx_viewDidLayoutSubviews(self.controller, @selector(viewDidLayoutSubviews));
    [self assertPrepared:key]; // Before a queue turn or a manual key reconcile.
}
- (void)testCompletedControllerLayoutRemountsTextBeforeAsynchronousWork {
    GKBSoftKeyView *key = [self emoji];
    GXKActionDisplayBinding *binding = GXKActionDisplayForKey(key);
    UILabel *label = binding.label;
    [label removeFromSuperview];
    XCTAssertFalse(GXKActionDisplayCoversIcon([self icon:key]));
    gkx_viewDidLayoutSubviews(self.controller, @selector(viewDidLayoutSubviews));
    XCTAssertEqual(label.superview, key); // Assert at return, before pending main-queue work.
    XCTAssertTrue(GXKActionDisplayCoversIcon([self icon:key]));
    XCTAssertEqualObjects(label.text, @"换行");
}
@end
