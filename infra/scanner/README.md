# Scanner host deployment

This directory preserves the deployed phone scanner repair from PLF-030 and
PLF-031. It uses the existing `clonerd-lan-caddy` ingress and the existing
Lenovo urirun filesystem API. Publishing this source is a separate step from
the already verified host deployment.

The public scanner is `https://192.168.188.212:8196/scanner`. Caddy terminates
TLS on 8196, redirects plaintext HTTP on that same port, and forwards to HTTP
on `127.0.0.1:18196`. Idle TCP/TLS clients no longer block the application's
Python accept loop. `reconcile.py` observes the live Caddy configuration and
updates it with one ETag/If-Match request. It preserves other servers and
refuses foreign changes to the scanner listener, certificate tag or logger.

Completed PDF/JSON pairs are delivered to the physical Lenovo node at
`192.168.188.201:8765`, under:

    ~/Documents/Faktury/scan-YYYYMMDD-<source-pair-hash>/*

The date is capture time. Subsequent assignment uses the metadata for the
accounting period, contractor and document type. This worker does no accounting
assignment or source deletion. It requires the remote hostname to be `lenovo`.
It verifies both files by reading back their bytes and SHA-256 hashes, then
publishes `.ready`. Interrupted transfers retry; conflicts fail; durable local
receipts prevent re-creating files moved by a subsequent assignment process.

Each PDF contains full original metadata in `/Info /URIRUNMetadata` and the
normalized data model in `/Info /WellmanifestJSON`. The worker uses PyMuPDF to
write valid metadata, renders every page before/after to check unchanged pixels,
and requires a valid PDF with a lossless metadata round-trip. The original JSON
sidecar and source archive remain intact.

## Host prerequisites

- Existing urirun environment at `~/github/if-uri/urirun/venv`, with the scanner
  connector and PyMuPDF. No shared environment installation is performed here.
- Existing Caddy admin API at `127.0.0.1:2019`, with the original configuration
  preserved. Its persistent volume contains `/data/scanner8196/lan.pem` and
  `lan-key.pem`, copied from the existing Faktury LAN certificate. The private
  key remains mode 600 and is never stored in Git. Phones must trust that CA.
- The already archived metadata model from `wellmanifest/metafile` at exact
  revision `58ddcbb380e4c3ba89ae33a403ddd8cfb6968abe`. Its source lives at
  `~/.config/urirun/scanner-delivery/packages/metafile-58ddcbb/src`.
  `URIRUN_METAFILE_SOURCE` can select this immutable source for isolated tests.
  The reference PDF writer is not used: it required PDF repair in validation.
- Existing Lenovo credentials resolved by the scanner connector. No credential
  is included in this deployment source.

## Installation layout

Install `reconcile.py` under `~/.config/urirun/scanner-ingress/` and `deliver.py`
under `~/.config/urirun/scanner-delivery/`. Install the five user units from
`systemd/` under `~/.config/systemd/user/`. They use `%h` for the user's home.
Preserve the existing `receipts.json`, `delivery.lock`, metadata model archive,
certificate files, host database and all documents when updating the scripts.
Do not run the workers from a Git checkout: their receipts belong in host state.

After reviewing the installed files, use `systemctl --user daemon-reload` and
enable the backend plus ingress and delivery timers. Ingress reconciliation runs
every 30 seconds; delivery runs every 15 seconds. The currently deployed scripts
continue serving while this source awaits independent protected publication.

To relinquish the listener, first disable the ingress timer, then run
`reconcile.py --remove`. Preserve the other Caddy routes. Only stop the backend
after its replacement is ready. Certificate renewal reuses the existing CA and
updates the two files in Caddy's persistent volume.

## Verification and logs

With the host's existing environment and pinned model source:

```sh
URIRUN_METAFILE_SOURCE="$HOME/.config/urirun/scanner-delivery/packages/metafile-58ddcbb/src" \
  "$HOME/github/if-uri/urirun/venv/bin/python" \
  -m unittest discover -s infra/scanner -p 'test_*.py'
bash project/governance-check.sh
```

The tests cover interrupted transfer, conflict protection, actual read-back
checksums, nested API failures, metadata/Unicode preservation, moved files,
unrelated Caddy routes and concurrent configuration changes.

Backend and transfer logs are in the user journal under the corresponding
service names. Caddy access logs are `/data/scanner8196/access.log` in its
persistent volume, rotated at 10 MB with three retained files. These are backend
and HTTP logs; they do not capture every phone browser console message.

Initial host validation delivered nine available PDF/JSON pairs, checked all
remote hashes and PDF metadata, and verified HTTPS, HTTP redirect and idle-peer
isolation. Stale historical index paths remain separately recorded. Physical
phone camera and CA installation were not observed.
