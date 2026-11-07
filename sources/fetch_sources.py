#!/usr/bin/env python3
"""Fetch and verify the immutable inputs in source-lock.json (stdlib only)."""
import argparse
import hashlib
import json
from pathlib import Path
import tempfile
import urllib.request

REPO = Path(__file__).resolve().parents[1]
LOCK = Path(__file__).with_name('source-lock.json')


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fetch(root=REPO / 'src', verify_only=False):
    lock = json.loads(LOCK.read_text())
    for item in lock['files']:
        destination = root / item['path']
        if destination.exists():
            if digest(destination) != item['sha256']:
                raise RuntimeError(f'Checksum mismatch in {destination}; remove this cached file and fetch again')
            print('verified', destination.relative_to(root), flush=True)
            continue
        if verify_only:
            raise FileNotFoundError(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=destination.parent, delete=False) as handle:
            temporary = Path(handle.name)
            try:
                request = urllib.request.Request(item['url'], headers={'User-Agent': 'Anodyne-source-fetch/1'})
                with urllib.request.urlopen(request, timeout=90) as response:
                    while chunk := response.read(1024 * 1024):
                        handle.write(chunk)
                handle.close()
                if digest(temporary) != item['sha256']:
                    raise RuntimeError(f'Download checksum mismatch for {item["path"]}')
                temporary.replace(destination)
            finally:
                temporary.unlink(missing_ok=True)
        print('fetched', destination.relative_to(root), flush=True)
    return lock


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=REPO / 'src')
    parser.add_argument('--verify-only', action='store_true')
    args = parser.parse_args()
    fetch(args.root, args.verify_only)


if __name__ == '__main__':
    main()
