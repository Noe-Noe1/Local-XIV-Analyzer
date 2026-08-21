#!/usr/bin/env python3
"""FFLogs public Clear-log collector.
Credentials are read only from environment variables. Raw actor names are removed
before any record is written. Supports resumable event pagination and a local cache.
"""
from __future__ import annotations
import argparse, base64, hashlib, json, os, sqlite3, time
import urllib.error, urllib.parse, urllib.request
from pathlib import Path

TOKEN_URL='https://www.fflogs.com/oauth/token'
API_URL='https://www.fflogs.com/api/v2/client'
FIGHTS_QUERY='''query($code:String!){reportData{report(code:$code){code title zone{id name} fights(killType:Kills){id encounterID name startTime endTime kill difficulty fightPercentage maps{id name} friendlyPlayers} masterData{actors{id name type subType petOwner gameID}}}} rateLimitData{limitPerHour pointsSpentThisHour pointsResetIn}}'''
EVENTS_QUERY='''query($code:String!,$fightIDs:[Int!],$start:Float!,$end:Float!){reportData{report(code:$code){events(fightIDs:$fightIDs,startTime:$start,endTime:$end,includeResources:true){data nextPageTimestamp}}} rateLimitData{limitPerHour pointsSpentThisHour pointsResetIn}}'''

class Client:
 def __init__(self,cache:Path,delay=.35):
  self.cid=os.getenv('FFLOGS_CLIENT_ID','').strip();self.secret=os.getenv('FFLOGS_CLIENT_SECRET','').strip()
  if not self.cid or not self.secret:raise SystemExit('FFLOGS_CLIENT_ID and FFLOGS_CLIENT_SECRET must be set.')
  self.cache=cache;cache.mkdir(parents=True,exist_ok=True);self.delay=delay;self.token=None
 def auth(self):
  body=urllib.parse.urlencode({'grant_type':'client_credentials'}).encode();basic=base64.b64encode(f'{self.cid}:{self.secret}'.encode()).decode()
  req=urllib.request.Request(TOKEN_URL,data=body,method='POST',headers={'Authorization':'Basic '+basic,'Content-Type':'application/x-www-form-urlencoded'})
  with urllib.request.urlopen(req,timeout=30) as r:self.token=json.load(r)['access_token']
 def query(self,q,variables,use_cache=True):
  key=hashlib.sha256(json.dumps([q,variables],sort_keys=True,separators=(',',':')).encode()).hexdigest();cp=self.cache/(key+'.json')
  if use_cache and cp.exists():return json.loads(cp.read_text(encoding='utf-8'))
  if not self.token:self.auth()
  payload=json.dumps({'query':q,'variables':variables}).encode();req=urllib.request.Request(API_URL,data=payload,method='POST',headers={'Authorization':'Bearer '+self.token,'Content-Type':'application/json','User-Agent':'LocalXIVAnalyzerCollector/0.1'})
  for attempt in range(5):
   try:
    time.sleep(self.delay)
    with urllib.request.urlopen(req,timeout=60) as r:data=json.load(r)
    if data.get('errors'):raise RuntimeError(json.dumps(data['errors'],ensure_ascii=False))
    cp.write_text(json.dumps(data,ensure_ascii=False,separators=(',',':')),encoding='utf-8');return data
   except urllib.error.HTTPError as e:
    if e.code==401 and attempt==0:self.auth();req.headers['Authorization']='Bearer '+self.token;continue
    if e.code in (429,500,502,503,504) and attempt<4:time.sleep(2**attempt);continue
    raise

def anon(value,salt):
 return hashlib.sha256((salt+'|'+str(value)).encode()).hexdigest()[:20]

def sanitize_event(e,actor_map,salt):
 x=dict(e)
 for k in ('sourceID','targetID','sourceInstance','targetInstance'):
  if k in x and x[k] is not None:x[k]=actor_map.get(str(x[k]),anon(x[k],salt))
 for k in ('source','target','sourceName','targetName'):x.pop(k,None)
 return x

def init_db(path):
 c=sqlite3.connect(path);c.executescript('''pragma journal_mode=WAL;
 create table if not exists reports(report_hash text primary key,zone_id integer,zone_name text,collected_at text);
 create table if not exists fights(report_hash text,fight_id integer,encounter_id integer,name text,start real,end real,difficulty integer,primary key(report_hash,fight_id));
 create table if not exists events(report_hash text,fight_id integer,seq integer,payload text,primary key(report_hash,fight_id,seq));
 create table if not exists rate_samples(at text,limit_hour integer,spent real,reset_sec integer);''');return c

def collect_report(client,db,code,salt,outdir):
 meta=client.query(FIGHTS_QUERY,{'code':code});root=meta['data'];report=root['reportData']['report']
 if not report:raise ValueError('Report not found or not public')
 rh=anon(code,salt);actors=report.get('masterData',{}).get('actors',[]);amap={str(a['id']):anon(a['id'],salt) for a in actors}
 db.execute('insert or replace into reports values(?,?,?,datetime("now"))',(rh,(report.get('zone') or {}).get('id'),(report.get('zone') or {}).get('name')))
 summary=[]
 for f in report.get('fights') or []:
  if not f.get('kill'):continue
  fid=int(f['id']);db.execute('insert or replace into fights values(?,?,?,?,?,?,?)',(rh,fid,f.get('encounterID'),f.get('name'),f.get('startTime'),f.get('endTime'),f.get('difficulty')))
  start=float(f['startTime']);end=float(f['endTime']);seq=0;count=0
  while start<end:
   page=client.query(EVENTS_QUERY,{'code':code,'fightIDs':[fid],'start':start,'end':end});ed=page['data']['reportData']['report']['events']
   for e in ed.get('data') or []:
    clean=sanitize_event(e,amap,salt);db.execute('insert or ignore into events values(?,?,?,?)',(rh,fid,seq,json.dumps(clean,ensure_ascii=False,separators=(',',':'))));seq+=1;count+=1
   nxt=ed.get('nextPageTimestamp')
   if nxt is None or float(nxt)<=start:break
   start=float(nxt);db.commit()
  summary.append({'report_hash':rh,'fight_id':fid,'encounter_id':f.get('encounterID'),'name':f.get('name'),'duration_ms':f.get('endTime',0)-f.get('startTime',0),'events':count})
 rate=root.get('rateLimitData') or {};db.execute('insert into rate_samples values(datetime("now"),?,?,?)',(rate.get('limitPerHour'),rate.get('pointsSpentThisHour'),rate.get('pointsResetIn')));db.commit()
 (outdir/(rh+'_summary.json')).write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8');return summary

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--report-code',action='append',default=[]);ap.add_argument('--report-file');ap.add_argument('--out',default='fflogs_dataset');ap.add_argument('--cache',default='fflogs_cache');ap.add_argument('--db',default='fflogs_clear.sqlite3');a=ap.parse_args()
 codes=list(a.report_code)
 if a.report_file:codes += [x.strip() for x in Path(a.report_file).read_text().splitlines() if x.strip() and not x.lstrip().startswith('#')]
 if not codes:raise SystemExit('Supply --report-code or --report-file.')
 out=Path(a.out);out.mkdir(parents=True,exist_ok=True);salt=os.getenv('FFLOGS_ANON_SALT','').strip()
 if len(salt)<16:raise SystemExit('Set FFLOGS_ANON_SALT to a private random value of at least 16 characters.')
 client=Client(Path(a.cache));db=init_db(a.db)
 try:
  total=[]
  for code in codes:total.extend(collect_report(client,db,code,salt,out))
  print(json.dumps({'clear_fights':len(total),'events':sum(x['events'] for x in total)},ensure_ascii=False))
 finally:db.close()
if __name__=='__main__':main()
