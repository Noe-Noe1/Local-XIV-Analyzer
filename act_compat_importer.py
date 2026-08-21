from __future__ import annotations
import hashlib,json,re,sqlite3
from datetime import datetime
from pathlib import Path
JOB_IDS={19:'PLD',20:'MNK',21:'WAR',22:'DRG',23:'BRD',24:'WHM',25:'BLM',27:'SMN',28:'SCH',30:'NIN',31:'MCH',32:'DRK',33:'AST',34:'SAM',35:'RDM',37:'GNB',38:'DNC',39:'RPR',40:'SGE',41:'VPR',42:'PCT'}
def ts(s):
 try:return datetime.fromisoformat(s).timestamp()*1000
 except:return 0
def hx(s):
 try:return int(s,16)
 except:return 0
def anon(v,salt):return hashlib.sha256((salt+'|'+str(v)).encode()).hexdigest()[:20]
def amount(words):
 vals=[]
 for w in words:
  if re.fullmatch(r'[0-9A-Fa-f]{8,16}',w or ''):
   b=bytes.fromhex(w if len(w)%2==0 else '0'+w)
   for n in (2,3,4):
    for i in range(len(b)-n+1):
     v=int.from_bytes(b[i:i+n],'little')
     if 0<v<20000000:vals.append(v)
 return min(vals,key=lambda x:abs(x-100000)) if vals else 0
def init(db):
 c=sqlite3.connect(db);c.executescript('''pragma journal_mode=WAL;create table if not exists reports(report_hash text primary key,zone_id integer,zone_name text,collected_at text);create table if not exists fights(report_hash text,fight_id integer,encounter_id integer,name text,start real,end real,difficulty integer,primary key(report_hash,fight_id));create table if not exists events(report_hash text,fight_id integer,seq integer,payload text,primary key(report_hash,fight_id,seq));create table if not exists fight_players(report_hash text,fight_id integer,actor_hash text,job text,primary key(report_hash,fight_id,actor_hash));create table if not exists import_audit(report_hash text primary key,source_type text,source_hash text,line_count integer,parsed_count integer,line_types text);''');return c
def parse(line,salt,base,seq):
 p=line.rstrip().split('|');typ=p[0] if p else ''
 if len(p)<2:return None,[]
 t=max(0,ts(p[1])-base);a=lambda x:anon(x,salt) if x else '';e=None;actors=[]
 if typ=='03' and len(p)>5:actors=[(a(p[2]),JOB_IDS.get(hx(p[4]),'UNKNOWN'))];e={'type':'combatantinfo','timestamp':t,'sourceID':a(p[2]),'job':actors[0][1]}
 elif typ=='20' and len(p)>8:e={'type':'begincast','timestamp':t,'sourceID':a(p[2]),'abilityGameID':hx(p[4]),'targetID':a(p[6]),'duration':float(p[8] or 0)*1000}
 elif typ in ('21','22') and len(p)>8:e={'type':'damage','timestamp':t,'sourceID':a(p[2]),'abilityGameID':hx(p[4]),'targetID':a(p[6]),'amount':amount(p[8:-1]),'rawEffects':p[8:-1]}
 elif typ=='24' and len(p)>6:e={'type':'damage','timestamp':t,'sourceID':a(p[2]),'targetID':a(p[4]),'amount':hx(p[6]),'tick':True}
 elif typ=='25' and len(p)>3:e={'type':'death','timestamp':t,'targetID':a(p[2])}
 elif typ=='26' and len(p)>8:e={'type':'applybuff','timestamp':t,'abilityGameID':hx(p[2]),'sourceID':a(p[5]),'targetID':a(p[7]),'duration':float(p[4] or 0)*1000}
 elif typ=='30' and len(p)>6:e={'type':'removebuff','timestamp':t,'abilityGameID':hx(p[2]),'sourceID':a(p[5]),'targetID':a(p[3])}
 if e:e['actSeq']=seq
 return e,actors
def import_log(path,db_path,salt='LocalXIVAnalyzer-ACT-v1',gap_ms=30000):
 raw=Path(path).read_bytes();lines=raw.decode('utf-8','ignore').splitlines();times=[ts(x.split('|')[1]) for x in lines if len(x.split('|'))>1 and ts(x.split('|')[1])]
 if not times:raise ValueError('ACT timestamp not found')
 base=min(times);events=[];roster={};types={}
 for i,line in enumerate(lines):
  e,aa=parse(line,salt,base,i)
  if e:events.append(e);types[line.split('|',1)[0]]=types.get(line.split('|',1)[0],0)+1
  for k,v in aa:roster[k]=v
 combat=[e for e in events if e['type'] in {'begincast','damage','death','applybuff','removebuff'}];groups=[];cur=[];last=None
 for e in combat:
  if last is not None and e['timestamp']-last>gap_ms and any(x['type']=='damage' for x in cur):groups.append(cur);cur=[]
  cur.append(e);last=e['timestamp']
 if cur and any(x['type']=='damage' for x in cur):groups.append(cur)
 sh=hashlib.sha256(raw).hexdigest();rh=anon(sh,salt);db=init(db_path);db.execute('insert or replace into reports values(?,?,?,datetime("now"))',(rh,0,'ACT Local Import'))
 for fid,g in enumerate(groups,1):
  db.execute('insert or replace into fights values(?,?,?,?,?,?,?)',(rh,fid,0,'ACT Encounter',min(x['timestamp'] for x in g),max(x['timestamp'] for x in g),0));used=set()
  for i,e in enumerate(g):db.execute('insert or replace into events values(?,?,?,?)',(rh,fid,i,json.dumps(e,separators=(',',':'))));used.add(e.get('sourceID',''))
  for actor in used:
   if actor:db.execute('insert or replace into fight_players values(?,?,?,?)',(rh,fid,actor,roster.get(actor,'UNKNOWN')))
 db.execute('insert or replace into import_audit values(?,?,?,?,?,?)',(rh,'ACT_NETWORK_LOG',sh,len(lines),len(events),json.dumps(types)));db.commit();db.close();return {'encounters':len(groups),'parsed':len(events)}
