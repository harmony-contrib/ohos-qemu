#!/usr/bin/env python3
"""Actual service producer against persistent SQLite; strict source installer and query joins."""
from contextlib import contextmanager
import base64
import copy
import gzip
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent
COMP=ROOT/'patches/common/foundation/multimedia/media_library/knowledge_holiday_index'
OLD=COMP.parent/'knowledge_content'
FIX=HERE/'fixtures/batch_media/knowledge'

def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module

@contextmanager
def sqlite_database(path):
    connection=sqlite3.connect(path)
    try:
        with connection:yield connection
    finally:connection.close()

class Holiday(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory(prefix='batch-media-holiday-');cls.root=Path(cls.temp.name)
        for path in (FIX/'holiday').glob('*.h'):(cls.root/path.name).write_bytes(path.read_bytes())
        (cls.root/'transaction.h').write_text('#include "rdb_store.h"\n')
        (cls.root/'rdb_errno.h').write_text('#include "rdb_store.h"\n')
        (cls.root/'medialibrary_log.h').write_text('#define MEDIA_ERR_LOG(...)\n')
        for name in ['knowledge_holiday_index.h','knowledge_content_query.h']:(cls.root/name).write_bytes((COMP/'files'/name).read_bytes())
        source=(FIX/'holiday/producer_harness.cpp').read_text().replace('// ACTUAL_PRODUCER',(COMP/'files/knowledge_holiday_index.cpp').read_text())
        (cls.root/'producer.cpp').write_text(source)
        openssl=Path('/opt/homebrew/opt/openssl@3')
        extra=['-I',str(openssl/'include'),'-L',str(openssl/'lib')] if openssl.exists() else []
        cls.flags=['clang++','-std=c++17','-Wall','-Wextra','-Werror','-pthread','-fsanitize=address,undefined','-fno-omit-frame-pointer','-I',str(cls.root)]
        subprocess.run(cls.flags+extra+[str(cls.root/'producer.cpp'),'-lsqlite3','-lcrypto','-o',str(cls.root/'producer')],check=True)
        # Actual final query builder and weighted selection; no fake query implementation.
        cli=(HERE/'batch_media_knowledge_query_cli.cpp').read_text().replace(' && !HasProducer(7)',' && HasProducer(7)')
        (cls.root/'query_cli.cpp').write_text(cli)
        subprocess.run(cls.flags+[str(cls.root/'query_cli.cpp'),str(COMP/'files/knowledge_content_query.cpp'),'-o',str(cls.root/'query')],check=True)
        cls.env=dict(os.environ,ASAN_OPTIONS='detect_leaks=0' if os.uname().sysname!='Linux' else 'detect_leaks=1')

    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()

    def setUp(self):
        self.work=tempfile.TemporaryDirectory(prefix='batch-media-holiday-db-');self.path=Path(self.work.name);self.resource=self.path/'resource';self.resource.mkdir();self.database=self.path/'media.db'
    def tearDown(self):self.work.cleanup()
    def calendar(self,events):return 'BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//Independent host calendar challenge//EN\r\n'+''.join(events)+'END:VCALENDAR\r\n'
    def event(self,uid='external-uid',start='20261231',end='20270102',name='真实假日:测试\\,别名\\;行\\n二',extra=''):
        return f'BEGIN:VEVENT\r\nUID:{uid}\r\nDTSTART;VALUE=DATE:{start}\r\nDTEND;VALUE=DATE:{end}\r\nSUMMARY:{name}\r\n{extra}END:VEVENT\r\n'
    def publish(self,text):
        target=self.resource/'holidays.ics';tmp=self.resource/'new.ics';tmp.write_bytes(text.encode() if isinstance(text,str) else text);tmp.replace(target)
    def run_producer(self,ok=True,**env):
        result=subprocess.run([str(self.root/'producer'),str(self.database),'trust-tests'],env=dict(self.env,BATCH_MEDIA_TEST_RESOURCE_DIRECTORY=str(self.resource),**env),capture_output=True,text=True,timeout=15)
        self.assertEqual(result.returncode==0,ok,result.stdout+result.stderr);return result
    def rows(self,sql='SELECT uid,instance_start,civil_date,name,entity_id FROM KnowledgeHoliday ORDER BY uid,civil_date'):
        with sqlite_database(self.database) as db:return db.execute(sql).fetchall()
    def query(self,topic,fields='7',suggest='7'):
        result=subprocess.run([str(self.root/'query'),'related',topic,fields,suggest],env=self.env,capture_output=True,text=True,check=True);query=json.loads(result.stdout)
        with sqlite_database(self.database) as db:return db.execute(query['sql'],query['args']).fetchall()
    def test_observer_cancel_join_reopen_inflight_and_reentrant_stop(self):
        self.publish(self.calendar([self.event()]))
        subprocess.run([str(self.root/'producer'),str(self.database),'observer-tests'],env=dict(self.env,BATCH_MEDIA_TEST_RESOURCE_DIRECTORY=str(self.resource)),check=True,timeout=18)

    def test_actual_sqlite_query_snapshot_during_source_replacement_and_directory_delete(self):
        self.publish(self.calendar([self.event()]));self.run_producer()
        reader=sqlite3.connect(self.database)
        try:
            reader.execute('PRAGMA journal_mode=WAL')
            cursor=reader.execute('SELECT uid,civil_date FROM KnowledgeHoliday ORDER BY civil_date')
            self.assertEqual(cursor.fetchone(),('external-uid','20261231'))
            old_directory=self.path/'old-resource';self.resource.rename(old_directory);self.resource.mkdir()
            self.publish(self.calendar([self.event(uid='new-version',start='20270101',end='20270103',name='Replacement')]))
            self.run_producer()
            self.assertEqual(cursor.fetchall(),[('external-uid','20270101')])
            self.assertEqual({row[0] for row in self.rows()},{'new-version'})
            (self.resource/'holidays.ics').unlink();self.resource.rmdir();self.run_producer()
            self.assertEqual(self.rows(),[])
        finally:reader.close()

    def test_actual_native_cursor_default_none_and_resource_errors(self):
        source=(COMP/'files/knowledge_content_napi.cpp').read_text()
        declarations=source[source.index('struct Suggestion {'):source.index('int32_t AccessError()')]
        functions=[]
        for signature in ['bool Number(', 'bool IntegerArray(', 'bool Account(', 'bool NextRow(', 'void ReadEntities(', 'void ReadSuggestions(']:
            a=source.index(signature);b=source.index('\n}',a)+2;functions.append(source[a:b])
        harness=(FIX/'holiday/cursor_harness.cpp').read_text().replace('// ACTUAL_DECLARATIONS',declarations).replace('// ACTUAL_FUNCTIONS','\n'.join(functions))
        path=self.path/'cursor.cpp';path.write_text(harness);binary=self.path/'cursor'
        subprocess.run(self.flags+[str(path),str(COMP/'files/knowledge_content_query.cpp'),'-o',str(binary)],check=True)
        subprocess.run([str(binary)],check=True,env=self.env,timeout=10)

    def test_real_schema_legacy_upgrade_unicode_dates_replacement_and_deletion(self):
        with sqlite_database(self.database) as db:db.execute('CREATE TABLE ExistingAssets(id INTEGER PRIMARY KEY)');db.execute('INSERT INTO ExistingAssets VALUES(7)')
        self.run_producer();self.assertEqual(self.rows(),[]);self.assertEqual(self.rows('SELECT * FROM ExistingAssets'),[(7,)])
        self.publish(self.calendar([self.event()]));self.run_producer();rows=self.rows();self.assertEqual([r[2] for r in rows],['20261231','20270101']);self.assertEqual(rows[0][3],'真实假日:测试,别名;行\n二');self.assertEqual(rows[0][4],rows[1][4])
        first_meta=self.rows('SELECT * FROM KnowledgeHolidayResource');self.assertEqual(first_meta[0][2],hashlib.sha256((self.resource/'holidays.ics').read_bytes()).hexdigest())
        self.publish(self.calendar([self.event(uid='replacement',start='20240228',end='20240301',name='新资源')]));self.run_producer();self.assertEqual([r[2] for r in self.rows()],['20240228','20240229']);self.assertEqual(self.rows()[0][0],'replacement')
        (self.resource/'holidays.ics').unlink();self.run_producer();self.assertEqual(self.rows(),[]);self.assertEqual(self.rows('SELECT sha256,present,row_count FROM KnowledgeHolidayResource'),[('absent',0,0)])
        self.assertEqual(self.rows('SELECT * FROM ExistingAssets'),[(7,)])
    def test_invalid_io_permission_and_transaction_failure_keep_complete_previous_version(self):
        self.publish(self.calendar([self.event()]));self.run_producer();before=self.rows();meta=self.rows('SELECT * FROM KnowledgeHolidayResource')
        invalid=[self.calendar([self.event(start='20260229')]),self.calendar([self.event(end='20261230')]),self.calendar([self.event(extra='RRULE:FREQ=YEARLY\r\n')]),self.calendar([self.event()]).replace('DTSTART;VALUE=DATE:20261231','DTSTART;TZID=Asia/Shanghai:20261231T000000'),self.calendar([self.event(extra='RECURRENCE-ID;VALUE=DATE:20261231\r\n')]),self.calendar([self.event(uid='')]),self.calendar([self.event(name='bad\\q')]),self.calendar([self.event()]).replace('END:VEVENT','END:VTODO'),self.calendar([self.event()]).encode().replace(b'SUMMARY:',b'SUMMARY:\xff'),self.calendar([self.event(name='x'*1025)]),self.calendar([self.event(start='20200101',end='20220101')])]
        for text in invalid:
            self.publish(text);self.run_producer(ok=False);self.assertEqual(self.rows(),before);self.assertEqual(self.rows('SELECT * FROM KnowledgeHolidayResource'),meta)
        self.publish(self.calendar([self.event(uid='updated',name='new')]))
        for env in [{'BATCH_MEDIA_TEST_READ_EIO':'1'},{'BATCH_MEDIA_TEST_BAD_OWNER':'1'},{'BATCH_MEDIA_TEST_DIRECTORY_EACCES':'1'},{'BATCH_MEDIA_TEST_CHANGE_DURING_READ':'1'},{'BATCH_MEDIA_TEST_FAIL_STATEMENT':'5'},{'BATCH_MEDIA_TEST_FAIL_COMMIT':'1'}]:
            self.run_producer(ok=False,**env);self.assertEqual(self.rows(),before);self.assertEqual(self.rows('SELECT * FROM KnowledgeHolidayResource'),meta)
        self.run_producer();self.assertEqual(self.rows()[0][0],'updated')
    def test_folded_text_duplicate_uid_rules_and_resource_bounds(self):
        event=self.event(name='Unicode🙂:完整\\,') .replace('完整\\,','完\r\n 整\\,')
        self.publish(self.calendar([event,event]));self.run_producer();self.assertEqual(len(self.rows()),2);self.assertEqual(self.rows()[0][3],'Unicode🙂:完整,')
        before=self.rows();meta=self.rows('SELECT * FROM KnowledgeHolidayResource')
        self.publish(self.calendar([self.event(uid='same'),self.event(uid='same',name='conflict')]))
        self.run_producer(ok=False);self.assertEqual(self.rows(),before);self.assertEqual(self.rows('SELECT * FROM KnowledgeHolidayResource'),meta)
        self.publish(b'x'*(1024*1024+1));self.run_producer(ok=False);self.assertEqual(self.rows(),before)
        self.publish(self.calendar([self.event(uid=str(i),start='20260101',end='20270101',name='input') for i in range(60)]));self.run_producer(ok=False);self.assertEqual(self.rows(),before)
        (self.resource/'holidays.ics').unlink();(self.resource/'holidays.ics').symlink_to('/etc/passwd');self.run_producer(ok=False);self.assertEqual(self.rows(),before)
    def test_actual_photo_date_join_live_visibility_deletion_and_uid_relation(self):
        self.publish(self.calendar([self.event(name='Calendar challenge')]));self.run_producer()
        schema=load('existing_knowledge_schema',HERE/'test_batch_media_knowledge_content.py').SCHEMA
        with sqlite_database(self.database) as db:
            db.executescript(schema);db.execute("INSERT INTO Photos(file_id,date_year,date_month,date_day) VALUES(1,'2026','202612','20261231')");db.execute("INSERT INTO Photos(file_id,date_year,date_month,date_day) VALUES(2,'2027','202701','20270101')");db.execute("INSERT INTO Photos(file_id,date_year,date_month,date_day) VALUES(3,'2027','202701','20270102')")
        result=self.query('2026','4','7');self.assertEqual(len(result),1);self.assertEqual(result[0][2],'Calendar challenge');self.assertEqual(result[0][-1],1)
        result=self.query('Calendar challenge','7','4');self.assertEqual({r[2] for r in result},{'2026','2027'})
        with sqlite_database(self.database) as db:db.execute('UPDATE Photos SET hidden=1 WHERE file_id=1');db.execute('DELETE FROM Photos WHERE file_id=2')
        self.assertEqual(self.query('Calendar challenge','7','4'),[]);self.assertEqual(len(self.rows()),2)
        subprocess.run([str(self.root/'query'),'sampling'],env=self.env,check=True,capture_output=True)

if __name__=='__main__':unittest.main(verbosity=2)
