#!/usr/bin/env bash
# Run the real-production UIKit XCTest fixture on an already installed Simulator.
# Usage: bash tests/native/run_tests.sh [repo/_scratch/output-root] [simulator-udid]
# No downloads, package installs, source rewrites, or automatic deletion.
set -euo pipefail

fail() { printf '%s\n' "ERROR: $*" >&2; exit 1; }
[[ "$(uname -s)" == Darwin ]] || fail "UIKit XCTest requires macOS with Xcode; native tests NOT EXECUTED."
for tool in xcodebuild xcrun python3; do
    command -v "$tool" >/dev/null || fail "Missing $tool; native tests NOT EXECUTED."
done
[[ $# -le 2 ]] || fail "Usage: bash tests/native/run_tests.sh [scratch-output-root] [simulator-udid]"
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
repo="$(cd "$script_dir/../.." && pwd -P)"
requested="${1:-$repo/_scratch/$(date +%Y-%m-%d)-native-action-display}"
scratch="$(python3 -c 'import pathlib, sys; p = pathlib.Path(sys.argv[1]).resolve(); root = pathlib.Path(sys.argv[2]).resolve() / "_scratch"; p.relative_to(root); print(p)' "$requested" "$repo")" || fail "Output root must be inside this repository's _scratch/."
mkdir -p "$scratch"
run="$(mktemp -d "$scratch/run-XXXXXX")"
# Record whole-script status separately: a green xcodebuild may fail the evidence gate.
record_final_status() {
    final_status=$?
    printf '%s\n' "$final_status" >"$run/final-exit-status.txt"
}
trap record_final_status EXIT
mkdir -p "$run/tmp" "$run/module-cache"
export TMPDIR="$run/tmp/"
export CLANG_MODULE_CACHE_PATH="$run/module-cache"
printf '%s\n' "Native XCTest output: $run"
xcodebuild -version >"$run/xcode-version.txt"
xcrun simctl list devices available --json >"$run/simulators.json"
# Match the selected Xcode Simulator SDK, not an unrelated installed runtime.
sdk_version="$(xcrun --sdk iphonesimulator --show-sdk-version)"
wanted_simulator=""
if [[ $# -ge 2 ]]; then wanted_simulator="$2"; fi
selected="$(python3 -c 'import json, sys; data = json.load(open(sys.argv[1])); wanted = sys.argv[2]; runtime = "com.apple.CoreSimulator.SimRuntime.iOS-" + sys.argv[3].replace(".", "-"); rows = [d for d in data["devices"].get(runtime, []) if d.get("isAvailable", False) and d.get("name", "").startswith("iPhone") and (not wanted or d["udid"] == wanted)]; rows.sort(key=lambda d: (d.get("state") != "Booted", d["name"], d["udid"])); assert rows, "No iPhone for selected Xcode runtime " + runtime; d = rows[0]; print(d["udid"] + "|" + d["state"] + "|" + d["name"] + "|" + runtime)' "$run/simulators.json" "$wanted_simulator" "$sdk_version")" || fail "No matching Xcode/iPhone Simulator; native tests NOT EXECUTED."
xcodebuild -showdestinations -project "$script_dir/GXKActionDisplay.xcodeproj" \
    -scheme GXKActionDisplay >"$run/show-destinations.txt" 2>&1
IFS='|' read -r simulator state name runtime <<<"$selected"
[[ "$simulator" =~ ^[0-9A-Fa-f-]{36}$ ]] || fail "Invalid simulator UDID."
printf '%s\n' "Simulator: $name ($simulator, $state, $runtime)" | tee "$run/destination.txt"
if [[ "$state" != Booted ]]; then
    xcrun simctl boot "$simulator" >"$run/simulator-boot.log" 2>&1
fi
xcrun simctl bootstatus "$simulator" -b >"$run/simulator-ready.log" 2>&1

# Preserve xcodebuild's exit status through tee. A failed test blocks callers/CI.
set +e
xcodebuild test \
    -project "$script_dir/GXKActionDisplay.xcodeproj" \
    -scheme GXKActionDisplay \
    -configuration Debug \
    -sdk iphonesimulator \
    -destination "platform=iOS Simulator,id=$simulator" \
    -destination-timeout 180 \
    -derivedDataPath "$run/DerivedData" \
    -resultBundlePath "$run/ActionDisplay.xcresult" \
    -clonedSourcePackagesDirPath "$run/SourcePackages" \
    -disableAutomaticPackageResolution \
    -parallel-testing-enabled NO \
    -maximum-concurrent-test-simulator-destinations 1 \
    CODE_SIGNING_ALLOWED=NO \
    2>&1 | tee "$run/xcodebuild.log"
status=${PIPESTATUS[0]}
set -e
printf '%s\n' "$status" >"$run/exit-status.txt"
printf '%s\n' "xcodebuild exit: $status; result: $run/ActionDisplay.xcresult"
[[ "$status" -eq 0 ]] || exit "$status"
xcrun xcresulttool get test-results summary --path "$run/ActionDisplay.xcresult" \
    >"$run/native-summary.json"
# Exit 0 without executing the fixture (or skipping any test) is not a pass.
python3 "$script_dir/verify_result.py" "$run/native-summary.json" "$script_dir/ActionDisplayTests.m" \
    2>&1 | tee "$run/verify-result.log"
# Inspect/export evidence before approved scratch cleanup; this script never deletes it.
