import json,sqlite3,tempfile
from pathlib import Path
from damage_allocation_engine import run
with tempfile.TemporaryDirectory() as d:
 db=Path(d)/'x.db';rules=Path(d)/'r.json';rules.write_text(json.dumps({'version':'t','buffs':{'100':{'kind':'damage_percent','value':.1,'targeting':'party'}}}))
 c=sqlite3.connect(db);c.executescript('create table fights(report_hash text,fight_id integer,start real,end real);create table events(report_hash text,fight_id integer,seq integer,payload text);');c.execute('insert into fights values(?,?,?,?)',('r',1,0,10000))
 for i,e in enumerate([{'type':'applybuff','timestamp':0,'sourceID':'o','targetID':'p','abilityGameID':100,'duration':10000},{'type':'damage','timestamp':1000,'sourceID':'p','targetID':'b','amount':1100}]):c.execute('insert into events values(?,?,?,?)',('r',1,i,json.dumps(e)))
 c.commit();c.close();r=run(db,rules);assert round(r['allocated_damage'])==100
print('PASS')
