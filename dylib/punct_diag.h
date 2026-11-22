// [DIAG-punct] 一次性诊断包：定位「，。？」键长按无反应 + 成对补全不稳定。
//
// 交付形态：常驻 HUD（左上角小胶囊，点一下展开看日志，长按复制全文到剪贴板）
//          + 环形缓冲 300 行。之所以不用 Console.app：agent.md 红线⑥，
//          用户只走「复制 → 粘贴回聊天」这一条验收通道。
//
// 为什么默认收起：展开的 HUD 会盖住候选行，成对补全的复现需要正常打字；
//          收起后只占 62x16，不挡任何按键，需要看时点一下。
//
// 开关：主 App「设置 → Gboard → 诊断日志」。关（默认）时本文件不建视图、不写环形缓冲，
//      GXKPunctDiagLog 在展开参数之前就 return，键盘侧零成本、屏幕上完全看不见。
//      开关值存 App Group（GXKDiagLogEnabled），主 App 写、键盘扩展读，跨进程立刻生效。
//
// 删除方式：删掉本文件，再 grep -n "DIAG-punct" dylib/ 去掉所有埋点即可，其余逻辑零改动。
#ifndef GXK_PUNCT_DIAG_H
#define GXK_PUNCT_DIAG_H

#define GXK_DIAG_RING       300
#define GXK_DIAG_HUD_LINES  7
#define GXK_DIAG_HUD_ROW_H  9.5

static NSMutableArray<NSString *> *gDiagRing;
static UILabel *gDiagLabel;
static __weak UIView *gDiagRoot;
static NSString *gDiagLastHud;
static NSTimeInterval gDiagT0;
static NSTimeInterval gDiagFreezeUntil;
static BOOL gDiagExpanded;
static NSUInteger gDiagAttach, gDiagDetach, gDiagFast, gDiagFindHit, gDiagFindMiss;
static NSUInteger gDiagFire, gDiagPairOk, gDiagPairTimeout, gDiagPairOffPage, gDiagPairGiveUp;

static NSString *GXKPunctDiagReport(void);

// 诊断开关：App Group 里主 App 写入的 BOOL，默认关。
// 每帧都会被问到，所以按 0.5 秒缓存一次；设置里刚改完的那一侧最多半秒后就同步。
static BOOL GXKPunctDiagEnabled(void) {
    static BOOL cached = NO;
    static NSTimeInterval cachedAt = 0;
    static BOOL primed = NO;
    NSTimeInterval now = CACurrentMediaTime();
    if (primed && now - cachedAt < 0.5) return cached;
    NSUserDefaults *defaults = [[NSUserDefaults alloc] initWithSuiteName:GXKGroup];
    if (!defaults) defaults = [NSUserDefaults standardUserDefaults];
    cached = [defaults boolForKey:@"GXKDiagLogEnabled"];
    cachedAt = now;
    primed = YES;
    return cached;
}

static void GXKPunctDiagLog(NSString *fmt, ...) {
    if (!fmt) return;
    if (!GXKPunctDiagEnabled()) return; // 关着就不分配、不拼串、不写环形缓冲。
    va_list ap;
    va_start(ap, fmt);
    NSString *body = [[NSString alloc] initWithFormat:fmt arguments:ap];
    va_end(ap);
    if (!gDiagRing) {
        gDiagRing = [NSMutableArray array];
        gDiagT0 = CACurrentMediaTime();
    }
    NSTimeInterval ms = (CACurrentMediaTime() - gDiagT0) * 1000.0;
    [gDiagRing addObject:[NSString stringWithFormat:@"%7.0f %@", ms, body]];
    while (gDiagRing.count > GXK_DIAG_RING) [gDiagRing removeObjectAtIndex:0];
}

static NSString *GXKPunctDiagTail(NSUInteger n) {
    if (!gDiagRing.count || !n) return @"";
    NSUInteger take = MIN(n, gDiagRing.count);
    return [[gDiagRing subarrayWithRange:NSMakeRange(gDiagRing.count - take, take)]
            componentsJoinedByString:@"\n"];
}

static void GXKPunctDiagApplyFrame(void) {
    UIView *root = gDiagRoot;
    if (!gDiagLabel || !root) return;
    CGFloat w = root.bounds.size.width;
    if (gDiagExpanded) {
        CGFloat h = GXK_DIAG_HUD_LINES * GXK_DIAG_HUD_ROW_H + 6.0;
        gDiagLabel.frame = CGRectMake(6.0, 2.0, MAX(140.0, w - 12.0), h);
    } else {
        gDiagLabel.frame = CGRectMake(6.0, 2.0, 62.0, 16.0);
    }
}

static void GXKPunctDiagHud(void) {
    if (!gDiagLabel) return;
    if (!GXKPunctDiagEnabled()) return;
    if (CACurrentMediaTime() < gDiagFreezeUntil) return;
    NSString *text = gDiagExpanded
        ? GXKPunctDiagTail(GXK_DIAG_HUD_LINES)
        : [NSString stringWithFormat:@"diag %lu", (unsigned long)gDiagRing.count];
    if ([text isEqualToString:gDiagLastHud ?: @""]) return;
    gDiagLastHud = text;
    gDiagLabel.text = text;
}

@interface GXKPunctDiagTarget : NSObject
- (void)onDiagTap:(UITapGestureRecognizer *)gr;
- (void)onDiagHold:(UILongPressGestureRecognizer *)gr;
@end

@implementation GXKPunctDiagTarget

- (void)onDiagTap:(UITapGestureRecognizer *)gr {
    if (gr.state != UIGestureRecognizerStateEnded) return;
    gDiagExpanded = !gDiagExpanded;
    if (gDiagLabel) {
        gDiagLabel.font = gDiagExpanded ? [UIFont fontWithName:@"Courier" size:8.0]
                                        : [UIFont systemFontOfSize:10.0];
        gDiagLabel.textAlignment = gDiagExpanded ? NSTextAlignmentLeft : NSTextAlignmentCenter;
    }
    gDiagLastHud = nil;
    GXKPunctDiagApplyFrame();
    GXKPunctDiagHud();
}

- (void)onDiagHold:(UILongPressGestureRecognizer *)gr {
    if (gr.state != UIGestureRecognizerStateBegan) return;
    NSString *report = GXKPunctDiagReport();
    if (report.length) [UIPasteboard generalPasteboard].string = report;
    gDiagFreezeUntil = CACurrentMediaTime() + 2.0;
    gDiagExpanded = YES;
    gDiagLastHud = nil;
    if (gDiagLabel) {
        gDiagLabel.font = [UIFont fontWithName:@"Courier" size:8.0];
        gDiagLabel.textAlignment = NSTextAlignmentLeft;
        gDiagLabel.text = [NSString stringWithFormat:@"已复制 %lu 行 → 粘贴回聊天",
                           (unsigned long)gDiagRing.count];
    }
    GXKPunctDiagApplyFrame();
}

@end

static GXKPunctDiagTarget *gDiagTarget;

static void GXKPunctDiagAttachHud(UIView *root) {
    if (!root) return;
    // 关着：已经建过的 HUD 撤走，之后也不再建。屏幕上不留任何痕迹。
    if (!GXKPunctDiagEnabled()) {
        if (gDiagLabel) {
            [gDiagLabel removeFromSuperview];
            gDiagLabel = nil;
            gDiagLastHud = nil;
        }
        gDiagRoot = nil;
        return;
    }
    gDiagRoot = root;
    if (!gDiagLabel) {
        UILabel *label = [[UILabel alloc] initWithFrame:CGRectZero];
        label.numberOfLines = GXK_DIAG_HUD_LINES;
        label.lineBreakMode = NSLineBreakByClipping;
        label.font = [UIFont systemFontOfSize:10.0];
        label.textColor = [UIColor whiteColor];
        label.backgroundColor = [UIColor colorWithWhite:0.0 alpha:0.62];
        label.textAlignment = NSTextAlignmentCenter;
        label.userInteractionEnabled = YES;
        label.layer.cornerRadius = 3.0;
        label.clipsToBounds = YES;
        if (!gDiagTarget) gDiagTarget = [[GXKPunctDiagTarget alloc] init];
        UITapGestureRecognizer *tap = [[UITapGestureRecognizer alloc] initWithTarget:gDiagTarget
                                                                             action:@selector(onDiagTap:)];
        [label addGestureRecognizer:tap];
        UILongPressGestureRecognizer *hold = [[UILongPressGestureRecognizer alloc] initWithTarget:gDiagTarget
                                                                                           action:@selector(onDiagHold:)];
        hold.minimumPressDuration = 0.5;
        [label addGestureRecognizer:hold];
        gDiagLabel = label;
        GXKToolbarOwnViewRegister(label); // HUD 压在 G 行上，不能算原生遮挡。
        gDiagLastHud = nil;
    }
    if (gDiagLabel.superview != root) [root addSubview:gDiagLabel];
    GXKPunctDiagApplyFrame();
    [root bringSubviewToFront:gDiagLabel];
}

static NSString *GXKPunctDiagReport(void) {
    NSMutableString *out = [NSMutableString string];
    [out appendFormat:@"GXK punct diag v2\niOS=%@ ring=%lu\n",
     [UIDevice currentDevice].systemVersion, (unsigned long)gDiagRing.count];
    [out appendFormat:@"counters attach=%lu detach=%lu fast=%lu findHit=%lu findMiss=%lu\n",
     (unsigned long)gDiagAttach, (unsigned long)gDiagDetach, (unsigned long)gDiagFast,
     (unsigned long)gDiagFindHit, (unsigned long)gDiagFindMiss];
    [out appendFormat:@"counters fire=%lu pairOk=%lu pairTimeout=%lu pairOffPage=%lu pairGiveUp=%lu\n",
     (unsigned long)gDiagFire, (unsigned long)gDiagPairOk, (unsigned long)gDiagPairTimeout,
     (unsigned long)gDiagPairOffPage, (unsigned long)gDiagPairGiveUp];
    [out appendString:@"legend: upd=layout beat find=key lookup att=gesture attach det=detach\n"
                       "lp=long-press state cmt=commit pair=pair completion retry\n"
                       "lang=language decision gd=native repaint grabbed grce=grace expired\n"];
    [out appendString:[gDiagRing componentsJoinedByString:@"\n"]];
    return out;
}

#endif  // GXK_PUNCT_DIAG_H
