#!/usr/bin/env python3
"""PLF-031 host runtime: deliver verified scan pairs to Lenovo before routing."""
import base64
import datetime
import fcntl
import hashlib
import json
import os
import pathlib
import sys
import time
import urllib.request

DIRECTORY = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, os.environ.get('URIRUN_METAFILE_SOURCE', str(DIRECTORY/'packages/metafile-58ddcbb/src')))
INDEX = pathlib.Path.home() / '.urirun/documents/index.json'
ROOTS = [pathlib.Path.home() / '.urirun/documents',
         pathlib.Path.home() / 'Documents/Faktury/scan-input']
DEST = '/home/tom/Documents/Faktury'


def sha(data):
    return hashlib.sha256(data).hexdigest()


class Node:
    def __init__(self):
        from urirun_connector_scanner.document_sync import resolve_node_endpoint
        _, self.url, self.token = (
            resolve_node_endpoint('lenovo', 'http://192.168.188.201:8765')
        )

    def run(self, uri, payload):
        headers = {'Content-Type': 'application/json'}
        if self.token:
            headers['X-Urirun-Token'] = self.token
        request = urllib.request.Request(self.url+'/run',
            data=json.dumps({'uri': uri, 'payload': payload}).encode(), headers=headers)
        with urllib.request.urlopen(request, timeout=45) as response:
            result = json.load(response)
        value = result.get('value') or (result.get('result') or {}).get('value') or {}
        if not result.get('ok') or not value.get('ok'):
            raise RuntimeError(str(value.get('error') or result.get('error') or 'node operation failed'))
        return value

    def read(self, path):
        value = self.run('fs://laptop/file/query/read-b64', {'path': path, 'max_bytes': 50000000})
        data = base64.b64decode(value['bytes_b64'], validate=True)
        if sha(data) != value.get('sha256'):
            raise RuntimeError('Read-back response checksum mismatch')
        return data

    def ensure(self, path, data, expected_previous=None):
        try:
            previous = self.read(path)
        except RuntimeError as error:
            if 'not a file:' not in str(error):
                raise
            if expected_previous is not None:
                raise RuntimeError('Previously delivered file moved/missing; refusing to recreate: '+path)
        else:
            if previous == data:
                return
            if expected_previous is None or sha(previous) != expected_previous:
                raise RuntimeError('Destination conflict; refusing overwrite: '+path)
        result = self.run('fs://laptop/file/command/write-b64',
                          {'path': path, 'bytes_b64': base64.b64encode(data).decode(),
                           'overwrite': expected_previous is not None, 'make_dirs': True})
        if result.get('path') != path or result.get('sha256') != sha(data):
            raise RuntimeError('Destination or write checksum mismatch: '+path)
        if self.read(path) != data:
            raise RuntimeError('File read-back mismatch: '+path)


def prepare(pdf, sidecar):
    pdf, sidecar = pathlib.Path(pdf).resolve(), pathlib.Path(sidecar).resolve()
    if not any(pdf.is_relative_to(root.resolve()) and sidecar.is_relative_to(root.resolve()) for root in ROOTS):
        raise RuntimeError('Source is outside scanner archive/staging roots')
    if sidecar != pdf.with_suffix('.json'):
        raise RuntimeError('Metadata sidecar does not match PDF')
    before = [(p.stat().st_size, p.stat().st_mtime_ns) for p in (pdf, sidecar)]
    if any(time.time()-p.stat().st_mtime < 2 for p in (pdf, sidecar)):
        return None
    pdf_data, meta_data = pdf.read_bytes(), sidecar.read_bytes()
    meta = json.loads(meta_data)
    if not isinstance(meta, dict) or not meta.get('docId') or not pdf_data.startswith(b'%PDF-'):
        raise RuntimeError('Incomplete PDF/metadata pair')
    if before != [(p.stat().st_size, p.stat().st_mtime_ns) for p in (pdf, sidecar)]:
        raise RuntimeError('Source changed while reading; retry later')
    pair = sha((sha(pdf_data)+sha(meta_data)).encode())
    try:
        captured = datetime.datetime.fromisoformat(str(meta.get('createdAt', '')).replace('Z', '+00:00'))
    except ValueError:
        captured = datetime.datetime.fromtimestamp(pdf.stat().st_mtime, datetime.timezone.utc)
    remote = f'{DEST}/scan-{captured:%Y%m%d}-{pair[:16]}'
    return {'pair': pair, 'docId': meta['docId'], 'remote': remote, 'files':
            [(pdf.name, pdf_data), (sidecar.name, meta_data)]}


def embed_metadata(item):
    import fitz
    from wellmanifest_metafile import Metafile
    pdf_name, pdf_data = item['files'][0]
    meta = json.loads(item['files'][1][1])
    with fitz.open(stream=pdf_data, filetype='pdf') as doc:
        original_pages = [sha(page.get_pixmap().samples) for page in doc]
        kind, reference = doc.xref_get_key(-1, 'Info')
        if kind == 'xref':
            info = int(reference.split()[0])
        else:
            info = doc.get_new_xref()
            doc.update_object(info, '<<>>')
            doc.xref_set_key(-1, 'Info', f'{info} 0 R')
        for key, value in [('URIRUNMetadata', meta),
                           ('WellmanifestJSON', Metafile.from_dict(meta).to_dict())]:
            doc.xref_set_key(info, key, fitz.get_pdf_str(json.dumps(value, ensure_ascii=True, sort_keys=True)))
        enriched = doc.tobytes(garbage=0, deflate=False, no_new_id=True)
    with fitz.open(stream=enriched, filetype='pdf') as doc:
        if doc.is_repaired or original_pages != [sha(page.get_pixmap().samples) for page in doc]:
            raise RuntimeError('PDF metadata changed page rendering or requires repair')
        info = int(doc.xref_get_key(-1, 'Info')[1].split()[0])
        extracted = json.loads(doc.xref_get_key(info, 'URIRUNMetadata')[1])
        if extracted != meta:
            raise RuntimeError('Embedded PDF metadata round-trip mismatch')
    return {**item, 'files': [(pdf_name, enriched), item['files'][1]]}


def ready_data(doc_id, files):
    return json.dumps({'schema': 'scanner-delivery.ready/v1', 'docId': doc_id,
                       'files': files}, sort_keys=True).encode()+b'\n'


def transfer(node, item, previous=None):
    item = embed_metadata(item)
    for name, data in item['files']:
        if previous is None:
            node.ensure(item['remote']+'/'+name, data)
        else:
            node.ensure(item['remote']+'/'+name, data, expected_previous=previous['files'][name])
    hashes = {name: sha(data) for name, data in item['files']}
    marker = ready_data(item['docId'], hashes)
    if previous is None:
        node.ensure(item['remote']+'/.ready', marker)
    else:
        node.ensure(item['remote']+'/.ready', marker,
                    expected_previous=sha(ready_data(previous['docId'], previous['files'])))
    return {'directory': item['remote'], 'docId': item['docId'],
            'verifiedAt': datetime.datetime.now(datetime.timezone.utc).isoformat(),
            'metadataEmbedded': True, 'pageRenderingVerified': True, 'files': hashes}


def main():
    with (DIRECTORY/'delivery.lock').open('w') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return
        documents = json.loads(INDEX.read_text()).get('documents', [])
        state_path = DIRECTORY/'receipts.json'
        state = json.loads(state_path.read_text()) if state_path.exists() else {}
        node = Node()
        if node.read('/etc/hostname').decode().strip() != 'lenovo':
            raise RuntimeError('Remote node identity is not Lenovo')
        delivered, missing, failed = 0, 0, []
        for entry in documents:
            pdf, sidecar = entry.get('pdfPath'), entry.get('jsonPath')
            if not pdf or not sidecar or not pathlib.Path(pdf).is_file() or not pathlib.Path(sidecar).is_file():
                missing += 1
                continue
            try:
                item = prepare(pdf, sidecar)
                if item is None:
                    continue
                previous = state.get(item['pair'])
                if previous and previous.get('metadataEmbedded'):
                    continue
                state[item['pair']] = transfer(node, item, previous=previous)
                temporary = state_path.with_suffix('.tmp')
                temporary.write_text(json.dumps(state, indent=2)+'\n')
                temporary.chmod(0o600)
                temporary.replace(state_path)
                delivered += 1
                print(json.dumps({'event': 'scanner.delivered', 'destination': item['remote'],
                                  'verified': True}), flush=True)
            except Exception as error:
                failed.append({'source': pdf, 'error': str(error)})
        print(json.dumps({'event': 'scanner.delivery.completed', 'delivered': delivered,
                          'verifiedTotal': len(state), 'missingIndexPaths': missing,
                          'failed': failed}), flush=True)
        if failed:
            raise SystemExit(1)


if __name__ == '__main__':
    main()
