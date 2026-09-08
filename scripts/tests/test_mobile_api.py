import importlib.util
from pathlib import Path
import re
import unittest

spec = importlib.util.spec_from_file_location('mobile_api', Path(__file__).parents[1] / 'install_mobile_api.py')
api = importlib.util.module_from_spec(spec)
spec.loader.exec_module(api)


class MobileApiBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.capability = 'petrarca-mobile-' + 'a' * 64
        self.config = api.render(self.capability)

    def allowed(self, method, path):
        # Exercise the rendered nginx routing order, including method limits.
        for pattern, methods in re.findall(r'location ~ (\S+) \{\n.*?limit_except ([A-Z ]+) \{', self.config, re.S):
            if re.fullmatch(pattern.replace('(?<mobile_route>', '(?P<mobile_route>'), path):
                return method in methods.split()
        return False

    def test_native_read_write_and_query_endpoints(self):
        for method, path in [('GET', 'health'), ('GET', 'book/sync'), ('POST', 'book/sync'),
                             ('POST', 'curriculum/review/generate'), ('POST', 'explore/capture'),
                             ('POST', 'structural/grade'), ('GET', 'defender/sessions/abc-12')]:
            with self.subTest(path=path):
                self.assertTrue(self.allowed(method, '/' + self.capability + '/' + path))
        self.assertIn('$mobile_route$is_args$args', self.config)

    def test_no_anonymous_companion_admin_or_bulk_ingest_access(self):
        for path in ['/health', '/petrarca-private-' + 'a' * 64 + '/book/sync',
                     '/' + self.capability + '/admin/entity-queue',
                     '/' + self.capability + '/ingest-email',
                     '/' + self.capability + '/twitter/cookies',
                     '/' + self.capability + '/api/arbitrary',
                     '/' + self.capability + '/review/../admin/entity-queue']:
            with self.subTest(path=path):
                self.assertFalse(self.allowed('GET', path))
                self.assertFalse(self.allowed('POST', path))
        self.assertFalse(self.allowed('DELETE', '/' + self.capability + '/book/sync'))
        self.assertFalse(self.allowed('GET', '/' + self.capability + '/explore/capture'))

    def test_secret_validation_and_nginx_logging(self):
        with self.assertRaises(ValueError):
            api.render('invalid; nginx directive')
        self.assertNotIn('location ^~', self.config)
        self.assertEqual(self.config.count('location '), self.config.count('access_log off;'))
        self.assertEqual(self.config.count('location '), self.config.count('error_log /dev/null crit;'))


if __name__ == '__main__':
    unittest.main()
