#!/usr/bin/env python3
"""PLF-030: preserve existing Caddy config and reconcile only our scanner listener."""
import argparse
import copy
import json
import pathlib
import urllib.request

API = 'http://127.0.0.1:2019/config/'
CERT = {'certificate': '/data/scanner8196/lan.pem',
        'key': '/data/scanner8196/lan-key.pem', 'tags': ['urirun-scanner8196']}


def listener(port):
    return {
        'listen': [f':{port}'],
        'listener_wrappers': [{'wrapper': 'http_redirect'}, {'wrapper': 'tls'}],
        'tls_connection_policies': [{'certificate_selection': {'any_tag': ['urirun-scanner8196']}}],
        'automatic_https': {'disable': True},
        'read_header_timeout': 10000000000,
        'idle_timeout': 60000000000,
        'logs': {'default_logger_name': 'urirun_scanner'},
        'routes': [{'handle': [{'handler': 'reverse_proxy',
            'upstreams': [{'dial': '127.0.0.1:18196'}],
            'transport': {'protocol': 'http', 'dial_timeout': 3000000000,
                          'response_header_timeout': 120000000000}}]}],
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8196)
    parser.add_argument('--canary', action='store_true')
    parser.add_argument('--remove', action='store_true')
    args = parser.parse_args()
    name = 'urirun_scanner8196_canary' if args.canary else 'urirun_scanner8196'
    wanted = listener(args.port)
    with urllib.request.urlopen(API, timeout=10) as response:
        old = json.load(response)
        etag = response.headers['Etag']
    config = copy.deepcopy(old)
    servers = config['apps']['http']['servers']
    present = servers.get(name)
    if present is not None and present != wanted:
        raise RuntimeError(f'Foreign change to owned listener {name}; refusing overwrite')
    if args.remove:
        servers.pop(name, None)
    else:
        for other, server in servers.items():
            if other != name and any(addr.rsplit(':', 1)[-1] == str(args.port)
                                     for addr in server.get('listen', [])):
                raise RuntimeError(f'Port belongs to another Caddy server: {other}')
        servers[name] = wanted
        certificates = config.setdefault('apps', {}).setdefault('tls', {}).setdefault('certificates', {})
        files = certificates.setdefault('load_files', [])
        if any('urirun-scanner8196' in item.get('tags', []) and item != CERT for item in files):
            raise RuntimeError('Foreign certificate under scanner tag; refusing overwrite')
        if CERT not in files:
            files.append(CERT)
        logs = config.setdefault('logging', {}).setdefault('logs', {})
        log = {'writer': {'output': 'file', 'filename': '/data/scanner8196/access.log',
                          'roll_size_mb': 10, 'roll_keep': 3},
               'include': ['http.log.access.urirun_scanner']}
        if 'urirun_scanner' in logs and logs['urirun_scanner'] != log:
            raise RuntimeError('Foreign change to scanner log; refusing overwrite')
        logs['urirun_scanner'] = log
    if config == old:
        return
    # One CAS request preserves unrelated configuration and refuses concurrent changes.
    request = urllib.request.Request(API, data=json.dumps(config).encode(), method='POST',
                                    headers={'Content-Type': 'application/json', 'If-Match': etag})
    with urllib.request.urlopen(request, timeout=15) as response:
        response.read()
    pathlib.Path(__file__).with_name('last-config.json').write_text(json.dumps(config, indent=2)+'\n')
    print(json.dumps({'event': 'scanner.ingress.reconciled', 'ticket': 'PLF-030',
                      'listener': name, 'port': args.port, 'removed': args.remove}))


if __name__ == '__main__':
    main()
