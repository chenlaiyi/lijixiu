from contextlib import closing
import sqlite3
import tempfile
import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.reset_business_data import reset_database


class BusinessResetTest(unittest.TestCase):
    def test_reset_retains_accounts_customer_details_and_rolls_back_on_invalid_refs(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'test.db'
            with closing(sqlite3.connect(path)) as conn, conn:
                conn.executescript('''
                CREATE TABLE users(id INTEGER PRIMARY KEY, name TEXT, referrer_id INTEGER REFERENCES users(id));
                CREATE TABLE regions(id INTEGER PRIMARY KEY);
                CREATE TABLE stores(id INTEGER PRIMARY KEY, region_id INTEGER REFERENCES regions(id));
                CREATE TABLE orders(id INTEGER PRIMARY KEY, store_id INTEGER REFERENCES stores(id));
                CREATE TABLE store_addresses(id INTEGER PRIMARY KEY, store_id INTEGER REFERENCES stores(id));
                CREATE TABLE service_areas(id INTEGER PRIMARY KEY);
                CREATE TABLE customer_addresses(id INTEGER PRIMARY KEY,user_id INTEGER REFERENCES users(id),
                  contact_name TEXT,contact_phone TEXT,address TEXT,is_default INTEGER,enabled INTEGER,
                  created_at TEXT,updated_at TEXT,region_id INTEGER REFERENCES regions(id),
                  service_address_id INTEGER REFERENCES store_addresses(id));
                INSERT INTO users VALUES(1,'customer',NULL),(2,'manager',NULL);
                INSERT INTO regions VALUES(1); INSERT INTO stores VALUES(1,1);
                INSERT INTO orders VALUES(1,1); INSERT INTO store_addresses VALUES(1,1);
                INSERT INTO service_areas VALUES(1);
                INSERT INTO customer_addresses VALUES(1,1,'client','19900000001','saved address',1,1,'before','before',1,1);
                ''')
            assert not reset_database(path).get('applied')
            with closing(sqlite3.connect(path)) as conn, conn:
                assert conn.execute('SELECT COUNT(*) FROM orders').fetchone()[0] == 1
                conn.execute('UPDATE users SET referrer_id=99 WHERE id=2')
            with self.assertRaises(AssertionError):
                reset_database(path, True)
            with closing(sqlite3.connect(path)) as conn, conn:
                assert conn.execute('SELECT COUNT(*) FROM orders').fetchone()[0] == 1
                conn.execute('UPDATE users SET referrer_id=NULL WHERE id=2')
            result = reset_database(path, True)
            assert result['retained_accounts'] == 2
            with closing(sqlite3.connect(path)) as conn, conn:
                assert conn.execute('SELECT COUNT(*) FROM stores').fetchone()[0] == 0
                assert conn.execute('SELECT COUNT(*) FROM orders').fetchone()[0] == 0
                assert conn.execute('SELECT address,region_id,service_address_id FROM customer_addresses').fetchone() == ('saved address',None,None)
                assert conn.execute('SELECT COUNT(*) FROM service_areas').fetchone()[0] == 1
                assert not conn.execute('PRAGMA foreign_key_check').fetchall()


if __name__ == '__main__':
    unittest.main()
