# Third-party notices

## caniuse-lite

Browser support data, build-time dependency of the web toolchain.
Licence: CC-BY-4.0 (Creative Commons Attribution 4.0 International), https://creativecommons.org/licenses/by/4.0/
Source: https://github.com/browserslist/caniuse-lite (data from https://github.com/Fyrd/caniuse, Alexis Deveria and contributors).
Changes: none by us; used as distributed.

## IBM Plex fonts

IBM Plex Sans, Sans Condensed and Mono, self-hosted in `web/src/ui/fonts/`.
Copyright (c) 2017 IBM Corp., Reserved Font Name "Plex".
Licence: SIL Open Font License 1.1, https://openfontlicense.org (full text in `web/src/ui/fonts/LICENSE.txt`).
Source: https://github.com/IBM/plex

## Backup image tools (age, rclone, supercronic)

Run by the backup container (`infra/backup/Dockerfile`); not linked into the product.
- age v1.3.2, Copyright (c) 2021 The age Authors. Licence: BSD-3-Clause. Source: https://github.com/FiloSottile/age. Built by us from the unmodified release source.
- rclone v1.75.2, Copyright (C) 2012 by Nick Craig-Wood. Licence: MIT. Source: https://github.com/rclone/rclone. Built by us from source with `golang.org/x/net` raised to v0.62.0 (security fix).
- supercronic v0.2.51, Copyright (c) 2017 Aptible. Licence: MIT. Source: https://github.com/aptible/supercronic. Used as distributed.
