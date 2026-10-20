"""Turns a submission issue (made with one of the forms in .github/ISSUE_TEMPLATE) into a change of index.json.

Run by .github/workflows/submissions.yml with the issue as JSON in ISSUE (never as code). It changes index.json
(and icons/), then writes:
- submission-result.md: the comment for the issue (what changed, or what to fix);
- submission-pr.md: the pull request's body;
- to $GITHUB_OUTPUT: ok (true/false), auto (true: merge without review), branch and title.

    ISSUE="$(cat issue.json)" REPOSITORY=owner/catalog python scripts/submission.py   # to try it locally

Who may do what:
- new extension: anyone; always reviewed (a catalog maintainer merges the pull request). The submitter becomes its
  maintainer.
- new version, changes and removals: applied right away (merged) when the issue's author is one of the extension's
  `maintainers` or a maintainer of this repository; anyone else's go to review.
"""
import hashlib
import io
import json
import os
import pathlib
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
import zipfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from validate import ID, LICENSE_REF, LOGIN, MAX_ICON, MAX_PACKAGE, OPEN_LICENSES, ROOT, SEMVER, check  # noqa: E402

INDEX = ROOT / "index.json"
PACKAGE_URL = re.compile(
    r"^https://github\.com/(?P<owner>[A-Za-z0-9-]{1,39})/(?P<repo>[A-Za-z0-9._-]{1,100})/releases/download/[^/\s]+/[^/\s]+\.zip$")
CATEGORY = re.compile(r"^[a-z0-9][a-z0-9-]{0,31}$")
PRICING_LABELS = {"Open source": "open-source", "Free": "free", "Paid": "paid", "Freemium": "freemium"}
NO_RESPONSE = "_No response_"


class Problem(Exception):
    """Something the submitter has to fix."""


# ---- The issue's form ------------------------------------------------------------------------------------------

def form(body):
    """The fields of an issue form by their label: `### Label` followed by the answer."""
    fields = {}
    label = None
    lines = []
    for line in (body or "").replace("\r\n", "\n").split("\n"):
        heading = re.match(r"^### (.+?)\s*$", line)
        if heading:
            if label is not None:
                fields[label] = "\n".join(lines).strip()
            label, lines = heading.group(1), []
        elif label is not None:
            lines.append(line)
    if label is not None:
        fields[label] = "\n".join(lines).strip()
    return {k: ("" if v == NO_RESPONSE else v) for k, v in fields.items()}


def field(fields, label, required=False, limit=2000):
    value = fields.get(label, "").strip()
    if required and not value:
        raise Problem(f"**{label}** is required.")
    if len(value) > limit:
        raise Problem(f"**{label}** is too long (at most {limit} characters).")
    return value


# ---- Versions --------------------------------------------------------------------------------------------------

def version_key(version):
    """SemVer 2.0 precedence, as a sortable key."""
    core, _, rest = version.partition("+")[0].partition("-")
    numbers = tuple(int(n) for n in core.split("."))
    if not rest:
        return numbers, (1,)
    parts = []
    for part in rest.split("."):
        parts.append((0, int(part), "") if part.isdigit() else (1, 0, part))
    return numbers, (0, tuple(parts))


def min_server(fields):
    value = field(fields, "Oldest Arcanist version it runs on", limit=64)
    if value and not SEMVER.match(value):
        raise Problem("**Oldest Arcanist version it runs on** must be a version such as `0.1.0-alpha.2`.")
    return value or None


# ---- Downloads -------------------------------------------------------------------------------------------------

def download(url, limit, what):
    request = urllib.request.Request(url, headers={"User-Agent": "arcanist-extensions-submissions"})
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            data = response.read(limit + 1)
            content_type = response.headers.get("Content-Type", "")
    except urllib.error.HTTPError as error:
        raise Problem(f"The {what} could not be downloaded from {url} (HTTP {error.code}).") from error
    except (urllib.error.URLError, TimeoutError) as error:
        raise Problem(f"The {what} could not be downloaded from {url} ({error}).") from error
    if len(data) > limit:
        raise Problem(f"The {what} is larger than {limit // 1024} KB.")
    return data, content_type


def package(url):
    """Downloads a package and reads its manifest. Only releases of public GitHub repositories."""
    match = PACKAGE_URL.match(url)
    if not match:
        raise Problem("**Package URL** must be a `.zip` attached to a GitHub release: "
                      "`https://github.com/<owner>/<repo>/releases/download/<tag>/<file>.zip`.")
    data, _ = download(url, MAX_PACKAGE, "package")
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            manifest = json.loads(archive.read("arcanist-extension.json"))
    except (zipfile.BadZipFile, KeyError, json.JSONDecodeError, UnicodeDecodeError) as error:
        raise Problem("The package is not a zip with `arcanist-extension.json` at its root.") from error
    if not isinstance(manifest, dict):
        raise Problem("`arcanist-extension.json` is not an object.")
    for key in ("id", "name", "version", "assembly"):
        if not isinstance(manifest.get(key), str) or not manifest[key].strip():
            raise Problem(f"`arcanist-extension.json` has no `{key}`.")
    if not ID.match(manifest["id"]):
        raise Problem(f"The id `{manifest['id']}` must be 2-64 lowercase letters, digits and dashes.")
    if not SEMVER.match(manifest["version"]):
        raise Problem(f"The version `{manifest['version']}` is not a semantic version (1.2.3 or 1.2.3-beta.1).")
    return {
        "manifest": manifest,
        "homepage": f"https://github.com/{match['owner']}/{match['repo']}",
        "release": {"version": manifest["version"], "url": url, "sha256": hashlib.sha256(data).hexdigest(), "size": len(data)},
    }


def icon(url, extension_id):
    """Copies an icon into icons/; returns its path in the catalog."""
    if not url.startswith("https://"):
        raise Problem("**Icon URL** must be https.")
    data, content_type = download(url, MAX_ICON, "icon")
    path = urllib.parse.urlparse(url).path.lower()
    if path.endswith(".svg") or "svg" in content_type or data.lstrip()[:5] in (b"<?xml", b"<svg "):
        text = data.decode("utf-8", errors="replace").lower()
        if "<svg" not in text:
            raise Problem("The icon is not an SVG image.")
        if re.search(r"<script|javascript:|<foreignobject|\son[a-z]+\s*=|<iframe|<embed|<object", text):
            raise Problem("The SVG icon has scripts or embedded content: only plain drawings are accepted.")
        kind = "svg"
    elif data.startswith(b"\x89PNG\r\n\x1a\n"):
        kind = "png"
    elif data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        kind = "webp"
    else:
        raise Problem("The icon must be an `.svg`, `.png` or `.webp` image.")
    for old in (ROOT / "icons").glob(f"{extension_id}.*"):
        old.unlink()
    (ROOT / "icons").mkdir(exist_ok=True)
    (ROOT / "icons" / f"{extension_id}.{kind}").write_bytes(data)
    return f"icons/{extension_id}.{kind}"


def categories(value):
    items = [c.strip().lower() for c in value.split(",") if c.strip()]
    if len(items) > 5 or any(not CATEGORY.match(c) for c in items):
        raise Problem("**Categories**: up to 5, each lowercase letters, digits and dashes.")
    return list(dict.fromkeys(items))


def pricing(value):
    if value not in PRICING_LABELS:
        raise Problem(f"**Pricing** must be one of: {', '.join(PRICING_LABELS)}.")
    return PRICING_LABELS[value]


def pricing_url(value):
    if not value.startswith("https://"):
        raise Problem("**Pricing page** must be an https URL.")
    return value


def logins(value):
    items = [m.strip().lstrip("@") for m in value.split(",") if m.strip()]
    if not items or len(items) > 10 or any(not LOGIN.match(m) for m in items):
        raise Problem("**Maintainers**: GitHub users separated by commas (1 to 10).")
    return list(dict.fromkeys(items))


# ---- Who asks --------------------------------------------------------------------------------------------------

def repository_maintainer(login):
    """Whether the user can write to this repository (a maintainer of the catalog)."""
    repository, token = os.environ.get("REPOSITORY"), os.environ.get("GH_TOKEN")
    if not repository or not token:
        return False
    request = urllib.request.Request(
        f"https://api.github.com/repos/{repository}/collaborators/{urllib.parse.quote(login)}/permission",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
                 "User-Agent": "arcanist-extensions-submissions"})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.load(response).get("permission") in ("admin", "maintain", "write")
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        return False


def may_manage(entry, login):
    return login.lower() in (m.lower() for m in entry.get("maintainers", [])) or repository_maintainer(login)


# ---- The requests ----------------------------------------------------------------------------------------------

def find(index, extension_id):
    for entry in index["extensions"]:
        if entry["id"] == extension_id:
            return entry
    raise Problem(f"There is no extension `{extension_id}` in the catalog.")


def new_extension(index, fields, login):
    found = package(field(fields, "Package URL", required=True, limit=500))
    manifest, release = found["manifest"], found["release"]
    extension_id = manifest["id"]
    if any(e["id"] == extension_id for e in index["extensions"]):
        raise Problem(f"`{extension_id}` is already in the catalog: to publish a new version, use **Publish a version**.")
    model = pricing(field(fields, "Pricing", required=True, limit=20))
    license_id = manifest.get("license")
    if model == "open-source" and license_id not in OPEN_LICENSES:
        raise Problem(f"An open source extension needs an open source `license` in its manifest (one of: "
                      f"{', '.join(sorted(OPEN_LICENSES))}); it has {license_id or 'none'}.")
    if license_id not in OPEN_LICENSES and not LICENSE_REF.match(str(license_id or "")):
        raise Problem("The manifest's `license` must be an SPDX id, or `LicenseRef-<name>` for a license of your own.")
    description = field(fields, "Description", limit=500) or str(manifest.get("description") or "").strip()
    if not description:
        raise Problem("**Description** is required (the manifest has none).")
    if minimum := min_server(fields):
        release["minServerVersion"] = minimum
    entry = {
        "id": extension_id,
        "name": manifest["name"].strip()[:100],
        "description": description,
        "author": str(manifest.get("author") or login).strip()[:100],
        "homepage": found["homepage"],
        "license": license_id,
        "official": False,
        "pricing": model,
        "maintainers": [login],
        "releases": [release],
    }
    if name_es := field(fields, "Name in Spanish", limit=100):
        entry["names"] = {"es": name_es}
    if description_es := field(fields, "Description in Spanish", limit=500):
        entry["descriptions"] = {"es": description_es}
    if url := field(fields, "Icon URL", limit=500):
        entry["icon"] = icon(url, extension_id)
    if value := field(fields, "Categories", limit=200):
        entry["categories"] = categories(value)
    if value := field(fields, "Pricing page", limit=500):
        entry["pricingUrl"] = pricing_url(value)
    index["extensions"].append(entry)
    index["extensions"].sort(key=lambda e: e["id"])
    return extension_id, f"Add {entry['name']} ({extension_id}) {release['version']}", False, [
        f"Adds **{entry['name']}** (`{extension_id}`) {release['version']}, by {entry['author']}, maintained by @{login}.",
        f"- Package: {release['url']} ({release['size']:,} bytes, SHA-256 `{release['sha256']}`)",
        f"- {next(k for k, v in PRICING_LABELS.items() if v == model)}, license {license_id}; repository: {found['homepage']}",
        "",
        "A maintainer of the catalog reviews it (the source, what it does on the server) and merges the pull request.",
    ]


def new_version(index, fields, login):
    entry = find(index, field(fields, "Extension id", required=True, limit=64))
    found = package(field(fields, "Package URL", required=True, limit=500))
    manifest, release = found["manifest"], found["release"]
    if manifest["id"] != entry["id"]:
        raise Problem(f"The package is the extension `{manifest['id']}`, not `{entry['id']}`.")
    if any(r["version"] == release["version"] for r in entry["releases"]):
        raise Problem(f"Version {release['version']} is already listed: publish the package with a new version.")
    if minimum := min_server(fields):
        release["minServerVersion"] = minimum
    entry["releases"].append(release)
    entry["releases"].sort(key=lambda r: version_key(r["version"]), reverse=True)
    return entry["id"], f"{entry['name']} {release['version']}", may_manage(entry, login), [
        f"Publishes **{entry['name']}** {release['version']}.",
        f"- Package: {release['url']} ({release['size']:,} bytes, SHA-256 `{release['sha256']}`)",
        *([f"- For Arcanist {release['minServerVersion']} and later"] if "minServerVersion" in release else []),
    ]


def update(index, fields, login):
    entry = find(index, field(fields, "Extension id", required=True, limit=64))
    changes = []
    if value := field(fields, "Description", limit=500):
        entry["description"] = value
        changes.append("description")
    if value := field(fields, "Name in Spanish", limit=100):
        entry.setdefault("names", {})["es"] = value
        changes.append("name in Spanish")
    if value := field(fields, "Description in Spanish", limit=500):
        entry.setdefault("descriptions", {})["es"] = value
        changes.append("description in Spanish")
    if value := field(fields, "Icon URL", limit=500):
        entry["icon"] = icon(value, entry["id"])
        changes.append("icon")
    if value := field(fields, "Categories", limit=200):
        entry["categories"] = categories(value)
        changes.append("categories")
    if value := field(fields, "Homepage", limit=500):
        if not value.startswith("https://"):
            raise Problem("**Homepage** must be an https URL.")
        entry["homepage"] = value
        changes.append("homepage")
    if value := field(fields, "Maintainers", limit=500):
        entry["maintainers"] = logins(value)
        changes.append("maintainers")
    if value := field(fields, "Pricing", limit=20):
        entry["pricing"] = pricing(value)
        changes.append("pricing")
    if value := field(fields, "Pricing page", limit=500):
        entry["pricingUrl"] = pricing_url(value)
        changes.append("pricing page")
    if not changes:
        raise Problem("Nothing to change: fill in at least one field.")
    return entry["id"], f"Change {entry['name']}: {', '.join(changes)}", may_manage(entry, login), [
        f"Changes the {', '.join(changes)} of **{entry['name']}** (`{entry['id']}`)."]


def remove(index, fields, login):
    entry = find(index, field(fields, "Extension id", required=True, limit=64))
    reason = field(fields, "Reason", required=True)
    version = field(fields, "Version", limit=64)
    allowed = may_manage(entry, login)
    if version:
        if not any(r["version"] == version for r in entry["releases"]):
            raise Problem(f"{entry['name']} has no version {version} in the catalog.")
        if len(entry["releases"]) == 1:
            raise Problem(f"{version} is its only version: leave **Version** empty to remove the whole extension.")
        entry["releases"] = [r for r in entry["releases"] if r["version"] != version]
        return entry["id"], f"Remove {entry['name']} {version}", allowed, [
            f"Removes version {version} of **{entry['name']}**.", "", f"> {reason}"]
    index["extensions"].remove(entry)
    if entry.get("icon"):
        (ROOT / entry["icon"]).unlink(missing_ok=True)
    return entry["id"], f"Remove {entry['name']}", allowed, [
        f"Removes **{entry['name']}** (`{entry['id']}`) from the catalog.", "", f"> {reason}"]


KINDS = {
    "submission:new": new_extension,
    "submission:version": new_version,
    "submission:update": update,
    "submission:remove": remove,
}


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    issue = json.loads(os.environ["ISSUE"])
    number, login = issue["number"], issue["user"]["login"]
    labels = [label["name"] for label in issue.get("labels", [])]
    kind = next((k for k in KINDS if k in labels), None)
    output = {"ok": "false", "auto": "false", "branch": f"submission/{number}", "title": ""}
    try:
        if kind is None:
            raise Problem("This issue has no `submission:*` label: open it with one of the forms.")
        index = json.loads(INDEX.read_text(encoding="utf-8"))
        extension_id, title, auto, summary = KINDS[kind](index, form(issue.get("body")), login)
        INDEX.write_text(json.dumps(index, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
        problems = check(download=False)
        if problems:
            raise Problem("The catalog would not be valid:\n" + "\n".join(f"- {p}" for p in problems))
        output.update(ok="true", auto="true" if auto else "false", title=title)
        next_step = ("It is published now: Arcanist servers see it within the hour." if auto
                     else "A maintainer of the catalog will review the pull request.")
        (ROOT / "submission-result.md").write_text("\n".join(
            ["Thanks! ✅", "", *summary, "", next_step, "",
             "_Edit this issue to change anything: this runs again._" if not auto else ""]), encoding="utf-8", newline="\n")
        (ROOT / "submission-pr.md").write_text("\n".join(
            [*summary, "", f"Requested by @{login} in #{number}.", "", f"Closes #{number}"]), encoding="utf-8", newline="\n")
    except Problem as problem:
        (ROOT / "submission-result.md").write_text("\n".join(
            ["Something needs fixing before this can go ahead: ❌", "", str(problem), "",
             "_Edit this issue to fix it: this runs again._"]), encoding="utf-8", newline="\n")
    with open(os.environ.get("GITHUB_OUTPUT", os.devnull), "a", encoding="utf-8") as out:
        for key, value in output.items():
            # Values come from the submission: one line each, and nothing that could end the line.
            out.write(f"{key}={str(value).replace(chr(10), ' ').replace(chr(13), ' ')[:200]}\n")
    print((ROOT / "submission-result.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
