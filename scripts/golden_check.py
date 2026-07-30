"""Golden-output gate for the decomposition refactor.

Behavior-preserving phases must not change what the pipeline produces. This
harness runs the two artifact builders (04d -> output/website_data.json,
04e -> output/performance_data.json) as subprocesses against the repo's
current data, then either stores the results as baselines (capture) or diffs
them against stored baselines (compare) after stripping volatile fields.

The pre-run artifact bytes are restored afterwards, so the git tree is left
exactly as found regardless of mode.

Baselines belong OUTSIDE the repo (a scratch dir) and are valid same-day
only: 04c/04d/04e freeze TODAY at import, so days_remaining/status drift
across midnight. Re-capture after midnight, a nightly data commit, or any
intentional model change.

Usage:
  python scripts/golden_check.py capture --baseline-dir /path/to/golden
  python scripts/golden_check.py compare --baseline-dir /path/to/golden [--skip-perf]
"""

import argparse
import difflib
import json
import os
import shutil
import subprocess
import sys

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_DIR = os.path.join(PROJECT_DIR, "output")

ARTIFACTS = {
    "website": ("04d_website_data_v2.py", "website_data.json", 600),
    "perf": ("04e_performance_data.py", "performance_data.json", 1800),
}

# Fields that legitimately differ between two identical-code runs.
VOLATILE_KEYS = {"generated", "generated_time", "degraded_at", "stamped_at",
                 "last_updated"}


def _strip_volatile(obj):
    if isinstance(obj, dict):
        return {k: _strip_volatile(v) for k, v in obj.items()
                if k not in VOLATILE_KEYS}
    if isinstance(obj, list):
        return [_strip_volatile(v) for v in obj]
    return obj


def _normalize(path):
    with open(path) as f:
        data = json.load(f)
    return json.dumps(_strip_volatile(data), sort_keys=True, indent=1)


def _run_builders(skip_perf):
    produced = {}
    for name, (script, artifact, timeout) in ARTIFACTS.items():
        if skip_perf and name == "perf":
            continue
        print(f"  running {script} ...", flush=True)
        result = subprocess.run(
            [sys.executable, script], cwd=PROJECT_DIR,
            capture_output=True, text=True, timeout=timeout,
        )
        if result.returncode != 0:
            sys.stderr.write(result.stdout[-2000:] + "\n" + result.stderr[-2000:])
            raise RuntimeError(f"{script} exited {result.returncode}")
        produced[name] = os.path.join(OUTPUT_DIR, artifact)
    return produced


def _preserve(paths):
    return {p: open(p, "rb").read() for p in paths if os.path.exists(p)}


def _restore(saved):
    for p, blob in saved.items():
        with open(p, "wb") as f:
            f.write(blob)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["capture", "compare"])
    parser.add_argument("--baseline-dir", required=True)
    parser.add_argument("--skip-perf", action="store_true",
                        help="inner-loop mode: gate website_data.json only")
    args = parser.parse_args(argv)

    os.makedirs(args.baseline_dir, exist_ok=True)
    artifact_paths = [os.path.join(OUTPUT_DIR, a) for _, a, _ in ARTIFACTS.values()]
    saved = _preserve(artifact_paths)
    try:
        produced = _run_builders(args.skip_perf)
        failures = []
        for name, path in produced.items():
            golden = os.path.join(args.baseline_dir,
                                  ARTIFACTS[name][1].replace(".json", ".golden.json"))
            if args.mode == "capture":
                shutil.copyfile(path, golden)
                print(f"  captured {os.path.basename(golden)}")
                continue
            if not os.path.exists(golden):
                raise SystemExit(f"no baseline {golden} — run capture first")
            new, old = _normalize(path), _normalize(golden)
            if new == old:
                print(f"  OK {name}: matches golden")
            else:
                diff = list(difflib.unified_diff(
                    old.splitlines(), new.splitlines(),
                    fromfile=f"{name}.golden", tofile=f"{name}.current",
                    lineterm="", n=2))
                print("\n".join(diff[:120]))
                if len(diff) > 120:
                    print(f"  ... {len(diff) - 120} more diff lines")
                failures.append(name)
        if failures:
            raise SystemExit(f"GOLDEN MISMATCH: {', '.join(failures)}")
    finally:
        _restore(saved)
        print("  pre-run artifacts restored")


if __name__ == "__main__":
    main()
