// [FEATURE-symbol] 九键符号页：双击锁定常驻、单击延时回拼音、成对符号自动补全。
//
// 为什么不能「加个双击手势，其余交给原生」：
//   原生单击符号键 = 上屏一次 + 立刻切回拼音页。等手势识别出第二击时，页面早已回到
//   拼音页，第二击落在拼音键上——双击永远拼不出来。所以必须先把「上屏即切走」这一步
//   关掉（-shouldReturnToPrimeOnKey: 在九键符号页恒 NO），停留与否改由本模块按时间窗决定。
//
// 双击的判定放在按键 fire 上，不放手势上：
//   同一格在 0.25 秒内第二次 fire = 双击。这样不依赖「手势回调 vs 原生 fire」的先后，
//   也就不需要任何手势识别器，红线 2（严禁拦截按键触摸事件）连边都不碰。
//
// 为什么是「跳过第二击」而不是「上屏后再删」：
//   跳过只需一行，文本天然只上屏一次；删字符会和成对补全抢同一个光标位置。
//
// 性能：fire 只读被按的键所属原生九键体；其它场合读 weak 页身份登记，不做全树扫描。
//
// 锁定（gSymbolLocked）：双击一次 = 常驻符号页，此后每次单击只上屏、不再回拼音；
// 再双击同一格解除，或切到拼音/数字/表情等任何别的页面也自动解除（见 GXKSymbolNoteLayout）。
// 触感一律走 gkx.m 的全局 GXKImpact：锁定时 Medium、解除时 Light，不再自建 generator。
#ifndef GXK_SYMBOL_DOUBLETAP_H
#define GXK_SYMBOL_DOUBLETAP_H

#import <dispatch/dispatch.h> // dispatch_block_create/cancel：延时回拼音要能被下一击取消

#define GXK_SYMBOL_TAP_WINDOW 0.25    // 两击之间允许的最大间隔，超过即两次单击
#define GXK_SYMBOL_RETURN_DELAY 0.28  // 单击后多久回拼音，必须略大于双击窗口
static BOOL (*gOrigSymbolShouldReturnToPrime)(id, SEL, id);
static BOOL (*gOrigZhSymbolShouldReturnToPrime)(id, SEL, id);
static void (*gOrigSymbolFireEvent)(id, SEL, id, id);
static __weak UIView *gSymbolHostCache;
static BOOL gSymbolPageCacheValid;
static __weak UIView *gSymbolLastFireView;
static __weak UIView *gSymbolLastFireBody;
static NSTimeInterval gSymbolLastFireAt;
static dispatch_block_t gSymbolReturnWork;
static NSUInteger gSymbolReturnGeneration; // 只由回页取消/换页推进，不受成对补全消耗影响。
static BOOL gSymbolLocked; // 双击锁定：YES 时符号页常驻，单击不回拼音。
static NSUInteger gSymbolPairToken; // 补全重试的序号：新的一击作废旧的重试。

// 开符号 -> 闭符号。符号页上屏的是布局里定义的全角变体（｛［＜｢），
// 所以全角、半角、日文半角、制表四套都要列全：漏一个，就有一个符号永远不成对。
static NSDictionary<NSString *, NSString *> *GXKSymbolPairTable(void) {
    static NSDictionary<NSString *, NSString *> *table;
    static dispatch_once_t once;
    dispatch_once(&once, ^{
        table = @{
            // 圆括号
            @"（": @"）", @"(": @")",
            // 方括号：全角、半角、六角
            @"【": @"】", @"［": @"］", @"[": @"]", @"〔": @"〕",
            // 花括号：全角、半角
            @"｛": @"｝", @"{": @"}",
            // 尖括号：书名、单书名、全角、半角
            @"《": @"》", @"〈": @"〉", @"＜": @"＞", @"<": @">",
            // 引号类：直角、双直角、日文半角、制表
            @"「": @"」", @"『": @"』", @"｢": @"｣", @"〘": @"〙", @"〚": @"〛",
            @"“": @"”", @"‘": @"’",
            // 开闭同形的双引号：先查表命中，再由上下文配平否决
            @"\"": @"\"", @"＂": @"＂",
        };
    });
    return table;
}

// 开闭同形的字符：查表永远命中，必须靠上下文决定这一击是开还是收。
static BOOL GXKSymbolIsAmbiguous(NSString *ch) {
    return [ch isEqualToString:@"\""] || [ch isEqualToString:@"＂"];
}

static NSString *GXKSymbolCloserForChar(NSString *ch) {
    if (![ch isKindOfClass:[NSString class]] || !ch.length) return nil;
    return GXKSymbolPairTable()[ch];
}

// before 是刚上屏之后的光标前文本（末字符就是这一击）：含这一击数到奇数次 = 开。
static BOOL GXKSymbolAmbiguousOpens(NSString *ch, NSString *before) {
    if (!ch.length || ![before isKindOfClass:[NSString class]]) return YES;
    unichar target = [ch characterAtIndex:0];
    NSUInteger count = 0;
    for (NSUInteger i = 0; i < before.length; i++) {
        if ([before characterAtIndex:i] == target) count++;
    }
    return (count % 2) == 1;
}

static id<UITextDocumentProxy> GXKSymbolProxy(void) {
    UIViewController *vc = gCurrentVC;
    if (!vc || ![vc isKindOfClass:[UIInputViewController class]]) return nil;
    return ((UIInputViewController *)vc).textDocumentProxy;
}

// key_pos_9keys_symbols 同时存在于 123 和符号页，不能代表分页。
static BOOL GXKSymbolViewIsOnSymbolPage(UIView *view) {
    return GXKNineKeyPageForView(view) == GXKNineKeyPageSymbol;
}

// 只读原生 Helper 标注过且属于当前可见 root 的真正符号键体。
static UIView *GXKSymbolFindHost(UIView *root) {
    return GXKNineKeyVisibleBodyForPage(root, GXKNineKeyPageSymbol);
}

// 拿不到按键视图时读原生页登记；缓存正结果也必须复核当前 root 归属与完整可见性。
static UIView *GXKSymbolHost(void) {
    UIViewController *vc = gCurrentVC;
    if (!vc || !vc.isViewLoaded) return nil;
    if (gSymbolPageCacheValid) {
        UIView *cached = gSymbolHostCache;
        if (!cached) return nil;
        if (GXKNineKeyPageForBody(cached) == GXKNineKeyPageSymbol &&
            GXKKeyIsVisible(cached, vc.view)) return cached;
    }
    UIView *host = GXKSymbolFindHost(vc.view);
    gSymbolHostCache = host;
    gSymbolPageCacheValid = YES;
    return host;
}

static void GXKSymbolInvalidatePageCache(void) { gSymbolPageCacheValid = NO; }

static BOOL GXKSymbolPageActive(void) { return GXKSymbolHost() != nil; }

static BOOL GXKNineKeyDigitPageActive(void) {
    UIViewController *vc = gCurrentVC;
    return vc && vc.isViewLoaded && GXKNineKeyVisibleBodyForPage(vc.view, GXKNineKeyPageDigit) != nil;
}

static void GXKSymbolCancelReturn(void) {
    gSymbolReturnGeneration++;
    dispatch_block_t work = gSymbolReturnWork;
    gSymbolReturnWork = nil;
    if (work) dispatch_block_cancel(work);
}

static void GXKSymbolResetPageState(void) {
    GXKSymbolCancelReturn();
    gSymbolPairToken++;
    gSymbolLocked = NO;
    gSymbolLastFireView = nil;
    gSymbolLastFireBody = nil;
    gSymbolLastFireAt = 0;
    GXKSymbolInvalidatePageCache();
}

static void GXKSymbolPageBodyRetired(UIView *body) {
    if (body == gSymbolLastFireBody) GXKSymbolResetPageState();
    GXKSymbolInvalidatePageCache();
}

// 回拼音：GKBInputViewControllerBase -inputBundleManager -> GKBInputBundle -switchToPrimeKeyboard。
static void GXKSymbolSwitchToPrime(void) {
    UIViewController *vc = gCurrentVC;
    if (!vc) return;
    SEL managerSel = NSSelectorFromString(@"inputBundleManager");
    if (![vc respondsToSelector:managerSel]) return;
    id manager = ((id (*)(id, SEL))objc_msgSend)(vc, managerSel);
    SEL bundleSel = NSSelectorFromString(@"currentInputBundle");
    if (!manager || ![manager respondsToSelector:bundleSel]) return;
    id bundle = ((id (*)(id, SEL))objc_msgSend)(manager, bundleSel);
    SEL switchSel = NSSelectorFromString(@"switchToPrimeKeyboard");
    if (!bundle || ![bundle respondsToSelector:switchSel]) return;
    ((void (*)(id, SEL))objc_msgSend)(bundle, switchSel);
    GXKSymbolResetPageState();
}

// 单击后延时回拼音；这段时间内的第二次 fire 会把它取消。
// 已锁定则不排程：常驻期间每一击都只上屏。
static void GXKSymbolScheduleReturn(void) {
    GXKSymbolCancelReturn();
    if (gSymbolLocked) return;
    __weak UIView *originBody = gSymbolLastFireBody;
    NSUInteger generation = gSymbolReturnGeneration;
    dispatch_block_t work = dispatch_block_create(0, ^{
        if (generation != gSymbolReturnGeneration) return;
        gSymbolReturnWork = nil;
        if (originBody && originBody == GXKSymbolHost()) GXKSymbolSwitchToPrime();
    });
    gSymbolReturnWork = work;
    dispatch_after(dispatch_time(DISPATCH_TIME_NOW, (int64_t)(GXK_SYMBOL_RETURN_DELAY * NSEC_PER_SEC)),
                   dispatch_get_main_queue(), work);
}

// 真正补右半边：光标前文本里必须已经含有这一击，配平判断才准。
static void GXKSymbolInsertPair(NSString *typed) {
    id<UITextDocumentProxy> proxy = GXKSymbolProxy();
    if (!proxy || !typed.length) return;
    NSString *closer = GXKSymbolCloserForChar(typed);
    if (!closer.length) return;
    NSString *before = proxy.documentContextBeforeInput;
    // 双引号开闭同形：前面已经有一个没配对的，这一击就是收尾，不再补第二个。
    if (GXKSymbolIsAmbiguous(typed) && [before isKindOfClass:[NSString class]] &&
        !GXKSymbolAmbiguousOpens(typed, before)) return;
    [proxy insertText:closer];
    SEL moveSel = NSSelectorFromString(@"adjustTextPositionByCharacterOffset:");
    if ([proxy respondsToSelector:moveSel]) {
        ((void (*)(id, SEL, NSInteger))objc_msgSend)(proxy, moveSel, (NSInteger)-1);
    }
}

// 等这一击真正落进宿主文本再补：宿主同步写入时第一次就命中，异步写入时最多重试 8 次（约 120ms）。
// 每次 fire 带一个 token，新的一击会作废旧的重试，所以既不会补两次，也不会补到下一格。
static void GXKSymbolPairAttempt(NSString *preText, UIView *anchor,
                                NSUInteger token, int attempt) {
    if (token != gSymbolPairToken) { gDiagPairGiveUp++; return; } // [DIAG-punct]
    // 用按下那一刻的键视图当锚点复查是否还在符号页：这条判定就是 fire 里判 YES 的同一条，
    // 不依赖会被布局回调作废的 BFS 缓存——换页后键视图的祖先链会隐藏或脱离，这里立刻为 NO，
    // 于是绝不会把右半边补到拼音页的文本里。
    if (anchor && !GXKSymbolViewIsOnSymbolPage(anchor)) {
        gDiagPairOffPage++; // [DIAG-punct] anchor 判定离页：补全被静默丢弃的头号嫌疑
        GXKPunctDiagLog(@"pair offPage a=%d pre=%ld", attempt, (long)preText.length);
        return;
    }
    id<UITextDocumentProxy> proxy = GXKSymbolProxy();
    if (!proxy) return;
    NSString *before = proxy.documentContextBeforeInput;
    if (![before isKindOfClass:[NSString class]]) before = @"";
    NSString *last = before.length > 0 ? [before substringFromIndex:before.length - 1] : nil;
    // 「这一击已经落进宿主」只认一种形态：末尾恰好追加了一个字符。
    //   · 用整串比对而不是比长度：选中一段后按键替换，长度可以不变；
    //   · 必须是「追加」而不是「变短」：退格后留下的末字符也是成对符号，
    //     只看末字符会把右半边补到退格之后，凭空多出一个符号。
    // documentContextBeforeInput 有长度上限：超长时窗口整体右移一格，长度不变、只丢首字符，
    // 所以两种形态都要认，否则长文本下补全会悄悄失效。
    //
    // 但「变短 1」和「窗口右移」在长度上不可区分：空输入框里打第一个符号时 preText=@""，
    // 宿主把空串补成 1 个字符，于是 before.length(1) == preText.length+1 成立、preText 又是
    // 任何串的前缀——追加判定会把「从空到有」误判成追加，可它根本不是这一击造成的（这一击
    // 还在异步路上）。下面的 last 是空串时 last=nil，closer=0，于是静默 return，补全永久丢失。
    // 真机日志：pre=0 的 6 次全部 pair changed，pre>=1 的 2 次全部 pair ok。
    // 所以这一击必须真的让文本变长：preText 为空时只认「有内容」这一条，
    // 且必须等到宿主写出非空内容才算落地，不能把「仍是空」当成已落地。
    if (preText.length == 0) {
        // 空输入框：宿主写没写进来，只能看「有没有内容」。空 = 还没写，继续等。
        if (before.length == 0) {
            if (attempt >= 8) {
                gDiagPairTimeout++;
                GXKPunctDiagLog(@"pair timeout empty attempt=%d", attempt);
                return;
            }
            dispatch_after(dispatch_time(DISPATCH_TIME_NOW, (int64_t)(0.015 * NSEC_PER_SEC)),
                           dispatch_get_main_queue(), ^{
                GXKSymbolPairAttempt(preText, anchor, token, attempt + 1);
            });
            return;
        }
        if (before.length == 1) {
            NSString *ch = before;
            BOOL closer0 = GXKSymbolCloserForChar(ch) != nil;
            GXKPunctDiagLog(@"pair ok a=%d before=1 pre=0 last=%@ closer=%d",
                            attempt, ch, (int)closer0);
            if (closer0) {
                gSymbolPairToken++;
                gDiagPairOk++;
                GXKSymbolInsertPair(ch);
            }
            return;
        }
        gDiagPairGiveUp++;
        GXKPunctDiagLog(@"pair changed a=%d before=%ld pre=0", attempt, (long)before.length);
        return; // 一次落了不止一个字符：不是这一击，不补
    }
    BOOL appended = (before.length == preText.length + 1 && [before hasPrefix:preText]) ||
                    (before.length == preText.length && preText.length > 0 &&
                     [before hasPrefix:[preText substringFromIndex:1]]);
    if (appended) {
        // 以宿主真正落下的末字符为准，不看键面画的是什么：键面画全角、布局里发的可能是半角。
        BOOL closer = last.length > 0 && GXKSymbolCloserForChar(last) != nil;
        GXKPunctDiagLog(@"pair ok a=%d before=%ld pre=%ld last=%@ closer=%d",
                        attempt, (long)before.length, (long)preText.length, last ?: @"nil", (int)closer);
        if (closer) {
            gSymbolPairToken++; // 一次 fire 只补一次
            gDiagPairOk++;
            GXKSymbolInsertPair(last);
        }
        return; // 追加了：要么补完，要么这一击本就不是成对符号
    }
    if (![before isEqualToString:preText]) {
        // [DIAG-punct] 变了但不是追加：窗口右移超过 1 字符、或宿主改写了别的内容。
        gDiagPairGiveUp++;
        GXKPunctDiagLog(@"pair changed a=%d before=%ld pre=%ld", attempt,
                        (long)before.length, (long)preText.length);
        return; // 变了但不是追加（删除/替换/多字插入）：不补
    }
    if (attempt >= 8) {
        gDiagPairTimeout++;
        GXKPunctDiagLog(@"pair timeout before=%ld pre=%ld same=%d", (long)before.length,
                        (long)preText.length, (int)[before isEqualToString:preText]);
        return; // 宿主还没写进来就放弃：宁可不补，也不猜错位置
    }
    dispatch_after(dispatch_time(DISPATCH_TIME_NOW, (int64_t)(0.015 * NSEC_PER_SEC)),
                   dispatch_get_main_queue(), ^{
        GXKSymbolPairAttempt(preText, anchor, token, attempt + 1);
    });
}

static void GXKSymbolFireEvent(id self, SEL _cmd, id bundle, id event) {
    SEL viewSel = NSSelectorFromString(@"targetView");
    UIView *view = (bundle && [bundle respondsToSelector:viewSel])
        ? ((id (*)(id, SEL))objc_msgSend)(bundle, viewSel) : nil;
    BOOL onSymbolPage = view ? GXKSymbolViewIsOnSymbolPage(view) : GXKSymbolPageActive();
    NSTimeInterval now = [NSProcessInfo processInfo].systemUptime;
    BOOL sameKey = onSymbolPage && view && view == gSymbolLastFireView &&
                   now - gSymbolLastFireAt < GXK_SYMBOL_TAP_WINDOW;

    if (sameKey) {
        // 双击的第二击：不上屏，只翻转锁定。
        // 锁定 -> 常驻（取消已排的回拼音）；解除 -> 留在本页，下一击恢复「上屏后回拼音」。
        GXKSymbolCancelReturn();
        gSymbolLocked = !gSymbolLocked;
        gSymbolLastFireView = nil;
        gSymbolLastFireAt = 0;
        // 触感复用 gkx.m 的全局 generator：锁定时 Medium（更重，表示「按住了」），解除时 Light。
        GXKImpact(gSymbolLocked ? UIImpactFeedbackStyleMedium : UIImpactFeedbackStyleLight);
        return;
    }

    if (onSymbolPage) {
        gSymbolLastFireView = view;
        UIViewController *vc = gCurrentVC;
        gSymbolLastFireBody = (view && vc.isViewLoaded) ? GXKNineKeyBodyForKey(view, vc.view) : GXKSymbolHost();
        gSymbolLastFireAt = now;
    } else {
        // 这一击不在符号页：锁定就地解除，不等布局回调（切页后立刻打字也能复位）。
        // 同时作废还没落地的补全重试，免得它把右半边补进这一击所在的页面。
        GXKSymbolResetPageState();
    }

    // 转发之前先存一份光标前文本：宿主是同步写还是异步写，靠「内容变了没有」判定。
    NSString *preText = @"";
    if (onSymbolPage) {
        id<UITextDocumentProxy> probe = GXKSymbolProxy();
        NSString *pre = probe ? probe.documentContextBeforeInput : nil;
        if ([pre isKindOfClass:[NSString class]]) preText = pre;
    }

    if (gOrigSymbolFireEvent) gOrigSymbolFireEvent(self, _cmd, bundle, event); // 其余一律原样转发

    if (onSymbolPage) {
        // [DIAG-punct] 这一击的入口证据：锚点是否判在符号页、光标前文本多长。
        gDiagFire++;
        GXKPunctDiagLog(@"fire ident=%@ pre=%ld locked=%d view=%d",
                        view.restorationIdentifier ?: @"nil", (long)preText.length,
                        (int)gSymbolLocked, view != nil);
        // 文本由原生同步写入宿主，补全与回拼音都排在下一拍，避免和这一次提交抢光标。
        // 这里不再复查「是否还在符号页」：布局回调会在提交与补全之间让页面缓存失效，
        // 一旦复查落空，补全就被静默跳过——那正是「有时只补半边」的来源之一。
        // 是否在符号页改由重试里的键视图锚点判定，那条判定不吃这个缓存。
        NSUInteger token = ++gSymbolPairToken;
        UIView *anchor = view; // 只在这一击的重试窗口内强引用，最多 120ms
        dispatch_async(dispatch_get_main_queue(), ^{
            GXKSymbolPairAttempt(preText, anchor, token, 0);
        });
        GXKSymbolScheduleReturn();
    }
}

// 布局变化后校正锁定：离开符号页（切拼音/数字/表情）就自动解除。
// 由 gkx_viewDidLayoutSubviews 调用，本身不做任何扫描，只读布局阶段已经算好的缓存。
static void GXKSymbolNoteLayout(void) {
    if (GXKSymbolPageActive() && (!gSymbolLastFireBody || GXKSymbolHost() == gSymbolLastFireBody)) return;
    GXKSymbolResetPageState();
}

static BOOL GXKSymbolShouldReturnToPrime(id self, SEL _cmd, id key) {
    // 数字页始终常驻；符号页的停留/返回仍由本模块双击时间窗控制。
    if (GXKNineKeyDigitPageActive() || GXKSymbolPageActive()) return NO;
    GXKSymbolResetPageState();
    return gOrigSymbolShouldReturnToPrime ? gOrigSymbolShouldReturnToPrime(self, _cmd, key) : YES;
}

static BOOL GXKZhSymbolShouldReturnToPrime(id self, SEL _cmd, id key) {
    if (GXKNineKeyDigitPageActive() || GXKSymbolPageActive()) return NO;
    GXKSymbolResetPageState();
    return gOrigZhSymbolShouldReturnToPrime ? gOrigZhSymbolShouldReturnToPrime(self, _cmd, key) : YES;
}

static void GXKSymbolInstallHooks(void) {
    static BOOL installed;
    GXKInstallNineKeyPageHooks();
    if (installed) return;
    if (!NSClassFromString(@"GKBTapTouchHandler")) return; // framework 未加载，下次再试
    installed = YES;
    // 只挂这两个类自身的单点方法：不碰任何 touchesBegan/Moved/Ended/Cancelled。
    // 两个类各自拥有实现、ABI 均为 B24@0:8@16；分别保存，26 键回退不串类。
    GXKSwizzleOrSkip(@"GKBSymbolKeyboard", @"shouldReturnToPrimeOnKey:",
                     (IMP)GXKSymbolShouldReturnToPrime,
                     (void **)&gOrigSymbolShouldReturnToPrime);
    GXKSwizzleOrSkip(@"GKBZhSymbolKeyboard", @"shouldReturnToPrimeOnKey:",
                     (IMP)GXKZhSymbolShouldReturnToPrime, (void **)&gOrigZhSymbolShouldReturnToPrime);
    GXKSwizzleOrSkip(@"GKBTapTouchHandler", @"touchActionBundle:fireEvent:",
                     (IMP)GXKSymbolFireEvent, (void **)&gOrigSymbolFireEvent);
}

#endif  // GXK_SYMBOL_DOUBLETAP_H
