"""Checks index.json: its format, and with --download that every release is the package it says (SHA-256, size, id).

Extensions and web players are described the same way; their packages hold arcanist-extension.json and
arcanist-frontend.json. An id is unique in the whole catalog.

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
PRICING = ("open-source", "free", "paid", "freemium")
# Open source licenses an extension published as open source may use (SPDX ids).
OPEN_LICENSES = {
    "MIT", "MIT-0", "ISC", "0BSD", "Unlicense", "BSD-2-Clause", "BSD-3-Clause", "Apache-2.0", "MPL-2.0", "Zlib",
    "LGPL-2.1-or-later", "LGPL-3.0-only", "LGPL-3.0-or-later", "GPL-3.0-only", "GPL-3.0-or-later",
    "AGPL-3.0-only", "AGPL-3.0-or-later",
}
LICENSE_REF = re.compile(r"^LicenseRef-[A-Za-z0-9.-]{1,64}$")
LOGIN = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?$")
ICON_TYPES = (".svg", ".png", ".webp")
MAX_ICON = 256 * 1024
MAX_PACKAGE = 250 * 1024 * 1024
# The lists of the catalog and the manifest at the root of their packages.
MANIFESTS = {"extensions": "arcanist-extension.json", "players": "arcanist-frontend.json"}


def fail(errors, where, message):
    errors.append(f"{where}: {message}")


def check(download):
    errors = []
    index = json.loads((ROOT / "index.json").read_text(encoding="utf-8"))
    if index.get("format") != 1:
        fail(errors, "index", "format must be 1")
    seen = set()
    for kind, manifest_file in MANIFESTS.items():
        entries = index.get(kind, [])
        if not isinstance(entries, list):
            fail(errors, "index", f"{kind} must be a list")
            continue
        for entry in entries:
            check_entry(errors, seen, entry, manifest_file, download)
    return errors


def check_entry(errors, seen, entry, manifest_file, download):
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
    pricing = entry.get("pricing")
    if pricing not in PRICING:
        fail(errors, where, f"pricing must be one of {', '.join(PRICING)}")
    license_id = entry.get("license")
    if pricing == "open-source" and license_id not in OPEN_LICENSES:
        fail(errors, where, "license: open source extensions need an open source license (SPDX id)")
    elif license_id is not None and license_id not in OPEN_LICENSES and not LICENSE_REF.match(str(license_id)):
        fail(errors, where, "license: an SPDX id, or LicenseRef-<name> for a license of its own")
    pricing_url = entry.get("pricingUrl")
    if pricing_url is not None and not str(pricing_url).startswith("https://"):
        fail(errors, where, "pricingUrl: https only")
    maintainers = entry.get("maintainers")
    if maintainers is not None and (not isinstance(maintainers, list) or not maintainers
                                    or not all(isinstance(m, str) and LOGIN.match(m) for m in maintainers)):
        fail(errors, where, "maintainers: a list of GitHub users")
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
            check_package(errors, at, entry["id"], release, manifest_file)


def check_package(errors, at, extension_id, release, manifest_file="arcanist-extension.json"):
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
            manifest = json.loads(package.read(manifest_file))
    except (zipfile.BadZipFile, KeyError, json.JSONDecodeError):
        fail(errors, at, f"not a zip with {manifest_file} at its root")
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
