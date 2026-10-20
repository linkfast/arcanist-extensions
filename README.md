# Arcanist extensions

The catalog of [Arcanist](https://github.com/linkfast/arcanist) extensions: what the **Marketplace** in Arcanist's
admin panel (Extensions) lists and installs with one click.

Arcanist reads [`index.json`](index.json) from this repository (at most once an hour), shows each extension in the
newest version it can run, and installs it after checking the downloaded package against the SHA-256 listed here.
Icons are read through the Arcanist server, so the people using it never reach GitHub for them.

A server administrator can point Arcanist at another catalog with `Arcanist:Marketplace:Url`.

## Format 1

```jsonc
{
  "format": 1,
  "extensions": [
    {
      "id": "youtube",                       // the id in its arcanist-extension.json
      "name": "YouTube Audio",               // in English
      "names": { "es": "Audio de YouTube" }, // optional, by language
      "description": "…",
      "descriptions": { "es": "…" },         // optional
      "author": "gchiappe",
      "homepage": "https://…",               // optional
      "license": "AGPL-3.0-or-later",        // optional, SPDX
      "icon": "icons/youtube.svg",           // optional: a file here (.svg, .png or .webp, up to 256 KB)
      "official": false,                     // true only for those made by the Arcanist project
      "maintainers": ["gchiappe"],           // GitHub users who publish its versions (see below)
      "categories": ["import"],              // optional
      "releases": [
        {
          "version": "0.1.0-alpha.1",        // the package's version (semantic versioning)
          "url": "https://…/x.zip",          // https only
          "sha256": "…",                     // of the .zip, 64 lowercase hex digits
          "size": 127365,                    // optional, in bytes
          "minServerVersion": "0.1.0-alpha.1" // optional: the oldest Arcanist it runs on
        }
      ]
    }
  ]
}
```

Arcanist installs the newest release whose `minServerVersion` it meets; older releases stay listed so servers that
have not been updated still get one that runs.

## Proposing and managing extensions

Everything goes through an issue: open one with a form (**New issue**) and an automation
([`submissions.yml`](.github/workflows/submissions.yml)) downloads the package, checks it and opens a pull request
with the change. Edit the issue to fix what it reports and it runs again; closing it closes its pull request.

| Form | Who | What happens |
|---|---|---|
| **Add an extension** | anyone | A pull request that a maintainer of the catalog reviews and merges. You become the extension's maintainer. |
| **Publish a version** | its maintainers | Published right away (others: reviewed). |
| **Change an extension's entry** | its maintainers | Description, names, icon, categories, homepage or maintainers, right away (others: reviewed). |
| **Remove an extension or a version** | its maintainers | Right away (anyone else, to report a problem: reviewed). |

Before proposing one:

1. Publish the extension's `.zip` as a release of its **public GitHub repository**, built from that source (see
   [docs/developers/extensions.md](https://github.com/linkfast/arcanist/blob/main/docs/developers/extensions.md)).
   Its id, name, version and license come from the `arcanist-extension.json` inside it.
2. Its license must let Arcanist's users run it alongside an AGPL-3.0 server (MIT, BSD, Apache-2.0, MPL-2.0, LGPL,
   GPL-3.0, AGPL-3.0…).
3. Extensions run inside the server with full trust: say in its description what it does with users' data.

Pull requests are still welcome too (with `"official": false`); `python scripts/validate.py --download` checks them.
The forms and the automation can be tried locally: `ISSUE="$(cat issue.json)" python scripts/submission.py`.

## License

The catalog (this repository) is under the MIT license. Each extension has its own license.
