import io
import json
import sys
import unittest
import urllib.error
from unittest.mock import patch

import reconcile


class Response(io.BytesIO):
    def __init__(self, config):
        super().__init__(json.dumps(config).encode())
        self.headers = {'Etag': '"observed-revision"'}


class IngressTests(unittest.TestCase):
    def test_single_cas_update_preserves_existing_routes_and_uses_tls_ingress(self):
        original = {'apps': {'http': {'servers': {'existing': {
            'listen': [':80'], 'routes': [{'unrelated': 'preserve'}]}}}}}
        requests = []

        def api(request, timeout):
            requests.append(request)
            return Response(original if isinstance(request, str) else {})

        with patch.object(sys, 'argv', ['reconcile.py']), \
             patch.object(reconcile.urllib.request, 'urlopen', side_effect=api), \
             patch.object(reconcile.pathlib.Path, 'write_text'):
            reconcile.main()
        self.assertEqual(len(requests), 2)
        update = requests[1]
        self.assertEqual(update.method, 'POST')
        self.assertEqual(update.get_header('If-match'), '"observed-revision"')
        config = json.loads(update.data)
        servers = config['apps']['http']['servers']
        self.assertEqual(servers['existing'], original['apps']['http']['servers']['existing'])
        scanner = servers['urirun_scanner8196']
        self.assertEqual(scanner['listener_wrappers'],
                         [{'wrapper': 'http_redirect'}, {'wrapper': 'tls'}])
        self.assertEqual(scanner['routes'][0]['handle'][0]['upstreams'],
                         [{'dial': '127.0.0.1:18196'}])

    def test_foreign_listener_change_is_preserved_without_post(self):
        foreign = reconcile.listener(8196)
        foreign['listen'] = [':18197']
        config = {'apps': {'http': {'servers': {'urirun_scanner8196': foreign}}}}
        with patch.object(sys, 'argv', ['reconcile.py']), \
             patch.object(reconcile.urllib.request, 'urlopen', return_value=Response(config)) as api:
            with self.assertRaisesRegex(RuntimeError, 'Foreign change'):
                reconcile.main()
        self.assertEqual(api.call_count, 1)

    def test_port_already_owned_by_another_server_is_not_stolen(self):
        config = {'apps': {'http': {'servers': {'foreign': {'listen': [':8196']}}}}}
        with patch.object(sys, 'argv', ['reconcile.py']), \
             patch.object(reconcile.urllib.request, 'urlopen', return_value=Response(config)) as api:
            with self.assertRaisesRegex(RuntimeError, 'belongs to another'):
                reconcile.main()
        self.assertEqual(api.call_count, 1)

    def test_concurrent_config_change_rejects_update_and_persists_no_receipt(self):
        config = {'apps': {'http': {'servers': {}}}}
        conflict = urllib.error.HTTPError(reconcile.API, 412, 'precondition failed', {}, None)
        with patch.object(sys, 'argv', ['reconcile.py']), \
             patch.object(reconcile.urllib.request, 'urlopen',
                          side_effect=[Response(config), conflict]), \
             patch.object(reconcile.pathlib.Path, 'write_text') as persist:
            with self.assertRaises(urllib.error.HTTPError):
                reconcile.main()
        persist.assert_not_called()


if __name__ == '__main__':
    unittest.main()
