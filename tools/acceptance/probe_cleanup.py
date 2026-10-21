"""Ownership-journal cleanup for the private SDK probe, not a production API.

Environment IDs use the verified server contract in gateway/apiserver/src/
contract.rs:907: namespace + '-' + request name. The installed SDK fixes the
namespace to 'default'; authenticated tenant identity is a separate field.
Only bound return values or structured create errors can prove an environment
ID. A planned ID alone is never enough to delete an uncertain create.
"""

import json
import os
from pathlib import Path
import re
import uuid


class OwnershipError(RuntimeError):
    pass


def sanitized(value):
    value = re.sub(r'(?i)(bearer\s+)[^\s,\"}]+', r'\1[REDACTED]', str(value))
    return re.sub(r'(?i)((?:password|token|api_key|secret)[\"\s:=]+)[^\s,\"}]+',
                  r'\1[REDACTED]', value)


class ProbeCleanup:
    def __init__(self, api, connection, journal_path, *, nonce=None,
                 namespace='default', preexisting_environment_ids=(), max_pages=20):
        if namespace != 'default':
            raise OwnershipError('only the verified installed SDK namespace is supported')
        self.api, self.connection = api, connection
        self.path = Path(journal_path)
        if self.path.exists():
            raise OwnershipError('fresh cleanup journal required; do not replay mutations')
        self.nonce = nonce or uuid.uuid4().hex
        if not re.fullmatch(r'[0-9a-f]{32}', self.nonce) or max_pages < 1:
            raise ValueError('32-hex nonce and positive pagination bound required')
        self.namespace, self.max_pages = namespace, max_pages
        self.preexisting = set(preexisting_environment_ids)
        self.objects = {}
        self.data = {'version': 1, 'nonce': self.nonce, 'namespace': namespace,
                     'environments': {}, 'snapshot': None, 'primary_errors': [],
                     'cleanup_records': [], 'cleanup_errors': [],
                     'preexisting_snapshot_ids_untouched': []}
        self._sync()

    def _sync(self):
        temporary = self.path.with_name(self.path.name + '.' + uuid.uuid4().hex + '.tmp')
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'w') as stream:
            json.dump(self.data, stream, indent=2)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, self.path)
        fd = os.open(self.path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)

    def _environment_name(self, role):
        suffix = {'source': 's', 'clone': 'c', 'fresh': 'f'}[role]
        return 'a1-' + self.nonce + '-' + suffix

    @staticmethod
    def _metadata(error):
        pending, seen, rows = [error], set(), []
        while pending:
            current = pending.pop()
            if id(current) in seen:
                continue
            if len(seen) >= 16:
                raise OwnershipError('exception metadata chain exceeds bound')
            seen.add(id(current))
            row = {}
            for name in ('request_id', 'operation_id', 'environment_id', 'code', 'retry', 'outcome'):
                value = getattr(current, name, None)
                if isinstance(value, str) and value:
                    row[name] = sanitized(value)
            payload = getattr(current, 'payload', None)
            if isinstance(payload, dict):
                for source in (payload, payload.get('error')):
                    if isinstance(source, dict):
                        for name in ('requestId', 'operationId', 'environmentId'):
                            value = source.get(name)
                            if isinstance(value, str) and value:
                                row.setdefault(name, []).append(sanitized(value))
            rows.append(row)
            for name in ('__cause__', '__context__', 'error'):
                child = getattr(current, name, None)
                if isinstance(child, BaseException):
                    pending.append(child)
        return rows

    def record_primary(self, operation, error):
        try:
            metadata = self._metadata(error)
        except OwnershipError as failure:
            metadata = [{'unresolved': str(failure)}]
        self.data['primary_errors'].append({'operation': operation,
                                            'type': type(error).__name__,
                                            'message': sanitized(error), 'metadata': metadata})
        self._sync()
        return metadata

    def create_environment(self, role, factory):
        if role in self.data['environments']:
            raise OwnershipError('one create per role; retries are not cleanup')
        name = self._environment_name(role)
        expected = self.namespace + '-' + name
        record = {'role': role, 'name': name, 'planned_id_unproven': expected,
                  'id': None, 'proof': None, 'state': 'intent', 'delete_attempted': False}
        self.data['environments'][role] = record
        self._sync()  # Survives driver death before constructor assignment.
        try:
            obj = factory(name=name)
        except BaseException as error:
            rows = self.record_primary('create ' + role, error)
            ids, requests = set(), set()
            for row in rows:
                ids.update(row.get('environmentId', []))
                if row.get('environment_id'):
                    ids.add(row['environment_id'])
                requests.update(row.get('requestId', []))
                if row.get('request_id'):
                    requests.add(row['request_id'])
            ids.difference_update(('', 'unknown', name))  # SDK's name fallback is NOT an ID proof.
            request_ok = len(requests) == 1 and all(
                re.fullmatch(r'create-[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', value)
                for value in requests)
            if ids == {expected} and request_ok and expected not in self.preexisting:
                record.update(id=expected, proof='structured_error_bound_to_owned_name_and_request',
                              state='proven', request_ids=sorted(requests))
            else:
                record.update(state='unresolved', structured_ids=sorted(ids),
                              request_ids=sorted(requests))
            self._sync()
            raise  # Never replace the original constructor/fresh-create failure.
        actual = getattr(obj, 'id', None)
        if actual != expected or actual in self.preexisting:
            record.update(state='unresolved', returned_id=actual if isinstance(actual, str) else None)
            self._sync()
            raise OwnershipError('create return does not match owned name or was preexisting')
        self.objects[role] = obj
        record.update(id=actual, proof='authenticated_create_return_for_owned_name', state='proven')
        self._sync()  # Proven ID persists before caller's assignment.
        return obj

    def _matches(self, name):
        cursor, tokens, ids, matches = None, set(), set(), []
        for _ in range(self.max_pages):
            items, following = self.api.list_snapshots(
                name=name, page_token=cursor, page_size=100, connection=self.connection)
            if not isinstance(following, str):
                raise OwnershipError('invalid snapshot pagination metadata')
            for item in items:
                sid, names = getattr(item, 'snapshot_id', None), getattr(item, 'names', None)
                if (not isinstance(sid, str) or not re.fullmatch(r'snapshot-[0-9a-f]{64}', sid)
                        or not isinstance(names, (list, tuple))
                        or not all(isinstance(value, str) for value in names) or sid in ids):
                    raise OwnershipError('ambiguous or invalid snapshot metadata')
                ids.add(sid)
                if name in names:
                    matches.append(sid)
                elif sid not in self.data['preexisting_snapshot_ids_untouched']:
                    self.data['preexisting_snapshot_ids_untouched'].append(sid)
            if not following:
                return matches
            if following in tokens:
                raise OwnershipError('snapshot pagination cycle')
            tokens.add(following)
            cursor = following
        raise OwnershipError('snapshot pagination exceeded bound')

    def create_snapshot(self, environment, **kwargs):
        if self.data['snapshot'] is not None:
            raise OwnershipError('one snapshot intent per probe')
        name = 'a1-snap-' + self.nonce
        record = {'name': name, 'source_environment_id': environment.id,
                  'state': 'preflight', 'empty_preflight': False,
                  'id': None, 'delete_attempted': False}
        self.data['snapshot'] = record
        self._sync()
        try:
            if self._matches(name):
                raise OwnershipError('owned snapshot nonce already exists; refuse mutation')
            record.update(state='intent', empty_preflight=True)
            self._sync()
            result = environment.create_snapshot(name=name, **kwargs)
        except BaseException as error:
            self.record_primary('create snapshot', error)
            record['state'] = 'unknown_result' if record['empty_preflight'] else 'preflight_failed'
            self._sync()
            raise
        sid, names = getattr(result, 'snapshot_id', None), getattr(result, 'names', None)
        if (not isinstance(sid, str) or not re.fullmatch(r'snapshot-[0-9a-f]{64}', sid)
                or not isinstance(names, (list, tuple)) or name not in names):
            record['state'] = 'unresolved'
            self._sync()
            raise OwnershipError('snapshot return lacks exact owned nonce metadata')
        record.update(id=sid, state='proven', proof='bound_return_with_owned_nonce')
        self._sync()
        return result

    def _cleanup_error(self, step, error):
        self.data['cleanup_errors'].append({'step': step, 'error': sanitized(error)})
        self._sync()

    def delete_environment(self, role):
        record = self.data['environments'].get(role)
        if not record or not record.get('id'):
            return
        if record['delete_attempted']:
            if record['state'] != 'deleted':
                raise OwnershipError('prior environment deletion uncertain; no automatic retry')
            return
        record.update(delete_attempted=True, state='deleting')
        self._sync()
        failure = None
        try:
            self.api.delete(record['id'], connection=self.connection)
            record['state'] = 'deleted'
        except Exception as error:
            record['state'] = 'delete_failed'
            self._cleanup_error('delete environment ' + role, error)
            failure = error
        finally:
            obj = self.objects.pop(role, None)
            if obj is not None:
                try:
                    obj.close()  # Public SDK close releases clients, NOT the environment.
                except Exception as error:
                    self._cleanup_error('close local clients ' + role, error)
            self.data['cleanup_records'].append({'kind': 'environment', 'role': role,
                                                  'id': record['id'], 'state': record['state']})
            self._sync()
        if failure is not None:
            raise failure

    def delete_snapshot(self):
        record = self.data['snapshot']
        if record is None:
            return
        if record['delete_attempted']:
            if record['state'] != 'deleted':
                raise OwnershipError('prior snapshot deletion uncertain; no automatic retry')
            return
        if not record['empty_preflight']:
            raise OwnershipError('snapshot ownership has no empty nonce preflight')
        matches = self._matches(record['name'])
        if len(matches) != 1 or (record['id'] is not None and matches[0] != record['id']):
            record.update(state='unresolved', matched_ids=matches)
            self._sync()
            raise OwnershipError('snapshot unknown result or ambiguous nonce match; retain')
        record.update(id=matches[0], proof='unique_exact_nonce_match_after_empty_preflight',
                      delete_attempted=True, state='deleting')
        self._sync()
        try:
            self.api.delete_snapshot(record['id'], connection=self.connection)
            record['state'] = 'deleted'
        except Exception as error:
            record['state'] = 'delete_failed'
            self._cleanup_error('delete snapshot', error)
            raise
        finally:
            self.data['cleanup_records'].append({'kind': 'snapshot', 'id': record['id'],
                                                  'state': record['state']})
            self._sync()

    def finish(self):
        for role in ('fresh', 'clone', 'source'):
            record = self.data['environments'].get(role)
            if record and not record['delete_attempted']:
                try:
                    self.delete_environment(role)
                except Exception:
                    pass  # Already journaled; cannot mask the primary failure.
        record = self.data['snapshot']
        if record and not record['delete_attempted']:
            try:
                self.delete_snapshot()
            except Exception as error:
                self._cleanup_error('reconcile snapshot', error)
        retained = []
        for role, item in self.data['environments'].items():
            if item['state'] != 'deleted':
                retained.append('environment ' + role + ': ' + (item['id'] or item['name'])
                                + ' (' + item['state'] + ')')
        if record and record['state'] != 'deleted':
            retained.append('snapshot: ' + (record['id'] or record['name'])
                            + ' (' + record['state'] + ')')
        self.data['retained'] = retained
        self._sync()
        return {name: self.data[name] for name in (
            'cleanup_records', 'cleanup_errors', 'retained', 'primary_errors',
            'preexisting_snapshot_ids_untouched')}
