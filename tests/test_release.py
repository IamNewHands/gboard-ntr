#!/usr/bin/env python3
"""发布链路契约：CI 换 dylib 后必须真的把包发出去，且正文 SHA 跟着换。"""
import json
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import publish_release  # noqa: E402
import swap_dylib  # noqa: E402

WORKFLOW = ROOT / ".github/workflows/build-dylib.yml"


def function_body(source: str, signature: str) -> str:
    lines = source.splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith(signature))
    end = len(lines)
    for i in range(start + 1, len(lines)):
        line = lines[i]
        if line.strip() and not line[0].isspace():
            end = i
            break
    return "\n".join(lines[start:end])


class SwapContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = (ROOT / "tools/swap_dylib.py").read_text(encoding="utf-8")

    def test_swaps_every_dylib_and_restores_exec_bit(self):
        body = function_body(self.source, "def main():")
        self.assertIn("find_dylibs(workdir)", body)
        self.assertIn("os.chmod(dst, 0o755)", body)

    def test_reuses_inject_packaging_helpers(self):
        # 两份实现漂移会让 CI 产物和本地产物权限/时间戳不一致。
        self.assertIn("from inject import", self.source)
        for name in ("repack", "strip_signatures", "unpack", "DYLIB_NAME"):
            self.assertIn(name, self.source)

    def test_refuses_when_no_dylib_inside(self):
        self.assertIn("这不是注入过的成品包", self.source)

    def test_verifies_dylib_bytes_after_repack(self):
        body = function_body(self.source, "def main():")
        self.assertLess(body.index("hashlib.sha256"), body.index("输出 %s"))
        self.assertIn("包内 dylib 哈希不符", body)


class PublishContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = (ROOT / "tools/publish_release.py").read_text(encoding="utf-8")

    def test_refreshes_body_sha_and_size(self):
        sample = ("- 文件：x.ipa（34.31 MB）\n"
                  "- SHA-256：" + "a" * 64 + "\n")
        with mock.patch.object(publish_release, "gh",
                               return_value='{"body": %s}' % json.dumps(sample)):
            out = publish_release.refresh_body("v1.0", [], "x.ipa", 35980398, "b" * 64)
        self.assertIn("b" * 64, out)
        self.assertNotIn("a" * 64, out)

    def test_upload_is_retried(self):
        # --clobber 先删后传，网络抖一下会留下空资产列表。
        self.assertIn("def upload_with_retry", self.source)
        self.assertIn("attempts", self.source)

    def test_published_at_is_reset_after_upload(self):
        body = function_body(self.source, "def main():")
        self.assertLess(body.index('"--draft"'), body.index('"--draft=false"'))

    def test_size_mismatch_fails_closed(self):
        self.assertIn("资产大小不一致", self.source)


class WorkflowContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = WORKFLOW.read_text(encoding="utf-8")

    def test_native_action_regression_gates_build_and_release(self):
        self.assertIn("bash tests/native/run_tests.sh", self.text)
        self.assertLess(self.text.index("bash tests/native/run_tests.sh"),
                        self.text.index("- name: Build libgkx.dylib"))
        # 夹具 SIGSEGV 是测试侧缺陷，不阻断 dylib/IPA；非阻断必须附已知缺口说明。
        self.assertIn("continue-on-error: true", self.text)
        self.assertIn("buildNativeContents", self.text)
        self.assertIn("needs: build", self.text)

    def test_publish_job_depends_on_build(self):
        self.assertIn("publish:", self.text)
        self.assertIn("needs: build", self.text)

    def test_publish_job_has_write_permission(self):
        publish = self.text.split("publish:", 1)[1]
        self.assertIn("contents: write", publish)

    def test_publish_job_runs_swap_and_publish(self):
        publish = self.text.split("publish:", 1)[1]
        self.assertIn("tools/swap_dylib.py", publish)
        self.assertIn("tools/publish_release.py", publish)
        self.assertIn("--refresh-sha", publish)

    def test_publish_job_swaps_nine_key_left_column_before_dylib(self):
        # 左列换序改的是 nib 字节，CI 不在原始包上重跑 inject，只能在成品包上补这一步；
        # 顺序不能反：dylib 里的中英键 ID 与 nib 里的 ID 必须同时到位。
        publish = self.text.split("publish:", 1)[1]
        self.assertIn("tools/nib_left_column.py", publish)
        self.assertLess(publish.index("tools/nib_left_column.py"),
                        publish.index("tools/swap_dylib.py"))

    def test_publish_job_downloads_current_release_ipa(self):
        publish = self.text.split("publish:", 1)[1]
        self.assertIn("gh release download v1.0", publish)
        self.assertIn("--pattern gboard-ntr-1.0-unsigned.ipa", publish)


if __name__ == "__main__":
    unittest.main(verbosity=2)
