import importlib.util
import pathlib
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('delivery', pathlib.Path(__file__).with_name('deliver.py'))
delivery = importlib.util.module_from_spec(spec)
spec.loader.exec_module(delivery)


class DeliveryTests(unittest.TestCase):
    def test_partial_delivery_never_publishes_ready_marker_and_can_resume(self):
        class Remote:
            def __init__(self):
                self.files = {}
                self.fail = True

            def ensure(self, path, data):
                if path.endswith('.json') and self.fail:
                    raise RuntimeError('Lenovo disconnected')
                if path in self.files:
                    self.assert_same(path, data)
                self.files[path] = data

            def assert_same(self, path, data):
                if self.files[path] != data:
                    raise RuntimeError('Conflict')

        remote = Remote()
        item = {'remote': '/scan-20261006-hash', 'docId': 'document',
                'files': [('document.pdf', b'%PDF-complete'), ('document.json', b'{"docId":"document"}')]}
        with patch.object(delivery, 'embed_metadata', side_effect=lambda x:x):
            with self.assertRaisesRegex(RuntimeError, 'disconnected'):
                delivery.transfer(remote, item)
        self.assertNotIn(item['remote']+'/.ready', remote.files)
        remote.fail = False
        with patch.object(delivery, 'embed_metadata', side_effect=lambda x:x):
            result = delivery.transfer(remote, item)
        self.assertIn(item['remote']+'/.ready', remote.files)
        self.assertEqual(len(remote.files), 3)
        self.assertEqual(result['files']['document.pdf'], delivery.sha(b'%PDF-complete'))

    def test_existing_foreign_file_is_not_overwritten(self):
        node = delivery.Node.__new__(delivery.Node)
        with patch.object(node, 'read', return_value=b'foreign'), patch.object(node, 'run') as run:
            with self.assertRaisesRegex(RuntimeError, 'refusing overwrite'):
                node.ensure('/scan-1/document.pdf', b'new')
            run.assert_not_called()

    def test_read_back_verifies_actual_bytes(self):
        node = delivery.Node.__new__(delivery.Node)
        with patch.object(node, 'run', return_value={'ok': True,
                          'bytes_b64': 'Y29ycnVwdA==', 'sha256': delivery.sha(b'expected')}):
            with self.assertRaisesRegex(RuntimeError, 'checksum mismatch'):
                node.read('/scan-1/document.pdf')

    def test_top_level_success_does_not_hide_nested_failure(self):
        import io
        node = delivery.Node.__new__(delivery.Node)
        node.url, node.token = 'http://lenovo', None
        response = io.BytesIO(b'{"ok":true,"result":{"value":{"ok":false,"error":"disk full"}}}')
        with patch.object(delivery.urllib.request, 'urlopen', return_value=response):
            with self.assertRaisesRegex(RuntimeError, 'disk full'):
                node.run('fs://laptop/file/command/write-b64', {})

    def test_metadata_embedding_is_valid_lossless_and_handles_unicode_parentheses(self):
        import fitz
        import json
        with fitz.open() as doc:
            doc.new_page().insert_text((50, 50), 'Original invoice page')
            data = doc.tobytes()
        meta = {'docId': 'test', 'contractor': 'Firma (Łódź)', 'amount':'1234.56',
                'currency':'PLN', 'date':'2026-10-06', 'text':'Opis (usługa)'}
        item = {'files': [('document.pdf',data),('document.json',json.dumps(meta).encode())]}
        first = delivery.embed_metadata(item)
        self.assertEqual(first['files'], delivery.embed_metadata(item)['files'])
        with fitz.open(stream=first['files'][0][1],filetype='pdf') as doc:
            self.assertFalse(doc.is_repaired)
            self.assertIn('Original invoice page', doc[0].get_text())
            info = int(doc.xref_get_key(-1,'Info')[1].split()[0])
            self.assertEqual(json.loads(doc.xref_get_key(info,'URIRUNMetadata')[1]),meta)

    def test_owned_migration_refuses_changed_or_moved_destination(self):
        node = delivery.Node.__new__(delivery.Node)
        with patch.object(node, 'read', return_value=b'changed'), patch.object(node,'run') as run:
            with self.assertRaisesRegex(RuntimeError,'refusing overwrite'):
                node.ensure('/scan-1/document.pdf',b'enriched',expected_previous=delivery.sha(b'original'))
            run.assert_not_called()
        with patch.object(node,'read',side_effect=RuntimeError('not a file: moved')):
            with self.assertRaisesRegex(RuntimeError,'refusing to recreate'):
                node.ensure('/scan-1/document.pdf',b'enriched',expected_previous=delivery.sha(b'original'))


if __name__ == '__main__':
    unittest.main()
