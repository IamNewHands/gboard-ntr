// 原生九键页身份：绑定本轮实际加载的 layout，而不是数字/符号共用的 collection ID。
#ifndef GXK_KEYBOARD_PAGE_IDENTITY_H
#define GXK_KEYBOARD_PAGE_IDENTITY_H

typedef NS_ENUM(NSInteger, GXKNineKeyPage) {
    GXKNineKeyPageUnknown = 0,
    GXKNineKeyPagePinyin,
    GXKNineKeyPageDigit,
    GXKNineKeyPageSymbol,
};

static char gNineKeyPageAssociation;
static NSHashTable<UIView *> *gNineKeyPageBodies; // weak：原生拥有键体，插件不延长生命周期。
static void (*gOrigKeyboardHelperCreateView)(id, SEL);
static void (*gOrigKeyboardHelperDiscardView)(id, SEL);
static void GXKSymbolPageBodyRetired(UIView *body);

static GXKNineKeyPage GXKNineKeyPageForLayoutName(NSString *name) {
    if ([name isEqualToString:@"keyboard_body_pinyin_ninekeys"]) return GXKNineKeyPagePinyin;
    if ([name isEqualToString:@"keyboard_body_pinyin_9key_digit"]) return GXKNineKeyPageDigit;
    if ([name isEqualToString:@"keyboard_body_pinyin_9key_symbol"]) return GXKNineKeyPageSymbol;
    return GXKNineKeyPageUnknown; // 未知布局不按 substring 或键帽猜测。
}

static GXKNineKeyPage GXKNineKeyPageForBody(UIView *body) {
    NSNumber *page = objc_getAssociatedObject(body, &gNineKeyPageAssociation);
    return page ? (GXKNineKeyPage)page.integerValue : GXKNineKeyPageUnknown;
}

static GXKNineKeyPage GXKNineKeyPageForView(UIView *view) {
    UIViewController *vc = gCurrentVC;
    if (!view || !vc || !vc.isViewLoaded || !GXKKeyIsVisible(view, vc.view)) return GXKNineKeyPageUnknown;
    Class nineClass = GXKClassCached(@"GKB9KeysSoftKeyboardView", &gCachedNineKeyClass);
    UIView *body = (nineClass && [view isKindOfClass:nineClass]) ? view : GXKNineKeyBodyForKey(view, vc.view);
    return body ? GXKNineKeyPageForBody(body) : GXKNineKeyPageUnknown;
}

static UIView *GXKNineKeyVisibleBodyForPage(UIView *root, GXKNineKeyPage page) {
    if (!root || !root.window) return nil;
    UIView *candidate = nil;
    for (UIView *body in gNineKeyPageBodies) {
        if (GXKNineKeyPageForBody(body) != page || !GXKKeyIsVisible(body, root)) continue;
        if (candidate && candidate != body) return nil; // 两个同页都可见：保持原生，不猜。
        candidate = body;
    }
    return candidate;
}

// 2.3.19 元数据已核实 _view / _currentLayoutName 均为对象字段。
// 使用运行时字段名与类型，不写死偏移，不向 nine body 发送不存在的 -layoutName。
static id GXKKeyboardHelperObject(id helper, const char *name) {
    Ivar field = class_getInstanceVariable(object_getClass(helper), name);
    const char *type = field ? ivar_getTypeEncoding(field) : NULL;
    return (type && type[0] == '@') ? object_getIvar(helper, field) : nil;
}

static void GXKNineKeyPageRetireBody(UIView *body) {
    if (![body isKindOfClass:[UIView class]]) return;
    objc_setAssociatedObject(body, &gNineKeyPageAssociation, nil, OBJC_ASSOCIATION_RETAIN_NONATOMIC);
    [gNineKeyPageBodies removeObject:body];
    GXKSymbolPageBodyRetired(body); // 只取消属于这个旧键体的延时返回/双击状态。
}

static void GXKKeyboardHelperCreateView(id self, SEL _cmd) {
    UIView *oldView = GXKKeyboardHelperObject(self, "_view");
    if (gOrigKeyboardHelperCreateView) gOrigKeyboardHelperCreateView(self, _cmd);
    UIView *view = GXKKeyboardHelperObject(self, "_view");
    NSString *name = GXKKeyboardHelperObject(self, "_currentLayoutName");
    GXKNineKeyPage page = [name isKindOfClass:[NSString class]] ? GXKNineKeyPageForLayoutName(name) : GXKNineKeyPageUnknown;
    if (oldView && (oldView != view || GXKNineKeyPageForBody(oldView) != page)) GXKNineKeyPageRetireBody(oldView);
    Class nineClass = GXKClassCached(@"GKB9KeysSoftKeyboardView", &gCachedNineKeyClass);
    if (!nineClass || ![view isKindOfClass:nineClass] || page == GXKNineKeyPageUnknown) return;
    if (!gNineKeyPageBodies) gNineKeyPageBodies = [NSHashTable weakObjectsHashTable];
    objc_setAssociatedObject(view, &gNineKeyPageAssociation, @(page), OBJC_ASSOCIATION_RETAIN_NONATOMIC);
    [gNineKeyPageBodies addObject:view];
    GXKSymbolInvalidatePageCache(); // create 回调内的布局可能缓存过“尚无符号页”，登记后即失效。
}

static void GXKKeyboardHelperDiscardView(id self, SEL _cmd) {
    // 原 discardView 会清空 _view，所以必须在转发前保存旧对象。
    UIView *oldView = GXKKeyboardHelperObject(self, "_view");
    if (gOrigKeyboardHelperDiscardView) gOrigKeyboardHelperDiscardView(self, _cmd);
    GXKNineKeyPageRetireBody(oldView);
}

static void GXKInstallNineKeyPageHooks(void) {
    static BOOL installed;
    if (installed) return;
    Class cls = NSClassFromString(@"GKBKeyboardViewHelper");
    Method create = cls ? class_getInstanceMethod(cls, NSSelectorFromString(@"createView")) : NULL;
    Method discard = cls ? class_getInstanceMethod(cls, NSSelectorFromString(@"discardView")) : NULL;
    if (!create || !discard || strcmp(method_getTypeEncoding(create), "v16@0:8") != 0 ||
        strcmp(method_getTypeEncoding(discard), "v16@0:8") != 0) return;
    if (!class_getInstanceVariable(cls, "_view") || !class_getInstanceVariable(cls, "_currentLayoutName")) return;
    gOrigKeyboardHelperCreateView = (void (*)(id, SEL))method_getImplementation(create);
    gOrigKeyboardHelperDiscardView = (void (*)(id, SEL))method_getImplementation(discard);
    // 两个方法均由 Helper 本类声明；不覆盖 KeyboardImpl / Zh 子类的 delegate 回调。
    method_setImplementation(create, (IMP)GXKKeyboardHelperCreateView);
    method_setImplementation(discard, (IMP)GXKKeyboardHelperDiscardView);
    installed = YES;
}

#endif // GXK_KEYBOARD_PAGE_IDENTITY_H
