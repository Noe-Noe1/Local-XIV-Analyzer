#!/usr/bin/env python3
"""P0-8 all-job and boss/phase analysis framework.
Provides complete job registration and generic boss analysis; exact encounter rules are
loaded from versioned JSON and are never guessed when unavailable.
"""
from __future__ import annotations
import argparse,json,sqlite3,statistics
from collections import Counter,defaultdict
from pathlib import Path
from rule_registry import load_registry
JOBS=['PLD','WAR','DRK','GNB','WHM','SCH','AST','SGE','MNK','DRG','NIN','SAM','RPR','VPR','BRD','MCH','DNC','BLM','SMN','RDM','PCT','BLU']
ROLES={j:('tank' if j in {'PLD','WAR','DRK','GNB'} else 'healer' if j in {'WHM','SCH','AST','SGE'} else 'melee' if j in {'MNK','DRG','NIN','SAM','RPR','VPR'} else 'physical_ranged' if j in {'BRD','MCH','DNC'} else 'caster') for j in JOBS}
SCHEMA='''create table if not exists boss_analysis_runs(run_id integer primary key autoincrement,created_at text default current_timestamp,rules_version text,fights integer,findings integer);create table if not exists boss_analysis_results(run_id integer,report_hash text,fight_id integer,encounter_id integer,phase integer,category text,severity text,code text,message text,timestamp real,evidence_json text);create table if not exists phase_windows(report_hash text,fight_id integer,phase integer,start_ms real,end_ms real,source text,confidence text,primary key(report_hash,fight_id,phase));create table if not exists job_boss_summary(run_id integer,report_hash text,fight_id integer,actor_hash text,job text,role text,phase integer,actions integer,damage real,damage_taken real,deaths integer,primary key(run_id,report_hash,fight_id,actor_hash,phase));'''
DEFAULT={'version':'p0-8.generic.1','encounters':{}}
def load(path):
 if not path:return DEFAULT
 return load_registry("encounter",path).as_dict()
def typ(e):return str(e.get('type','')).lower()
def aid(e):
 a=e.get('abilityGameID');return str(a if a is not None else ((e.get('ability') or {}).get('guid') if isinstance(e.get('ability'),dict) else 'unknown'))
def ts(e):return float(e.get('timestamp') or 0)
def get_events(db,rh,fid):
 out=[]
 for (p,) in db.execute('select payload from events where report_hash=? and fight_id=? order by seq',(rh,fid)):
  try:out.append(json.loads(p))
  except:pass
 return out
def phases(events,start,end,rule):
 explicit=[]
 for e in events:
  if typ(e) in {'phasetransition','phase'}:
   try:explicit.append((int(e.get('phase') or e.get('id')),ts(e)))
   except:pass
 if explicit:
  explicit=sorted(set(explicit),key=lambda x:x[1]);return [(p,t,explicit[i+1][1] if i+1<len(explicit) else end,'event','high') for i,(p,t) in enumerate(explicit)]
 defs=rule.get('phases',[])
 if defs:return [(int(x['id']),start+float(x['start_ms']),start+float(x.get('end_ms',end-start)),'rule','medium') for x in defs]
 return [(0,start,end,'whole_fight','low')]
def add(out,phase,cat,sev,code,msg,t=None,ev=None):out.append((phase,cat,sev,code,msg,t,json.dumps(ev or {},ensure_ascii=False,separators=(',',':'))))
def analyze_fight(events,start,end,enc,rule,roster):
 out=[];ps=phases(events,start,end,rule)
 # Generic boss diagnostics available for all encounters.
 deaths=[e for e in events if typ(e)=='death']
 for e in deaths:add(out,0,'survival','major','death','戦闘不能を検出しました。',ts(e),{'target':e.get('targetID')})
 interrupts=[e for e in events if typ(e)=='interrupt']
 casts=[e for e in events if typ(e) in {'begincast','cast'}]
 for req in rule.get('required_interrupts',[]):
  matches=[e for e in casts if aid(e)==str(req)]
  for c in matches:
   ok=any(abs(ts(i)-ts(c))<=5000 for i in interrupts)
   if not ok:add(out,0,'mechanic','major','missed_interrupt',f'中断対象アクション {req} の中断を確認できません。',ts(c),{'ability':req})
 avoid={str(x) for x in rule.get('avoidable_damage',[])}
 for e in events:
  if typ(e) in {'damage','calculateddamage'} and aid(e) in avoid:add(out,0,'mechanic','minor','avoidable_damage',f'回避対象アクション {aid(e)} の被弾を検出しました。',ts(e),{'ability':aid(e),'amount':e.get('amount',0),'target':e.get('targetID')})
 for mech in rule.get('mechanics',[]):
  ab=str(mech.get('ability_id'));count=sum(aid(e)==ab for e in events)
  if count<int(mech.get('min_count',0)):add(out,0,'data','info','mechanic_data_missing',f'ギミック {ab} の観測数が規則未満です。',None,{'count':count})
 summaries=[]
 for p,lo,hi,source,conf in ps:
  pe=[e for e in events if lo<=ts(e)<hi]
  for actor,job in roster:
   actions=[e for e in pe if str(e.get('sourceID') or '')==actor and typ(e) in {'cast','begincast','damage','calculateddamage'}]
   damage=sum(float(e.get('amount') or 0) for e in pe if str(e.get('sourceID') or '')==actor and typ(e) in {'damage','calculateddamage'})
   taken=sum(float(e.get('amount') or 0) for e in pe if str(e.get('targetID') or '')==actor and typ(e) in {'damage','calculateddamage'})
   dead=sum(1 for e in pe if str(e.get('targetID') or '')==actor and typ(e)=='death')
   summaries.append((actor,job,ROLES.get(job,'unknown'),p,len(actions),damage,taken,dead))
 return ps,out,summaries
def run(db_path,rules_path=None,report_hash=None,fight_id=None):
 db=sqlite3.connect(db_path);db.executescript(SCHEMA);rules=load(rules_path);cur=db.execute('insert into boss_analysis_runs(rules_version,fights,findings) values(?,0,0)',(rules['version'],));rid=cur.lastrowid;nf=0;total=0
 fights_sql='select report_hash,fight_id,encounter_id,start,end from fights'
 params=()
 if report_hash is not None and fight_id is not None:
  fights_sql+=' where report_hash=? and fight_id=?'
  params=(report_hash,fight_id)
 for rh,fid,enc,start,end in db.execute(fights_sql,params).fetchall():
  ev=get_events(db,rh,fid);roster=db.execute('select actor_hash,job from fight_players where report_hash=? and fight_id=?',(rh,fid)).fetchall();rule=rules['encounters'].get(str(enc),{});ps,findings,sums=analyze_fight(ev,float(start),float(end),enc,rule,roster)
  for p,a,b,src,conf in ps:db.execute('insert or replace into phase_windows values(?,?,?,?,?,?,?)',(rh,fid,p,a,b,src,conf))
  for p,cat,sev,code,msg,t,evidence in findings:db.execute('insert into boss_analysis_results values(?,?,?,?,?,?,?,?,?,?,?)',(rid,rh,fid,enc,p,cat,sev,code,msg,t,evidence));total+=1
  for actor,job,role,p,acts,dmg,taken,dead in sums:db.execute('insert or replace into job_boss_summary values(?,?,?,?,?,?,?,?,?,?,?)',(rid,rh,fid,actor,job,role,p,acts,dmg,taken,dead))
  nf+=1
 db.execute('update boss_analysis_runs set fights=?,findings=? where run_id=?',(nf,total,rid));db.commit();db.close();return {'run_id':rid,'rules_version':rules['version'],'fights':nf,'findings':total,'jobs_registered':len(JOBS)}
def main():
 p=argparse.ArgumentParser();p.add_argument('--db',required=True);p.add_argument('--rules');a=p.parse_args();print(json.dumps(run(a.db,a.rules),ensure_ascii=False,indent=2))
if __name__=='__main__':main()
