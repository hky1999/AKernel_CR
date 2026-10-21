"""Offline tests only: fake clients; importing the real SDK exception makes no RPC."""

import ast
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from adx_environment._transport import EnvironmentHTTPError
from probe_cleanup import OwnershipError, ProbeCleanup


REQUEST = 'create-5a9cded4-2cb3-4245-9afb-f62d53dff784'
SNAP = 'snapshot-' + 'a' * 64
UNRELATED = 'snapshot-03dcd988f0ce74d4569bcfcb5d6b35c6f874dc5e7ed12b9fcb8413efa42cfc12'
FORENSIC = 'snapshot-775a6194976b74ecbb411e3620b7ae55f8f5cfda4574c4b32f7e83faec631da8'


def sdk_error(environment_id=None, request_id=REQUEST):
    # Source-derived fixture, NOT a captured raw5a SSE payload. Unknown wire
    # fields/status are intentionally not asserted. This is the actual installed
    # SDK exception type with its supported structured identity attributes.
    payload = {'status': 'failed'}
    if environment_id:
        payload['environmentId'] = environment_id
    return EnvironmentHTTPError(503, payload, 'EXECD readiness: deadline exceeded',
                                environment_id=environment_id, request_id=request_id)


class FakeAPI:
    def __init__(self):
        self.deleted = []
        self.deleted_snapshots = []
        self.snapshots = []
        self.pages = None
        self.fail_delete = False
        self.fail_snapshot_delete = False

    def delete(self, environment_id, **kwargs):
        self.deleted.append(environment_id)
        if self.fail_delete:
            raise RuntimeError('delete failed')

    def delete_snapshot(self, snapshot_id, **kwargs):
        self.deleted_snapshots.append(snapshot_id)
        if self.fail_snapshot_delete:
            raise RuntimeError('snapshot delete failed')

    def list_snapshots(self, **kwargs):
        if self.pages:
            return self.pages(kwargs)
        return list(self.snapshots), ''


class FakeEnvironment:
    def __init__(self, name, on_snapshot=None):
        self.id = 'default-' + name
        self.closed = 0
        self.on_snapshot = on_snapshot

    def close(self):
        self.closed += 1

    def create_snapshot(self, **kwargs):
        return self.on_snapshot(**kwargs)


class CleanupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'journal.json'
        self.api = FakeAPI()
        self.journal = ProbeCleanup(self.api, object(), self.path, nonce='b' * 32)

    def failing_factory(self, **kwargs):
        raise sdk_error('default-' + kwargs['name'])

    def test_constructor_failure_before_assignment(self):
        with self.assertRaises(EnvironmentHTTPError):
            self.journal.create_environment('source', self.failing_factory)
        report = self.journal.finish()
        self.assertEqual(len(self.api.deleted), 1)
        self.assertEqual(report['retained'], [])
        self.assertTrue(report['primary_errors'])

    def test_actual_5a_id_and_request_context_is_cleanable(self):
        name = 'environment-5a9cded4-2cb3-4245-9afb-f62d53dff784'
        with patch.object(self.journal, '_environment_name', return_value=name):
            with self.assertRaises(EnvironmentHTTPError):
                self.journal.create_environment('fresh', self.failing_factory)
        self.journal.finish()
        self.assertEqual(self.api.deleted, ['default-' + name])

    def test_fresh_failure_cleans_all_three_roles_and_original_clients(self):
        source = self.journal.create_environment('source', lambda **kw: FakeEnvironment(kw['name']))
        clone = self.journal.create_environment('clone', lambda **kw: FakeEnvironment(kw['name']))
        with self.assertRaises(EnvironmentHTTPError):
            self.journal.create_environment('fresh', self.failing_factory)
        self.assertFalse(self.journal.finish()['retained'])
        self.assertEqual(len(set(self.api.deleted)), 3)
        self.assertEqual((source.closed, clone.closed), (1, 1))

    def test_intent_is_durable_before_constructor_and_id_before_return(self):
        def factory(**kwargs):
            saved = json.loads(self.path.read_text())['environments']['source']
            self.assertEqual(saved['state'], 'intent')
            self.assertEqual(saved['name'], kwargs['name'])
            self.assertIsNone(saved['id'])
            self.assertLess(len(kwargs['name']), len('environment-' + '0' * 36))
            return FakeEnvironment(kwargs['name'])
        obj = self.journal.create_environment('source', factory)
        self.assertEqual(json.loads(self.path.read_text())['environments']['source']['id'], obj.id)

    def test_request_only_unknown_outcome_is_retained(self):
        def factory(**kw):
            raise sdk_error(request_id=REQUEST)
        with self.assertRaises(EnvironmentHTTPError):
            self.journal.create_environment('fresh', factory)
        self.assertTrue(self.journal.finish()['retained'])
        self.assertEqual(self.api.deleted, [])

    def test_name_fallback_is_not_canonical_id_proof(self):
        def factory(**kw):
            raise sdk_error(kw['name'])
        with self.assertRaises(EnvironmentHTTPError):
            self.journal.create_environment('fresh', factory)
        self.assertTrue(self.journal.finish()['retained'])
        self.assertEqual(self.api.deleted, [])

    def test_foreign_exception_metadata_is_not_deleted(self):
        def factory(**kw):
            raise sdk_error('default-unrelated')
        with self.assertRaises(EnvironmentHTTPError):
            self.journal.create_environment('source', factory)
        self.assertTrue(self.journal.finish()['retained'])
        self.assertEqual(self.api.deleted, [])

    def test_conflicting_exception_chain_is_retained(self):
        def factory(**kw):
            outer = sdk_error('default-' + kw['name'])
            outer.__cause__ = sdk_error('default-foreign')
            raise outer
        with self.assertRaises(EnvironmentHTTPError):
            self.journal.create_environment('clone', factory)
        self.assertTrue(self.journal.finish()['retained'])
        self.assertEqual(self.api.deleted, [])

    def test_preexisting_id_is_excluded(self):
        expected = 'default-' + self.journal._environment_name('source')
        self.journal.preexisting.add(expected)
        with self.assertRaises(EnvironmentHTTPError):
            self.journal.create_environment('source', self.failing_factory)
        self.journal.finish()
        self.assertEqual(self.api.deleted, [])

    def test_environment_delete_failure_no_retry_and_original_failure_preserved(self):
        error = None
        try:
            self.journal.create_environment('source', self.failing_factory)
        except EnvironmentHTTPError as caught:
            error = caught
        self.assertIsNotNone(error)
        self.api.fail_delete = True
        first = self.journal.finish()
        self.journal.finish()
        self.assertTrue(first['retained'])
        self.assertTrue(first['cleanup_errors'])
        self.assertEqual(len(self.api.deleted), 1)
        self.assertIn('EXECD readiness', first['primary_errors'][0]['message'])

    def snapshot_source(self, fail=False):
        def create(**kwargs):
            saved = json.loads(self.path.read_text())['snapshot']
            self.assertTrue(saved['empty_preflight'])
            self.assertEqual(saved['state'], 'intent')
            value = SimpleNamespace(snapshot_id=SNAP, names=[kwargs['name']])
            self.api.snapshots.append(value)
            if fail:
                raise RuntimeError('snapshot published but response lost')
            return value
        return FakeEnvironment('owned', create)

    def test_snapshot_published_before_error_is_reconciled(self):
        with self.assertRaisesRegex(RuntimeError, 'response lost'):
            self.journal.create_snapshot(self.snapshot_source(fail=True), timeout_seconds=120)
        report = self.journal.finish()
        self.assertEqual(self.api.deleted_snapshots, [SNAP])
        self.assertFalse(report['retained'])
        self.assertTrue(report['primary_errors'])

    def test_unrelated_forensic_snapshots_are_never_deleted(self):
        self.api.snapshots = [SimpleNamespace(snapshot_id=UNRELATED, names=['a0-shared-fs']),
                              SimpleNamespace(snapshot_id=FORENSIC, names=['a0-shared-fs'])]
        self.journal.create_snapshot(self.snapshot_source())
        report = self.journal.finish()
        self.assertEqual(self.api.deleted_snapshots, [SNAP])
        self.assertEqual(set(report['preexisting_snapshot_ids_untouched']), {UNRELATED, FORENSIC})

    def test_missing_snapshot_after_unknown_result_is_unresolved(self):
        source = FakeEnvironment('owned', lambda **kw: (_ for _ in ()).throw(RuntimeError('lost')))
        with self.assertRaises(RuntimeError):
            self.journal.create_snapshot(source)
        report = self.journal.finish()
        self.assertTrue(report['retained'])
        self.assertTrue(report['cleanup_errors'])
        self.assertEqual(self.api.deleted_snapshots, [])

    def test_snapshot_delete_failure_has_one_attempt(self):
        self.journal.create_snapshot(self.snapshot_source())
        self.api.fail_snapshot_delete = True
        self.assertTrue(self.journal.finish()['retained'])
        self.journal.finish()
        self.assertEqual(self.api.deleted_snapshots, [SNAP])

    def test_ambiguous_nonce_matches_are_retained(self):
        self.journal.create_snapshot(self.snapshot_source())
        name = self.journal.data['snapshot']['name']
        self.api.snapshots.append(SimpleNamespace(snapshot_id='snapshot-' + 'c' * 64, names=[name]))
        self.assertTrue(self.journal.finish()['retained'])
        self.assertEqual(self.api.deleted_snapshots, [])

    def test_pagination_cycle_refuses_snapshot_creation(self):
        self.api.pages = lambda kw: ([], 'loop')
        with self.assertRaisesRegex(OwnershipError, 'cycle'):
            self.journal.create_snapshot(self.snapshot_source())
        self.assertFalse(self.journal.data['snapshot']['empty_preflight'])
        self.journal.finish()
        self.assertEqual(self.api.deleted_snapshots, [])

    def test_pagination_is_bounded(self):
        self.journal.max_pages = 2
        self.api.pages = lambda kw: ([], (kw['page_token'] or '') + 'n')
        with self.assertRaisesRegex(OwnershipError, 'bound'):
            self.journal.create_snapshot(self.snapshot_source())

    def test_existing_nonce_refuses_mutation(self):
        self.api.snapshots = [SimpleNamespace(snapshot_id=SNAP, names=['a1-snap-' + self.journal.nonce])]
        with self.assertRaisesRegex(OwnershipError, 'already exists'):
            self.journal.create_snapshot(self.snapshot_source())
        self.journal.finish()
        self.assertEqual(self.api.deleted_snapshots, [])

    def test_probe_preserves_all_11_functional_check_names(self):
        tree = ast.parse(Path(__file__).with_name('shared_fs_probe.py').read_text())
        names = {node.args[0].value for node in ast.walk(tree) if isinstance(node, ast.Call)
                 and isinstance(node.func, ast.Name) and node.func.id == 'passed'
                 and node.args and isinstance(node.args[0], ast.Constant)}
        self.assertEqual(len(names), 11)
        self.assertIn('fresh cold clone from original snapshot restored pre-snapshot payload', names)
        self.assertIn('clone writes independent; source continues with its own mutation', names)


if __name__ == '__main__':
    unittest.main()
