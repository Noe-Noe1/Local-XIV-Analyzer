#!/usr/bin/env python3
"""P0-10 local healing, shielding, mitigation, and death-window analysis."""
from __future__ import annotations
import argparse,json,math,sqlite3
from collections import defaultdict
from pathlib import Path
SCHEMA='''
create table if not exists healing_runs(run_id integer primary key autoincrement,created_at text default current_timestamp,rules_version text,fights integer,events integer,warnings integer);
create table if not exists healing_metrics(run_id integer,report_hash text,fight_id integer,actor_hash text,duration_ms real,raw_healing real,effective_healing real,overheal real,absorbed real,hps real,ehps real,targets integer,confidence text,warnings text,primary key(run_id,report_hash,fight_id,actor_hash));
create table if not exists mitigation_metrics(run_id integer,report_hash text,fight_id integer,actor_hash text,damage_taken real,prevented_estimate real,shield_absorbed real,mitigation_uses integer,coverage_ms real,confidence text,warnings text,primary key(run_id,report_hash,fight_id,actor_hash));
create table if not exists mitigation_allocations(run_id integer,report_hash text,fight_id integer,event_seq integer,target_actor text,owner_actor text,status_id text,observed_damage real,unmitigated_estimate real,prevented_estimate real,method text,confidence text,evidence_json text);
create table if not exists death_windows(run_id integer,report_hash text,fight_id integer,target_actor text,death_timestamp real,window_start real,incoming_damage real,effective_healing real,shield_absorbed real,last_hit_ability text,last_hit_amount real,evidence_json text);
'''
DEFAULT={'version':'p0-10.rules.1','mitigations':{}}
def load(path=None):
 if not path:return DEFAULT
 x=json.loads(Path(path).read_text(encoding='utf-8'))
 if not x.get('version') or not isinstance(x.get('mitigations'),dict):raise ValueError('Invalid mitigation rules')
 return x
def typ(e):return str(e.get('type','')).lower()
def ts(e):return float(e.get('timestamp') or 0)
def actor(e,k):return str(e.get(k) or '')
def ability(e):
 a=e.get('abilityGameID')
 if a is None and isinstance(e.get('ability'),dict):a=e['ability'].get('guid')
 return str(a or 'unknown')
def amount(e,k='amount'):
 try:return max(0,float(e.get(k) or 0))
 except:return 0.0
def heal_parts(e):
 raw=amount(e);over=amount(e,'overheal') or amount(e,'overHealing');absorbed=amount(e,'absorbed')
 effective=max(0,raw-over)
 return raw,effective,over,absorbed
def windows(events,rules,end):
 opened={};out=defaultdict(list)
 for e in events:
  k=typ(e);sid=ability(e);target=actor(e,'targetID');owner=actor(e,'sourceID');t=ts(e)
  if sid not in rules['mitigations'] or not target:continue
  key=(target,sid,owner)
  if k in {'applybuff','applydebuff','refreshbuff','refreshdebuff'}:
   if key in opened:
    s,natural=opened.pop(key);out[target].append((sid,owner,s,min(t,natural)))
   dur=amount(e,'duration');opened[key]=(t,min(end,t+dur) if dur else end)
  elif k in {'removebuff','removedebuff'} and key in opened:
   s,natural=opened.pop(key);out[target].append((sid,owner,s,min(t,natural)))
 for (target,sid,owner),(s,natural) in opened.items():out[target].append((sid,owner,s,natural))
 return out
def run(db_path,rules_path=None,death_window_ms=10000):
 db=sqlite3.connect(db_path);db.executescript(SCHEMA);rules=load(rules_path);rid=db.execute('insert into healing_runs(rules_version,fights,events,warnings) values(?,0,0,0)',(rules['version'],)).lastrowid;nf=ne=nw=0
 for rh,fid,start,end in db.execute('select report_hash,fight_id,start,end from fights').fetchall():
  ev=[]
  for seq,(p,) in enumerate(db.execute('select payload from events where report_hash=? and fight_id=? order by seq',(rh,fid))):
   try:e=json.loads(p);e['_seq']=seq;ev.append(e)
   except:pass
  duration=max(float(end)-float(start),1);mw=windows(ev,rules,float(end));heals=defaultdict(lambda:[0,0,0,0,set(),set()]);taken=defaultdict(float);prevented=defaultdict(float);shield=defaultdict(float);uses=defaultdict(int);coverage=defaultdict(float);warn=defaultdict(set)
  for target,ws in mw.items():
   for sid,owner,a,b in ws:uses[owner]+=1;coverage[owner]+=max(0,b-a)
  for e in ev:
   k=typ(e)
   if k in {'heal','calculatedheal','healing'}:
    ne+=1;src=actor(e,'sourceID');target=actor(e,'targetID');raw,eff,over,absb=heal_parts(e);x=heals[src];x[0]+=raw;x[1]+=eff;x[2]+=over;x[3]+=absb;x[4].add(target);x[5].add(ability(e));shield[src]+=absb
    if 'overheal' not in e and 'overHealing' not in e:warn[src].add('overheal_field_missing');nw+=1
   elif k in {'absorbed','absorb'}:
    src=actor(e,'sourceID');shield[src]+=amount(e);ne+=1
   elif k in {'damage','calculateddamage'}:
    ne+=1;target=actor(e,'targetID');obs=amount(e);taken[target]+=obs;t=ts(e);active=[x for x in mw.get(target,[]) if x[2]<=t<x[3]];pct=[]
    for sid,owner,*_ in active:
     r=rules['mitigations'][sid]
     if r.get('kind')=='damage_reduction' and 0<float(r.get('value',0))<1:pct.append((sid,owner,float(r['value']),r))
    if pct:
     mult=math.prod(1-v for _,_,v,_ in pct);unmit=obs/max(mult,1e-9);loss=max(0,unmit-obs);weights=[v for _,_,v,_ in pct];den=sum(weights) or 1
     for (sid,owner,v,r),w in zip(pct,weights):
      share=loss*w/den;prevented[owner]+=share;vals=(rid,rh,fid,e['_seq'],target,owner,sid,obs,unmit,share,'multiplicative_inverse_weighted','medium',json.dumps({'timestamp':t,'ability':ability(e)},separators=(',',':')));db.execute('insert into mitigation_allocations values('+','.join('?'*len(vals))+')',vals)
  actors=set(heals)|set(prevented)|set(shield)|set(uses)
  for a in actors:
   h=heals[a];conf='medium' if warn[a] else 'high';db.execute('insert or replace into healing_metrics values(?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(rid,rh,fid,a,duration,h[0],h[1],h[2],h[3],h[0]*1000/duration,h[1]*1000/duration,len(h[4]),conf,','.join(sorted(warn[a]))))
   db.execute('insert or replace into mitigation_metrics values(?,?,?,?,?,?,?,?,?,?,?)',(rid,rh,fid,a,taken[a],prevented[a],shield[a],uses[a],coverage[a],conf,','.join(sorted(warn[a]))))
  for d in [x for x in ev if typ(x)=='death']:
   target=actor(d,'targetID');dt=ts(d);lo=max(float(start),dt-death_window_ms);inc=[x for x in ev if lo<=ts(x)<=dt and actor(x,'targetID')==target and typ(x) in {'damage','calculateddamage'}];hs=[x for x in ev if lo<=ts(x)<=dt and actor(x,'targetID')==target and typ(x) in {'heal','calculatedheal','healing'}];incoming=sum(amount(x) for x in inc);effective=sum(heal_parts(x)[1] for x in hs);absb=sum(heal_parts(x)[3] for x in hs);last=max(inc,key=ts) if inc else {};db.execute('insert into death_windows values(?,?,?,?,?,?,?,?,?,?,?,?)',(rid,rh,fid,target,dt,lo,incoming,effective,absb,ability(last) if last else '',amount(last) if last else 0,json.dumps({'damage_events':len(inc),'heal_events':len(hs)},separators=(',',':'))))
  nf+=1
 db.execute('update healing_runs set fights=?,events=?,warnings=? where run_id=?',(nf,ne,nw,rid));db.commit();db.close();return {'run_id':rid,'rules_version':rules['version'],'fights':nf,'events':ne,'warnings':nw}
def main():
 p=argparse.ArgumentParser();p.add_argument('--db',required=True);p.add_argument('--rules');p.add_argument('--death-window-ms',type=int,default=10000);a=p.parse_args();print(json.dumps(run(a.db,a.rules,a.death_window_ms),ensure_ascii=False,indent=2))
if __name__=='__main__':main()
