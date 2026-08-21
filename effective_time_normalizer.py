#!/usr/bin/env python3
"""P0-3 effective combat time normalization for anonymized FFLogs events."""
from __future__ import annotations
import argparse,json,sqlite3
from pathlib import Path

ACTION_TYPES={'damage','calculateddamage','heal','calculatedheal','cast'}
TARGETABLE_TYPES={'targetabilityupdate','targetable'}
# Default IDs can be extended through configuration. Unknown statuses are not guessed.
DEFAULT_UNABLE_STATUS_IDS={7,8,9,14,15,16,17,418,419,1495}
SCHEMA='''
create table if not exists effective_time(
 report_hash text,fight_id integer,actor_hash text,
 fight_ms real,targetable_ms real,unable_ms real,effective_ms real,
 first_action_ms real,last_action_ms real,prepull_ms real,end_slack_ms real,
 confidence text,notes text,primary key(report_hash,fight_id,actor_hash));
'''

def merge(intervals):
 if not intervals:return []
 out=[]
 for a,b in sorted((max(0,float(a)),max(0,float(b))) for a,b in intervals if b>a):
  if out and a<=out[-1][1]:out[-1]=(out[-1][0],max(out[-1][1],b))
  else:out.append((a,b))
 return out

def length(intervals):return sum(b-a for a,b in merge(intervals))

def intersection(a,b):
 out=[]
 for x1,x2 in merge(a):
  for y1,y2 in merge(b):
   lo=max(x1,y1);hi=min(x2,y2)
   if hi>lo:out.append((lo,hi))
 return merge(out)

def subtract(base,cuts):
 result=[];cuts=merge(cuts)
 for a,b in merge(base):
  cur=a
  for c,d in cuts:
   if d<=cur or c>=b:continue
   if c>cur:result.append((cur,min(c,b)))
   cur=max(cur,d)
   if cur>=b:break
  if cur<b:result.append((cur,b))
 return merge(result)

def timestamp(e):
 try:return float(e.get('timestamp',0))
 except:return 0.0

def status_id(e):
 x=e.get('abilityGameID')
 if x is None and isinstance(e.get('ability'),dict):x=e['ability'].get('guid')
 try:return int(x)
 except:return -1

def actor_id(e,key):return str(e.get(key) or '')

def bool_targetable(e):
 for k in ('targetable','isTargetable'):
  if k in e:return bool(e[k])
 # Some exports use targetability state 1/0.
 for k in ('targetableState','state'):
  if k in e:
   try:return int(e[k])!=0
   except:pass
 return None

def targetable_intervals(events,start,end,boss_ids=None):
 changes=[]
 for e in events:
  typ=str(e.get('type','')).lower()
  if typ not in TARGETABLE_TYPES:continue
  aid=actor_id(e,'targetID') or actor_id(e,'sourceID')
  if boss_ids and aid not in boss_ids:continue
  state=bool_targetable(e)
  if state is not None:changes.append((timestamp(e),state))
 if not changes:return [(start,end)],'fallback_full_fight'
 changes.sort();state=True;cur=start;out=[]
 for t,s in changes:
  t=min(max(t,start),end)
  if state and t>cur:out.append((cur,t))
  state=s;cur=t
 if state and cur<end:out.append((cur,end))
 return merge(out),'event_based'

def unable_intervals(events,actor,start,end,ids):
 opened={};out=[]
 for e in sorted(events,key=timestamp):
  if actor_id(e,'targetID')!=actor:continue
  typ=str(e.get('type','')).lower();sid=status_id(e)
  if sid not in ids:continue
  t=min(max(timestamp(e),start),end)
  if typ in {'applybuff','applydebuff','refreshbuff','refreshdebuff'}:opened[sid]=t
  elif typ in {'removebuff','removedebuff'} and sid in opened:out.append((opened.pop(sid),t))
 for t in opened.values():out.append((t,end))
 return merge(out)

def normalize(events,start,end,actor,boss_ids=None,unable_ids=None):
 unable_ids=set(unable_ids or DEFAULT_UNABLE_STATUS_IDS);fight=max(end-start,1)
 actions=[timestamp(e) for e in events if actor_id(e,'sourceID')==actor and str(e.get('type','')).lower() in ACTION_TYPES]
 first=min(actions) if actions else start;last=max(actions) if actions else start
 tgt,mode=targetable_intervals(events,start,end,boss_ids);unable=unable_intervals(events,actor,start,end,unable_ids)
 active_window=[(max(start,first),min(end,max(last,first)))] if actions else []
 target_actor=intersection(tgt,active_window) if active_window else []
 effective=subtract(target_actor,unable);eff=length(effective)
 notes=[]
 if mode!='event_based':notes.append('targetability_fallback')
 if not actions:notes.append('no_actions')
 confidence='high' if mode=='event_based' and actions else 'medium' if actions else 'low'
 return {'fight_ms':fight,'targetable_ms':length(tgt),'unable_ms':length(intersection(unable,tgt)),'effective_ms':eff,'first_action_ms':first,'last_action_ms':last,'prepull_ms':max(0,first-start),'end_slack_ms':max(0,end-last),'confidence':confidence,'notes':','.join(notes)}

def run(db_path,unable_ids=None):
 db=sqlite3.connect(db_path);db.executescript(SCHEMA);db.execute('delete from effective_time');count=0
 fights=db.execute('select report_hash,fight_id,start,end from fights').fetchall()
 for rh,fid,start,end in fights:
  events=[]
  for (p,) in db.execute('select payload from events where report_hash=? and fight_id=? order by seq',(rh,fid)):
   try:events.append(json.loads(p))
   except:pass
  actors={r[0] for r in db.execute('select actor_hash from fight_players where report_hash=? and fight_id=?',(rh,fid))} if 'fight_players' in {r[0] for r in db.execute("select name from sqlite_master where type='table'")} else {actor_id(e,'sourceID') for e in events if actor_id(e,'sourceID')}
  boss_ids={actor_id(e,'targetID') for e in events if str(e.get('type','')).lower() in {'damage','calculateddamage'} and actor_id(e,'targetID')}
  for actor in actors:
   n=normalize(events,float(start),float(end),actor,boss_ids,unable_ids)
   db.execute('insert or replace into effective_time values(?,?,?,?,?,?,?,?,?,?,?,?)',(rh,fid,actor,n['fight_ms'],n['targetable_ms'],n['unable_ms'],n['effective_ms'],n['first_action_ms'],n['last_action_ms'],n['prepull_ms'],n['end_slack_ms'],n['confidence'],n['notes']));count+=1
 db.commit();db.close();return {'normalized_players':count,'fights':len(fights)}

def main():
 p=argparse.ArgumentParser();p.add_argument('--db',required=True);p.add_argument('--unable-status-id',action='append',type=int);a=p.parse_args();print(json.dumps(run(a.db,a.unable_status_id),ensure_ascii=False,indent=2))
if __name__=='__main__':main()
