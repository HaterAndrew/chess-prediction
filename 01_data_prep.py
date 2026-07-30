"""Compatibility shim -- implementation lives in dataprep/ (2026-07-30
decomposition). The filename is load-bearing: auto_update.run_step and
the step-timeout map invoke it by name. Importing no longer executes the
pipeline (G4); the export is read only when main() runs.
"""

from dataprep.families import (  # noqa: F401
    ADMIN_ENTRIES,
    extract_family,
    extract_year,
    repair_family_name,
)
from dataprep.main import main  # noqa: F401

if __name__ == "__main__":
    main()
