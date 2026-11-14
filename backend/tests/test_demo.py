from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from backend import demo
from database.connection import connect


class DemoTest(unittest.TestCase):
    def test_seed_assigns_one_person_to_each_position(self):
        with TemporaryDirectory(dir=Path(__file__).resolve().parents[2]) as directory:
            path=Path(directory)/"demo.sqlite3"
            with patch.object(demo,"DEMO_DB",path):
                demo.seed()
                demo.seed()
            db=connect(path)
            try:
                self.assertEqual(db.execute("""SELECT COUNT(*) FROM
                    (SELECT shift_id FROM attendance GROUP BY shift_id HAVING COUNT(*)>1)""").fetchone()[0],0)
                self.assertEqual(db.execute("SELECT COUNT(*) FROM weekly_slots").fetchone()[0],8)
                for shop in (1,2):
                    slots=db.execute("SELECT slot FROM weekly_slots WHERE shop_id=?",(shop,)).fetchall()
                    self.assertEqual({row["slot"] for row in slots},{"morning","afternoon","evening","split"})
            finally:
                db.close()
