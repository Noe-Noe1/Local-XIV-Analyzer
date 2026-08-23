#!/usr/bin/env python3
"""P0-7 job-specific analysis engine.
Combines deterministic job rules with P0-6 statistical baselines.
Rules are patch-versioned JSON and missing rules degrade to statistical-only analysis.
"""
from __future__ import annotations
import argparse,json,math,sqlite3
from collections import Counter,defaultdict
from pathlib import Path
from rule_registry import load_registry

SCHEMA='''
create table if not exists job_analysis_runs(
 run_id integer primary key autoincrement,created_at text default current_timestamp,
 baseline_version text,rules_version text,players integer,findings integer);
create table if not exists job_analysis_results(
 run_id integer,report_hash text,fight_id integer,actor_hash text,job text,
 cell_key text,category text,severity text,code text,message text,
 actual real,expected_low real,expected_median real,expected_high real,
 confidence text,evidence_json text);
'''
DEFAULT_RULES={
 'version':'p0-7.rules.1','patch':'generic','jobs':{
  j:{'role':('tank' if j in {'PLD','WAR','DRK','GNB'} else 'healer' if j in {'WHM','SCH','AST','SGE'} else 'melee' if j in {'MNK','DRG','NIN','SAM','RPR','VPR'} else 'physical_ranged' if j in {'BRD','MCH','DNC'} else 'caster'),
     'max_gcd_gap_ms':3500,'min_active_ratio':.85,'required_actions':[], 'combos':[], 'cooldowns':{}}
  for j in ['PLD','WAR','DRK','GNB','WHM','SCH','AST','SGE','MNK','DRG','NIN','SAM','RPR','VPR','BRD','MCH','DNC','BLM','SMN','RDM','PCT','BLU']}}

def load_rules(path=None):
 if not path:return DEFAULT_RULES
 return load_registry("job",path).as_dict()

def ability_id(e):
 a=e.get('abilityGameID')
 if a is None and isinstance(e.get('ability'),dict):a=e['ability'].get('guid')
 return str(a or 'unknown')
def etype(e):return str(e.get('type','')).lower()
def actions_for(db,rh,fid,actor):
 out=[]
 for (p,) in db.execute('select payload from events where report_hash=? and fight_id=? order by seq',(rh,fid)):
  try:e=json.loads(p)
  except:continue
  if str(e.get('sourceID') or '')==actor and etype(e) in {'cast','begincast','damage','calculateddamage'}:out.append(e)
 return out

def latest_version(db):
 row=db.execute('select version_id from baseline_versions order by created_at desc limit 1').fetchone()
 return row[0] if row else None

def baseline_map(db,version,cell):
 return {r[0]:dict(zip(['n','confidence','median','q1','q3','p10','p90'],r[1:])) for r in db.execute('select metric,sample_count,confidence,median,q1,q3,p10,p90 from statistical_baselines where version_id=? and cell_key=?',(version,cell))}
def action_map(db,version,cell):
 return {str(r[0]):dict(zip(['n','usage','median','q1','q3'],r[1:])) for r in db.execute('select ability_id,sample_count,usage_rate,median_uses_per_min,q1_uses_per_min,q3_uses_per_min from action_baselines where version_id=? and cell_key=?',(version,cell))}

def finding(cat,sev,code,msg,actual=None,lo=None,med=None,hi=None,conf='rule',evidence=None):
 return {'category':cat,'severity':sev,'code':code,'message':msg,'actual':actual,'low':lo,'median':med,'high':hi,'confidence':conf,'evidence':evidence or {}}

def analyse_player(db,baseline_db,row,version,rules):
 rh,fid,actor,job,part,patch,enc,diff,phase,duration,active,action_count,damage,bucket=row
 cell='|'.join(map(str,(part,patch,enc,diff,phase,job,bucket)));bs=baseline_map(baseline_db,version,cell);ab=action_map(baseline_db,version,cell);ev=actions_for(db,rh,fid,actor);rule=rules['jobs'].get(job,{})
 out=[];apm=action_count*60000/max(duration,1);dpm=damage*60000/max(duration,1)
 for metric,val in [('active_ratio',active),('actions_per_min',apm),('damage_per_min',dpm)]:
  b=bs.get(metric)
  if not b:continue
  if val<b['q1']:
   sev='major' if val<b['p10'] else 'minor';out.append(finding('statistics',sev,'below_'+metric,f'{metric} が同条件Clear群より低い範囲です。',val,b['q1'],b['median'],b['q3'],b['confidence']))
 counts=Counter(ability_id(e) for e in ev);dur_min=max(duration/60000,1e-9)
 for aid,b in ab.items():
  if b['usage']<.5:continue
  rate=counts.get(aid,0)/dur_min
  if rate+1e-9<b['q1']:out.append(finding('action','minor','low_action_usage',f'アクション {aid} の使用頻度が比較群より低めです。',rate,b['q1'],b['median'],b['q3'],'statistical',{'ability_id':aid,'usage_rate':b['usage']}))
 required={str(x) for x in rule.get('required_actions',[])}
 for aid in required:
  if not counts.get(aid):out.append(finding('job_rule','major','required_action_missing',f'ジョブ規則で必要なアクション {aid} が確認できません。',0,1,1,None,'rule',{'ability_id':aid}))
 seq=[ability_id(e) for e in ev]
 for combo in rule.get('combos',[]):
  combo=list(map(str,combo));attempts=sum(1 for i in range(len(seq)-len(combo)+1) if seq[i]==combo[0]);success=sum(1 for i in range(len(seq)-len(combo)+1) if seq[i:i+len(combo)]==combo)
  if attempts and success<attempts:out.append(finding('combo','minor','combo_incomplete','コンボ完遂率が100%未満です。',success/attempts,1,1,1,'rule',{'combo':combo,'attempts':attempts,'success':success}))
 for aid,cd in rule.get('cooldowns',{}).items():
  times=sorted(float(e.get('timestamp') or 0) for e in ev if ability_id(e)==str(aid));late=[times[i]-times[i-1]-float(cd) for i in range(1,len(times)) if times[i]-times[i-1]>float(cd)+1000]
  if late:out.append(finding('cooldown','minor','cooldown_delay',f'アクション {aid} の再使用遅延を検出しました。',max(late),0,0,1000,'rule',{'delays_ms':late}))
 gcd=[float(e.get('timestamp') or 0) for e in ev if etype(e) in {'cast','begincast'}]
 gap=float(rule.get('max_gcd_gap_ms',3500));gaps=[gcd[i]-gcd[i-1] for i in range(1,len(gcd)) if gcd[i]-gcd[i-1]>gap]
 if gaps:out.append(finding('uptime','minor','long_action_gap','ジョブ規則の閾値を超える行動間隔があります。',max(gaps),None,gap,None,'rule',{'gaps_ms':gaps[:20]}))
 return cell,out

def run(db_path,rules_path=None,baseline_version=None,report_hash=None,fight_id=None,baseline_db_path=None):
 db=sqlite3.connect(db_path);db.executescript(SCHEMA);rules=load_rules(rules_path)
 baseline_db=sqlite3.connect(baseline_db_path) if baseline_db_path else db
 version=baseline_version or latest_version(baseline_db)
 if not version:
  if baseline_db is not db:baseline_db.close()
  db.close()
  raise RuntimeError('P0-6 baseline is required.')
 hasq='eligibility_results' in {r[0] for r in db.execute("select name from sqlite_master where type='table'")}
 join=' join eligibility_results e using(report_hash,fight_id,actor_hash)' if hasq else ''
 clauses=["p.job<>'UNKNOWN'"]
 params=[]
 if hasq:clauses.append('e.hard_eligible=1')
 if report_hash is not None and fight_id is not None:
  clauses.extend(['p.report_hash=?','p.fight_id=?'])
  params.extend([report_hash,fight_id])
 where=' where '+' and '.join(clauses) if clauses else ''
 q=f'''select p.report_hash,p.fight_id,p.actor_hash,p.job,p.partition_id,p.patch,p.encounter_id,p.difficulty,p.phase,p.duration_ms,p.active_ratio,p.action_count,p.total_damage,p.kill_time_bucket from player_features p {join} {where}'''
 rows=db.execute(q,params).fetchall();cur=db.execute('insert into job_analysis_runs(baseline_version,rules_version,players,findings) values(?,?,?,0)',(version,rules['version'],len(rows)));run_id=cur.lastrowid;total=0
 for row in rows:
  cell,findings=analyse_player(db,baseline_db,row,version,rules)
  for f in findings:
   vals=(run_id,row[0],row[1],row[2],row[3],cell,f['category'],f['severity'],f['code'],f['message'],f['actual'],f['low'],f['median'],f['high'],f['confidence'],json.dumps(f['evidence'],ensure_ascii=False,separators=(',',':')));db.execute('insert into job_analysis_results values('+','.join('?'*len(vals))+')',vals);total+=1
 db.execute('update job_analysis_runs set findings=? where run_id=?',(total,run_id));db.commit()
 if baseline_db is not db:baseline_db.close()
 db.close()
 return {'run_id':run_id,'baseline_version':version,'rules_version':rules['version'],'players':len(rows),'findings':total}
def main():
 p=argparse.ArgumentParser();p.add_argument('--db',required=True);p.add_argument('--rules');p.add_argument('--baseline-version');a=p.parse_args();print(json.dumps(run(a.db,a.rules,a.baseline_version),ensure_ascii=False,indent=2))
if __name__=='__main__':main()
