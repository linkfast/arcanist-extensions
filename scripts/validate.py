"""Checks index.json: its format, and with --download that every release is the package it says (SHA-256, size, id).

    python scripts/validate.py              # format only
    python scripts/validate.py --download   # also downloads each release (CI does)
"""
import hashlib
import io
import json
import pathlib
import re
import sys
import urllib.request
import zipfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
ID = re.compile(r"^[a-z0-9][a-z0-9-]{1,63}$")
SEMVER = re.compile(r"^\d+\.\d+\.\d+(-[0-9A-Za-z-]+(\.[0-9A-Za-z-]+)*)?(\+[0-9A-Za-z.-]+)?$")
HEX64 = re.compile(r"^[0-9a-f]{64}$")
ICON_TYPES = (".svg", ".png", ".webp")
MAX_ICON = 256 * 1024
MAX_PACKAGE = 250 * 1024 * 1024


def fail(errors, where, message):
    errors.append(f"{where}: {message}")


def check(download):
    errors = []
    index = json.loads((ROOT / "index.json").read_text(encoding="utf-8"))
    if index.get("format") != 1:
        fail(errors, "index", "format must be 1")
    seen = set()
    for entry in index.get("extensions", []):
        where = entry.get("id", "?")
        if not ID.match(entry.get("id", "")):
            fail(errors, where, "id: lowercase letters, digits and dashes, 2-64 characters")
        if entry.get("id") in seen:
            fail(errors, where, "listed twice")
        seen.add(entry.get("id"))
        for field in ("name", "description", "author"):
            if not isinstance(entry.get(field), str) or not entry[field].strip():
                fail(errors, where, f"{field} is required")
        if not isinstance(entry.get("official"), bool):
            fail(errors, where, "official must be true or false")
        icon = entry.get("icon")
        if icon is not None:
            if icon.startswith("http"):
                fail(errors, where, "icon: a file of this repository (icons/<id>.svg), not a URL")
            elif not (ROOT / icon).is_file() or not icon.lower().endswith(ICON_TYPES):
                fail(errors, where, f"icon: {icon} is not an .svg, .png or .webp file here")
            elif (ROOT / icon).stat().st_size > MAX_ICON:
                fail(errors, where, "icon: larger than 256 KB")
        releases = entry.get("releases") or []
        if not releases:
            fail(errors, where, "needs at least one release")
        for release in releases:
            at = f"{where} {release.get('version', '?')}"
            if not SEMVER.match(release.get("version", "")):
                fail(errors, at, "version: semantic versioning (1.2.3 or 1.2.3-beta.1)")
            if not str(release.get("url", "")).startswith("https://"):
                fail(errors, at, "url: https only")
            if not HEX64.match(release.get("sha256", "")):
                fail(errors, at, "sha256: 64 lowercase hex digits")
            minimum = release.get("minServerVersion")
            if minimum is not None and not SEMVER.match(minimum):
                fail(errors, at, "minServerVersion: semantic versioning")
            if download and not errors:
                check_package(errors, at, entry["id"], release)
    return errors


def check_package(errors, at, extension_id, release):
    with urllib.request.urlopen(release["url"], timeout=120) as response:
        data = response.read(MAX_PACKAGE + 1)
    if len(data) > MAX_PACKAGE:
        fail(errors, at, "package larger than 250 MB")
        return
    if hashlib.sha256(data).hexdigest() != release["sha256"]:
        fail(errors, at, "sha256 does not match the package")
    if release.get("size") is not None and release["size"] != len(data):
        fail(errors, at, f"size is {len(data)}, not {release['size']}")
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as package:
            manifest = json.loads(package.read("arcanist-extension.json"))
    except (zipfile.BadZipFile, KeyError, json.JSONDecodeError):
        fail(errors, at, "not a zip with arcanist-extension.json at its root")
        return
    if manifest.get("id") != extension_id:
        fail(errors, at, f"the package holds {manifest.get('id')!r}")
    if manifest.get("version") != release["version"]:
        fail(errors, at, f"the package is version {manifest.get('version')!r}")


if __name__ == "__main__":
    problems = check("--download" in sys.argv)
    for problem in problems:
        print(problem)
    print("index.json is valid" if not problems else f"{len(problems)} problem(s)")
    sys.exit(1 if problems else 0)
