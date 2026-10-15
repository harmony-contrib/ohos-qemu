"""Actual production builder SQL against a populated, persistent SQLite database.

This verifies relational data/index behavior, not OHOS VISITOR/ACL/HAP acceptance.
"""
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[2]
COMPONENT = REPO/'patches/common/foundation/multimedia/media_library/knowledge_content'

# These column/primary-key contracts are pinned in media_column.cpp,
# vision_db_sqls.h and vision_portrait_nickname_column.h. Deliberately omit
# cascades: stale producer rows must never bypass a missing/hidden asset.
SCHEMA = '''
CREATE TABLE Photos(file_id INTEGER PRIMARY KEY,date_year TEXT,date_month TEXT,date_day TEXT,
 media_type INTEGER DEFAULT 1,sync_status INTEGER DEFAULT 0,clean_flag INTEGER DEFAULT 0,
 hidden INTEGER DEFAULT 0,date_trashed INTEGER DEFAULT 0,time_pending INTEGER DEFAULT 0,
 is_temp INTEGER DEFAULT 0,is_critical INTEGER DEFAULT 0,burst_cover_level INTEGER DEFAULT 1);
CREATE TABLE AnalysisAlbum(album_id INTEGER PRIMARY KEY,album_subtype INTEGER,album_name TEXT);
CREATE TABLE AnalysisPhotoMap(map_album INTEGER,map_asset INTEGER,order_position INTEGER,
 PRIMARY KEY(map_album,map_asset));
CREATE TABLE tab_analysis_nick_name(album_id INTEGER NOT NULL,nick_name TEXT NOT NULL);
CREATE UNIQUE INDEX idx_analysis_nick_name_album_id_nick_name
 ON tab_analysis_nick_name(album_id,nick_name);
CREATE INDEX idx_photo_date_day ON Photos(date_day);
'''


class KnowledgeContentQueryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler=shutil.which('clang++')
        if not compiler:raise unittest.SkipTest('clang++ required')
        cls.scratch=tempfile.TemporaryDirectory(prefix='batch-media-knowledge-')
        cls.binary=Path(cls.scratch.name)/'knowledge-query'
        cls.env={**os.environ,'ASAN_OPTIONS':('detect_leaks=1' if sys.platform.startswith('linux') else 'detect_leaks=0'),
                 'UBSAN_OPTIONS':'halt_on_error=1'}
        command=[compiler,'-std=c++17','-Wall','-Wextra','-Werror','-fsanitize=address,undefined',
                 '-fno-sanitize-recover=all','-g','-I'+str(COMPONENT/'files'),
                 str(COMPONENT/'files/knowledge_content_query.cpp'),
                 str(REPO/'ci/capability-audit/batch_media_knowledge_query_cli.cpp'),'-o',str(cls.binary)]
        subprocess.run(command,check=True,capture_output=True,text=True,env=cls.env)

    @classmethod
    def tearDownClass(cls):cls.scratch.cleanup()

    def setUp(self):
        self.directory=tempfile.TemporaryDirectory(prefix='batch-media-knowledge-db-')
        self.path=Path(self.directory.name)/'gallery.db'
        self.db=sqlite3.connect(self.path)
        self.db.executescript(SCHEMA)
        for asset in range(1,13):
            self.db.execute('INSERT INTO Photos(file_id,date_year,date_month,date_day) VALUES(?,?,?,?)',
                (asset,'2026','202610','20261016' if asset!=3 else '20261017'))
        excluded={4:('hidden',1),5:('date_trashed',999),6:('time_pending',1),7:('is_temp',1),
                  8:('is_critical',1),9:('clean_flag',1),10:('sync_status',1),11:('burst_cover_level',0),12:('media_type',999)}
        for asset,(column,value) in excluded.items():self.db.execute(f'UPDATE Photos SET {column}=? WHERE file_id=?',(value,asset))
        self.db.executemany('INSERT INTO AnalysisAlbum VALUES(?,?,?)',
            [(101,4102,'Ranger'),(102,4102,'Ranger'),(201,4097,'海边'),(301,4100,'上海')])
        for asset in range(1,13):
            for album in [102 if asset==3 else 101,201,301]:
                self.db.execute('INSERT INTO AnalysisPhotoMap VALUES(?,?,0)',(album,asset))
        self.db.executemany('INSERT INTO tab_analysis_nick_name VALUES(?,?)',[(101,'张三'),(101,'Ranger'),(101,'海风')])
        self.db.commit()

    def tearDown(self):self.db.close();self.directory.cleanup()

    def plan(self,*args):
        result=subprocess.run([str(self.binary),*args],env=self.env,check=True,capture_output=True,text=True)
        return json.loads(result.stdout)

    def query(self,*args):
        plan=self.plan(*args)
        return self.db.execute(plan['sql'],plan['args']).fetchall()

    def test_nonempty_related_entities_aliases_and_real_asset_votes(self):
        rows=self.query('related','上海','3','1,2,4,5,6,8')
        self.assertTrue(rows)
        people={row[1] for row in rows if row[0]==1}
        self.assertEqual(people,{'101','102'}) # Same display name never merges stable entity identities.
        self.assertEqual({row[3] for row in rows if row[1]=='101'},{'张三','Ranger','海风'})
        self.assertEqual({row[4] for row in rows if row[1]=='101'},{2})
        self.assertEqual({row[4] for row in rows if row[0]==2},{3})
        self.assertEqual({row[2] for row in rows if row[0]==8},{'IMAGE'})
        self.assertNotIn(3,{row[0] for row in rows})

    def test_all_seven_search_types_count_distinct_photos_without_alias_inflation(self):
        rows=self.query('suggestions','0,1,2,3,4,5,6')
        self.assertEqual({r[0] for r in rows},set(range(7)))
        for kind in range(7):
            subset=[r for r in rows if r[0]==kind]
            self.assertEqual(sorted(r[2] for r in subset),[1,2])
            self.assertTrue(any('20261016' in r[1] and r[2]==2 for r in subset))
            self.assertTrue(any('20261017' in r[1] and r[2]==1 for r in subset))

    def test_hide_trash_pending_temporary_risk_clean_sync_burst_and_type_exclusions(self):
        rows=self.query('related','上海','3','2')
        self.assertEqual(rows,[(2,'201','海边','',3)])
        self.db.execute('UPDATE Photos SET hidden=1 WHERE file_id=2')
        self.assertEqual(self.query('related','上海','3','2'),[(2,'201','海边','',2)])
        self.db.execute('UPDATE Photos SET date_trashed=1 WHERE file_id=1')
        self.assertEqual(self.query('related','上海','3','2'),[(2,'201','海边','',1)])

    def test_actual_delete_and_relationship_updates_are_not_cached(self):
        self.db.execute('DELETE FROM Photos WHERE file_id=1')
        self.assertEqual(self.query('related','上海','3','2'),[(2,'201','海边','',2)])
        self.db.execute('DELETE FROM AnalysisPhotoMap WHERE map_asset=2 AND map_album=301')
        self.assertEqual(self.query('related','上海','3','2'),[(2,'201','海边','',1)])
        self.db.execute('DELETE FROM AnalysisAlbum WHERE album_id=201')
        self.assertEqual(self.query('related','上海','3','2'),[])
        self.assertEqual(self.query('suggestions','0'),[])
        self.assertTrue(self.query('suggestions','1'))

    def test_alias_update_index_uniqueness_and_reopen_persistence(self):
        self.assertTrue(self.query('related','张三','1','3'))
        self.db.execute("UPDATE tab_analysis_nick_name SET nick_name='新别名' WHERE nick_name='张三'")
        self.assertEqual(self.query('related','张三','1','3'),[])
        self.assertEqual(self.query('related','新别名','1','3'),[(3,'301','上海','',2)])
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.execute('INSERT INTO tab_analysis_nick_name VALUES(101,?)',('新别名',))
        self.db.commit();self.db.close();self.db=sqlite3.connect(self.path)
        self.assertEqual(self.query('related','新别名','1','3'),[(3,'301','上海','',2)])

    def test_parameter_binding_unicode_no_match_and_sql_injection(self):
        topic="' OR 1=1; DROP TABLE Photos; --"
        plan=self.plan('related',topic,'3','1,2')
        self.assertNotIn(topic,plan['sql']);self.assertEqual(plan['args'].count(topic),2)
        self.assertEqual(self.db.execute(plan['sql'],plan['args']).fetchall(),[])
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM Photos').fetchone(),(12,))
        self.assertEqual(self.query('related','无匹配实体','3','1'),[])
        self.assertEqual(self.query('related','上海','3','2'),[(2,'201','海边','',3)])
        self.assertEqual(self.query('related','rAnGeR','1','3'),[(3,'301','上海','',3)])

    def test_new_actual_asset_is_counted_and_source_index_plan_is_used(self):
        self.db.execute("INSERT INTO Photos(file_id,date_year,date_month,date_day) VALUES(13,'2026','202610','20261016')")
        self.db.executemany('INSERT INTO AnalysisPhotoMap VALUES(?,13,0)',[(101,),(201,),(301,)])
        self.assertEqual(self.query('related','上海','3','2'),[(2,'201','海边','',4)])
        rows=self.query('suggestions','0')
        self.assertIn((0,'20261016 上海 海边',3),rows)
        plan=self.plan('related','上海','3','2')
        details=[r[3] for r in self.db.execute('EXPLAIN QUERY PLAN '+plan['sql'],plan['args'])]
        self.assertTrue(any('INDEX' in line and 'map' in line.lower() for line in details),details)

    def test_actual_random_vote_weighting_without_replacement_and_unsupported_producer(self):
        result=self.plan('sampling')
        self.assertEqual(result['draws'],10000);self.assertGreater(result['dominant'],9500)
        # The production native parser rejects field NONE/HOLIDAY as unavailable before scheduling;
        # the pure query module declares the source producer boundary explicitly.
        self.assertIn('field != 7',(COMPONENT/'files/knowledge_content_query.cpp').read_text())


if __name__=='__main__':unittest.main(verbosity=2)
