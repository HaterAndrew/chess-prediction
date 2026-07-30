"""Registration-export loader (01_data_prep head, verbatim). The export
read happens at call time now, not at import (G4).
"""
import os

import pandas as pd

DATA_PATH = os.path.expanduser("~/Downloads/all_registrations.csv")


def load_registrations():
    print("Loading data...")
    df = pd.read_csv(DATA_PATH)
    print(f"  {len(df):,} registrations, {df['tid'].nunique()} tournaments")

    # Parse timestamps
    df['registered_time'] = pd.to_datetime(df['registered_time'], errors='coerce')
    # Null out the 0000-00-00 sentinel values (they become NaT from errors='coerce')
    null_mask = df['registered_time'].isna() | (df['registered_time'].dt.year < 2000)
    df.loc[null_mask, 'registered_time'] = pd.NaT

    has_ts = df['registered_time'].notna()
    print(f"  {has_ts.sum():,} registrations with valid timestamps")
    return df
