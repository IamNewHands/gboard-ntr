// [FEATURE-punct] 九键空格左侧「，。？」键：长按弹层 + 按住左右滑动选择。
//
// 为什么不走原生弹层：
//   该键绑定的 softkey_9keys_punctuation_candidates 定义里只有 label ",.;" 与无障碍串，
//   没有 field3 候选表、也没有 popup_selector，原生 GKBPopupHandler 对这个键根本不建视图。
//   要让它弹层就得改打包后的 KeyDefinition 二进制，跨版本不可维护，故自绘。
//
// 为什么是「给这一格加长按手势」而不是覆盖 UIButton：
//   覆盖按钮会吃掉单击，而单击是原生的标点候选行为，自己实现必然走样。
//   手势识别失败（普通点击）时触摸原样下发给键，单击行为零改动；
//   只有长按被识别时才取消这一条触摸链，范围仅限这一格。
//   滑行输入发生在字母键上，这里不碰任何全局触摸回调，红线 2 不受影响。
//
// 性能：定位键只在 gkx_viewDidLayoutSubviews 的合并拍里做一次（每帧至多一次全树扫描），
//       弹层只有 10 个 UILabel，构建一次后复用；拖动只改背景色，不重建视图树。
#ifndef GXK_PUNCT_POPUP_H
#define GXK_PUNCT_POPUP_H

#define GXK_PUNCT_KEY_IDENT    @"key_pos_9keys_4_1" // 只有拼音页有这个 ident；数字页靠键帽文字认
#define GXK_PUNCT_HOLD_DELAY   0.32   // 长按判定阈值：低于原生 0.5s，手感更跟手
#define GXK_PUNCT_CELL_MAX     44.0   // 单格最大宽度，超出则整排按可用宽度均分
#define GXK_PUNCT_PANEL_HEIGHT 42.0
#define GXK_PUNCT_ASSOC_KEY    "gxk.punct.gesture"
#define GXK_PUNCT_SYMBOLS_KEY  @"GXKPunctSymbols" // App Group：拼音页符号表
#define GXK_PUNCT_COUNT_KEY    @"GXKPunctCount"   // App Group：拼音页显示前几个
#define GXK_PUNCT_DIGIT_SYMBOLS_KEY @"GXKPunctDigitSymbols" // App Group：数字页符号表
#define GXK_PUNCT_DIGIT_COUNT_KEY   @"GXKPunctDigitCount"   // App Group：数字页显示前几个
#define GXK_PUNCT_MAX_SYMBOLS  10                 // 上限沿用原版 10 格：375pt 宽键盘单格仍有 37pt

// 拼音页这一格的 restorationIdentifier 是 key_pos_9keys_4_1，123 数字页那一格**没有** ident
// （真机核对：数字页 24 个可见软键只有 8 个带 ident，4_1 不在其中）。两页绑的 softKeyDef 也不同：
// 拼音页是 softkey_9keys_comma（显示「，」），数字页是 softkey_9keys_punctuation_candidates（显示 ",.;"）。
// 所以身份判定分两路：有 ident 按 ident 认，没 ident 按键帽文字认（见 GXKPunctKeyMatches）。
// 分页同样看这一格显示的字：单字是拼音页，多字是数字页。
// 两页的符号表与显示个数分开存：改数字页不影响拼音页，反之亦然。
typedef NS_ENUM(NSInteger, GXKPunctPage) {
    GXKPunctPagePinyin = 0,
    GXKPunctPageDigit = 1,
};

// 视图引用一律 __weak：键盘根视图与键体由原生持有，这里绝不延长它们的生命周期（Jetsam 红线）。
static __weak UIView *gPunctKey;
static __weak UIView *gPunctRoot;
static UIView *gPunctPanel;
static NSArray<UILabel *> *gPunctCells;
static CGFloat gPunctCellWidth;
static NSInteger gPunctIndex;
static GXKPunctPage gPunctPage;                 // 当前这排格子对应哪一页（两页共用同一个 ident）
static NSString *gPunctPreText;
static UILongPressGestureRecognizer *gPunctGesture;
static NSArray<NSString *> *gPunctSymbolsInUse; // 当前这排格子对应的符号表（指针比较即可判断变没变）
static UIColor *gPunctSkinColor;                // 键盘底色，换肤后重算
static UIColor *gPunctNativeTextColor;          // 键盘原生文字色
static BOOL gPunctDark;                         // 弹层当前是深色还是浅色

// 深浅配色与皮肤采样都实现在 gkx.m 里（本文件在 gkx.m 中途引入，函数体在后面）。
// 这里只前置声明，签名必须与定义逐字一致。
static UIColor *GXKPhraseSkinColor(UIView *body);
static BOOL GXKPhrasePrefersDark(UIView *body, UIColor *skin, UITraitCollection *traits);
static UIColor *GXKPhraseBackgroundColor(UIColor *skin, BOOL dark);
static UIColor *GXKPhrasePrimaryTextColor(UIColor *native, BOOL dark);
static UIColor *GXKPhraseSeparatorColor(UIColor *native, BOOL dark);

// 默认符号表：按中文输入的实际频次排，前几位最常用，滑到即中。
// 用户没改过设置时弹层就是这张表的前 GXK_PUNCT_MAX_SYMBOLS 项，与旧版本完全一致。
static NSArray<NSString *> *GXKPunctDefaultSymbols(void) {
    static NSArray<NSString *> *list;
    static dispatch_once_t once;
    dispatch_once(&once, ^{
        list = @[@"，", @"。", @"？", @"！", @"、", @"；", @"：", @"…", @"“", @"”"];
    });
    return list;
}

// 设置存 App Group：主 App 写、键盘扩展读，跨进程立刻生效（和常用语、诊断开关同一条路）。
static NSUserDefaults *GXKPunctDefaults(void) {
    static NSUserDefaults *defaults = nil;
    static BOOL tried = NO;
    if (!tried) {
        tried = YES;
        defaults = [[NSUserDefaults alloc] initWithSuiteName:GXKGroup];
        if (!defaults) defaults = [NSUserDefaults standardUserDefaults];
    }
    return defaults;
}

// 两页各存一套：拼音页沿用原键名（老用户存过的自定义表原样保留），数字页用新键名。
static NSString *GXKPunctSymbolsKey(GXKPunctPage page) {
    return page == GXKPunctPageDigit ? GXK_PUNCT_DIGIT_SYMBOLS_KEY : GXK_PUNCT_SYMBOLS_KEY;
}

static NSString *GXKPunctCountKey(GXKPunctPage page) {
    return page == GXKPunctPageDigit ? GXK_PUNCT_DIGIT_COUNT_KEY : GXK_PUNCT_COUNT_KEY;
}

// 数字页默认表：这一格本身印的是 ASCII ",.;"，所以默认弹 ASCII 标点最不违和；
// 拼音页那张中文表在数字页上按出来是一串全角标点，和键帽对不上。
static NSArray<NSString *> *GXKPunctDigitDefaultSymbols(void) {
    static NSArray<NSString *> *list;
    static dispatch_once_t once;
    dispatch_once(&once, ^{
        list = @[@",", @".", @";", @":", @"?", @"!", @"~", @"-", @"_", @"'"];
    });
    return list;
}

static NSArray<NSString *> *GXKPunctDefaultForPage(GXKPunctPage page) {
    return page == GXKPunctPageDigit ? GXKPunctDigitDefaultSymbols() : GXKPunctDefaultSymbols();
}

// 用户符号表：只收非空字符串，超上限截断；空表退回默认表，保证弹层永远有东西可点。
static NSArray<NSString *> *GXKPunctSymbolsForPage(GXKPunctPage page) {
    id raw = [GXKPunctDefaults() objectForKey:GXKPunctSymbolsKey(page)];
    if (![raw isKindOfClass:[NSArray class]]) return GXKPunctDefaultForPage(page);
    NSMutableArray<NSString *> *list = [NSMutableArray array];
    for (id item in (NSArray *)raw) {
        if ([item isKindOfClass:[NSString class]] && ((NSString *)item).length > 0) {
            [list addObject:(NSString *)item];
        }
        if (list.count >= GXK_PUNCT_MAX_SYMBOLS) break;
    }
    return list.count ? list : GXKPunctDefaultForPage(page);
}

// 显示个数：没设过 = 全显示（旧行为）；越界一律夹回 1..上限。
static NSInteger GXKPunctSymbolCountForPage(GXKPunctPage page) {
    NSInteger n = [GXKPunctDefaults() integerForKey:GXKPunctCountKey(page)];
    if (n <= 0) n = GXK_PUNCT_MAX_SYMBOLS;
    if (n > GXK_PUNCT_MAX_SYMBOLS) n = GXK_PUNCT_MAX_SYMBOLS;
    return n;
}

static void GXKPunctSaveSettings(GXKPunctPage page, NSArray<NSString *> *symbols, NSInteger count) {
    NSUserDefaults *defaults = GXKPunctDefaults();
    if (!defaults) return;
    NSMutableArray<NSString *> *clean = [NSMutableArray array];
    for (id item in symbols) {
        if ([item isKindOfClass:[NSString class]] && ((NSString *)item).length > 0) {
            [clean addObject:(NSString *)item];
        }
        if (clean.count >= GXK_PUNCT_MAX_SYMBOLS) break;
    }
    if (count < 1) count = 1;
    if (count > (NSInteger)clean.count) count = (NSInteger)clean.count;
    if (clean.count) {
        [defaults setObject:clean forKey:GXKPunctSymbolsKey(page)];
        [defaults setInteger:count forKey:GXKPunctCountKey(page)];
    } else {
        [defaults removeObjectForKey:GXKPunctSymbolsKey(page)];
        [defaults removeObjectForKey:GXKPunctCountKey(page)];
    }
    [defaults synchronize]; // 跨进程，键盘那边要立刻看见。
}

// 恢复默认：只删这一页的两个键，另一页的自定义表不受影响。
static void GXKPunctResetSettings(GXKPunctPage page) {
    NSUserDefaults *defaults = GXKPunctDefaults();
    if (!defaults) return;
    [defaults removeObjectForKey:GXKPunctSymbolsKey(page)];
    [defaults removeObjectForKey:GXKPunctCountKey(page)];
    [defaults synchronize];
}

// 弹层真正显示的那几个：该页符号表的前 count 项。
// 两页各有一份 0.5 秒缓存，且只在内容真的变了才换新对象——调用方靠指针比较就知道要不要重建格子。
static NSArray<NSString *> *GXKPunctCandidatesForPage(GXKPunctPage page) {
    static NSArray<NSString *> *cached[2];
    static NSTimeInterval cachedAt[2];
    static BOOL primed[2];
    NSUInteger slot = (page == GXKPunctPageDigit) ? 1 : 0;
    NSTimeInterval now = CACurrentMediaTime();
    if (primed[slot] && now - cachedAt[slot] < 0.5) return cached[slot];
    NSArray<NSString *> *all = GXKPunctSymbolsForPage(page);
    NSInteger n = GXKPunctSymbolCountForPage(page);
    if (n < 1) n = 1;
    if ((NSUInteger)n > all.count) n = (NSInteger)all.count;
    NSArray<NSString *> *next = [all subarrayWithRange:NSMakeRange(0, (NSUInteger)n)];
    cachedAt[slot] = now;
    if (!primed[slot] || ![next isEqualToArray:cached[slot]]) cached[slot] = next;
    primed[slot] = YES;
    return cached[slot];
}

// 单字符是否属于 Unicode 标点/符号类。数字、字母（含汉字 Lo）、空白都不算。
static BOOL GXKPunctCharIsPunct(unichar ch) {
    return [[NSCharacterSet punctuationCharacterSet] characterIsMember:ch] ||
           [[NSCharacterSet symbolCharacterSet] characterIsMember:ch];
}

static BOOL GXKPunctLabelIsPunctCandidates(NSString *text); // 定义在下方

// 从一个视图上取它自己承载的文字。数字页那一格的 ",.;" 不在 idToViewDict[@"label"] 上，
// 而是挂在带 caption 的图片视图里（全包只有 GKBImageViewWithCaption / GKBMinimizedLabelWithBackgroundImage /
// GKBSpaceSoftKeyView 三类有 captionLabel），所以这一层必须认 caption 与 -text，不能只认 UILabel。
static NSString *GXKPunctTextOfView(id view) {
    if (!view) return nil;
    if ([view isKindOfClass:[UILabel class]]) {
        UILabel *label = (UILabel *)view;
        if (label.text.length) return label.text;
        if (label.attributedText.length) return label.attributedText.string;
        return nil;
    }
    @try {
        if ([view respondsToSelector:@selector(captionLabel)]) {
            id captionView = [view valueForKey:@"captionLabel"];
            if (captionView && captionView != view) { // 自引用时不再递归，避免死循环
                NSString *caption = GXKPunctTextOfView(captionView);
                if (caption.length) return caption;
            }
        }
        if ([view respondsToSelector:@selector(text)]) {
            id text = [view valueForKey:@"text"];
            if ([text isKindOfClass:[NSString class]] && ((NSString *)text).length) return (NSString *)text;
        }
        if ([view respondsToSelector:@selector(attributedText)]) {
            id attributed = [view valueForKey:@"attributedText"];
            if ([attributed isKindOfClass:[NSAttributedString class]] &&
                ((NSAttributedString *)attributed).length) {
                return ((NSAttributedString *)attributed).string;
            }
        }
    } @catch (__unused NSException *e) {}
    return nil;
}

// 键帽文字可能挂在任意深度的子视图上（数字页就是），收集有限几段交给下面挑。
static void GXKPunctCollectTexts(UIView *view, NSUInteger depth, NSMutableArray<NSString *> *out) {
    if (!view || depth > 3 || out.count >= 8) return;
    NSString *own = GXKPunctTextOfView(view);
    if (own.length && ![out containsObject:own]) [out addObject:own];
    if (out.count >= 8) return;
    for (UIView *sub in view.subviews) GXKPunctCollectTexts(sub, depth + 1, out);
}

// 这一格的键帽文字：拼音页是「，」（单字），数字页是 ",.;"（简中）或 "，。？"（繁中）。
// 读不到就返回 nil，调用方各自决定怎么兜底。
static NSString *GXKPunctKeyLabelText(UIView *key) {
    if (!key) return nil;
    // 第一路：原生内容字典。拼音页这一格走这条；数字页这一格字典里没有可用的 label。
    if ([key respondsToSelector:@selector(idToViewDict)]) {
        NSDictionary *contents = ((id<GXKNativeSoftKeyContent>)key).idToViewDict;
        if ([contents isKindOfClass:[NSDictionary class]]) {
            NSString *text = GXKPunctTextOfView(contents[@"label"]);
            if (text.length) return text;
        }
    }
    // 第二路：键自己的子视图。优先取「整段都是标点」的那一段：同一个键上可能还挂着图标说明之类的短文字。
    NSMutableArray<NSString *> *texts = [NSMutableArray arrayWithCapacity:4];
    GXKPunctCollectTexts(key, 0, texts);
    for (NSString *text in texts) {
        if (GXKPunctLabelIsPunctCandidates(text)) return text;
    }
    // 第三路：",.;" 也可能被拆成三个单字标签。按子视图顺序拼起来再看一次，
    // 只在「每一段都是单字符标点」时拼，避免把无关短文字粘成一串假标点。
    if (texts.count >= 2) {
        NSMutableString *joined = [NSMutableString string];
        BOOL allSinglePunct = YES;
        for (NSString *text in texts) {
            if (text.length != 1 || !GXKPunctCharIsPunct([text characterAtIndex:0])) {
                allSinglePunct = NO;
                break;
            }
            [joined appendString:text];
            if (joined.length > 8) { allSinglePunct = NO; break; }
        }
        if (allSinglePunct) return joined;
    }
    // 第四路：无障碍串。原包里这一格的 softKeyDef 带一条无障碍文字，键帽若整个用图绘制，
    // 这是唯一还留着「这一格是什么」的地方。它是给人读的，可能是「标点」这类词，所以只作兜底。
    @try {
        if ([key respondsToSelector:@selector(accessibilityLabel)]) {
            id acc = [key valueForKey:@"accessibilityLabel"];
            if ([acc isKindOfClass:[NSString class]] && ((NSString *)acc).length) return (NSString *)acc;
        }
    } @catch (__unused NSException *e) {}
    return (NSString *)texts.firstObject;
}

// 数字页这一格没有 restorationIdentifier：真机诊断日志（2026-11-23）里数字页 24 个可见软键
// 只有 8 个带 ident（search_logo / return / emoji / del / left_1..4），key_pos_9keys_4_1
// 根本不在其中，所以「只按 ident 认」在数字页必然每拍落空，手势从未挂上。
// 改为按键帽文字认：原包里这一格的 label 字面量是 ",.;"（简中）或 "，。？"（繁中），
// 全是标点且不止一个字符。判据要求「2~8 个字符，且每个字符都属于 Unicode 标点或符号类」：
// 数字键 0-9（数字）、空格「空格」、回车「换行」、切换键「123:」（带数字）都不满足；
// 「按键盘」「符号」这类汉字标签属于字母类（Lo），同样被排除；拼音页那一格只有一个字，长度就不够。
// 用「必须是标点」而不是「不能是字母数字」：后者会把汉字标签放进来，数字页上不止一格会命中，
// 命中两格时 find 按布局不确定放弃，长按又会没反应。
static BOOL GXKPunctLabelIsPunctCandidates(NSString *text) {
    if (![text isKindOfClass:[NSString class]] || text.length < 2 || text.length > 8) return NO;
    for (NSUInteger i = 0; i < text.length; i++) {
        if (!GXKPunctCharIsPunct([text characterAtIndex:i])) return NO;
    }
    return YES;
}

// 这一格绑定的 softKeyDef 是不是标点候选那一个：数字页的键帽若整个用图绘制、
// 连 caption 都读不到，只剩这条线索能证明「就是这一格」。字符串来自原包布局表里的定义名
// softkey_9keys_punctuation_candidates，全包没有第二个键用它，不会误伤。
// 结果按键缓存：-description 会拼字符串，而这条判定在「还没认出这一格」时每拍都在跑，
// 不缓存就是每帧几十次字符串分配（键盘扩展内存与卡顿红线）。
// 缓存必须连着 def 对象一起存：键体视图会被原生复用，切页后同一个视图可能已经绑了另一个
// softKeyDef（数字键「5」复用了上一页标点格的视图）。只存布尔值就会把上一页的结论套到新页。
// 存成 {def 指针, 结论}，指针一变就重算。
static char GXKPunctDefCacheKey;
static BOOL GXKPunctKeyDefIsPunctuation(UIView *key) {
    if (!key) return NO;
    if (![key respondsToSelector:@selector(softKeyDef)]) return NO;
    id def = nil;
    @try { def = [key valueForKey:@"softKeyDef"]; } @catch (__unused NSException *e) { def = nil; }
    if (!def) return NO;
    NSArray *cached = objc_getAssociatedObject(key, &GXKPunctDefCacheKey);
    if ([cached isKindOfClass:[NSArray class]] && cached.count == 2 && cached[0] == def) {
        return [cached[1] boolValue];
    }
    BOOL hit = NO;
    @try {
        NSString *desc = [def description];
        if ([desc isKindOfClass:[NSString class]] &&
            [desc rangeOfString:@"punctuation"].location != NSNotFound) {
            hit = YES;
        }
    } @catch (__unused NSException *e) {}
    objc_setAssociatedObject(key, &GXKPunctDefCacheKey, @[def, @(hit)], OBJC_ASSOCIATION_RETAIN_NONATOMIC);
    return hit;
}

// 身份判定，全项目唯一一处：有 ident 的键按 ident 认（拼音页 key_pos_9keys_4_1），
// 没 ident 的键才看键帽文字或 softKeyDef（数字页）。有 ident 的键绝不拿文字去猜——反过来让
// 文字盖过 ident，会把布局里别的带 ident 的键误认成这一格，而数字页的问题正是从「没有 ident」开始的。
static BOOL GXKPunctKeyMatches(UIView *key) {
    if (!key) return NO;
    NSString *ident = key.restorationIdentifier;
    if (ident.length) return [ident isEqualToString:GXK_PUNCT_KEY_IDENT];
    // 先看键帽文字（最便宜、也最贴近用户看到的东西），读不出来才去问 softKeyDef。
    if (GXKPunctLabelIsPunctCandidates(GXKPunctKeyLabelText(key))) return YES;
    return GXKPunctKeyDefIsPunctuation(key);
}

// 这一格在哪一页。第一判据是 ident：key_pos_9keys_4_1 只有拼音页有，数字页那一格没有 ident，
// 所以「有 ident 就是拼音页」是最稳的一条，不依赖能否读到字。
// 没有 ident 时退到键帽文字：数字页印 ",.;"（三个字符），拼音页永远只有一个字。
// 不用「首字符是否 ASCII」判断：英文系统下拼音页逗号键也是 ASCII 的 ","，会误判成数字页。
static GXKPunctPage GXKPunctPageForKey(UIView *key) {
    if (!key) return gPunctPage;
    if (key.restorationIdentifier.length) return GXKPunctPagePinyin;
    // 没有 ident 就是数字页那一格：布局表里数字页的标点格不写 restorationIdentifier。
    // 不按文字长短判，是因为键帽文字可能整个读不出来；ident 的有无本来就是两页的硬差别。
    if (GXKPunctKeyDefIsPunctuation(key)) return GXKPunctPageDigit;
    NSString *text = GXKPunctKeyLabelText(key);
    if (text.length == 0) return gPunctPage;
    return text.length > 1 ? GXKPunctPageDigit : GXKPunctPagePinyin;
}

// 只认 GXKPunctKeyMatches 命中的那一格，且必须挂在可见九键体上；出现两个可见同款就放弃，保持原生不猜。
static UIView *GXKPunctFindKey(UIView *root) {
    Class keyClass = GXKClassCached(@"GKBSoftKeyView", &gCachedKeyClass);
    Class nineClass = GXKClassCached(@"GKB9KeysSoftKeyboardView", &gCachedNineKeyClass);
    if (!root || !root.window || !keyClass || !nineClass) return nil;
    UIView *candidate = nil;
    NSMutableArray<UIView *> *stack = [NSMutableArray arrayWithObject:root];
    NSUInteger visited = 0;
    // [DIAG-punct] 记录九键体里所有 GKBSoftKeyView 的 ident：判定是「ident 不存在」还是四连判定之一失败。
    // 诊断关闭（出货默认）时不建数组、不 containsObject、不拼字符串：这条路径每次布局都在跑。
    BOOL diag = GXKPunctDiagEnabled();
    NSMutableArray<NSString *> *seenIdents = diag ? [NSMutableArray array] : nil;
    // [DIAG-punct] 无 ident 的键都印了什么字：数字页那一格若连键帽文字也读不到，
    // 这条清单会直接显示「那一格没有 label」，不用再猜一轮。
    NSMutableArray<NSString *> *seenLabels = diag ? [NSMutableArray array] : nil;
    NSUInteger seenKeys = 0, hiddenSkip = 0, bodyFail = 0, visibleFail = 0, dupes = 0, labelHits = 0;
    while (stack.count && visited++ < 1500) {
        UIView *v = stack.lastObject;
        [stack removeLastObject];
        if (v.isHidden || v.alpha < 0.05 || v.window != root.window) { hiddenSkip++; continue; }
        if ([v isKindOfClass:keyClass]) {
            seenKeys++;
            NSString *ident = v.restorationIdentifier;
            if (diag && ident.length && ![seenIdents containsObject:ident]) [seenIdents addObject:ident];
            if (diag && ident.length == 0) {
                // 打「原始收集结果」而不是最终判定：判定为空时才能看出到底是没文字，
                // 还是有文字但被标点判据否掉（例如拆成单字、或带了数字）。
                NSMutableArray<NSString *> *raw = [NSMutableArray arrayWithCapacity:4];
                GXKPunctCollectTexts(v, 0, raw);
                NSString *entry = raw.count ? [raw componentsJoinedByString:@"/"] : @"<no-text>";
                if (GXKPunctKeyDefIsPunctuation(v)) entry = [entry stringByAppendingString:@" [def:punct]"];
                if (![seenLabels containsObject:entry]) [seenLabels addObject:entry];
            }
            // 数字页那一格没有 restorationIdentifier，只按 ident 认必然每拍落空（真机日志：数字页
            // 24 个可见软键只有 8 个带 ident，key_pos_9keys_4_1 不在其中）。统一走 GXKPunctKeyMatches。
            if (GXKPunctKeyMatches(v)) {
                if (diag && ident.length == 0) labelHits++; // [DIAG-punct] 无 ident 靠键帽文字命中
                BOOL inBody = GXKNineKeyBodyForKey(v, root) != nil;
                BOOL visible = inBody && GXKKeyIsVisible(v, root);
                if (!inBody) bodyFail++;
                if (inBody && !visible) visibleFail++;
                if (inBody && visible) {
                    if (candidate && candidate != v) dupes++;
                    candidate = v;
                }
            }
        }
        [stack addObjectsFromArray:v.subviews];
    }
    if (diag) {
        gDiagFindMiss++;
        GXKPunctDiagLog(@"find keys=%lu visit=%lu hid=%lu bodyFail=%lu visFail=%lu dup=%lu cand=%d tail=%lu labelHit=%lu ids=%@",
                        (unsigned long)seenKeys, (unsigned long)visited, (unsigned long)hiddenSkip,
                        (unsigned long)bodyFail, (unsigned long)visibleFail, (unsigned long)dupes,
                        candidate != nil, (unsigned long)stack.count, (unsigned long)labelHits,
                        [seenIdents count] > 24
                            ? [NSString stringWithFormat:@"%@…(+%lu)", [seenIdents subarrayWithRange:NSMakeRange(0, 24)],
                                                         (unsigned long)(seenIdents.count - 24)]
                            : [seenIdents componentsJoinedByString:@","]);
        GXKPunctDiagLog(@"find labels=%@",
                        [seenLabels count] > 24
                            ? [NSString stringWithFormat:@"%@…(+%lu)", [seenLabels subarrayWithRange:NSMakeRange(0, 24)],
                                                         (unsigned long)(seenLabels.count - 24)]
                            : [seenLabels componentsJoinedByString:@"|"]);
    }
    if (dupes) return nil; // 布局不确定：不动原生
    return stack.count ? nil : candidate;
}

static void GXKPunctHidePanel(void) {
    gPunctIndex = -1;
    gPunctPreText = nil;
    if (gPunctPanel) gPunctPanel.hidden = YES;
}

// 配色：皮肤与深浅都跟键盘本体走，和常用语面板同一套采样函数，不读系统外观开关——
// Gboard 皮肤可以和系统深浅模式不一致，读系统开关会出现「深色皮肤配白底弹层」。
static void GXKPunctRefreshTheme(void) {
    UIView *body = (gToolbarNineBody && gToolbarNineBody.window) ? gToolbarNineBody : nil;
    UIColor *skin = GXKPhraseSkinColor(body);
    UIColor *native = body ? GXKToolbarTextStyle(body, NULL) : nil;
    if (![native isKindOfClass:[UIColor class]]) native = nil;
    BOOL dark = GXKPhrasePrefersDark(body, skin, nil);
    gPunctSkinColor = skin;
    gPunctNativeTextColor = native;
    gPunctDark = dark;
}

static UIColor *GXKPunctPanelColor(void) {
    return GXKPhraseBackgroundColor(gPunctSkinColor, gPunctDark);
}

static UIColor *GXKPunctTextColor(void) {
    return GXKPhrasePrimaryTextColor(gPunctNativeTextColor, gPunctDark);
}

// 高亮块：深色皮肤上用白、浅色皮肤上用黑，透明度固定，两种底色下都读得清。
static UIColor *GXKPunctHighlightColor(void) {
    return [UIColor colorWithWhite:(gPunctDark ? 1.0 : 0.0) alpha:0.14];
}

static void GXKPunctApplyTheme(void) {
    if (!gPunctPanel) return;
    gPunctPanel.backgroundColor = GXKPunctPanelColor();
    gPunctPanel.layer.borderColor = GXKPhraseSeparatorColor(gPunctNativeTextColor, gPunctDark).CGColor;
    gPunctPanel.layer.shadowOpacity = gPunctDark ? 0.45f : 0.16f;
    for (NSUInteger i = 0; i < gPunctCells.count; i++) {
        BOOL on = ((NSInteger)i == gPunctIndex);
        gPunctCells[i].textColor = GXKPunctTextColor();
        gPunctCells[i].backgroundColor = on ? GXKPunctHighlightColor() : [UIColor clearColor];
    }
}

// 符号表或个数变了才重建格子：旧格子在弹层里就地删掉，弹层本身与遮挡登记都不重建。
static void GXKPunctSyncCells(NSArray<NSString *> *items) {
    if (!gPunctPanel || items == gPunctSymbolsInUse) return;
    for (UILabel *cell in gPunctCells) [cell removeFromSuperview];
    NSMutableArray<UILabel *> *cells = [NSMutableArray arrayWithCapacity:items.count];
    for (NSString *ch in items) {
        UILabel *cell = [[UILabel alloc] initWithFrame:CGRectZero];
        cell.text = ch;
        cell.font = [UIFont systemFontOfSize:20.0];
        cell.textColor = GXKPunctTextColor();
        cell.textAlignment = NSTextAlignmentCenter;
        cell.layer.cornerRadius = 6.0;
        cell.clipsToBounds = YES;
        [gPunctPanel addSubview:cell];
        [cells addObject:cell];
    }
    gPunctCells = cells;
    gPunctSymbolsInUse = items;
    gPunctIndex = -1;
}

// 弹层只建一次：格子常驻，显示/隐藏靠 hidden，避免每次长按都重建视图树。
static void GXKPunctBuildPanelIfNeeded(void) {
    GXKPunctRefreshTheme();
    if (gPunctPanel) {
        GXKPunctSyncCells(GXKPunctCandidatesForPage(gPunctPage));
        GXKPunctApplyTheme();
        return;
    }
    UIView *panel = [[UIView alloc] initWithFrame:CGRectZero];
    panel.layer.cornerRadius = 9.0;
    panel.layer.borderWidth = 1.0 / UIScreen.mainScreen.scale;
    panel.layer.shadowColor = [UIColor blackColor].CGColor;
    panel.layer.shadowRadius = 6.0;
    panel.layer.shadowOffset = CGSizeMake(0, 2);
    panel.clipsToBounds = NO;
    panel.hidden = YES;
    gPunctPanel = panel;
    GXKToolbarOwnViewRegister(panel); // 弹层连同它的格子都不进遮挡表。
    gPunctCells = @[];
    gPunctSymbolsInUse = nil;
    gPunctIndex = -1;
    GXKPunctSyncCells(GXKPunctCandidatesForPage(gPunctPage));
    GXKPunctApplyTheme();
}

static void GXKPunctHighlight(NSInteger index) {
    if (index == gPunctIndex) return;
    gPunctIndex = index;
    for (NSUInteger i = 0; i < gPunctCells.count; i++) {
        BOOL on = ((NSInteger)i == index);
        gPunctCells[i].backgroundColor = on ? GXKPunctHighlightColor() : [UIColor clearColor];
        gPunctCells[i].textColor = GXKPunctTextColor();
    }
}

// 定位：整排贴在键正上方，越界就夹回宿主内；上方放不下改贴下方。
static void GXKPunctLayoutPanel(void) {
    if (!gPunctPanel || !gPunctKey || !gPunctRoot) return;
    NSUInteger n = gPunctCells.count;
    if (!n) return;
    CGRect keyRect = [gPunctKey convertRect:gPunctKey.bounds toView:gPunctRoot];
    CGFloat hostW = gPunctRoot.bounds.size.width;
    CGFloat cellW = MIN(GXK_PUNCT_CELL_MAX, floor(hostW / (CGFloat)n));
    if (cellW < 16.0) cellW = 16.0;
    gPunctCellWidth = cellW;
    CGFloat panelW = cellW * (CGFloat)n;
    CGFloat x = CGRectGetMidX(keyRect) - panelW / 2.0;
    x = MAX(0.0, MIN(x, MAX(0.0, hostW - panelW)));
    CGFloat y = CGRectGetMinY(keyRect) - GXK_PUNCT_PANEL_HEIGHT - 8.0;
    if (y < 0.0) y = CGRectGetMaxY(keyRect) + 8.0;
    gPunctPanel.frame = CGRectMake(x, y, panelW, GXK_PUNCT_PANEL_HEIGHT);
    for (NSUInteger i = 0; i < n; i++) {
        gPunctCells[i].frame = CGRectMake(cellW * (CGFloat)i, 0, cellW, GXK_PUNCT_PANEL_HEIGHT);
    }
}

static NSInteger GXKPunctIndexAtPoint(CGPoint point) {
    NSUInteger n = gPunctCells.count;
    if (!n || gPunctCellWidth <= 0.0) return -1;
    NSInteger idx = (NSInteger)floor(point.x / gPunctCellWidth);
    if (idx < 0) idx = 0;
    if (idx > (NSInteger)n - 1) idx = (NSInteger)n - 1;
    return idx;
}

static void GXKPunctCommit(NSInteger index) {
    NSArray<NSString *> *items = GXKPunctCandidatesForPage(gPunctPage);
    if (index < 0 || index >= (NSInteger)items.count) return;
    NSString *ch = items[(NSUInteger)index];
    UIViewController *vc = gCurrentVC;
    if (!vc || ![vc isKindOfClass:[UIInputViewController class]]) return;
    id<UITextDocumentProxy> proxy = ((UIInputViewController *)vc).textDocumentProxy;
    if (!proxy) return;
    // 长按被识别时原生触摸链已取消，正常情况下宿主文本没变；
    // 但若原生仍然提交了一次标点，这里先撤掉它，避免叠字（只认「恰好追加一个字符」）。
    NSString *now = proxy.documentContextBeforeInput;
    if (![now isKindOfClass:[NSString class]]) now = @"";
    if (gPunctPreText && now.length == gPunctPreText.length + 1 && [now hasPrefix:gPunctPreText]) {
        [proxy deleteBackward];
    }
    [proxy insertText:ch];
    GXKImpact(UIImpactFeedbackStyleLight);
    // [DIAG-punct] 上屏结果：pre/now 长度能区分「原生先提交了一次」与「文本没动」。
    GXKPunctDiagLog(@"cmt idx=%ld ch=%@ pre=%ld now=%ld", (long)index, ch,
                    (long)(gPunctPreText ? gPunctPreText.length : -1), (long)now.length);
}

@interface GXKPunctGestureTarget : NSObject
- (void)onPunctLongPress:(UILongPressGestureRecognizer *)gr;
@end

@implementation GXKPunctGestureTarget
- (void)onPunctLongPress:(UILongPressGestureRecognizer *)gr {
    UIView *root = gPunctRoot;
    // [DIAG-punct] 状态迁移就是「完全无反应」的分水岭：一条 Began 都没有 = 手势从未识别。
    GXKPunctDiagLog(@"lp state=%ld root=%d", (long)gr.state, root != nil);
    if (!root) { GXKPunctHidePanel(); return; }
    if (gr.state == UIGestureRecognizerStateBegan) {
        gPunctPage = GXKPunctPageForKey(gPunctKey); // 先认页，再按这一页的表建格子
        GXKPunctBuildPanelIfNeeded();
        if (gPunctPanel.superview != root) [root addSubview:gPunctPanel];
        GXKPunctLayoutPanel();
        gPunctPanel.hidden = NO;
        [root bringSubviewToFront:gPunctPanel];
        UIViewController *vc = gCurrentVC;
        if (vc && [vc isKindOfClass:[UIInputViewController class]]) {
            NSString *pre = ((UIInputViewController *)vc).textDocumentProxy.documentContextBeforeInput;
            gPunctPreText = [pre isKindOfClass:[NSString class]] ? pre : @"";
        } else {
            gPunctPreText = nil;
        }
        GXKPunctHighlight(GXKPunctIndexAtPoint([gr locationInView:gPunctPanel]));
        GXKImpact(UIImpactFeedbackStyleMedium);
        return;
    }
    if (gr.state == UIGestureRecognizerStateChanged) {
        if (gPunctPanel.hidden) return;
        GXKPunctHighlight(GXKPunctIndexAtPoint([gr locationInView:gPunctPanel]));
        return;
    }
    if (gr.state == UIGestureRecognizerStateEnded) {
        NSInteger index = gPunctIndex;
        GXKPunctHidePanel();
        GXKPunctCommit(index);
        return;
    }
    GXKPunctHidePanel(); // Cancelled / Failed：什么也不上屏
}
@end

static GXKPunctGestureTarget *gPunctTarget;

static void GXKPunctDetach(void) {
    if (gPunctKey) { gDiagDetach++; } // [DIAG-punct]
    GXKPunctHidePanel();
    if (gPunctGesture) {
        [gPunctGesture.view removeGestureRecognizer:gPunctGesture];
        gPunctGesture = nil;
    }
    if (gPunctKey) objc_setAssociatedObject(gPunctKey, GXK_PUNCT_ASSOC_KEY, nil, OBJC_ASSOCIATION_RETAIN_NONATOMIC);
    if (gPunctPanel.superview) [gPunctPanel removeFromSuperview];
    gPunctKey = nil;
    gPunctRoot = nil;
}

static void GXKPunctAttach(UIView *key, UIView *root) {
    if (!gPunctTarget) gPunctTarget = [[GXKPunctGestureTarget alloc] init];
    UILongPressGestureRecognizer *gr =
        [[UILongPressGestureRecognizer alloc] initWithTarget:gPunctTarget
                                                      action:@selector(onPunctLongPress:)];
    gr.minimumPressDuration = GXK_PUNCT_HOLD_DELAY;
    gr.allowableMovement = 24.0;
    // 只有长按被识别才取消这一格的触摸链；普通点击时识别失败，触摸原样下发给键。
    gr.cancelsTouchesInView = YES;
    gr.delaysTouchesBegan = NO;
    gr.delaysTouchesEnded = NO;
    [key addGestureRecognizer:gr];
    objc_setAssociatedObject(key, GXK_PUNCT_ASSOC_KEY, gr, OBJC_ASSOCIATION_RETAIN_NONATOMIC);
    gPunctGesture = gr;
    gPunctKey = key;
    gPunctRoot = root;
    gPunctPage = GXKPunctPageForKey(key); // 挂手势时就定页，长按那一拍不用再判
    // [DIAG-punct] 手势真的挂上了没有：UI 交互开关、已有手势数、可见性、九键体。
    gDiagAttach++;
    CGRect r = [key convertRect:key.bounds toView:root];
    GXKPunctDiagLog(@"att ident=%@ label=%@ cls=%@ f=(%.0f,%.0f,%.0f,%.0f) uie=%d ges=%lu inBody=%d vis=%d",
                    key.restorationIdentifier ?: @"nil", GXKPunctKeyLabelText(key) ?: @"nil",
                    NSStringFromClass(key.class),
                    r.origin.x, r.origin.y, r.size.width, r.size.height,
                    (int)key.userInteractionEnabled, (unsigned long)key.gestureRecognizers.count,
                    GXKNineKeyBodyForKey(key, root) != nil, (int)GXKKeyIsVisible(key, root));
}

// 布局拍里调用：至多一次全树定位，键没变时只做一次指针比较。
static void GXKPunctPopupUpdate(UIViewController *vc) {
    if (!vc || vc != gCurrentVC || !vc.isViewLoaded) return;
    UIView *root = vc.view;
    GXKPunctDiagAttachHud(root); // [DIAG-punct] HUD 常驻，每拍校准一次
    GXKPunctDiagHud();
    // 常数级快路径：上一帧的键仍然在同一次布局里、仍然可见、手势还在，就不扫全树。
    UIView *key = gPunctKey;
    if (key && gPunctRoot == root && key.window == root.window && !key.isHidden && key.alpha > 0.05 &&
        GXKPunctKeyMatches(key) &&
        [key isDescendantOfView:root] && GXKKeyIsVisible(key, root) &&
        objc_getAssociatedObject(key, GXK_PUNCT_ASSOC_KEY)) {
        if (gPunctPanel && gPunctPanel.superview != root) [root addSubview:gPunctPanel];
        // 同一格在两页之间切换时 ident 不变、手势也不用重挂，只有符号表要换。
        GXKPunctPage page = GXKPunctPageForKey(key);
        if (page != gPunctPage) {
            gPunctPage = page;
            if (gPunctPanel) GXKPunctSyncCells(GXKPunctCandidatesForPage(page));
        }
        // 弹层正显示时键盘可能因旋转/高度变化重排，跟着键走一次；隐藏时零成本。
        if (gPunctPanel && !gPunctPanel.hidden) {
            GXKPunctLayoutPanel();
            [root bringSubviewToFront:gPunctPanel];
        }
        gDiagFast++; // [DIAG-punct] 快路径仍指向同一个键：手势应当仍在
        return;
    }
    UIView *found = GXKPunctFindKey(root);
    if (!found) {
        // [DIAG-punct] 只记状态变化，避免每帧刷屏。
        if (gPunctKey) GXKPunctDiagLog(@"det no-key (was %@ label=%@)",
                                      gPunctKey.restorationIdentifier ?: @"nil",
                                      GXKPunctKeyLabelText(gPunctKey) ?: @"nil");
        GXKPunctDetach();
        return;
    }
    if (gPunctKey == found) {
        // 键没换，只是这一拍没走快路径：手势已经在键上，重建等于白删白挂一次。
        if (gPunctPanel && gPunctPanel.superview != root) [root addSubview:gPunctPanel];
        return;
    }
    GXKPunctDiagLog(@"hit new key %@ label=%@", found.restorationIdentifier ?: @"nil",
                    GXKPunctKeyLabelText(found) ?: @"nil");
    GXKPunctDetach();
    GXKPunctAttach(found, root);
    if (gPunctPanel && gPunctPanel.superview != root) [root addSubview:gPunctPanel];
}

static void GXKPunctPopupTeardown(void) {
    GXKPunctDetach();
}

#endif  // GXK_PUNCT_POPUP_H
