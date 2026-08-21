import json,sqlite3,tempfile
from pathlib import Path
from job_boss_analysis_engine import run,JOBS
with tempfile.TemporaryDirectory() as d:
 p=Path(d)/'x.db';c=sqlite3.connect(p);c.executescript('''create table fights(report_hash text,fight_id integer,encounter_id integer,name text,start real,end real,difficulty integer,primary key(report_hash,fight_id));create table events(report_hash text,fight_id integer,seq integer,payload text,primary key(report_hash,fight_id,seq));create table fight_players(report_hash text,fight_id integer,actor_hash text,job text,primary key(report_hash,fight_id,actor_hash));''');c.execute('insert into fights values(?,?,?,?,?,?,?)',('r',1,99,'Boss',0,120000,101));c.execute('insert into fight_players values(?,?,?,?)',('r',1,'p','NIN'))
 for i,e in enumerate([{'type':'phasetransition','timestamp':0,'phase':1},{'type':'phasetransition','timestamp':60000,'phase':2},{'type':'damage','timestamp':1000,'sourceID':'p','targetID':'b','amount':100},{'type':'death','timestamp':70000,'targetID':'p'}]):c.execute('insert into events values(?,?,?,?)',('r',1,i,json.dumps(e)))
 c.commit();c.close();r=run(p);assert r['fights']==1 and r['findings']==1 and r['jobs_registered']==len(JOBS)
 c=sqlite3.connect(p);assert c.execute('select count(*) from phase_windows').fetchone()[0]==2;assert c.execute('select count(*) from job_boss_summary').fetchone()[0]==2;c.close()
print('PASS')
