"""Explicit SQLite business reset; accounts and customer contact/address text survive.

Default is a read-only plan. Stop this project's API and take a consistent backup
before using --apply. Never resets sqlite_sequence or touches uploaded files.
"""
import argparse
import json
import sqlite3
from pathlib import Path

KEEP = {'users', 'customer_addresses', 'user_role_grants', 'service_areas', 'alembic_version'}


def reset_database(path: Path, apply: bool = False):
    if not path.is_file():
        raise ValueError('Existing database file required')
    conn = sqlite3.connect(f'file:{path.as_posix()}?mode=rw', uri=True)
    conn.execute('PRAGMA foreign_keys=ON')
    tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")}
    if not {'users', 'orders', 'stores', 'customer_addresses'} <= tables:
        raise ValueError('Not a recognized xiulijiu database')
    counts = {table: conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0] for table in sorted(tables)}
    plan = {'retained_tables': sorted(tables & KEEP), 'clear_counts': {t: counts[t] for t in sorted(tables - KEEP)}}
    if not apply:
        conn.close()
        return plan
    users_before = conn.execute('SELECT * FROM users ORDER BY id').fetchall()
    customer_before = conn.execute('SELECT id,user_id,contact_name,contact_phone,address,is_default,enabled,created_at,updated_at FROM customer_addresses ORDER BY id').fetchall()
    try:
        conn.execute('BEGIN IMMEDIATE')
        conn.execute('PRAGMA defer_foreign_keys=ON')
        # Preserve the customer's own address text; remove references to deleted business rows.
        conn.execute('UPDATE customer_addresses SET region_id=NULL,service_address_id=NULL')
        for table in sorted(tables - KEEP):
            conn.execute(f'DELETE FROM "{table}"')
        assert conn.execute('SELECT * FROM users ORDER BY id').fetchall() == users_before
        assert conn.execute('SELECT id,user_id,contact_name,contact_phone,address,is_default,enabled,created_at,updated_at FROM customer_addresses ORDER BY id').fetchall() == customer_before
        assert not conn.execute('PRAGMA foreign_key_check').fetchall(), 'Foreign-key verification failed'
        assert all(conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0] == 0 for table in tables - KEEP)
        conn.commit()
        plan['applied'] = True
        plan['retained_accounts'] = len(users_before)
        plan['retained_customer_addresses'] = len(customer_before)
        return plan
    except BaseException:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', type=Path, required=True)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    print(json.dumps(reset_database(args.database.resolve(), args.apply), ensure_ascii=False))
