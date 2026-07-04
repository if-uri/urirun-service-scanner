# urirun-service-scanner

Standalone phone scanner service for urirun.

This package moves the scanner runtime behind a service package boundary, while
still reusing the existing scanner page and capture API from
`urirun.host.host_dashboard`. It is intended to run beside
`urirun-service-chat`, not inside it.

The scanner participates in the dashboard chat flow described in
`/home/tom/github/if-uri/urirun/docs/HOST_DASHBOARD_CHAT.md`. The resulting
document archive, `index.json` and `scanned.id.jsonl` are documented in
`/home/tom/github/if-uri/urirun/docs/DOCUMENT_ARCHIVE.md`.

## Defaults

- service id: `scanner`
- default port: `8196`
- default bind: `0.0.0.0`
- default scheme: HTTPS, because phone camera access normally requires a secure
  browser context
- env port override: `URIRUN_PHONE_SCANNER_PORT`
- env host override: `URIRUN_PHONE_SCANNER_HOST`

The scanner URL includes the existing autonomous defaults:

```text
autostart=1&auto=1&best=1&count=6&minScore=45&interval=3
```

## Run

```bash
urirun-service-scanner serve --project /home/tom/github/if-uri/urirun --db ~/.urirun/host.db
```

Then open the printed `/scanner` URL from a phone on the same LAN.

`serve` replaces an older `urirun-service-scanner` process that is still
listening on the same port, so a stale `8196` holder does not fail with
`Address already in use`. Use `--no-replace` to disable that behavior, or
`--force-replace` only in a controlled development environment when the port is
known to be disposable.

You can also spell the intent explicitly:

```bash
urirun-service-scanner restart --project /home/tom/github/if-uri/urirun --db ~/.urirun/host.db --port 8196
```

For local HTTP-only testing:

```bash
urirun-service-scanner serve --http --host 127.0.0.1
```

## URI surface

The scanner service exposes the same scanner API as the current host dashboard:

- `/scanner`
- `/api/scanner/capture`
- `/api/scanner/best/finish`
- `/api/scanner/session`
- `/api/scanner/live`
- `/api/page/actions/poll`
- `/api/page/actions/result`
- `/api/uri/invoke`

Page-level camera actions are intentionally queued. The browser page polls them
and reports completion. This lets chat send URI actions such as autonomous scan
or torch toggle while still respecting browser camera permissions.

The host dashboard can also restart the scanner service through URI:

```text
dashboard://host/service/phone-scanner/command/restart
service://host/phone-scanner/command/restart
```

For a supervised service, configure one of:

```bash
export URIRUN_PHONE_SCANNER_RESTART_MANAGER=systemd
export URIRUN_PHONE_SCANNER_SYSTEMD_UNIT=urirun-service-scanner.service
```

or:

```bash
export URIRUN_PHONE_SCANNER_RESTART_CMD='systemctl --user restart urirun-service-scanner.service'
```

Then invoke from the chat dashboard:

```bash
curl -s http://127.0.0.1:8194/api/uri/invoke \
  -H 'content-type: application/json' \
  -d '{"uri":"service://host/phone-scanner/command/restart","mode":"execute"}'
```

If the scanner was started in-process by `dashboard://host/phone-scanner/command/start`,
the dashboard can restart that in-process server directly. If port `8196` is held by
an older `urirun-service-scanner` process, urirun terminates that old scanner and
starts a fresh one. If the port is owned by an unrelated process, urirun refuses
unless the URI payload explicitly includes `"forcePortKill": true`.

The service manifest is available from Python:

```python
from urirun_service_scanner import urirun_service

print(urirun_service())
```
