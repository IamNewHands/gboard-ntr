#!/usr/bin/env python3
"""Require all production XCTest fixture methods to pass in an xcresult summary.

Usage: python3 tests/native/verify_result.py SUMMARY_JSON FIXTURE_SOURCE
SUMMARY_JSON comes from: xcrun xcresulttool get test-results summary --path RESULT
This checks execution/counts only, not real-device rendering or acceptance.
"""
import argparse
import json
import re
from pathlib import Path


def fixture_test_names(source: str) -> list[str]:
    names = re.findall(r"^-\s*\(void\)\s*(test\w+)\s*\{", source, re.MULTILINE)
    if not names or len(names) != len(set(names)):
        raise ValueError("Fixture must declare unique, nonempty XCTest test methods")
    return names


def verify_summary(summary: dict, expected: list[str]) -> dict:
    if not expected or len(expected) != len(set(expected)):
        raise ValueError("Expected tests must be unique and nonempty")
    if not isinstance(summary, dict):
        raise ValueError("xcresult summary must be a JSON object")
    counts = {}
    for field in ("totalTestCount", "passedTests", "failedTests", "skippedTests"):
        value = summary.get(field)
        if type(value) is not int or value < 0:
            raise ValueError(f"Missing or invalid xcresult count: {field}")
        counts[field] = value
    if summary.get("result") != "Passed":
        raise ValueError(f"Native XCTest result is not Passed: {summary.get('result')!r}")
    count = len(expected)
    if counts != {"totalTestCount": count, "passedTests": count,
                  "failedTests": 0, "skippedTests": 0}:
        raise ValueError(f"Incomplete native XCTest execution: expected {count}, got {counts}")
    return {"result": "Passed", "expectedTests": count, **counts,
            "deviceRendering": "NOT VERIFIED"}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("summary", type=Path)
    parser.add_argument("fixture", type=Path)
    args = parser.parse_args()
    expected = fixture_test_names(args.fixture.read_text(encoding="utf-8"))
    result = verify_summary(json.loads(args.summary.read_text(encoding="utf-8")), expected)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
