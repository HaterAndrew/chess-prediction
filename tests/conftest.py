"""
Shared pytest fixtures for chess prediction pipeline integration tests.

Provides frozen test data, temporary output directories, and pre-loaded
DataFrames that mirror the production data layout without hitting the
real CCA site or reading from the live output/ directory.
"""

import os
import shutil
import tempfile

import pandas as pd
import pytest

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")


@pytest.fixture
def fixtures_dir():
    """Path to the frozen fixture CSV directory."""
    return FIXTURES_DIR


@pytest.fixture
def tmp_output(tmp_path):
    """Temporary output directory pre-populated with fixture CSVs.

    Copies all fixture files into a temp dir so tests can write outputs
    without polluting the repo.  Returns the temp dir path.
    """
    out = tmp_path / "output"
    out.mkdir()
    for fname in os.listdir(FIXTURES_DIR):
        src = os.path.join(FIXTURES_DIR, fname)
        # Map fixture names to production names
        dest_name = fname
        if fname == "test_summary.csv":
            dest_name = "tournament_summary.csv"
        elif fname == "test_daily_regs.csv":
            dest_name = "daily_registration_counts.csv"
        elif fname == "test_metadata.csv":
            dest_name = "tournament_metadata.csv"
        elif fname == "test_scrape.csv":
            dest_name = "daily_scrape.csv"
        shutil.copy2(src, out / dest_name)
    return str(out)


@pytest.fixture
def summary_df(fixtures_dir):
    """Frozen tournament_summary DataFrame."""
    return pd.read_csv(os.path.join(fixtures_dir, "test_summary.csv"))


@pytest.fixture
def daily_df(fixtures_dir):
    """Frozen daily_registration_counts DataFrame."""
    return pd.read_csv(os.path.join(fixtures_dir, "test_daily_regs.csv"))


@pytest.fixture
def metadata_df(fixtures_dir):
    """Frozen tournament_metadata DataFrame."""
    return pd.read_csv(os.path.join(fixtures_dir, "test_metadata.csv"))


@pytest.fixture
def scrape_df(fixtures_dir):
    """Frozen daily_scrape DataFrame."""
    return pd.read_csv(os.path.join(fixtures_dir, "test_scrape.csv"))
