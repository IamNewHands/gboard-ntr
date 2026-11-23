"""Read-only assertions against the original Gboard 2.3.19 NIBs.

This validates shipped identities/templates, not UIKit behavior or a new IPA.
Run: python tests/test_native_resources.py
Override the default original IPA with GXK_TEST_IPA when necessary.
"""
import hashlib
import os
import struct
import unittest
import zipfile
from pathlib import Path
import importlib.util
import io
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def _default_ipa():
    for candidate in (ROOT.parent / "ipa" / "Gboard_2.3.19.ipa", ROOT.parent / "Gboard_2.3.19.ipa"):
        if candidate.is_file():
            return candidate
    return ROOT.parent / "ipa" / "Gboard_2.3.19.ipa"


IPA = Path(os.environ.get("GXK_TEST_IPA", str(_default_ipa())))
BUNDLE = "Payload/Gboard.app/PlugIns/Gboard.appex/GKBKeyboardResources.bundle/"
EMOJI = "key_pos_9keys_emoji"
RETURN = "key_pos_9keys_return"


def varint(raw, pos):
    value = 0
    for shift in range(0, 70, 7):
        byte = raw[pos]
        pos += 1
        value |= (byte & 127) << shift
        if byte & 128:
            return value, pos
    raise ValueError("Unterminated NIBArchive varint")


class NibArchive:
    """Bounded decoder for the typed tables present in the pinned NIB fixtures."""
    def __init__(self, raw):
        if not raw.startswith(b"NIBArchive"):
            raise ValueError("Expected NIBArchive")
        version, coder, nobj, pobj, nkey, pkey, nval, pval, nclass, pclass = struct.unpack_from("<10I", raw, 10)
        if (version, coder) != (1, 10):
            raise ValueError("Unsupported NIBArchive version/coder")
        if not all(50 <= pos < len(raw) for pos in (pobj, pkey, pval, pclass)):
            raise ValueError("Invalid NIBArchive table offset")
        if max(nobj, nkey, nval, nclass) > 10000:
            raise ValueError("Fixture table exceeds decoder bound")
        keys, pos = [], pkey
        for _ in range(nkey):
            size, pos = varint(raw, pos)
            keys.append(raw[pos:pos + size].decode("utf-8"))
            pos += size
        classes, pos = [], pclass
        for _ in range(nclass):
            size, pos = varint(raw, pos)
            extra, pos = varint(raw, pos)
            pos += extra * 4
            classes.append(raw[pos:pos + size].rstrip(b"\0").decode("utf-8"))
            pos += size
        values, pos = [], pval
        formats = {0: "<b", 1: "<h", 2: "<i", 3: "<q", 6: "<f", 7: "<d"}
        for _ in range(nval):
            key, pos = varint(raw, pos)
            kind, pos = raw[pos], pos + 1
            if kind in formats:
                fmt = formats[kind]
                value = struct.unpack_from(fmt, raw, pos)[0]
                pos += struct.calcsize(fmt)
            elif kind in (4, 5, 9):
                value = {4: True, 5: False, 9: None}[kind]
            elif kind == 8:
                size, pos = varint(raw, pos)
                value = raw[pos:pos + size]
                pos += size
            elif kind == 10:
                value = ("ref", struct.unpack_from("<I", raw, pos)[0])
                pos += 4
            else:
                raise ValueError(f"Unsupported NIB value kind {kind}")
            values.append((keys[key], value))
        self.objects, pos = [], pobj
        for _ in range(nobj):
            cls, pos = varint(raw, pos)
            first, pos = varint(raw, pos)
            count, pos = varint(raw, pos)
            if cls >= nclass or first + count > nval:
                raise ValueError("Invalid NIBArchive object range")
            self.objects.append((classes[cls], dict(values[first:first + count])))

    def fields(self, index):
        return self.objects[index][1]

    def resolve(self, value):
        if isinstance(value, tuple) and value[0] == "ref":
            cls, fields = self.objects[value[1]]
            if cls == "NSString":
                return fields["NS.bytes"].decode("utf-8")
            return fields
        return value

    def named_views(self):
        return {self.resolve(fields.get("UIRestorationIdentifier")): (index, self.resolve(fields.get("UIClassName")))
                for index, (cls, fields) in enumerate(self.objects)
                if cls == "UIClassSwapper" and fields.get("UIRestorationIdentifier")}

    def runtime_attributes(self):
        return {self.resolve(fields["UIKeyPath"]): self.resolve(fields["UIValue"])
                for cls, fields in self.objects if cls == "UINibKeyValuePair"}


@unittest.skipUnless(IPA.is_file(), "Original IPA is absent; set GXK_TEST_IPA")
class OriginalNativeResources(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.archive = zipfile.ZipFile(IPA, "r")

    @classmethod
    def tearDownClass(cls):
        cls.archive.close()

    def nib(self, filename, expected_sha):
        raw = self.archive.read(BUNDLE + filename)
        self.assertEqual(hashlib.sha256(raw).hexdigest(), expected_sha, filename)
        return NibArchive(raw)

    def assert_key_pair(self, nib):
        views = nib.named_views()
        self.assertEqual(views[EMOJI][1], "GKBSoftKeyView")
        self.assertEqual(views[RETURN][1], "GKBSoftKeyView")
        self.assertNotEqual(views[EMOJI][0], views[RETURN][0])

    def test_nine_key_root_and_inner_emoji_return_are_distinct(self):
        body = self.nib("keyboard_body_pinyin_ninekeys.nib", "b266d4f19418525af7f02c9d4b825d6cd979ae0fccdf76c3ae9e062a84cd0fe2")
        self.assertEqual(body.resolve(body.fields(6)["UIClassName"]), "GKB9KeysSoftKeyboardView")
        inner = self.nib("keyboard_pinyin_ninekeys.nib", "52df512c47ff33d683a4a8950bbb01182a4de08a9872a6676981362e8ba6995b")
        self.assert_key_pair(inner)

    def test_nine_key_123_uses_same_exact_emoji_id(self):
        nib = self.nib("keyboard_body_pinyin_9key_digit.nib", "69e7c387ab0f7c38910ff8026c1637fa76354073f0549dc5589f033fa8428d69")
        self.assertEqual(nib.resolve(nib.fields(6)["UIClassName"]), "GKB9KeysSoftKeyboardView")
        self.assert_key_pair(nib)

    def test_nine_key_symbols_use_same_exact_emoji_id(self):
        nib = self.nib("keyboard_body_pinyin_9key_symbol.nib", "d62b38a9e43d8878dcb2305b48e4370cdc71e7abb357dd269bd8aefdeaa377ec")
        self.assertEqual(nib.resolve(nib.fields(6)["UIClassName"]), "GKB9KeysSoftKeyboardView")
        self.assert_key_pair(nib)

    def test_qwerty_and_qwerty_symbols_are_not_nine_key_roots(self):
        fixtures = {
            "keyboard_body_pinyin.nib": "97bb10f1ae3618e259beef383a5c2ca45a3cc558cc2a5bcd70dc83ee823ca35e",
            "keyboard_symbol_body_pinyin.nib": "9f0050971072abe3b2dabe1e092989562de8e9f07f944e61d735e73781564a92",
        }
        for filename, sha in fixtures.items():
            with self.subTest(filename=filename):
                nib = self.nib(filename, sha)
                self.assertEqual(nib.resolve(nib.fields(6)["UIClassName"]), "GKBZhQwertySoftKeyboardView")
                self.assertNotIn(EMOJI, nib.named_views())

    def test_icon_is_native_uiview_with_separate_background_layer(self):
        nib = self.nib("softkey_9keys_icon.nib", "215a944ec8c2f7de3f79ba07150cef4ce032c6a1ad96cad6882aeea151ccee88")
        self.assertEqual(nib.named_views()["image"][1], "GKBImageViewWithBackground")
        self.assertEqual(nib.resolve(nib.fields(6)["UIOriginalClassName"]), "UIView")
        attributes = nib.runtime_attributes()
        self.assertEqual(attributes["themeTag"], "9keys_icon")
        for name in ("foregroundColor", "backgroundLayer.bgColor", "backgroundLayer.highlightedBgColor", "backgroundLayer.borderWidth"):
            self.assertIn(name, attributes)
        for component, expected in zip(("UIRed", "UIGreen", "UIBlue"), (68 / 255, 74 / 255, 82 / 255)):
            self.assertAlmostEqual(attributes["foregroundColor"][component], expected, places=6)
        self.assertEqual(attributes["backgroundLayer.borderWidth"]["NS.dblval"], 0.25)

    def test_fallback_font_matches_shipped_native_label(self):
        nib = self.nib("softkey_9keys_label_blue.nib", "7fe5a55fe8d9b31bba7a9b1bddf80e125acbcd083493ecfe796fcc223cc43a6a")
        label = nib.fields(nib.named_views()["label"][0])
        font = nib.resolve(label["UIFont"])
        self.assertEqual(nib.resolve(font["UIFontName"]), "Roboto-Regular")
        self.assertEqual(font["UIFontPointSize"], 16.0)


    def native_macho(self):
        """Reuse the repository's format-aware probe over original ZIP bytes.

        No extracted fixture, live process, emulator, or disassembler is involved.
        The in-memory open shim supplies the exact bytes to MachO's existing reader.
        """
        raw = self.archive.read("Payload/Gboard.app/PlugIns/Gboard.appex/Gboard")
        self.assertEqual(hashlib.sha256(raw).hexdigest(),
                         "711bc3dbeaec7cce6551d48286a7e5322b460e78aaaafa580e2ccd7fafb86566")
        spec = importlib.util.spec_from_file_location("gxk_objc_probe", ROOT / "tools/objc_probe.py")
        probe = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(probe)
        with patch("builtins.open", return_value=io.BytesIO(raw)):
            return probe.MachO("original-appex-in-memory")

    def native_imp(self, macho, class_name, selector):
        """Resolve a pinned class-local, absolute Objective-C method entry."""
        for section in ("__DATA_CONST,__objc_classlist", "__DATA,__objc_classlist"):
            if section not in macho.segs:
                continue
            _, size, offset = macho.segs[section]
            for index in range(size // 8):
                cls = struct.unpack_from("<Q", macho.d, offset + index * 8)[0]
                if not cls:
                    continue
                ro = macho.u64(cls + 32) & ~7
                if macho.cstr(macho.u64(ro + 24)) != class_name:
                    continue
                methods = macho.u64(ro + 32)
                flags, count = macho.u32(methods), macho.u32(methods + 4)
                self.assertFalse(flags & 0x80000000, "Pinned fixture changed to relative methods")
                entry_size = flags & 0xFFFF
                self.assertEqual(entry_size, 24, "Pinned arm64 absolute method layout changed")
                self.assertLess(count, 500)
                for method in range(count):
                    entry = methods + 8 + method * entry_size
                    if macho.cstr(macho.u64(entry)) == selector:
                        return macho.u64(entry + 16)
        self.fail(f"Missing pinned class-local method: -[{class_name} {selector}]")

    def test_native_image_layer_action_for_key_is_constant_nil_not_a_fade(self):
        """A selector's existence does not prove implicit animation.

        These are the complete pinned function's two ARM64 instructions:
        mov x0,#0; ret. This rejects the old 'actionForKey exists => fades' claim,
        not every possible animation in the actual Gboard presentation tree.
        """
        macho = self.native_macho()
        self.assertEqual(dict(macho.classes()["GKBImageLayer"][0])["actionForKey:"], "@24@0:8@16")
        imp = self.native_imp(macho, "GKBImageLayer", "actionForKey:")
        self.assertEqual(imp, 0x100295D50)
        offset = macho.vm2off(imp)
        self.assertIsNotNone(offset)
        self.assertEqual(macho.d[offset:offset + 8], bytes.fromhex("000080d2c0035fd6"))

    def test_native_key_update_and_model_setter_have_verified_void_abi(self):
        macho = self.native_macho()
        methods = dict(macho.classes()["GKBSoftKeyView"][0])
        self.assertEqual(methods["updateView"], "v16@0:8")
        self.assertEqual(methods["setSoftKeyDef:"], "v24@0:8@16")
        self.assertEqual(self.native_imp(macho, "GKBSoftKeyView", "updateView"), 0x10027CA3C)
        self.assertEqual(self.native_imp(macho, "GKBSoftKeyView", "setSoftKeyDef:"), 0x10027B944)


if __name__ == "__main__":
    unittest.main(verbosity=2)
