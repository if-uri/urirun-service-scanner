from __future__ import annotations

import argparse
import json
import os
import sys
from http.server import ThreadingHTTPServer
from typing import Sequence

from urirun.host import host_dashboard

SERVICE_ID = "scanner"
DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 8196
DEFAULT_CERT = "~/.urirun/certs/urirun-dashboard.crt"
DEFAULT_KEY = "~/.urirun/certs/urirun-dashboard.key"


def _env_int(name: str, default: int) -> int:
    value = os.environ.get(name)
    if not value:
        return default
    return int(value)


def default_host() -> str:
    return os.environ.get("URIRUN_PHONE_SCANNER_HOST", DEFAULT_HOST)


def default_port() -> int:
    return _env_int("URIRUN_PHONE_SCANNER_PORT", DEFAULT_PORT)


def service_manifest() -> dict:
    return {
        "id": SERVICE_ID,
        "kind": "service",
        "name": "urirun-service-scanner",
        "label": "urirun phone document scanner",
        "defaultHost": DEFAULT_HOST,
        "defaultPort": DEFAULT_PORT,
        "env": {
            "host": "URIRUN_PHONE_SCANNER_HOST",
            "port": "URIRUN_PHONE_SCANNER_PORT",
            "tlsCert": "URIRUN_PHONE_SCANNER_TLS_CERT",
            "tlsKey": "URIRUN_PHONE_SCANNER_TLS_KEY",
            "interval": "URIRUN_PHONE_SCANNER_INTERVAL",
        },
        "routes": [
            "dashboard://host/phone-scanner/command/start",
            "dashboard://host/service/phone-scanner/command/restart",
            "service://host/phone-scanner/command/restart",
            "service://phone-scanner/command/restart",
            "scanner://page/camera/command/scan",
            "scanner://page/camera/command/best-pdf",
            "scanner://page/camera/command/autonomous",
            "scanner://host/capture/command/save",
        ],
        "http": {
            "index": "/scanner",
            "api": [
                "/api/scanner/capture",
                "/api/scanner/best/finish",
                "/api/scanner/session",
                "/api/scanner/live",
                "/api/page/actions/poll",
                "/api/page/actions/result",
                "/api/uri/invoke",
            ],
        },
    }


def urirun_service() -> dict:
    return service_manifest()


def _public_host_for_url(bind_host: str) -> str:
    clean = (bind_host or "").strip("[]")
    if clean in {"", "0.0.0.0", "::"}:
        return host_dashboard._lan_host()
    return clean


def scanner_url(host: str | None = None, port: int | None = None, *, https: bool = True) -> str:
    scheme = "https" if https else "http"
    url_host = host_dashboard._url_host(_public_host_for_url(host or default_host()))
    return host_dashboard._scanner_page_url(f"{scheme}://{url_host}:{int(port or default_port())}/scanner")


def serve(
    *,
    project: str = ".",
    db: str | None = None,
    config: str | None = None,
    host: str | None = None,
    port: int | None = None,
    node_urls: list[str] | None = None,
    token: str | None = None,
    identity: str | None = None,
    tls_cert: str | None = None,
    tls_key: str | None = None,
    https: bool = True,
    startup_qr: bool = False,
    qr_url: str | None = None,
    replace: bool = True,
    force_replace: bool = False,
) -> ThreadingHTTPServer:
    bind_port = int(port or default_port())
    replace_result = None
    if replace:
        replace_result = host_dashboard._free_port_from_old_scanner(bind_port, force=force_replace, emit=True)
        if not replace_result.get("ok"):
            raise OSError(
                "port is already in use by a non-scanner process; "
                f"port={bind_port} replace={json.dumps(replace_result, sort_keys=True)}"
            )
    cert = tls_cert or os.environ.get("URIRUN_PHONE_SCANNER_TLS_CERT", DEFAULT_CERT)
    key = tls_key or os.environ.get("URIRUN_PHONE_SCANNER_TLS_KEY", DEFAULT_KEY)
    if https:
        cert, key = host_dashboard._ensure_tls_cert(cert, key)
    else:
        cert, key = None, None
    server = host_dashboard.serve(
        project=project,
        db=db,
        config=config,
        host=host or default_host(),
        port=bind_port,
        node_urls=node_urls,
        token=token or os.environ.get("URIRUN_NODE_TOKEN"),
        identity=identity,
        tls_cert=cert,
        tls_key=key,
        startup_qr=startup_qr,
        qr_url=qr_url,
    )
    setattr(server, "urirun_replace", replace_result)
    return server


def _add_common_args(parser: argparse.ArgumentParser, *, allow_no_replace: bool = True) -> None:
    parser.add_argument("--project", default=".", help="planfile/project directory")
    parser.add_argument("--db", default=None, help="host SQLite db path; default follows urirun")
    parser.add_argument("--config", default=None, help="host mesh config path")
    parser.add_argument("--host", default=None, help=f"bind host; default {DEFAULT_HOST} or URIRUN_PHONE_SCANNER_HOST")
    parser.add_argument("--port", type=int, default=None, help=f"bind port; default {DEFAULT_PORT} or URIRUN_PHONE_SCANNER_PORT")
    parser.add_argument("--node-url", action="append", default=None, help="temporarily add NAME=URL node; repeatable")
    parser.add_argument("--token", default=None, help="X-Urirun-Token for auth-gated nodes")
    parser.add_argument("--identity", default=None, help="SSH private key used to sign /run calls")
    parser.add_argument("--tls-cert", default=None, help="TLS certificate file")
    parser.add_argument("--tls-key", default=None, help="TLS private key file")
    parser.add_argument("--http", action="store_true", help="serve HTTP instead of HTTPS; useful only for local tests")
    if allow_no_replace:
        parser.add_argument("--no-replace", action="store_true", help="do not replace an older scanner process holding the same port")
    parser.add_argument("--force-replace", action="store_true", help="allow replacing any process holding the scanner port; use only in controlled dev environments")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="urirun-service-scanner")
    sub = parser.add_subparsers(dest="command")

    serve_parser = sub.add_parser("serve", help="serve the phone scanner")
    _add_common_args(serve_parser)
    serve_parser.add_argument("--startup-qr", action="store_true", help="add a scanner QR message on startup")
    serve_parser.add_argument("--qr-url", default=None, help="scanner URL encoded into startup QR")

    restart_parser = sub.add_parser("restart", help="replace any older scanner on the port, then serve")
    _add_common_args(restart_parser, allow_no_replace=False)
    restart_parser.add_argument("--startup-qr", action="store_true", help="add a scanner QR message on startup")
    restart_parser.add_argument("--qr-url", default=None, help="scanner URL encoded into startup QR")

    url_parser = sub.add_parser("url", help="print the scanner URL")
    url_parser.add_argument("--host", default=None)
    url_parser.add_argument("--port", type=int, default=None)
    url_parser.add_argument("--http", action="store_true")

    sub.add_parser("manifest", help="print the service manifest")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    command = args.command or "serve"

    if command == "manifest":
        print(json.dumps(service_manifest(), indent=2, sort_keys=True))
        return 0
    if command == "url":
        print(scanner_url(args.host, args.port, https=not bool(args.http)))
        return 0
    if command in {"serve", "restart"}:
        try:
            server = serve(
                project=args.project,
                db=args.db,
                config=args.config,
                host=args.host,
                port=args.port,
                node_urls=args.node_url,
                token=args.token,
                identity=args.identity,
                tls_cert=args.tls_cert,
                tls_key=args.tls_key,
                https=not bool(args.http),
                startup_qr=bool(getattr(args, "startup_qr", False)),
                qr_url=getattr(args, "qr_url", None),
                replace=command == "restart" or not bool(getattr(args, "no_replace", False)),
                force_replace=bool(getattr(args, "force_replace", False)),
            )
        except OSError as exc:
            print(json.dumps({
                "ok": False,
                "event": "urirun.service_scanner.start_failed",
                "error": str(exc),
                "host": args.host or default_host(),
                "port": int(args.port or default_port()),
            }, sort_keys=True), file=sys.stderr)
            return 1
        url = scanner_url(args.host, args.port, https=not bool(args.http))
        print(json.dumps({
            "event": "urirun.service_scanner.ready",
            "url": url,
            "replace": getattr(server, "urirun_replace", None),
        }, sort_keys=True), flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            return 130
        return 0

    parser.error(f"unknown command: {command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
