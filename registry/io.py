"""CSV adapter: load the registry's input files, write the registry table."""
import os

import pandas as pd

from registry.sources import SOURCES

REGISTRY_CSV = "edition_registry.csv"


def load_frames(output_dir):
    """{file: DataFrame} for every source file present in output_dir."""
    frames = {}
    for source in SOURCES:
        path = os.path.join(output_dir, source.file)
        if os.path.exists(path):
            frames[source.file] = pd.read_csv(path)
    return frames


def write_registry(frame, output_dir):
    path = os.path.join(output_dir, REGISTRY_CSV)
    frame.to_csv(path, index=False, lineterminator="\n")
    return path
