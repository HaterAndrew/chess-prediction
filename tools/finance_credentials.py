#!/usr/bin/env python3
"""Enter the collector's existing login without putting it in chat or argv."""
import argparse
import getpass
import json
import os
from pathlib import Path
import stat


def read_private_json(path):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, encoding='utf-8') as stream:
        info = os.fstat(stream.fileno())
        if (info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) & 0o077
                or not stat.S_ISREG(info.st_mode) or info.st_size > 32_768):
            raise ValueError('A small private credential file owned by this user is required')
        return json.load(stream)


def write_private_json(destination, data):
    destination = Path(destination).expanduser().absolute()
    repository = Path(__file__).resolve().parents[1]
    if destination.resolve().is_relative_to(repository):
        raise ValueError('Choose a private location outside the repository')
    parent = os.open(destination.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        info = os.fstat(parent)
        if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) & 0o077:
            raise ValueError('The destination directory must be private (0700) and owned by this user')
        fd = os.open(destination.name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=parent)
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump(data, stream)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
    finally:
        os.close(parent)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path, help="New JSON file outside the repository")
    args = parser.parse_args()
    destination = args.destination.expanduser().absolute()
    repository = Path(__file__).resolve().parents[1]
    if destination.resolve().is_relative_to(repository):
        parser.error("Choose a private location outside the repository")
    if not destination.parent.is_dir() or destination.parent.is_symlink():
        parser.error("The private parent directory must already exist and not be a symlink")
    username = getpass.getpass("Chess Action username (hidden): ").strip()
    password = getpass.getpass("Chess Action password (hidden): ")
    if not username or not password:
        parser.error("Both values are required; no file was created")
    # Exclusive creation preserves existing secrets and refuses symlink targets.
    write_private_json(destination, {"CHESS_ACTION_USERNAME": username, "CHESS_ACTION_PASSWORD": password})
    print(f"Saved private credentials to {destination}; values were not printed.")


if __name__ == "__main__":
    main()
