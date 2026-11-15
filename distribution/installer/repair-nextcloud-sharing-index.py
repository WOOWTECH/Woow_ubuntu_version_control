#!/usr/bin/env python3
"""Review-gated cleanup of one empty legacy sharing table on Nextcloud 35.0.3.

Not a general schema repair tool. A full database/application backup is required.
Official source: nextcloud/server@52a07c0b16ec1dd622003af9c4cbbb3429c64e08.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess

os.umask(0o077)
p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--app', default='nextcloud-app')
p.add_argument('--db', default='nextcloud-db')
p.add_argument('--backup', type=Path, required=True)
p.add_argument('--apply', action='store_true')
a = p.parse_args()
table = 'oc_sharing_share_recipients'
index = 'uniq_734621b62ae63fdb4185a14495a838f'

def run(args):
    return subprocess.run(args, check=True, capture_output=True, text=True).stdout.strip()

def occ(*args):
    return run(['podman', 'exec', '-u', 'www-data', a.app, 'php', 'occ', *args])

def sql(query):
    return run(['podman', 'exec', a.db, 'psql', '-Unextcloud', '-dnextcloud', '-vON_ERROR_STOP=1', '-Atqc', query])

assert json.loads(occ('status', '--output=json'))['versionstring'] == '35.0.3'
assert occ('config:app:get', 'sharing', 'installed_version') == '1.0.5'
expected = json.loads(occ('db:schema:expected', table, '--output=json'))[table]['indexes']
assert index not in expected
assert expected[table + '_pkey']['columns'] == ['id']
assert expected['uniq_734621b645af3a']['columns'] == ['recipient_secret']
assert expected['uniq_734621b645af3a']['unique']
assert sql('SELECT count(*) FROM ' + table) == '0', 'Nonempty table requires separate review'
check = subprocess.run(['podman', 'exec', '-u', 'www-data', a.app, 'php', 'occ', 'db:schema:check', '--output=json'], capture_output=True, text=True)
findings = json.loads(check.stdout)
if not findings:
    print(json.dumps({'passed': True, 'already_clean': True}))
    raise SystemExit(0)
assert len(findings) == 1 and findings[0]['table'] == table and findings[0]['name'] == index and findings[0]['type'] == 'unexpected_index', findings
definition = sql("SELECT indexdef FROM pg_indexes WHERE schemaname='public' AND tablename='" + table + "' AND indexname='" + index + "'")
assert definition == 'CREATE UNIQUE INDEX ' + index + ' ON public.' + table + ' USING btree (share_id, recipient_class_id, recipient_value)'
assert sql("SELECT count(*) FROM pg_constraint WHERE conindid='" + index + "'::regclass") == '0'
other = sql("SELECT indexname || ':' || indexdef FROM pg_indexes WHERE tablename='" + table + "' AND indexname <> '" + index + "' ORDER BY indexname")
assert all(name in other for name in expected)
constraints = sql("SELECT oid::text || ':' || pg_get_constraintdef(oid) FROM pg_constraint WHERE conrelid='" + table + "'::regclass OR confrelid='" + table + "'::regclass ORDER BY oid")
if not a.apply:
    print(json.dumps({'preview': True, 'empty_table': True, 'drop_index': index, 'other_constraints_preserved': True}))
    raise SystemExit(0)
assert all((a.backup / name).is_file() for name in ('html.tgz', 'data.tgz', 'config.tgz', 'nextcloud.pgdump', 'roles.sql', 'SHA256SUMS'))
subprocess.run(['sha256sum', '-c', '--quiet', 'SHA256SUMS'], cwd=a.backup, check=True)
saved = a.backup.parent / 'sharing-legacy-index-rollback.sql'
saved.write_text(definition + ';\n')
# The row/constraint checks also run inside the lock: concurrent inserts cannot
# turn an empty-table-only repair into a change to a populated table.
statement = """BEGIN;
SET LOCAL lock_timeout = '10s';
LOCK TABLE oc_sharing_share_recipients IN ACCESS EXCLUSIVE MODE;
DO $$ BEGIN
 IF EXISTS (SELECT 1 FROM oc_sharing_share_recipients) THEN
  RAISE EXCEPTION 'Sharing table changed; repair refused';
 END IF;
 IF EXISTS (SELECT 1 FROM pg_constraint WHERE conindid='uniq_734621b62ae63fdb4185a14495a838f'::regclass) THEN
  RAISE EXCEPTION 'Index is constraint-owned; repair refused';
 END IF;
END $$;
DROP INDEX public.uniq_734621b62ae63fdb4185a14495a838f;
COMMIT;"""
sql(statement)
try:
    assert sql("SELECT indexname || ':' || indexdef FROM pg_indexes WHERE tablename='" + table + "' ORDER BY indexname") == other
    assert sql("SELECT oid::text || ':' || pg_get_constraintdef(oid) FROM pg_constraint WHERE conrelid='" + table + "'::regclass OR confrelid='" + table + "'::regclass ORDER BY oid") == constraints
    assert json.loads(occ('db:schema:check', '--output=json')) == []
except BaseException:
    sql(definition)
    raise
print(json.dumps({'passed': True, 'schema_findings': [], 'empty_legacy_table': True, 'only_obsolete_index_removed': index, 'other_indexes_primary_and_foreign_keys_preserved': True, 'rollback_ddl_sha256': hashlib.sha256(saved.read_bytes()).hexdigest()}))
