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
      "author": "LinkFast S.A.",
      "homepage": "https://…",               // optional
      "license": "AGPL-3.0-or-later",        // optional, SPDX
      "icon": "icons/youtube.svg",           // optional: a file here (.svg, .png or .webp, up to 256 KB)
      "official": true,                      // made by the Arcanist project
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

## Proposing an extension

Extensions run inside the server with full trust, so every entry is reviewed before it is merged.

1. Publish the extension's `.zip` as a release of a public repository, with its source (see
   [docs/developers/extensions.md](https://github.com/linkfast/arcanist/blob/main/docs/developers/extensions.md)).
   Its license must let Arcanist's users run it alongside an AGPL-3.0 server.
2. Open a pull request that adds its entry (with `"official": false`) and its icon under `icons/`.
3. `python scripts/validate.py --download` checks the entry and the package; the pull request runs it too.

A new version is a pull request that adds a release at the top of its `releases`.

## License

The catalog (this repository) is under the MIT license. Each extension has its own license.
