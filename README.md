# Arcanist extensions

The catalog of [Arcanist](https://github.com/linkfast/arcanist) extensions and web players: what the **Marketplace**
in Arcanist's admin panel (Extensions) lists and installs with one click. Web players (Ultimate Web Player, and those
anyone makes) are listed the same way as extensions, in `players`.

Arcanist reads [`index.json`](index.json) from this repository (at most once an hour), shows each entry in the
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
      "pricing": "open-source",              // open-source, free, paid or freemium
      "pricingUrl": "https://…",             // optional: its prices, or where to buy it
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
  ],
  "players": [
    // Web players, with the same fields; their packages hold arcanist-frontend.json
    // (see docs/developers/frontends.md). An id is unique in the whole catalog.
  ]
}
```

Arcanist installs the newest release whose `minServerVersion` it meets; older releases stay listed so servers that
have not been updated still get one that runs.

## Open source, free, paid and freemium

Every entry says how it is offered, and the marketplace shows it (and filters by it):

| `pricing` | Meaning | License |
|---|---|---|
| `open-source` | Free, with its source published. | An open source SPDX id (MIT, Apache-2.0, MPL-2.0, GPL-3.0, AGPL-3.0…). |
| `free` | Free of charge, without its source. | An SPDX id, or `LicenseRef-<name>` for a license of its own. |
| `freemium` | Free, with paid features. | Same. |
| `paid` | Paid. | Same. |

**Purchases are the maintainer's:** the catalog never sells anything. A paid or freemium extension handles its
purchases itself (in its settings page or app, with its own licensing) or on its maintainer's site, which
`pricingUrl` links to. Its package is still a `.zip` attached to a release of a public GitHub repository (the
repository may hold only the releases), so servers can check it against its SHA-256.

**About Arcanist's license:** Arcanist is AGPL-3.0, and an extension runs inside the server's process. Whether a
closed source extension may be combined with it is for its maintainer to work out (with a lawyer if in doubt): one
that runs its own code as a separate program, as Arcanist does with ffmpeg, avoids the question.

## Proposing and managing extensions

Everything goes through an issue: open one with a form (**New issue**) and an automation
([`submissions.yml`](.github/workflows/submissions.yml)) downloads the package, checks it and opens a pull request
with the change. Edit the issue to fix what it reports and it runs again; closing it closes its pull request.

| Form | Who | What happens |
|---|---|---|
| **Add an extension** / **Add a web player** | anyone | A pull request that a maintainer of the catalog reviews and merges. You become its maintainer. |
| **Publish a version** | its maintainers | Published right away (others: reviewed). |
| **Change an extension's entry** | its maintainers | Description, names, icon, categories, homepage or maintainers, right away (others: reviewed). |
| **Remove an extension or a version** | its maintainers | Right away (anyone else, to report a problem: reviewed). |

Before proposing one:

1. Publish the extension's `.zip` as a release of its **public GitHub repository**, built from that source (see
   [docs/developers/extensions.md](https://github.com/linkfast/arcanist/blob/main/docs/developers/extensions.md)).
   Its id, name, version and license come from the `arcanist-extension.json` inside it.
2. Choose how it is offered (open source, free, freemium or paid). An open source one needs an open source license
   (MIT, BSD, Apache-2.0, MPL-2.0, LGPL, GPL-3.0, AGPL-3.0…).
3. Extensions run inside the server with full trust: say in its description what it does with users' data.

Web players go through the same forms: the package says which it is (`arcanist-frontend.json` at its root makes
it a web player, listed in `players`). Build one following
[docs/developers/frontends.md](https://github.com/linkfast/arcanist/blob/main/docs/developers/frontends.md); it runs
on the server's address with its users' sessions, so say in its description what it does with them.

Pull requests are still welcome too (with `"official": false`); `python scripts/validate.py --download` checks them.
The forms and the automation can be tried locally: `ISSUE="$(cat issue.json)" python scripts/submission.py`.

## License

The catalog (this repository) is under the MIT license. Each extension and web player has its own license.
