#!/usr/bin/env python3
"""九键左列换序工具契约：只动两个 ID，其余字节逐字保留，且可重复执行。

不声称 UIKit 运行时行为——真机效果靠注入后的包验证；这里锁住几条硬约束：
    1. 只认三个已知 nib，用固定 SHA-256 区分「原包 / 已对调」，不猜方向；
    2. 替换等长，nib 总字节数不变，NIBArchive 仍能完整解析；
    3. 除这两个字符串以外没有任何字节变化；
    4. 对合：对调两次回到原包；对已对调的输入不写文件（CI 会重复跑）。

Run exactly this file:
    python tests/test_nib_left_column.py
"""
import hashlib
import importlib.util
import os
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _default_ipa():
    for candidate in (ROOT.parent / "ipa" / "Gboard_2.3.19.ipa", ROOT.parent / "Gboard_2.3.19.ipa"):
        if candidate.is_file():
            return candidate
    return ROOT.parent / "ipa" / "Gboard_2.3.19.ipa"


IPA = Path(os.environ.get("GXK_TEST_IPA", str(_default_ipa())))


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


nlc = _load("nib_left_column", ROOT / "tools" / "nib_left_column.py")
tnr = _load("test_native_resources", ROOT / "tests" / "test_native_resources.py")


class SwapToolContracts(unittest.TestCase):
    def test_targets_are_the_three_left_column_nibs(self):
        self.assertEqual(set(nlc.TARGET_NIBS), {
            "keyboard_pinyin_ninekeys.nib",
            "keyboard_body_pinyin_9key_digit.nib",
            "keyboard_body_pinyin_9key_symbol.nib",
        })
        # 等长是原地替换的前提：长度不等就会挪动 NIBArchive 的偏移。
        self.assertEqual(len(nlc.LEFT_3), len(nlc.LEFT_4))
        self.assertEqual(len(nlc.LEFT_3), len(nlc.PLACEHOLDER))

    def test_original_hashes_match_the_pinned_original_ipa(self):
        # 原包哈希是判方向的前提；它必须与 test_native_resources.py 钉的是同一份字节。
        pinned = {
            "keyboard_pinyin_ninekeys.nib": "52df512c47ff33d683a4a8950bbb01182a4de08a9872a6676981362e8ba6995b",
            "keyboard_body_pinyin_9key_digit.nib": "69e7c387ab0f7c38910ff8026c1637fa76354073f0549dc5589f033fa8428d69",
            "keyboard_body_pinyin_9key_symbol.nib": "d62b38a9e43d8878dcb2305b48e4370cdc71e7abb357dd269bd8aefdeaa377ec",
        }
        for name, digest in pinned.items():
            self.assertEqual(nlc.NIB_HASHES[name][0], digest)

    def test_rejects_ambiguous_input(self):
        with self.assertRaises(ValueError):
            nlc.swap_ids(b"key_pos_9keys_left_3")
        with self.assertRaises(ValueError):
            nlc.swap_ids(nlc.LEFT_3 + nlc.LEFT_3 + nlc.LEFT_4)

    def test_rejects_unknown_nib_bytes(self):
        with self.assertRaises(ValueError):
            nlc.nib_state("keyboard_pinyin_ninekeys.nib", b"not a nib")

    @unittest.skipUnless(IPA.is_file(), "Original IPA is absent; set GXK_TEST_IPA")
    def test_only_the_two_ids_change(self):
        archive = zipfile.ZipFile(IPA, "r")
        try:
            hits = [n for n in archive.namelist() if os.path.basename(n) in nlc.NIB_HASHES]
            self.assertEqual(len(hits), len(nlc.TARGET_NIBS))
            for name in hits:
                with self.subTest(nib=os.path.basename(name)):
                    raw = archive.read(name)
                    self.assertEqual(nlc.nib_state(os.path.basename(name), raw), "original")
                    swapped = nlc.swap_ids(raw)
                    self.assertEqual(len(swapped), len(raw))
                    self.assertEqual(nlc.swap_ids(swapped), raw)
                    # 对调后的字节必须命中钉住的哈希，否则 CI 幂等判断会失配。
                    self.assertEqual(hashlib.sha256(swapped).hexdigest(),
                                     nlc.NIB_HASHES[os.path.basename(name)][1])
                    self.assertEqual(nlc.nib_state(os.path.basename(name), swapped), "swapped")

                    before, after = tnr.NibArchive(raw), tnr.NibArchive(swapped)
                    self.assertEqual(len(before.objects), len(after.objects))
                    views_before, views_after = before.named_views(), after.named_views()
                    self.assertEqual(views_before["key_pos_9keys_left_3"][0],
                                     views_after["key_pos_9keys_left_4"][0])
                    self.assertEqual(views_before["key_pos_9keys_left_4"][0],
                                     views_after["key_pos_9keys_left_3"][0])
                    self.assertEqual(views_before["key_pos_9keys_left_3"][1], "GKBSoftKeyView")
                    self.assertEqual(views_after["key_pos_9keys_left_3"][1], "GKBSoftKeyView")

                    # 差异只能落在这两个字符串的 20 字节窗口里。
                    windows = []
                    for ident in (nlc.LEFT_3, nlc.LEFT_4):
                        start = 0
                        while True:
                            at = raw.find(ident, start)
                            if at < 0:
                                break
                            windows.append((at, at + len(ident)))
                            start = at + 1
                    for index, (left, right) in enumerate(zip(raw, swapped)):
                        if left != right:
                            self.assertTrue(any(lo <= index < hi for lo, hi in windows),
                                            "unexpected byte change at %d" % index)
        finally:
            archive.close()

    @unittest.skipUnless(IPA.is_file(), "Original IPA is absent; set GXK_TEST_IPA")
    def test_already_swapped_input_is_left_untouched(self):
        archive = zipfile.ZipFile(IPA, "r")
        try:
            swapped = {n: nlc.swap_ids(archive.read(n))
                       for n in archive.namelist() if os.path.basename(n) in nlc.NIB_HASHES}
        finally:
            archive.close()
        self.assertEqual(len(swapped), len(nlc.TARGET_NIBS))
        # 模拟第二次运行：每个 nib 都已是目标状态，不应再产生改写。
        for name, raw in swapped.items():
            self.assertEqual(nlc.nib_state(os.path.basename(name), raw), "swapped")

    def test_no_change_still_writes_output(self):
        # CI 把 --out 当中间产物喂给 swap_dylib.py，跳过写文件会断链。
        body = (ROOT / "tools/nib_left_column.py").read_text(encoding="utf-8")
        no_change = body.split("if not patched:", 1)[1].split("tmp =", 1)[0]
        self.assertIn("shutil.copy2(args.ipa, args.out)", no_change)


if __name__ == "__main__":
    unittest.main(verbosity=2)
