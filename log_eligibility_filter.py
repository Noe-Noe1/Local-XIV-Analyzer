#!/usr/bin/env python3
"""P0-4 eligibility and robust outlier screening.
Hard exclusions are deterministic. Statistical outliers are review flags by default.
"""
from __future__ import annotations
import argparse,json,math,sqlite3,statistics
from collections import defaultdict

SCHEMA='''
create table if not exists eligibility_results(
 report_hash text,fight_id integer,actor_hash text,hard_eligible integer,
 review_flag integer,reasons text,quality_score real,
 duration_modified_z real,apm_modified_z real,dpm_modified_z real,
 duplicate_group text,primary key(report_hash,fight_id,actor_hash));
create table if not exists duplicate_fights(
 duplicate_group text,report_hash text,fight_id integer,is_canonical integer,
 primary key(duplicate_group,report_hash,fight_id));
'''

def median(xs):return statistics.median(xs) if xs else 0.0

def mad(xs):
 if not xs:return 0.0
 m=median(xs);return median([abs(x-m) for x in xs])

def modified_z(x,xs):
 m=median(xs);d=mad(xs)
 return (0.0 if x==m else math.copysign(float('inf'),x-m)) if d==0 else .6745*(x-m)/d

def percentile(xs,p):
 xs=sorted(float(x) for x in xs)
 if not xs:return 0.0
 k=(len(xs)-1)*p;lo=math.floor(k);hi=math.ceil(k)
 return xs[lo] if lo==hi else xs[lo]*(hi-k)+xs[hi]*(k-lo)

def fight_signature(db,rh,fid,encounter,duration):
 # Uses anonymized action stream; no names. Rounds duration to avoid tiny upload differences.
 rows=[]
 for (payload,) in db.execute('select payload from events where report_hash=? and fight_id=? order by seq',(rh,fid)):
  try:e=json.loads(payload)
  except:continue
  typ=str(e.get('type','')).lower()
  if typ in {'damage','calculateddamage','cast','death'}:
   aid=e.get('abilityGameID') or (e.get('ability') or {}).get('guid') if isinstance(e.get('ability'),dict) else e.get('abilityGameID')
   rows.append(f"{typ}:{aid or 0}:{e.get('sourceID') or 0}:{e.get('targetID') or 0}:{int(float(e.get('timestamp') or 0))}:{int(float(e.get('amount') or 0))}")
 import hashlib
 raw=f'{encounter}|{round(duration/1000)}|'+'|'.join(rows[:500])
 return hashlib.sha256(raw.encode()).hexdigest()[:24]

def run(db_path,z_threshold=3.5,min_cell_samples=10,exclude_review=False):
 db=sqlite3.connect(db_path);db.executescript(SCHEMA);db.execute('delete from eligibility_results');db.execute('delete from duplicate_fights')
 tables={r[0] for r in db.execute("select name from sqlite_master where type='table'")}
 if 'player_features' not in tables:raise RuntimeError('Run P0-2 comparison-cell generation first.')
 # Duplicate fight screening.
 sigs=defaultdict(list)
 for rh,fid,enc,start,end in db.execute('select report_hash,fight_id,encounter_id,start,end from fights'):
  sig=fight_signature(db,rh,fid,enc,max(float(end or 0)-float(start or 0),1));sigs[sig].append((rh,fid))
 duplicate_noncanonical=set()
 for sig,items in sigs.items():
  for i,(rh,fid) in enumerate(sorted(items)):
   canonical=i==0;db.execute('insert into duplicate_fights values(?,?,?,?)',(sig,rh,fid,int(canonical)))
   if not canonical:duplicate_noncanonical.add((rh,fid))
 rows=[]
 q='''select report_hash,fight_id,actor_hash,job,partition_id,patch,encounter_id,difficulty,phase,
 duration_ms,active_ratio,action_count,total_damage,deaths,weakness_events,eligible,exclusion_reason,kill_time_bucket
 from player_features'''
 for r in db.execute(q):
  d=dict(zip(['rh','fid','actor','job','partition','patch','enc','difficulty','phase','duration','active','actions','damage','deaths','weak','eligible','reason','bucket'],r));
  d['apm']=d['actions']*60000/max(d['duration'],1);d['dpm']=d['damage']*60000/max(d['duration'],1);rows.append(d)
 groups=defaultdict(list)
 for r in rows:groups[(r['partition'],r['patch'],r['enc'],r['difficulty'],r['phase'],r['job'],r['bucket'])].append(r)
 hard_ok=review=0
 for key,group in groups.items():
  ds=[x['duration'] for x in group];apms=[x['apm'] for x in group];dpms=[x['dpm'] for x in group]
  enough=len(group)>=min_cell_samples
  for x in group:
   reasons=[z for z in str(x['reason'] or '').split(',') if z]
   if (x['rh'],x['fid']) in duplicate_noncanonical:reasons.append('duplicate_fight')
   # Broken/truncated event streams.
   if x['actions']<2:reasons.append('insufficient_actions')
   if x['duration']<=0:reasons.append('invalid_duration')
   h=not any(r in reasons for r in ('job_unknown','low_active_ratio','death','weakness','duplicate_fight','insufficient_actions','invalid_duration'))
   zd=modified_z(x['duration'],ds) if enough else 0;za=modified_z(x['apm'],apms) if enough else 0;zp=modified_z(x['dpm'],dpms) if enough else 0
   flags=[]
   if enough and abs(zd)>=z_threshold:flags.append('duration_outlier')
   if enough and abs(za)>=z_threshold:flags.append('apm_outlier')
   if enough and abs(zp)>=z_threshold:flags.append('dpm_outlier')
   if not enough:flags.append('small_sample_no_outlier_test')
   rv=bool(flags and flags!=['small_sample_no_outlier_test'])
   if exclude_review and rv:h=False;reasons+=flags
   quality=max(0,100-25*len(set(reasons))-10*len(flags))
   db.execute('insert or replace into eligibility_results values(?,?,?,?,?,?,?,?,?,?,?)',(x['rh'],x['fid'],x['actor'],int(h),int(rv),','.join(sorted(set(reasons+flags))),quality,zd,za,zp,next((s for s,it in sigs.items() if (x['rh'],x['fid']) in it),'')))
   hard_ok+=int(h);review+=int(rv)
 # Rebuild cells only from hard eligible, excluding review only when explicitly requested.
 if 'comparison_cells' in tables:
  db.execute('delete from comparison_cells')
  chosen=[x for x in rows if db.execute('select hard_eligible,review_flag from eligibility_results where report_hash=? and fight_id=? and actor_hash=?',(x['rh'],x['fid'],x['actor'])).fetchone() in ([(1,0)] if exclude_review else [(1,0),(1,1)])]
  cg=defaultdict(list)
  for x in chosen:cg[(x['partition'],x['patch'],x['enc'],x['difficulty'],x['phase'],x['job'],x['bucket'])].append(x)
  for key,g in cg.items():
   ar=[x['active'] for x in g];ap=[x['apm'] for x in g];dp=[x['dpm'] for x in g];n=len(g);conf='high' if n>=100 else 'medium' if n>=30 else 'low' if n>=10 else 'insufficient';cell='|'.join(map(str,key))
   vals=(cell,*key,n,conf,median(ar),percentile(ar,.25),percentile(ar,.75),median(ap),percentile(ap,.25),percentile(ap,.75),median(dp),percentile(dp,.25),percentile(dp,.75))
   db.execute('insert into comparison_cells values('+','.join('?'*len(vals))+')',vals)
 db.commit();summary={'rows':len(rows),'hard_eligible':hard_ok,'review_flags':review,'duplicate_fights':len(duplicate_noncanonical),'cells':db.execute('select count(*) from comparison_cells').fetchone()[0] if 'comparison_cells' in tables else 0};db.close();return summary

def main():
 p=argparse.ArgumentParser();p.add_argument('--db',required=True);p.add_argument('--z-threshold',type=float,default=3.5);p.add_argument('--min-cell-samples',type=int,default=10);p.add_argument('--exclude-review',action='store_true');a=p.parse_args();print(json.dumps(run(a.db,a.z_threshold,a.min_cell_samples,a.exclude_review),ensure_ascii=False,indent=2))
if __name__=='__main__':main()
