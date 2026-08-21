#!/usr/bin/env python3
"""Build comparable Clear-log cells from the anonymized FFLogs collector SQLite DB.

A cell is strictly keyed by partition, encounter, difficulty, phase, job, and
kill-time bucket. The builder never uses actor names and does not require network access.
"""
from __future__ import annotations
import argparse, json, math, sqlite3, statistics
from collections import defaultdict
from pathlib import Path

SCHEMA='''
pragma journal_mode=WAL;
create table if not exists fight_players(
 report_hash text not null, fight_id integer not null, actor_hash text not null,
 job text not null default 'UNKNOWN', primary key(report_hash,fight_id,actor_hash));
create table if not exists fight_context(
 report_hash text not null, fight_id integer not null, partition_id integer not null default 0,
 patch text not null default 'unknown', phase integer not null default 0,
 primary key(report_hash,fight_id));
create table if not exists player_features(
 report_hash text, fight_id integer, actor_hash text, job text, partition_id integer,
 patch text, encounter_id integer, difficulty integer, phase integer,
 duration_ms real, active_ms real, active_ratio real, action_count integer,
 casts integer, damage_events integer, total_damage real, deaths integer,
 weakness_events integer, eligible integer, exclusion_reason text,
 kill_time_bucket text, primary key(report_hash,fight_id,actor_hash,phase));
create table if not exists comparison_cells(
 cell_key text primary key, partition_id integer, patch text, encounter_id integer,
 difficulty integer, phase integer, job text, kill_time_bucket text,
 sample_count integer, confidence text, median_active_ratio real,
 q1_active_ratio real, q3_active_ratio real, median_actions_per_min real,
 q1_actions_per_min real, q3_actions_per_min real,
 median_damage_per_min real, q1_damage_per_min real, q3_damage_per_min real);
'''
ACTION_TYPES={'damage','calculateddamage','heal','calculatedheal','cast','begincast','applybuff','applydebuff','refreshbuff','refreshdebuff'}
DAMAGE_TYPES={'damage','calculateddamage'}
CAST_TYPES={'cast','begincast'}
DEATH_TYPES={'death'}
WEAKNESS_IDS={43,44,1789}  # Weakness/Brink IDs vary by patch; configurable additions supported.

def quantile(xs,p):
 xs=sorted(float(x) for x in xs)
 if not xs:return 0.0
 k=(len(xs)-1)*p; lo=math.floor(k); hi=math.ceil(k)
 return xs[lo] if lo==hi else xs[lo]*(hi-k)+xs[hi]*(k-lo)

def confidence(n):
 return 'high' if n>=100 else 'medium' if n>=30 else 'low' if n>=10 else 'insufficient'

def event_actor(e):
 return str(e.get('sourceID') or '')

def load_job_map(path):
 if not path:return {}
 raw=json.loads(Path(path).read_text(encoding='utf-8'))
 # accepted keys: "report_hash:fight_id:actor_hash" or actor_hash
 return {str(k):str(v) for k,v in raw.items()}

def ensure_roster(db,job_map):
 # Populate missing roster rows from source actors. UNKNOWN actors remain visible but ineligible.
 fights={(r[0],int(r[1])) for r in db.execute('select report_hash,fight_id from fights')}
 for rh,fid in fights:
  seen=set()
  for (payload,) in db.execute('select payload from events where report_hash=? and fight_id=?',(rh,fid)):
   try:e=json.loads(payload)
   except:continue
   aid=event_actor(e)
   if not aid or aid in seen:continue
   seen.add(aid);job=job_map.get(f'{rh}:{fid}:{aid}',job_map.get(aid,'UNKNOWN'))
   db.execute('insert or ignore into fight_players values(?,?,?,?)',(rh,fid,aid,job))

def duration_buckets(fights):
 by=defaultdict(list)
 for f in fights:by[(f['partition'],f['encounter'],f['difficulty'])].append(f['duration'])
 cuts={}
 for k,x in by.items():cuts[k]=(quantile(x,.25),quantile(x,.75))
 return cuts

def bucket(value,cuts):
 q1,q3=cuts
 return 'fast' if value<=q1 else 'slow' if value>=q3 else 'mid'

def build(src,out=None,job_map_path=None,min_active=.85,weakness_ids=None):
 src=Path(src); out=Path(out or src)
 db=sqlite3.connect(out)
 if out.resolve()!=src.resolve():
  srcdb=sqlite3.connect(src);srcdb.backup(db);srcdb.close()
 db.executescript(SCHEMA);job_map=load_job_map(job_map_path);ensure_roster(db,job_map)
 has_effective='effective_time' in {r[0] for r in db.execute("select name from sqlite_master where type='table'")}
 weakness=set(weakness_ids or WEAKNESS_IDS)
 fights=[]
 q='''select f.report_hash,f.fight_id,f.encounter_id,f.difficulty,f.start,f.end,
 coalesce(c.partition_id,0),coalesce(c.patch,'unknown'),coalesce(c.phase,0)
 from fights f left join fight_context c using(report_hash,fight_id)'''
 for r in db.execute(q):
  fights.append({'rh':r[0],'fid':r[1],'encounter':r[2] or 0,'difficulty':r[3] or 0,'start':float(r[4] or 0),'end':float(r[5] or 0),'duration':max(float(r[5] or 0)-float(r[4] or 0),1),'partition':r[6],'patch':r[7],'phase':r[8]})
 cuts=duration_buckets(fights);db.execute('delete from player_features');db.execute('delete from comparison_cells')
 for f in fights:
  events=[]
  for (payload,) in db.execute('select payload from events where report_hash=? and fight_id=? order by seq',(f['rh'],f['fid'])):
   try:events.append(json.loads(payload))
   except:pass
  kt=bucket(f['duration'],cuts[(f['partition'],f['encounter'],f['difficulty'])])
  for aid,job in db.execute('select actor_hash,job from fight_players where report_hash=? and fight_id=?',(f['rh'],f['fid'])):
   ae=[e for e in events if event_actor(e)==aid]; times=[float(e.get('timestamp',0)) for e in ae if str(e.get('type','')).lower() in ACTION_TYPES and e.get('timestamp') is not None]
   active=max(times)-min(times) if len(times)>=2 else 0
   effective=f['duration']
   if has_effective:
    row=db.execute('select effective_ms from effective_time where report_hash=? and fight_id=? and actor_hash=?',(f['rh'],f['fid'],aid)).fetchone()
    if row and row[0] and row[0]>0:effective=float(row[0])
   ratio=max(0,min(1,active/effective))
   actions=sum(str(e.get('type','')).lower() in ACTION_TYPES for e in ae);casts=sum(str(e.get('type','')).lower() in CAST_TYPES for e in ae)
   dmg=[e for e in ae if str(e.get('type','')).lower() in DAMAGE_TYPES];total=sum(float(e.get('amount') or 0) for e in dmg)
   deaths=sum(str(e.get('type','')).lower() in DEATH_TYPES for e in events if str(e.get('targetID') or '')==aid)
   weak=sum(int(e.get('abilityGameID') or e.get('ability',{}).get('guid') or 0) in weakness for e in events if str(e.get('targetID') or '')==aid and str(e.get('type','')).lower() in {'applybuff','refreshbuff'})
   reasons=[]
   if job=='UNKNOWN':reasons.append('job_unknown')
   if ratio<min_active:reasons.append('low_active_ratio')
   if deaths:reasons.append('death')
   if weak:reasons.append('weakness')
   eligible=not reasons
   vals=(f['rh'],f['fid'],aid,job,f['partition'],f['patch'],f['encounter'],f['difficulty'],f['phase'],effective,active,ratio,actions,casts,len(dmg),total,deaths,weak,int(eligible),','.join(reasons),kt)
   db.execute('insert or replace into player_features values('+','.join('?'*len(vals))+')',vals)
 groups=defaultdict(list)
 for r in db.execute('''select partition_id,patch,encounter_id,difficulty,phase,job,kill_time_bucket,duration_ms,active_ratio,action_count,total_damage from player_features where eligible=1'''):
  groups[r[:7]].append(r[7:])
 for key,samples in groups.items():
  dur=[x[0] for x in samples];ar=[x[1] for x in samples];apm=[x[2]*60000/x[0] for x in samples];dpm=[x[3]*60000/x[0] for x in samples]
  cell='|'.join(map(str,key));vals=(cell,*key,len(samples),confidence(len(samples)),statistics.median(ar),quantile(ar,.25),quantile(ar,.75),statistics.median(apm),quantile(apm,.25),quantile(apm,.75),statistics.median(dpm),quantile(dpm,.25),quantile(dpm,.75))
  db.execute('insert into comparison_cells values('+','.join('?'*len(vals))+')',vals)
 db.commit();summary={'fights':len(fights),'features':db.execute('select count(*) from player_features').fetchone()[0],'eligible':db.execute('select count(*) from player_features where eligible=1').fetchone()[0],'cells':db.execute('select count(*) from comparison_cells').fetchone()[0],'insufficient_cells':db.execute("select count(*) from comparison_cells where confidence='insufficient'").fetchone()[0]};db.close();return summary

def main():
 p=argparse.ArgumentParser();p.add_argument('--db',required=True);p.add_argument('--out-db');p.add_argument('--job-map');p.add_argument('--min-active',type=float,default=.85);p.add_argument('--summary');a=p.parse_args()
 s=build(a.db,a.out_db,a.job_map,a.min_active)
 text=json.dumps(s,ensure_ascii=False,indent=2);print(text)
 if a.summary:Path(a.summary).write_text(text,encoding='utf-8')
if __name__=='__main__':main()
