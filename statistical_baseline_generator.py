#!/usr/bin/env python3
"""P0-6 versioned statistical baseline generator for Local XIV Analyzer.
Consumes player_features + eligibility_results and produces robust, auditable baselines.
No network access and no personal names are required.
"""
from __future__ import annotations
import argparse, hashlib, json, math, random, sqlite3, statistics
from collections import defaultdict
from datetime import datetime, timezone

SCHEMA='''
create table if not exists baseline_versions(
 version_id text primary key, created_at text, algorithm_version text,
 source_fingerprint text, config_json text, cell_count integer, sample_count integer);
create table if not exists statistical_baselines(
 version_id text, cell_key text, metric text, sample_count integer,
 confidence text, median real, q1 real, q3 real, iqr real, mad real,
 p10 real, p25 real, p50 real, p75 real, p90 real,
 ci_low real, ci_high real, minimum real, maximum real,
 primary key(version_id,cell_key,metric));
create table if not exists action_baselines(
 version_id text, cell_key text, ability_id text, sample_count integer,
 usage_rate real, median_uses_per_min real, q1_uses_per_min real,
 q3_uses_per_min real, primary key(version_id,cell_key,ability_id));
'''
ALGORITHM='p0-6.1'

def q(xs,p):
 xs=sorted(float(x) for x in xs)
 if not xs:return 0.0
 k=(len(xs)-1)*p;lo=math.floor(k);hi=math.ceil(k)
 return xs[lo] if lo==hi else xs[lo]*(hi-k)+xs[hi]*(k-lo)

def mad(xs):
 if not xs:return 0.0
 m=statistics.median(xs);return statistics.median(abs(x-m) for x in xs)

def confidence(n,ci_width,med):
 rel=ci_width/max(abs(med),1e-9)
 if n>=100 and rel<=.08:return 'high'
 if n>=30 and rel<=.20:return 'medium'
 if n>=10:return 'low'
 return 'insufficient'

def bootstrap_median_ci(xs,reps=1000,seed=0,level=.95):
 if not xs:return (0.0,0.0)
 if len(xs)==1:return (float(xs[0]),float(xs[0]))
 rng=random.Random(seed);n=len(xs);vals=[]
 for _ in range(reps):vals.append(statistics.median(xs[rng.randrange(n)] for _ in range(n)))
 a=(1-level)/2;return q(vals,a),q(vals,1-a)

def fingerprint(db):
 h=hashlib.sha256()
 for row in db.execute('''select report_hash,fight_id,actor_hash,job,partition_id,patch,encounter_id,difficulty,phase,duration_ms,active_ratio,action_count,total_damage from player_features order by 1,2,3,9'''):
  h.update(json.dumps(row,separators=(',',':'),ensure_ascii=False).encode())
 return h.hexdigest()

def version_id(source_fp,config):return hashlib.sha256((ALGORITHM+'|'+source_fp+'|'+json.dumps(config,sort_keys=True)).encode()).hexdigest()[:20]

def generate(db_path,reps=1000,level=.95,include_review=False,min_samples=10):
 db=sqlite3.connect(db_path);db.executescript(SCHEMA)
 tables={r[0] for r in db.execute("select name from sqlite_master where type='table'")}
 if 'player_features' not in tables:raise RuntimeError('player_features is missing. Run P0-2 first.')
 has_quality='eligibility_results' in tables
 where='where coalesce(e.hard_eligible,1)=1' if has_quality else ''
 if has_quality and not include_review:where+=' and coalesce(e.review_flag,0)=0'
 join='left join eligibility_results e using(report_hash,fight_id,actor_hash)' if has_quality else ''
 sql=f'''select p.report_hash,p.fight_id,p.actor_hash,p.partition_id,p.patch,p.encounter_id,p.difficulty,p.phase,p.job,p.kill_time_bucket,p.duration_ms,p.active_ratio,p.action_count,p.total_damage from player_features p {join} {where}'''
 rows=[]
 for r in db.execute(sql):
  d=dict(zip(['rh','fid','actor','partition','patch','enc','difficulty','phase','job','bucket','duration','active','actions','damage'],r));d['apm']=d['actions']*60000/max(d['duration'],1);d['dpm']=d['damage']*60000/max(d['duration'],1);rows.append(d)
 cells=defaultdict(list)
 for x in rows:cells[(x['partition'],x['patch'],x['enc'],x['difficulty'],x['phase'],x['job'],x['bucket'])].append(x)
 config={'reps':reps,'level':level,'include_review':include_review,'min_samples':min_samples};fp=fingerprint(db);vid=version_id(fp,config)
 db.execute('delete from statistical_baselines where version_id=?',(vid,));db.execute('delete from action_baselines where version_id=?',(vid,))
 metrics={'active_ratio':lambda x:x['active'],'actions_per_min':lambda x:x['apm'],'damage_per_min':lambda x:x['dpm'],'effective_duration_ms':lambda x:x['duration']}
 for key,group in cells.items():
  cell='|'.join(map(str,key))
  for metric,getter in metrics.items():
   xs=[float(getter(x)) for x in group];med=statistics.median(xs);lo,hi=bootstrap_median_ci(xs,reps,int(hashlib.sha256((cell+metric).encode()).hexdigest()[:8],16),level);n=len(xs)
   vals=(vid,cell,metric,n,confidence(n,hi-lo,med),med,q(xs,.25),q(xs,.75),q(xs,.75)-q(xs,.25),mad(xs),q(xs,.10),q(xs,.25),q(xs,.50),q(xs,.75),q(xs,.90),lo,hi,min(xs),max(xs))
   db.execute('insert into statistical_baselines values('+','.join('?'*len(vals))+')',vals)
 # Optional action baselines from normalized JSON events.
 if 'events' in tables:
  feature_lookup={(x['rh'],x['fid'],x['actor']):x for x in rows};counts=defaultdict(lambda:defaultdict(int))
  for rh,fid,actor,dur in [(x['rh'],x['fid'],x['actor'],x['duration']) for x in rows]:
   for (payload,) in db.execute('select payload from events where report_hash=? and fight_id=?',(rh,fid)):
    try:e=json.loads(payload)
    except:continue
    if str(e.get('sourceID') or '')!=actor:continue
    if str(e.get('type','')).lower() not in {'cast','damage','calculateddamage'}:continue
    ability=str(e.get('abilityGameID') or ((e.get('ability') or {}).get('guid') if isinstance(e.get('ability'),dict) else '') or 'unknown');counts[(rh,fid,actor)][ability]+=1
  for key,group in cells.items():
   cell='|'.join(map(str,key));members=[(x['rh'],x['fid'],x['actor']) for x in group];abilities=set().union(*(counts[m].keys() for m in members)) if members else set()
   for ability in abilities:
    vals=[];users=0
    for x,m in zip(group,members):
     c=counts[m].get(ability,0);users+=int(c>0);vals.append(c*60000/max(x['duration'],1))
    db.execute('insert into action_baselines values(?,?,?,?,?,?,?,?)',(vid,cell,ability,len(group),users/len(group),statistics.median(vals),q(vals,.25),q(vals,.75)))
 db.execute('insert or replace into baseline_versions values(?,?,?,?,?,?,?)',(vid,datetime.now(timezone.utc).isoformat(),ALGORITHM,fp,json.dumps(config,sort_keys=True),len(cells),len(rows)));db.commit()
 summary={'version_id':vid,'cells':len(cells),'samples':len(rows),'metrics':db.execute('select count(*) from statistical_baselines where version_id=?',(vid,)).fetchone()[0],'action_metrics':db.execute('select count(*) from action_baselines where version_id=?',(vid,)).fetchone()[0],'insufficient':db.execute("select count(*) from statistical_baselines where version_id=? and confidence='insufficient'",(vid,)).fetchone()[0]};db.close();return summary

def main():
 p=argparse.ArgumentParser();p.add_argument('--db',required=True);p.add_argument('--bootstrap-reps',type=int,default=1000);p.add_argument('--confidence-level',type=float,default=.95);p.add_argument('--include-review',action='store_true');p.add_argument('--min-samples',type=int,default=10);a=p.parse_args();print(json.dumps(generate(a.db,a.bootstrap_reps,a.confidence_level,a.include_review,a.min_samples),ensure_ascii=False,indent=2))
if __name__=='__main__':main()
