#!/usr/bin/env python3
"""Extract tested codec inputs from an owner-supplied official Ford APK.

Neither the APK nor extracted files belong in source control. The library hash
pins the native offsets used by the isolated codec server to the tested build.
"""

from __future__ import annotations

import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
from zipfile import ZipFile


LIBRARY_PATH = "lib/arm64-v8a/libwbsk_crypto_tool.so"
KEYS_PATH = "assets/flutter_assets/assets/fordpass/data/whitebox_keys_for_prod.txt"
TESTED_LIBRARY_SHA256 = "19ed0892eafaa38d18060654b07117839f9124a3b1c804a7e94da29da48c65f2"


def write_private(path: Path, data: bytes) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as output:
        output.write(data)


def prepare(apk: Path, destination: Path) -> None:
    with ZipFile(apk) as package:
        library = package.read(LIBRARY_PATH)
        keys = package.read(KEYS_PATH)
    digest = sha256(library).hexdigest()
    if digest != TESTED_LIBRARY_SHA256:
        raise ValueError("Ford native codec differs from the tested 6.16.0 build")
    parsed = json.loads(keys)
    if not all(k in parsed["x_api"] for k in ("encrypt", "decrypt")):
        raise ValueError("Ford APK does not contain the expected x_api key pair")
    destination.mkdir(mode=0o700, parents=True, exist_ok=False)
    write_private(destination / "libwbsk_crypto_tool.so", library)
    write_private(destination / "whitebox_keys_for_prod.json", keys)
    print("Prepared a private codec directory from the tested Ford APK")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("apk", type=Path)
    parser.add_argument("destination", type=Path)
    options = parser.parse_args()
    prepare(options.apk, options.destination)
