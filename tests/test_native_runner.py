#!/usr/bin/env python3
"""Offline native-runner gates; these tests do not execute UIKit.
Run: python -B tests/test_native_runner.py
"""
import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NATIVE = ROOT / "tests" / "native"
spec = importlib.util.spec_from_file_location("gxk_native_result", NATIVE / "verify_result.py")
verifier = importlib.util.module_from_spec(spec)
spec.loader.exec_module(verifier)


class NativeResultContracts(unittest.TestCase):
    def summary(self, count=2):
        return {"result": "Passed", "totalTestCount": count, "passedTests": count,
                "failedTests": 0, "skippedTests": 0}

    def test_complete_execution_passes_without_claiming_device_rendering(self):
        result = verifier.verify_summary(self.summary(), ["testFirst", "testSecond"])
        self.assertEqual(result["passedTests"], 2)
        self.assertEqual(result["deviceRendering"], "NOT VERIFIED")

    def test_empty_or_duplicate_expected_tests_are_rejected(self):
        for names in ([], ["testFirst", "testFirst"]):
            with self.subTest(names=names), self.assertRaises(ValueError):
                verifier.verify_summary(self.summary(), names)

    def test_zero_or_partial_execution_is_rejected(self):
        for count in (0, 1, 3):
            with self.subTest(count=count), self.assertRaises(ValueError):
                verifier.verify_summary(self.summary(count), ["testFirst", "testSecond"])

    def test_failed_or_skipped_test_is_not_a_pass(self):
        for field in ("failedTests", "skippedTests"):
            summary = self.summary()
            summary[field] = 1
            summary["passedTests"] = 1
            with self.subTest(field=field), self.assertRaises(ValueError):
                verifier.verify_summary(summary, ["testFirst", "testSecond"])

    def test_missing_negative_boolean_or_string_counts_are_rejected(self):
        for field in ("totalTestCount", "passedTests", "failedTests", "skippedTests"):
            for value in (None, -1, True, "0"):
                summary = self.summary()
                if value is None:
                    del summary[field]
                else:
                    summary[field] = value
                with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                    verifier.verify_summary(summary, ["testFirst", "testSecond"])

    def test_nonpassed_result_is_rejected_even_when_counts_match(self):
        for result in (None, "Failed", "Unknown"):
            summary = self.summary()
            summary["result"] = result
            with self.subTest(result=result), self.assertRaises(ValueError):
                verifier.verify_summary(summary, ["testFirst", "testSecond"])

    def test_fixture_declares_unique_nonempty_actual_xctest_methods(self):
        names = verifier.fixture_test_names((NATIVE / "ActionDisplayTests.m").read_text(encoding="utf-8"))
        self.assertGreaterEqual(len(names), 20)
        self.assertIn("testFirstAttachmentCompletesProductionDisplayBeforeAQueueTurn", names)
        self.assertIn("testOnlyExactLiveForegroundLayerIsBlockedNotBackgroundOrMask", names)
        self.assertIn("testEmptyActionsTransitionKeepsConfirmedTextButNeverExecutesInput", names)

    def test_empty_or_duplicate_fixture_is_rejected(self):
        for source in ("@implementation NoTests\n@end", "- (void)testOne {}\n- (void)testOne {}"):
            with self.subTest(source=source), self.assertRaises(ValueError):
                verifier.fixture_test_names(source)


class NativeWiringContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = (NATIVE / "ActionDisplayTests.m").read_text(encoding="utf-8")
        cls.runner = (NATIVE / "run_tests.sh").read_text(encoding="utf-8")
        cls.project = (NATIVE / "GXKActionDisplay.xcodeproj/project.pbxproj").read_text(encoding="utf-8")
        cls.workflow = (ROOT / ".github/workflows/build-dylib.yml").read_text(encoding="utf-8")

    def test_fixture_executes_real_production_policy_not_a_duplicate(self):
        self.assertIn('#include "../../dylib/gkx.m"', self.fixture)
        self.assertIn("GXKInstallIconWriteGuard();", self.fixture)
        self.assertNotIn("static void GXKReconcileActionDisplay", self.fixture)
        self.assertNotIn("gkx_init();", self.fixture)
        self.assertNotIn("path = gkx.m;", self.project)
        self.assertIn("GXK_ACTION_DISPLAY_TESTING=1", self.project)

    def test_runner_fails_on_windows_without_trying_to_install_a_toolchain(self):
        self.assertIn('[[ "$(uname -s)" == Darwin ]]', self.runner)
        self.assertIn("native tests NOT EXECUTED", self.runner)
        for forbidden in ("brew install", "xcode-select --install", "downloadPlatform"):
            self.assertNotIn(forbidden, self.runner)

    def test_runner_matches_installed_xcode_runtime_and_records_destinations(self):
        self.assertIn("--sdk iphonesimulator --show-sdk-version", self.runner)
        self.assertIn('data["devices"].get(runtime, [])', self.runner)
        self.assertIn("-showdestinations", self.runner)
        self.assertIn("show-destinations.txt", self.runner)

    def test_runner_preserves_exit_and_checks_actual_execution_counts(self):
        self.assertIn("status=$" "{PIPESTATUS[0]}", self.runner)
        self.assertIn('[[ "$status" -eq 0 ]] || exit "$status"', self.runner)
        self.assertIn("xcresulttool get test-results summary", self.runner)
        self.assertIn("verify_result.py", self.runner)
        self.assertLess(self.runner.index("xcresulttool get test-results summary"),
                        self.runner.index('"$script_dir/verify_result.py"'))

    def test_final_gate_status_is_distinct_from_xcodebuild_status(self):
        self.assertIn("trap record_final_status EXIT", self.runner)
        self.assertIn("final_status=$?", self.runner)
        self.assertIn("final-exit-status.txt", self.runner)
        self.assertIn("exit-status.txt", self.runner)
        self.assertIn("_scratch/**/final-exit-status.txt", self.workflow)

    def test_native_failure_is_bounded_retained_and_blocks_publication(self):
        self.assertIn("timeout-minutes: 15", self.workflow)
        self.assertIn("if: always()", self.workflow)
        self.assertIn("action-display-native-evidence", self.workflow)
        self.assertIn("_scratch/**/ActionDisplay.xcresult", self.workflow)
        self.assertIn("_scratch/**/native-summary.json", self.workflow)
        self.assertNotIn("continue-on-error", self.workflow)
        self.assertIn("needs: build", self.workflow)
        self.assertIn("DEVELOPER_DIR: /Applications/Xcode_16.4.app/Contents/Developer", self.workflow)


if __name__ == "__main__":
    unittest.main(verbosity=2)
