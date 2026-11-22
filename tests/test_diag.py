#!/usr/bin/env python3
"""诊断开关的源码契约：默认不可见，开关在主 App 设置里。

两条硬约束：
1. 换行/动作键上不再挂任何诊断长按——那套探针（symbol_probe.h）整份删掉，
   但符号页识别本身是生产逻辑，必须留在 symbol_doubletap.h 里。
2. 标点诊断 HUD 只有主 App「设置 → 诊断日志」打开时才建视图、才写环形缓冲；
   关着时屏幕上完全看不见，键盘侧也不付任何成本。
"""
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
DY = ROOT / "dylib"


def function_body(source: str, signature: str) -> str:
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
    raise AssertionError("unbalanced braces for " + signature)


class DiagSwitchTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = (DY / "gkx.m").read_text(encoding="utf-8")
        cls.diag = (DY / "punct_diag.h").read_text(encoding="utf-8")
        cls.symbol = (DY / "symbol_doubletap.h").read_text(encoding="utf-8")

    def test_symbol_probe_is_gone(self) -> None:
        # 探针整份删除：文件不在，源码里也不再有调用点。
        self.assertFalse((DY / "symbol_probe.h").exists())
        for path in DY.glob("*.h"):
            text = path.read_text(encoding="utf-8")
            self.assertNotIn("GXKProbe", text, path.name)
        self.assertNotIn("symbol_probe.h", self.source)
        self.assertNotIn("GXKProbe", self.source)

    def test_symbol_page_lookup_survived_the_probe(self) -> None:
        # 符号页判定是生产路径（shouldReturnToPrimeOnKey: 靠它），不能随探针一起消失。
        body = function_body(self.symbol, "static UIView *GXKSymbolFindHost(")
        self.assertIn("GXK_SYMBOL_PAGE_IDENT", body)
        self.assertIn("CGRectIsEmpty", body)
        host = function_body(self.symbol, "static UIView *GXKSymbolHost(")
        self.assertIn("GXKSymbolFindHost(", host)

    def test_hud_is_off_unless_enabled(self) -> None:
        enabled = function_body(self.diag, "static BOOL GXKPunctDiagEnabled(")
        self.assertIn("initWithSuiteName:GXKGroup", enabled)
        self.assertIn('@"GXKDiagLogEnabled"', enabled)
        # 三处入口都要先问开关：写日志、刷 HUD、挂 HUD。
        log = function_body(self.diag, "static void GXKPunctDiagLog(")
        self.assertIn("GXKPunctDiagEnabled()", log)
        self.assertLess(log.index("GXKPunctDiagEnabled()"), log.index("initWithFormat"))
        hud = function_body(self.diag, "static void GXKPunctDiagHud(")
        self.assertIn("GXKPunctDiagEnabled()", hud)
        attach = function_body(self.diag, "static void GXKPunctDiagAttachHud(")
        self.assertIn("GXKPunctDiagEnabled()", attach)
        self.assertIn("removeFromSuperview", attach)
        self.assertLess(attach.index("GXKPunctDiagEnabled()"), attach.index("UILabel alloc"))

    def test_toggle_updates_the_row_without_reloading_the_page(self) -> None:
        """点一下就要看到新状态：只重载那一格，不许 reloadData 把整页重建。"""
        toggle = function_body(self.source, "static void GXKToggleDiagLog(")
        self.assertIn("reloadItemsAtIndexPaths:", toggle)
        self.assertNotIn("reloadData", toggle)
        # 行对象和屏幕上的 cell 未必是同一个，两条路都要写标题。
        self.assertIn("GXKRelabelDiagViews(", toggle)
        self.assertIn("cellForItemAtIndexPath:", toggle)
        self.assertLess(toggle.index("setBool:enabled forKey:"), toggle.index("reloadItemsAtIndexPaths:"))
        relabel = function_body(self.source, "static void GXKRelabelDiagViews(")
        self.assertIn('hasPrefix:@"诊断日志"', relabel)

    def test_settings_switch_writes_app_group(self) -> None:
        row = function_body(self.source, "static id GXKDiagSettingsRow(")
        self.assertIn("initWithType:settingID:title:accessibilityIdentifier:key:", row)
        self.assertIn("GKBSettingsItem", row)
        self.assertIn("GXKDiagRowTitle()", row)
        title = function_body(self.source, "static NSString *GXKDiagRowTitle(")
        self.assertIn('@"诊断日志（开）"', title)
        self.assertIn('@"诊断日志（关）"', title)
        toggle = function_body(self.source, "static void GXKToggleDiagLog(")
        self.assertIn("initWithSuiteName:GXKGroup", toggle)
        self.assertIn("GXKDiagLogKey", toggle)
        self.assertIn("synchronize", toggle)
        pick = function_body(self.source, "static void gxk_settingsPageDidSelect(")
        self.assertIn("GXKIsDiagRowSelected", pick)
        self.assertIn("GXKToggleDiagLog(", pick)
        self.assertIn("gOrigSettingsPageDidSelect", pick)
        inject = function_body(self.source, "static void GXKInjectPhrasesRow(")
        self.assertIn("GXKDiagSettingsRow(", inject)
        self.assertIn("insertObjects:ours", inject)

    def test_language_decision_prefers_gboard_language_object(self) -> None:
        # 根因：扩展 Info.plist 的 PrimaryLanguage 是 "mul"，宿主语言永远不是 zh/en，
        # 所以中英判据必须改问 Gboard 自己的 GKBLanguageID，宿主语言只作兜底。
        probe = function_body(self.source, "static NSInteger GXKLangReflectedState(")
        self.assertIn('NSClassFromString(@"GKBLanguageID")', probe)
        self.assertIn("@selector(currentLanguage)", probe)
        self.assertIn("@selector(isChinese)", probe)
        decide = function_body(self.source, "static BOOL GXKLangCurrentIsChinese(")
        self.assertLess(decide.index("GXKLangReflectedState()"),
                        decide.index("GXKLangCurrentLanguage(vc)"))
        self.assertIn('hasPrefix:@"zh"', decide)

    def test_flash_instrumentation_stays_behind_the_switch(self) -> None:
        # 闪烁埋点只在开关打开时写缓冲，且每条都走 GXKPunctDiagLog（关态立即 return）。
        for signature, token in (
            ("static void GXKExpireFlashGraceIfNeeded(", '@"grce exp %@"'),
            ("static void GXKDetachActionKey(", '@"det emoji %@"'),
        ):
            body = function_body(self.source, signature)
            self.assertIn("GXKPunctDiagLog(", body)
            self.assertIn(token, body)
        guard = function_body(self.source, "static void gxk_key_updateView(")
        self.assertIn("GXKIsOverlayKey(key)", guard)
        self.assertIn('@"upd %@ own=%d grace=%d"', guard)
        # 守卫主体原有的判据顺序不能被埋点打乱。
        self.assertLess(guard.index("gxk_flash_grace_active(key)"),
                        guard.index("isEqualToString:GXKEmojiKeyID]"))
        # 原型必须早于第一次使用，否则 ARC 下会按隐式声明当成返回 id。
        self.assertLess(self.source.index("static void GXKPunctDiagLog(NSString *fmt, ...);"),
                        self.source.index("GXKPunctDiagLog(@"))

