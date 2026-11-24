#!/usr/bin/env python3
"""「标点长按弹层」符号表与配色的静态契约。

本机没有 clang，真机行为靠 GitHub Actions 编译后再验；这里锁住几条硬约束：
默认表与旧版一致、个数越界有界、跨进程只走 App Group、符号表没变不重建格子、
配色跟键盘皮肤而不是系统外观、编辑器走全屏 modal、设置行按 key 认不被常用语行吞掉。
"""
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SOURCE = ROOT / "dylib" / "gkx.m"
POPUP = ROOT / "dylib" / "punct_popup.h"

DEFAULT_SYMBOLS = ["，", "。", "？", "！", "、", "；", "：", "…", "“", "”"]


def function_body(source: str, signature: str) -> str:
    """Locate a definition, skipping earlier forward declarations of the same name."""
    search = 0
    while True:
        start = source.index(signature, search)
        brace = source.index("{", start)
        semi = source.find(";", start, brace)
        if semi == -1:
            break  # 找到了函数定义，不是前置声明。
        search = semi + 1
    depth = 0
    for index in range(brace, len(source)):
        char = source[index]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return source[brace:index + 1]
    raise AssertionError("unbalanced braces after " + signature)


class PunctSettingsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = SOURCE.read_text(encoding="utf-8")
        cls.popup = POPUP.read_text(encoding="utf-8")

    def test_default_table_matches_the_old_build(self) -> None:
        # 没改过设置时弹层必须和旧版逐字一致，否则等于偷偷改了用户的手感。
        body = function_body(self.popup, "static NSArray<NSString *> *GXKPunctDefaultSymbols(void)")
        listed = body[body.index("@["):body.index("];")]
        for symbol in DEFAULT_SYMBOLS:
            self.assertIn('@"' + symbol + '"', listed)
        self.assertEqual(listed.count('@"'), len(DEFAULT_SYMBOLS))
        self.assertIn("GXK_PUNCT_MAX_SYMBOLS  10", self.popup)

    def test_count_is_clamped(self) -> None:
        body = function_body(self.popup,
                             "static NSInteger GXKPunctSymbolCountForPage(GXKPunctPage page)")
        self.assertIn("integerForKey:GXKPunctCountKey(page)", body)
        # 没设过或写了非正数：回退全显示（旧行为）；超过上限：截到上限。
        self.assertIn("n = GXK_PUNCT_MAX_SYMBOLS", body)
        self.assertIn("if (n > GXK_PUNCT_MAX_SYMBOLS)", body)

    def test_page_is_told_apart_by_the_native_key_definition(self) -> None:
        # 数字页键没有 ident/caption；精确 id_p 决定数字表，拼音固定键位不变。
        reader = function_body(self.popup, "static NSString *GXKPunctKeyDefinitionID(UIView *key)")
        self.assertIn("softKeyDef", reader)
        self.assertIn("@selector(id_p)", reader)
        self.assertIn(".id_p", reader)
        self.assertNotIn("description", reader)
        body = function_body(self.popup, "static GXKPunctPage GXKPunctPageForKey(UIView *key)")
        self.assertIn("GXKPunctKeyDefinitionID(key)", body)
        self.assertIn("GXK_PUNCT_DIGIT_KEY_DEF", body)
        self.assertIn("GXKPunctPageDigit : GXKPunctPagePinyin", body)
        self.assertNotIn("text.length", body)
        self.assertNotIn("return gPunctPage", body)

    def test_digit_key_is_recognised_without_a_caption_or_identifier(self) -> None:
        body = function_body(self.popup, "static BOOL GXKPunctKeyMatches(UIView *key)")
        self.assertIn("GXKPunctKeyDefinitionID(key)", body)
        self.assertIn("GXK_PUNCT_DIGIT_KEY_DEF", body)
        self.assertIn("key.restorationIdentifier isEqualToString:GXK_PUNCT_KEY_IDENT", body)
        self.assertIn('@"softkey_9keys_punctuation_candidates"', self.popup)
        self.assertNotIn("GXKPunctKeyLabelText", self.popup)
        self.assertNotIn('rangeOfString:@"punctuation"', self.popup)
        find = function_body(self.popup, "static UIView *GXKPunctFindKey(UIView *root) {")
        self.assertIn("if (GXKPunctKeyMatches(v)) {", find)
        self.assertIn("GXKNineKeyBodyForKey(v, root)", find)
        self.assertIn("GXKKeyIsVisible(v, root)", find)
        update = function_body(self.popup, "static void GXKPunctPopupUpdate(UIViewController *vc) {")
        self.assertIn("GXKPunctKeyMatches(key) &&", update)

    def test_digit_page_does_not_share_symbol_page_identity_or_return(self) -> None:
        pages = (ROOT / "dylib" / "keyboard_page_identity.h").read_text(encoding="utf-8")
        symbol = (ROOT / "dylib" / "symbol_doubletap.h").read_text(encoding="utf-8")
        classifier = function_body(pages, "static GXKNineKeyPage GXKNineKeyPageForLayoutName(")
        self.assertIn('@"keyboard_body_pinyin_9key_digit"', classifier)
        self.assertIn('@"keyboard_body_pinyin_9key_symbol"', classifier)
        self.assertNotIn("containsString", classifier)
        create = function_body(pages, "static void GXKKeyboardHelperCreateView(")
        self.assertLess(create.index("gOrigKeyboardHelperCreateView(self, _cmd)"),
                        create.index('GXKKeyboardHelperObject(self, "_currentLayoutName")'))
        self.assertIn("NSHashTable weakObjectsHashTable", create)
        discard = function_body(pages, "static void GXKKeyboardHelperDiscardView(")
        self.assertLess(discard.index('GXKKeyboardHelperObject(self, "_view")'),
                        discard.index("gOrigKeyboardHelperDiscardView(self, _cmd)"))
        view_page = function_body(symbol, "static BOOL GXKSymbolViewIsOnSymbolPage(")
        self.assertIn("GXKNineKeyPageForView(view) == GXKNineKeyPageSymbol", view_page)
        self.assertNotIn("restorationIdentifier", view_page)
        for signature in ("static BOOL GXKSymbolShouldReturnToPrime(",
                          "static BOOL GXKZhSymbolShouldReturnToPrime("):
            gate = function_body(symbol, signature)
            self.assertIn("if (GXKNineKeyDigitPageActive() || GXKSymbolPageActive()) return NO;", gate)
        self.assertIn("gOrigZhSymbolShouldReturnToPrime(self, _cmd, key)", symbol)
        schedule = function_body(symbol, "static void GXKSymbolScheduleReturn(")
        self.assertIn("originBody == GXKSymbolHost()", schedule)
        self.assertIn("generation != gSymbolReturnGeneration", schedule)
        self.assertNotIn("gSymbolPairToken", schedule)
        self.assertIn("GXKSymbolInvalidatePageCache()", create)

    def test_digit_page_has_its_own_ascii_table(self) -> None:
        # 数字页那一格键帽印的是 ASCII ",.;"，弹全角中文标点会和键帽对不上，
        # 所以两页默认表必须不同：拼音页中文、数字页纯 ASCII。
        body = function_body(self.popup,
                             "static NSArray<NSString *> *GXKPunctDigitDefaultSymbols(void)")
        listed = body[body.index("@["):body.index("];")]
        self.assertEqual(listed.count('@"'), 10)
        for symbol in [",", ".", ";", ":", "?", "!", "~", "-", "_", "'"]:
            self.assertIn('@"' + symbol + '"', listed)
        for symbol in DEFAULT_SYMBOLS:
            self.assertNotIn('@"' + symbol + '"', listed)
        picker = function_body(self.popup,
                               "static NSArray<NSString *> *GXKPunctDefaultForPage(GXKPunctPage page)")
        self.assertIn("GXKPunctPageDigit ? GXKPunctDigitDefaultSymbols()", picker)

    def test_the_two_pages_never_share_settings_keys(self) -> None:
        # 改数字页不能动到拼音页，反之亦然：两页的键名必须完全不相交。
        symbols_key = function_body(self.popup,
                                    "static NSString *GXKPunctSymbolsKey(GXKPunctPage page)")
        count_key = function_body(self.popup,
                                  "static NSString *GXKPunctCountKey(GXKPunctPage page)")
        self.assertIn("GXKPunctPageDigit ? GXK_PUNCT_DIGIT_SYMBOLS_KEY : GXK_PUNCT_SYMBOLS_KEY",
                      symbols_key)
        self.assertIn("GXKPunctPageDigit ? GXK_PUNCT_DIGIT_COUNT_KEY : GXK_PUNCT_COUNT_KEY", count_key)
        self.assertIn('@"GXKPunctDigitSymbols"', self.popup)
        self.assertIn('@"GXKPunctDigitCount"', self.popup)
        # 复位只删本页两个键，不能顺手把另一页也清掉。
        reset = function_body(self.popup, "static void GXKPunctResetSettings(GXKPunctPage page)")
        self.assertIn("removeObjectForKey:GXKPunctSymbolsKey(page)", reset)
        self.assertIn("removeObjectForKey:GXKPunctCountKey(page)", reset)

    def test_settings_live_in_app_group(self) -> None:
        defaults = function_body(self.popup, "static NSUserDefaults *GXKPunctDefaults(void)")
        self.assertIn("initWithSuiteName:GXKGroup", defaults)
        save = function_body(self.popup, "static void GXKPunctSaveSettings(")
        self.assertIn("forKey:GXKPunctSymbolsKey(page)", save)
        self.assertIn("forKey:GXKPunctCountKey(page)", save)
        self.assertIn("synchronize", save)  # 主 App 写、键盘读，必须立刻可见。
        reset = function_body(self.popup, "static void GXKPunctResetSettings(")
        self.assertIn("removeObjectForKey:GXKPunctSymbolsKey(page)", reset)
        self.assertIn("removeObjectForKey:GXKPunctCountKey(page)", reset)

    def test_candidates_reuse_identity_until_content_changes(self) -> None:
        # 调用方靠指针比较决定要不要重建格子，所以内容没变就不能换对象。
        body = function_body(self.popup,
                             "static NSArray<NSString *> *GXKPunctCandidatesForPage(GXKPunctPage page)")
        self.assertIn("CACurrentMediaTime", body)
        self.assertIn("0.5", body)
        self.assertIn("isEqualToArray", body)

    def test_cells_are_rebuilt_only_when_the_table_changes(self) -> None:
        body = function_body(self.popup, "static void GXKPunctSyncCells(")
        self.assertIn("items == gPunctSymbolsInUse", body)
        self.assertIn("removeFromSuperview", body)
        build = function_body(self.popup, "static void GXKPunctBuildPanelIfNeeded(void)")
        self.assertLess(build.index("GXKPunctRefreshTheme()"), build.index("GXKPunctSyncCells("))
        self.assertIn("GXKPunctApplyTheme()", build)
        # 弹层是自家视图，不能被工具条当成原生遮挡物。
        self.assertIn("GXKToolbarOwnViewRegister(panel)", build)

    def test_colors_follow_the_keyboard_skin_not_the_system(self) -> None:
        theme = function_body(self.popup, "static void GXKPunctRefreshTheme(void)")
        self.assertIn("GXKPhraseSkinColor(", theme)
        self.assertIn("GXKPhrasePrefersDark(", theme)
        self.assertIn("GXKToolbarTextStyle(", theme)
        apply = function_body(self.popup, "static void GXKPunctApplyTheme(void)")
        self.assertIn("GXKPunctPanelColor()", apply)
        self.assertIn("GXKPunctTextColor()", apply)
        highlight = function_body(self.popup, "static UIColor *GXKPunctHighlightColor(void)")
        self.assertIn("gPunctDark ? 1.0 : 0.0", highlight)
        self.assertIn("0.14", highlight)
        # 皮肤可以和系统深浅模式不一致，弹层不许读系统外观。
        self.assertNotIn("userInterfaceStyle", self.popup)
        self.assertNotIn("UIUserInterfaceStyle", self.popup)

    def test_editor_is_presented_not_pushed(self) -> None:
        body = function_body(self.source, "static void GXKPresentPunctEditor(")
        self.assertIn("UIModalPresentationFullScreen", body)
        self.assertNotIn("pushViewController", body)
        # 行标题带格数，改完就地刷新（按页取标题，两行各刷各的）。
        self.assertIn("GXKPunctRowTitle(page)", body)

    def test_row_is_recognised_by_key_only(self) -> None:
        ours = function_body(self.source, "static BOOL GXKKeyIsOurs(NSString *key)")
        self.assertIn("GXKPunctRowKey", ours)
        punct = function_body(self.source, "static BOOL GXKIsPunctRowSelected(")
        # 判定函数按 key 参数比对，两页各传自己的 key；不能靠标题文字。
        self.assertIn("isEqualToString:rowKey", punct)
        self.assertIn("GXKPunctDigitRowKey", ours)
        phrases = function_body(self.source, "static BOOL GXKIsPhrasesRowSelected(")
        # 常用语行不能把标点弹层行一起吞掉。
        self.assertIn("[key isEqualToString:GXKPhrasesRowKey]", phrases)
        self.assertIn("if (key) return NO;", phrases)
        inject = function_body(self.source, "static void GXKInjectPhrasesRow(")
        self.assertIn("GXKPunctSettingsRow(", inject)
        self.assertIn("hasPunct", inject)
        self.assertIn("rows.count + 4", inject)  # 常用语 + 拼音页弹层 + 数字页弹层 + 诊断日志
        pick = function_body(self.source, "static void gxk_settingsPageDidSelect(")
        self.assertIn("GXKIsPunctRowSelected", pick)
        self.assertIn("GXKPresentPunctEditor(", pick)

    def test_editor_writes_back_on_every_change(self) -> None:
        editor = self.source[self.source.index("@implementation GXKPunctEditorController"):
                              self.source.index("@end", self.source.index("@implementation GXKPunctEditorController"))]
        self.assertIn("GXKPunctSaveSettings(self.page, self.symbols, self.count)", editor)
        self.assertIn("GXKPunctResetSettings(self.page)", editor)
        self.assertIn("canEditRowAtIndexPath", editor)
        self.assertIn("GXK_PUNCT_MAX_SYMBOLS", editor)


if __name__ == "__main__":
    unittest.main()
