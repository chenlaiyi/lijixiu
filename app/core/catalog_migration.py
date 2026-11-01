"""Preserve address IDs while allowing catalog entries before store allocation."""
import re
import sqlite3


def migrate_catalog(path):
    if not path or path == ':memory:':
        return
    db = sqlite3.connect(path, timeout=30)
    try:
        row = db.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='store_addresses'").fetchone()
        if not row:
            return
        info = db.execute('PRAGMA table_info(store_addresses)').fetchall()
        if not next(c for c in info if c[1] == 'store_id')[3]:
            return
        sql = re.sub(r'\bstore_id\s+INTEGER\s+NOT NULL', 'store_id INTEGER', row[0], flags=re.I)
        if sql == row[0]:
            raise RuntimeError('Unsupported store_addresses schema; migration stopped')
        indexes = db.execute("SELECT sql FROM sqlite_master WHERE tbl_name='store_addresses' AND type='index' AND sql IS NOT NULL").fetchall()
        columns = ','.join('"' + c[1] + '"' for c in info)
        sequence = db.execute("SELECT seq FROM sqlite_sequence WHERE name='store_addresses'").fetchone() if db.execute("SELECT 1 FROM sqlite_master WHERE name='sqlite_sequence'").fetchone() else None
        db.execute('BEGIN IMMEDIATE')
        db.execute(sql.replace('store_addresses', 'catalog_addresses_migration', 1))
        db.execute(f'INSERT INTO catalog_addresses_migration ({columns}) SELECT {columns} FROM store_addresses')
        db.execute('DROP TABLE store_addresses')
        db.execute('ALTER TABLE catalog_addresses_migration RENAME TO store_addresses')
        for index in indexes:
            db.execute(index[0])
        if sequence:
            db.execute("UPDATE sqlite_sequence SET seq=MAX(seq,?) WHERE name='store_addresses'", sequence)
        if db.execute('PRAGMA foreign_key_check').fetchall():
            raise RuntimeError('Catalog migration foreign key check failed')
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
