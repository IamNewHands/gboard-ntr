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

    def test_page_is_told_apart_by_the_label_on_the_key(self) -> None:
        # 两页共用同一个 restorationIdentifier，唯一的区别是这一格印的字：
        # 拼音页一个字（「，」或英文系统下的 ","），数字页是 ",.;" 三个字符。
        # 不能用「首字符是否 ASCII」——英文系统下拼音页也是 ASCII，会误判成数字页。
        reader = function_body(self.popup, "static NSString *GXKPunctKeyLabelText(UIView *key)")
        self.assertIn('contents[@"label"]', reader)
        # 数字页那一格的键帽文字不在 idToViewDict 上，而在带 caption 的图片视图里，
        # 所以取字这一步必须认 caption / -text，不能只认 UILabel。
        self.assertIn('GXKPunctTextOfView(contents[@"label"])', reader)
        caption = function_body(self.popup, "static NSString *GXKPunctTextOfView(id view)")
        self.assertIn('valueForKey:@"captionLabel"', caption)
        self.assertIn("captionView != view", caption)  # 自引用会无限递归
        body = function_body(self.popup, "static GXKPunctPage GXKPunctPageForKey(UIView *key)")
        # 有 ident 就是拼音页，这一条不依赖能否读到字。
        self.assertIn("if (key.restorationIdentifier.length) return GXKPunctPagePinyin;", body)
        self.assertIn("GXKPunctKeyLabelText(key)", body)
        self.assertIn("text.length > 1 ? GXKPunctPageDigit : GXKPunctPagePinyin", body)
        self.assertNotIn("characterAtIndex:0", body)
        # 读不到字时保持上一次判定，不退回固定页——猜错会让数字页弹出中文表。
        self.assertIn("return gPunctPage;", body)

    def test_digit_key_is_recognised_without_a_restoration_identifier(self) -> None:
        # 真机日志：数字页 24 个可见软键只有 8 个带 ident，key_pos_9keys_4_1 不在其中，
        # 只按 ident 认必然每拍落空、手势从未挂上。有 ident 时仍只认 ident，
        # 没有 ident 才按键帽文字认，且文字必须是「多个标点字符」。
        body = function_body(self.popup, "static BOOL GXKPunctKeyMatches(UIView *key)")
        self.assertIn("if (ident.length) return [ident isEqualToString:GXK_PUNCT_KEY_IDENT];", body)
        # 先读键帽文字（便宜），读不出来才问 softKeyDef——真机上这一格的 caption
        # 可能整个用图绘制，文字那一路全空，只剩 def 还能证明它是哪一格。
        self.assertIn("if (GXKPunctLabelIsPunctCandidates(GXKPunctKeyLabelText(key))) return YES;", body)
        self.assertIn("return GXKPunctKeyDefIsPunctuation(key);", body)
        text = function_body(self.popup,
                             "static BOOL GXKPunctLabelIsPunctCandidates(NSString *text)")
        self.assertIn("text.length < 2 || text.length > 8", text)
        self.assertIn("GXKPunctCharIsPunct([text characterAtIndex:i])", text)
        # 必须「每个字符都是标点/符号」，而不是「不含字母数字」：
        # 后者会把「按键盘」「符号」这类汉字标签放进来，数字页不止一格命中，
        # find 会按布局不确定放弃，长按照样没反应。
        char = function_body(self.popup, "static BOOL GXKPunctCharIsPunct(unichar ch)")
        self.assertIn("[NSCharacterSet punctuationCharacterSet]", char)
        self.assertIn("[NSCharacterSet symbolCharacterSet]", char)
        # 数字键 0-9、空格「空格」、回车「换行」都不属于标点/符号，必须被排除。
        self.assertIn("return NO;", text)
        # def 判定会拼 -description 字符串，必须按键缓存，否则每帧几十次分配。
        # 缓存要连着 def 对象一起存：键体视图会被原生复用，切页后绑的是另一个 def。
        def_check = function_body(self.popup,
                                  "static BOOL GXKPunctKeyDefIsPunctuation(UIView *key)")
        self.assertIn("objc_getAssociatedObject", def_check)
        self.assertIn("cached[0] == def", def_check)
        self.assertIn("objc_setAssociatedObject", def_check)
        self.assertIn('rangeOfString:@"punctuation"', def_check)
        # 两处调用点都走同一个判定，不许再出现裸的 ident 比较。
        find = function_body(self.popup, "static UIView *GXKPunctFindKey(UIView *root) {")
        self.assertIn("if (GXKPunctKeyMatches(v)) {", find)
        self.assertNotIn("[ident isEqualToString:GXK_PUNCT_KEY_IDENT]", find)
        update = function_body(self.popup, "static void GXKPunctPopupUpdate(UIViewController *vc) {")
        self.assertIn("GXKPunctKeyMatches(key) &&", update)
        self.assertNotIn("[key.restorationIdentifier isEqualToString:GXK_PUNCT_KEY_IDENT]", update)

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
