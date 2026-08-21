import json,sqlite3,tempfile
from pathlib import Path
from healing_mitigation_engine import run
with tempfile.TemporaryDirectory() as d:
 db=Path(d)/'x.db';r=Path(d)/'r.json';r.write_text(json.dumps({'version':'t','mitigations':{'100':{'kind':'damage_reduction','value':.1}}}))
 c=sqlite3.connect(db);c.executescript('''create table fights(report_hash text,fight_id integer,encounter_id integer,name text,start real,end real,difficulty integer,primary key(report_hash,fight_id));create table events(report_hash text,fight_id integer,seq integer,payload text,primary key(report_hash,fight_id,seq));''');c.execute('insert into fights values(?,?,?,?,?,?,?)',('r',1,1,'b',0,10000,1));ev=[{'type':'applybuff','timestamp':0,'sourceID':'tank','targetID':'p','abilityGameID':100,'duration':10000},{'type':'damage','timestamp':1000,'sourceID':'b','targetID':'p','amount':900},{'type':'heal','timestamp':2000,'sourceID':'h','targetID':'p','amount':1000,'overheal':200,'absorbed':100},{'type':'death','timestamp':3000,'targetID':'p'}]
 for i,e in enumerate(ev):c.execute('insert into events values(?,?,?,?)',('r',1,i,json.dumps(e)))
 c.commit();c.close();x=run(db,r);assert x['fights']==1
 c=sqlite3.connect(db);h=c.execute("select raw_healing,effective_healing,overheal from healing_metrics where actor_hash='h'").fetchone();m=c.execute("select prevented_estimate from mitigation_metrics where actor_hash='tank'").fetchone();assert h==(1000,800,200) and round(m[0])==100 and c.execute('select count(*) from death_windows').fetchone()[0]==1;c.close()
print('PASS')
