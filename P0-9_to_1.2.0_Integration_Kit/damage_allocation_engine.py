from __future__ import annotations
import argparse,itertools,json,math,sqlite3
from collections import defaultdict
from pathlib import Path

SCHEMA='''
create table if not exists allocation_runs(run_id integer primary key autoincrement,created_at text default current_timestamp,rules_version text,fights integer,events integer,allocated_damage real,warnings integer);
create table if not exists damage_allocations(run_id integer,report_hash text,fight_id integer,event_seq integer,source_actor text,buff_owner text,buff_id text,buff_kind text,observed_damage real,base_damage real,allocated_damage real,method text,confidence text,evidence_json text);
create table if not exists dps_metrics(run_id integer,report_hash text,fight_id integer,actor_hash text,duration_ms real,raw_damage real,dps real,external_gain real,own_contribution real,single_target_gain real,rdps real,ndps real,adps real,cdps real,confidence text,warnings text,primary key(run_id,report_hash,fight_id,actor_hash));
'''
DEFAULT_RULES={'version':'p0-9.rules.1','buffs':{}}

def load_rules(path=None):
    if not path:return DEFAULT_RULES
    data=json.loads(Path(path).read_text(encoding='utf-8'))
    if not data.get('version') or not isinstance(data.get('buffs'),dict):raise ValueError('Invalid allocation rules')
    return data

def typ(e):return str(e.get('type','')).lower()
def ts(e):return float(e.get('timestamp') or 0)
def actor(e,k):return str(e.get(k) or '')
def ability(e):
    a=e.get('abilityGameID')
    if a is None and isinstance(e.get('ability'),dict):a=e['ability'].get('guid')
    return str(a or 'unknown')

def status_windows(events,rules,end):
    opened={};windows=defaultdict(list)
    for seq,e in enumerate(events):
        t=ts(e);k=typ(e);bid=ability(e);target=actor(e,'targetID');owner=actor(e,'sourceID')
        if bid not in rules['buffs'] or not target:continue
        key=(target,bid,owner)
        if k in {'applybuff','applydebuff','refreshbuff','refreshdebuff'}:
            if key in opened:
                b,o,s,n,q=opened.pop(key);windows[target].append((b,o,s,min(t,n),q))
            duration=float(e.get('duration') or 0);opened[key]=(bid,owner,t,min(t+duration,end) if duration else end,seq)
        elif k in {'removebuff','removedebuff'} and key in opened:
            b,o,s,n,q=opened.pop(key);windows[target].append((b,o,s,min(t,n),q))
    for (target,_,_),(b,o,s,n,q) in opened.items():windows[target].append((b,o,s,n,q))
    return windows

def percentage_allocation(observed,active,rules):
    buffs=[]
    for bid,owner,*_ in active:
        r=rules['buffs'][bid]
        if r.get('kind')=='damage_percent' and float(r.get('value',0))>0:buffs.append((bid,owner,float(r['value']),r))
    if not buffs:return observed,[]
    base=observed/math.prod(1+x[2] for x in buffs);gain=observed-base;n=len(buffs);out=[]
    for i,(bid,owner,value,rule) in enumerate(buffs):
        phi=0.0;others=[j for j in range(n) if j!=i]
        for size in range(n):
            for subset in itertools.combinations(others,size):
                before=base*math.prod(1+buffs[j][2] for j in subset)
                weight=math.factorial(size)*math.factorial(n-size-1)/math.factorial(n)
                phi+=weight*(before*(1+value)-before)
        out.append([bid,owner,phi,rule,'exact_percentage','high'])
    total=sum(x[2] for x in out);scale=gain/total if total else 1
    for x in out:x[2]*=scale
    return base,out

def crit_dh_estimate(observed,event,active,rules):
    critical=bool(event.get('critical') or event.get('isCritical') or event.get('hitType') in (2,4))
    direct=bool(event.get('directHit') or event.get('isDirectHit') or event.get('hitType') in (3,4));out=[]
    for bid,owner,*_ in active:
        r=rules['buffs'][bid];kind=r.get('kind')
        if kind not in {'crit_rate','direct_rate'}:continue
        if kind=='crit_rate' and not critical:continue
        if kind=='direct_rate' and not direct:continue
        rate=float(r.get('value',0));bonus=float(r.get('bonus_multiplier',.4 if kind=='crit_rate' else .25))
        out.append([bid,owner,observed*(rate*bonus)/(1+rate*bonus),r,'expected_value_estimate','low'])
    return out

def run(db_path,rules_path=None):
    db=sqlite3.connect(db_path);db.executescript(SCHEMA);rules=load_rules(rules_path)
    rid=db.execute('insert into allocation_runs(rules_version,fights,events,allocated_damage,warnings) values(?,0,0,0,0)',(rules['version'],)).lastrowid
    fights=events_count=warnings=0;allocated=0.0
    for rh,fid,start,end in db.execute('select report_hash,fight_id,start,end from fights').fetchall():
        events=[]
        for seq,(payload,) in enumerate(db.execute('select payload from events where report_hash=? and fight_id=? order by seq',(rh,fid))):
            try:e=json.loads(payload);e['_seq']=seq;events.append(e)
            except Exception:pass
        windows=status_windows(events,rules,float(end));raw=defaultdict(float);gained=defaultdict(float);given=defaultdict(float);single=defaultdict(float);warn=defaultdict(set)
        for e in events:
            if typ(e) not in {'damage','calculateddamage'}:continue
            src=actor(e,'sourceID');observed=float(e.get('amount') or 0)
            if not src or observed<=0:continue
            events_count+=1;raw[src]+=observed;t=ts(e);active=[x for x in windows.get(src,[]) if x[2]<=t<x[3]]
            base,allocs=percentage_allocation(observed,active,rules);allocs+=crit_dh_estimate(observed,e,active,rules)
            if any(x[4]=='expected_value_estimate' for x in allocs):warn[src].add('crit_dh_allocation_estimated');warnings+=1
            for bid,owner,amt,r,method,confidence in allocs:
                if not owner or owner==src:continue
                gained[src]+=amt;given[owner]+=amt;allocated+=amt
                if r.get('targeting')=='single':single[src]+=amt
                vals=(rid,rh,fid,e['_seq'],src,owner,bid,r.get('kind'),observed,base,amt,method,confidence,json.dumps({'timestamp':t,'ability':ability(e)},separators=(',',':')))
                db.execute('insert into damage_allocations values('+','.join('?'*len(vals))+')',vals)
        duration=max(float(end)-float(start),1)
        for a in set(raw)|set(given):
            dps=raw[a]*1000/duration;rdps=(raw[a]-gained[a]+given[a])*1000/duration;ndps=(raw[a]-gained[a])*1000/duration;adps=(raw[a]-single[a])*1000/duration;cdps=(raw[a]-single[a]+given[a])*1000/duration
            vals=(rid,rh,fid,a,duration,raw[a],dps,gained[a],given[a],single[a],rdps,ndps,adps,cdps,'low' if warn[a] else 'high',','.join(sorted(warn[a])))
            db.execute('insert into dps_metrics values('+','.join('?'*len(vals))+')',vals)
        fights+=1
    db.execute('update allocation_runs set fights=?,events=?,allocated_damage=?,warnings=? where run_id=?',(fights,events_count,allocated,warnings,rid));db.commit();db.close()
    return {'run_id':rid,'rules_version':rules['version'],'fights':fights,'damage_events':events_count,'allocated_damage':round(allocated,3),'warnings':warnings}

def main():
    p=argparse.ArgumentParser();p.add_argument('--db',required=True);p.add_argument('--rules');a=p.parse_args();print(json.dumps(run(a.db,a.rules),ensure_ascii=False,indent=2))
if __name__=='__main__':main()
