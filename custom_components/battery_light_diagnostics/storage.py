"""Bounded durable RF recorder; standard library only, safe for executor threads."""
from contextlib import closing
import gzip
import json
import os
from pathlib import Path
import sqlite3
import threading
import time
import uuid

class Store:
    def __init__(self, path, max_bytes=256*1024*1024, retention_days=7, incidents=20):
        self.path=Path(path);self.max_bytes=max_bytes;self.retention=retention_days*86400
        self.incidents=incidents;self.lock=threading.Lock()

    def _connect(self):
        self.path.mkdir(parents=True,exist_ok=True)
        c=sqlite3.connect(self.path/'rolling.sqlite3',timeout=30)
        c.execute('PRAGMA synchronous=FULL')
        c.execute('PRAGMA max_page_count=131072')
        c.execute('CREATE TABLE IF NOT EXISTS records (id INTEGER PRIMARY KEY, ts REAL NOT NULL, kind TEXT NOT NULL, payload TEXT NOT NULL, size INTEGER NOT NULL)')
        c.execute('CREATE INDEX IF NOT EXISTS record_time ON records(ts)')
        c.execute('CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value INTEGER NOT NULL)')
        c.execute("INSERT OR IGNORE INTO metadata VALUES ('bytes',0)")
        c.commit();return c

    def append(self, records):
        with self.lock, closing(self._connect()) as c:
            rows=[]
            for record in records:
                payload=json.dumps(record,separators=(',',':'))
                rows.append((record['ts'],record['kind'],payload,len(payload.encode())))
            total=c.execute("SELECT value FROM metadata WHERE key='bytes'").fetchone()[0]
            cutoff=time.time()-self.retention
            expired=c.execute('SELECT COALESCE(SUM(size),0) FROM records WHERE ts<?',(cutoff,)).fetchone()[0]
            c.execute('DELETE FROM records WHERE ts<?',(cutoff,));total-=expired
            incoming=sum(row[3] for row in rows)
            # Prune before insertion so free SQLite pages can be reused.
            while total+incoming>self.max_bytes:
                old=c.execute('SELECT id,size FROM records ORDER BY id LIMIT 256').fetchall()
                if not old:break
                c.execute('DELETE FROM records WHERE id<=?',(old[-1][0],));total-=sum(x[1] for x in old)
            # A bounded in-memory batch should be much smaller than the quota.
            while rows and incoming>self.max_bytes:incoming-=rows.pop(0)[3]
            c.executemany('INSERT INTO records(ts,kind,payload,size) VALUES (?,?,?,?)',rows)
            total+=incoming;c.execute("UPDATE metadata SET value=? WHERE key='bytes'",(total,));c.commit()
            result=c.execute('SELECT MIN(ts),MAX(ts),COUNT(*) FROM records').fetchone()
            return {'oldest':result[0],'newest':result[1],'records':result[2],'payload_bytes':total}

    def report(self, lookback_minutes=60, note='Owner reported missed Power On'):
        now=time.time();cutoff=now-lookback_minutes*60
        with self.lock,closing(self._connect()) as c:
            directory=self.path/'incidents';directory.mkdir(exist_ok=True)
            name=time.strftime('%Y%m%dT%H%M%SZ',time.gmtime(now))+'-'+uuid.uuid4().hex[:8]+'.jsonl.gz'
            final=directory/name;temporary=directory/(name+'.tmp')
            for abandoned in directory.glob('*.tmp'):abandoned.unlink()
            rows=[];size=0;truncated=False
            for payload,n in c.execute('SELECT payload,size FROM records WHERE ts>=? ORDER BY ts DESC,id DESC',(cutoff,)):
                if size+n>64*1024*1024:truncated=True;break
                rows.append(payload);size+=n
            with temporary.open('wb') as raw:
                with gzip.GzipFile(fileobj=raw,mode='wb') as z:
                    header={'kind':'incident','ts':now,'note':note,'lookback_minutes':lookback_minutes,'truncated':truncated,'records':len(rows)}
                    z.write((json.dumps(header)+'\n').encode())
                    for payload in reversed(rows):z.write((payload+'\n').encode())
                raw.flush();os.fsync(raw.fileno())
            temporary.replace(final)
            descriptor=os.open(directory,os.O_RDONLY)
            try:os.fsync(descriptor)
            finally:os.close(descriptor)
            for old in sorted(directory.glob('*.jsonl.gz'))[:-self.incidents]:old.unlink()
            return {'file':str(final),'records':len(rows),'truncated':truncated}
