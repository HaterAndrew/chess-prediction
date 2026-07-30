"""Compatibility shim -- implementation lives in sitebuild/ (2026-07-30
decomposition). The filename is load-bearing: auto_update.run_step, the
nightly workflow, and the golden harness invoke it by name.
"""

from sitebuild.main import main  # noqa: F401

if __name__ == "__main__":
    main()
