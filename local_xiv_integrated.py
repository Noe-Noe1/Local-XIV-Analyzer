#!/usr/bin/env python3
"""Local XIV Analyzer integrated desktop shell.
P0-1 public Clear collector and P0-2 comparison-cell builder are internal modules.
Secrets are accepted in-memory only and are never persisted by this application.
"""
from __future__ import annotations
import csv,json,os,sqlite3,threading,tkinter as tk
from pathlib import Path
from tkinter import filedialog,messagebox,ttk
from fflogs_clear_collector import Client,collect_report,init_db
from comparison_cell_builder import build as build_cells
from effective_time_normalizer import run as normalize_time
from log_eligibility_filter import run as filter_logs
from act_compat_importer import import_log as import_act
from statistical_baseline_generator import generate as generate_baselines
from job_analysis_engine import run as run_job_analysis
from job_boss_analysis_engine import run as run_boss_analysis
from healing_mitigation_engine import run as run_healing
from damage_allocation_engine import run as run_allocation

APP='Local XIV Analyzer 1.2.0'; HOME=Path.home()/'LocalXIVAnalyzer'; DB=HOME/'fflogs_clear.sqlite3'; CACHE=HOME/'fflogs_cache'; DATA=HOME/'fflogs_dataset'

class CredentialsDialog(tk.Toplevel):
 def __init__(self,parent):
  super().__init__(parent);self.title('FFLogs公開Clearログ収集');self.geometry('700x520');self.result=None;self.transient(parent);self.grab_set()
  ttk.Label(self,text='認証情報はメモリ内でのみ使用し、保存しません。',font=('Yu Gothic UI',11,'bold')).pack(anchor='w',padx=14,pady=(14,8))
  frm=ttk.Frame(self);frm.pack(fill='x',padx=14)
  self.cid=tk.StringVar();self.secret=tk.StringVar();self.salt=tk.StringVar()
  for row,(label,var,show) in enumerate([('Client ID',self.cid,''),('Client Secret',self.secret,'*'),('匿名化Salt（16文字以上）',self.salt,'*')]):
   ttk.Label(frm,text=label).grid(row=row,column=0,sticky='w',pady=5);ttk.Entry(frm,textvariable=var,show=show,width=60).grid(row=row,column=1,sticky='ew',pady=5)
  frm.columnconfigure(1,weight=1);ttk.Label(self,text='公開Report Code（1行1件）').pack(anchor='w',padx=14,pady=(10,3));self.codes=tk.Text(self,height=12);self.codes.pack(fill='both',expand=True,padx=14)
  b=ttk.Frame(self);b.pack(fill='x',padx=14,pady=12);ttk.Button(b,text='キャンセル',command=self.destroy).pack(side='right');ttk.Button(b,text='収集開始',command=self.ok).pack(side='right',padx=8)
 def ok(self):
  codes=[x.strip() for x in self.codes.get('1.0','end').splitlines() if x.strip()]
  if not self.cid.get().strip() or not self.secret.get().strip() or len(self.salt.get().strip())<16 or not codes:return messagebox.showerror(APP,'Client ID、Secret、16文字以上のSalt、Report Codeを入力してください。',parent=self)
  self.result=(self.cid.get().strip(),self.secret.get().strip(),self.salt.get().strip(),codes);self.destroy()

class App(tk.Tk):
 def __init__(self):
  super().__init__();HOME.mkdir(parents=True,exist_ok=True);CACHE.mkdir(exist_ok=True);DATA.mkdir(exist_ok=True)
  self.title(APP);self.geometry('1180x760');self.minsize(900,600);self.build_ui();self.refresh()
 def build_ui(self):
  top=ttk.Frame(self,padding=12);top.pack(fill='x');ttk.Label(top,text=APP,font=('Yu Gothic UI',19,'bold')).pack(side='left')
  workflow=ttk.Frame(self,padding=(12,0,12,10));workflow.pack(fill='x')
  ttk.Button(workflow,text='ACTログを開く',command=self.import_act_log).pack(side='left',padx=(0,8))
  ttk.Button(workflow,text='選択戦闘を解析',command=self.analyze_selected_fight).pack(side='left')
  ttk.Label(workflow,text='ACTログ取込 → 戦闘選択 → 解析').pack(side='left',padx=16)
  controls=ttk.Frame(self,padding=(12,0,12,8));controls.pack(fill='x')
  row1=ttk.Frame(controls);row1.pack(fill='x',pady=(0,6))
  row2=ttk.Frame(controls);row2.pack(fill='x')
  ttk.Button(row1,text='P0-1 Clearログ収集',command=self.collect_dialog).pack(side='left',padx=(0,8))
  ttk.Button(row1,text='P0-2 比較セル生成',command=self.cells).pack(side='left',padx=(0,8))
  ttk.Button(row1,text='P0-3 有効時間正規化',command=self.normalize).pack(side='left',padx=(0,8))
  ttk.Button(row1,text='P0-4 適格性判定',command=self.filter_quality).pack(side='left',padx=(0,8))
  ttk.Button(row1,text='P0-5 ACT取込',command=self.import_act_log).pack(side='left')
  ttk.Button(row2,text='P0-6 統計基準',command=self.baselines).pack(side='left',padx=(0,8))
  ttk.Button(row2,text='P0-7 ジョブ解析',command=self.job_analysis).pack(side='left',padx=(0,8))
  ttk.Button(row2,text='P0-8 全ジョブ・ボス',command=self.boss_analysis).pack(side='left',padx=(0,8))
  ttk.Button(row2,text='P0-9 火力配賦',command=self.allocate_damage).pack(side='left',padx=(0,8))
  ttk.Button(row2,text='P0-10 回復・軽減',command=self.healing_analysis).pack(side='left',padx=(0,8))
  ttk.Button(row2,text='更新',command=self.refresh).pack(side='left')
  self.status=tk.StringVar(value='待機中');ttk.Label(self,textvariable=self.status,padding=(12,0)).pack(fill='x');self.pb=ttk.Progressbar(self,mode='indeterminate');self.pb.pack(fill='x',padx=12,pady=8)
  self.tabs=ttk.Notebook(self);self.tabs.pack(fill='both',expand=True,padx=12,pady=6)
  f=ttk.Frame(self.tabs);self.tabs.add(f,text='収集済みClear')
  cols=('started','pull','enemy','progress','phase','duration','result','report','fight')
  self.fights=ttk.Treeview(f,columns=cols,show='tree headings',selectmode='browse')
  self.fights.heading('#0',text='\u30b3\u30f3\u30c6\u30f3\u30c4')
  self.fights.column('#0',width=250,stretch=True)
  headings=['\u958b\u59cb\u65e5\u6642','Pull','\u4e3b\u306a\u6575','\u5230\u9054HP','\u5230\u9054\u30d5\u30a7\u30fc\u30ba','\u6226\u95d8\u6642\u9593','\u7d50\u679c','Report','Fight']
  widths=[165,55,190,80,125,85,80,0,0]
  for c,h,w in zip(cols,headings,widths):
   self.fights.heading(c,text=h)
   self.fights.column(c,width=w,stretch=(w>0))
  self.fights.pack(fill='both',expand=True)
  c=ttk.Frame(self.tabs);self.tabs.add(c,text='比較セル')
  cols=('key','job','samples','confidence','active','apm','dpm');self.cells_tree=ttk.Treeview(c,columns=cols,show='headings')
  for x,h,w in zip(cols,['セルキー','ジョブ','件数','信頼度','Active中央値','行動/分','Damage/分'],[420,80,70,90,110,100,130]):self.cells_tree.heading(x,text=h);self.cells_tree.column(x,width=w)
  self.cells_tree.pack(fill='both',expand=True)
  i=ttk.Frame(self.tabs);self.tabs.add(i,text='状態・プライバシー');self.info=tk.Text(i,wrap='word');self.info.pack(fill='both',expand=True)
 def work(self,label,fn):
  self.status.set(label);self.pb.start(10)
  def run():
   try:r=fn();self.after(0,lambda:self.done(r))
   except Exception as e:self.after(0,lambda: self.failed(e))
  threading.Thread(target=run,daemon=True).start()
 def done(self,r):self.pb.stop();self.status.set(str(r));self.refresh()
 def failed(self,e):self.pb.stop();self.status.set('失敗');messagebox.showerror(APP,str(e))
 def collect_dialog(self):
  d=CredentialsDialog(self);self.wait_window(d)
  if not d.result:return
  cid,secret,salt,codes=d.result
  def task():
   old={k:os.environ.get(k) for k in ('FFLOGS_CLIENT_ID','FFLOGS_CLIENT_SECRET')};os.environ['FFLOGS_CLIENT_ID']=cid;os.environ['FFLOGS_CLIENT_SECRET']=secret
   try:
    client=Client(CACHE);db=init_db(DB);total=[]
    try:
     for code in codes:total.extend(collect_report(client,db,code,salt,DATA))
    finally:db.close()
    return f'収集完了: Clear {len(total)}件'
   finally:
    for k,v in old.items():
     if v is None:os.environ.pop(k,None)
     else:os.environ[k]=v
  self.work('公開Clearログを収集中...',task)
 def selected_fight(self):
  selected=self.fights.selection()
  if not selected:
   messagebox.showinfo(APP,'????????????????????')
   return None
  values=self.fights.item(selected[0],'values')
  if len(values)<9:
   messagebox.showerror(APP,'?????????????????')
   return None
  return str(values[7]),int(values[8])

 def analyze_selected_fight(self):
  selected=self.selected_fight()
  if not selected:return
  report_hash,fight_id=selected
  rules_path=Path(__file__).with_name('allocation_rules.example.json')
  def task():
   boss=run_boss_analysis(
    DB,report_hash=report_hash,fight_id=fight_id
   )
   allocation=run_allocation(
    DB,
    str(rules_path) if rules_path.exists() else None,
    report_hash=report_hash,
    fight_id=fight_id
   )
   healing=run_healing(
    DB,report_hash=report_hash,fight_id=fight_id
   )
   return (
    f'\u6226\u95d8 {fight_id} \u89e3\u6790\u5b8c\u4e86: '
    f'\u30dc\u30b9\u6240\u898b {boss["findings"]}\u4ef6 / '
    f'\u706b\u529b\u914d\u8ce6 {allocation["allocated_damage"]:.0f} / '
    f'\u56de\u5fa9\u30fb\u8efd\u6e1b\u8b66\u544a {healing["warnings"]}\u4ef6'
   )
  self.work('\u9078\u629e\u6226\u95d8\u3092\u89e3\u6790\u4e2d...',task)

 def import_act_log(self):
  p=filedialog.askopenfilename(filetypes=[('ACT network logs','*.log *.txt'),('All files','*.*')])
  if not p:return
  self.work('ACTログ取込中...',lambda:(lambda r:f"ACT取込完了: {r['encounters']}戦闘 / {r['parsed']}イベント")(import_act(p,DB)))
 def healing_analysis(self):
  if not DB.exists():return messagebox.showinfo(APP,'先にログを取り込んでください。')
  self.work('回復・軽減解析中...',lambda:(lambda r:f"回復・軽減解析完了: {r['fights']}戦闘 / 警告{r['warnings']}件")(run_healing(DB)))

 def allocate_damage(self):
  if not DB.exists():return messagebox.showinfo(APP,'先にログを取り込んでください。')
  self.work('火力配賦を計算中...',lambda:(lambda r:f"火力配賦完了: {r['fights']}戦闘 / {r['allocated_damage']:.0f}配賦")(run_allocation(DB)))

 def boss_analysis(self):
  if not DB.exists():return messagebox.showinfo(APP,'先にログを取り込んでください。')
  self.work('全ジョブ・ボス解析中...',lambda:(lambda r:f"ボス解析完了: {r['fights']}戦闘 / {r['findings']}件")(run_boss_analysis(DB)))
  if not DB.exists():return messagebox.showinfo(APP,'先にログを取り込んでください。')
  self.work('全ジョブ・ボス解析中...',lambda:(lambda r:f"ボス解析完了: {r['fights']}戦闘 / {r['findings']}件")(run_boss_analysis(DB)))
 def job_analysis(self):
  if not DB.exists():return messagebox.showinfo(APP,'先にP0-6を実行してください。')
  self.work('ジョブ別解析中...',lambda:(lambda r:f"ジョブ解析完了: {r['players']}人 / {r['findings']}件")(run_job_analysis(DB)))
 def baselines(self):
  if not DB.exists():return messagebox.showinfo(APP,'先にP0-2とP0-4を実行してください。')
  self.work('統計基準生成中...',lambda:(lambda r:f"基準生成完了: {r['cells']}セル / Version {r['version_id']}")(generate_baselines(DB)))
 def filter_quality(self):
  if not DB.exists():return messagebox.showinfo(APP,'先にP0-1～P0-3を実行してください。')
  self.work('不適格ログと外れ値を判定中...',lambda:(lambda r:f"適格性判定完了: 適格{r['hard_eligible']}件 / 要確認{r['review_flags']}件")(filter_logs(DB)))
 def normalize(self):
  if not DB.exists():return messagebox.showinfo(APP,'先にP0-1でClearログを収集してください。')
  self.work('有効戦闘時間を正規化中...',lambda:f"正規化完了: {normalize_time(DB)['normalized_players']}件")
 def cells(self):
  if not DB.exists():return messagebox.showinfo(APP,'先にP0-1でClearログを収集してください。')
  self.work('比較セルを生成中...',lambda:f"比較セル生成完了: {build_cells(DB)['cells']}件")
 def refresh(self):
  for tree in (self.fights,self.cells_tree):
   for x in tree.get_children():tree.delete(x)
  stats={'database':str(DB),'database_exists':DB.exists(),'network':'P0-1実行時のみFFLogs公開APIへ接続','credentials':'メモリ内のみ。DB・設定・ログへ保存しない'}
  if DB.exists():
   try:
    db=sqlite3.connect(DB);tables={r[0] for r in db.execute("select name from sqlite_master where type='table'")}
    if 'fights' in tables:
     latest_act=db.execute(
      "select report_hash from import_audit "
      "where source_type='ACT_NETWORK_LOG' "
      "order by rowid desc limit 1"
     ).fetchone()
     fight_rows=db.execute(
      'select report_hash,fight_id,encounter_id,name,start,end from fights '
      'where report_hash=? order by encounter_id,fight_id',
      (latest_act[0],)
     ).fetchall() if latest_act else []
     groups={}
     group_counts={}
     for row in fight_rows:
      group_counts[row[3]]=group_counts.get(row[3],0)+1
     for content,count in group_counts.items():
      groups[content]=self.fights.insert(
       '', 'end',
       text=f'{content} ({count})',
       open=True,
       values=('', '', '', '', '', '', '', '', '')
      )
     for rh,fid,encounter_id,content,start,end in fight_rows:
      enemy_stats={}
      first_time=None
      deaths=set()
      phase_markers=[]
      for payload, in db.execute(
       'select payload from events where report_hash=? and fight_id=? order by seq',
       (rh,fid)
      ):
       try:event=json.loads(payload)
       except Exception:continue
       if first_time is None and event.get('occurredAt'):first_time=event['occurredAt']
       if event.get('type')=='death':deaths.add(str(event.get('targetID') or ''))
       if (
        event.get('type')=='actorcontrol'
        and event.get('category')=='80000027'
       ):
        phase_markers.append(event.get('params') or [])
       name=event.get('targetName')
       target_id=str(event.get('targetID') or '')
       maximum=float(event.get('targetMaxHP') or 0)
       current=float(event.get('targetCurrentHP') or 0)
       if not name or maximum<=0:continue
       item=enemy_stats.setdefault(target_id,{'name':name,'max_hp':maximum,'min_ratio':1.0,'hits':0})
       item['max_hp']=max(item['max_hp'],maximum)
       item['min_ratio']=min(item['min_ratio'],max(0,current/maximum))
       item['hits']+=1
      by_name={}
      for target_id,item in enemy_stats.items():
       current=by_name.get(item['name'])
       if current is None or item['hits']>current['hits']:
        by_name[item['name']]=dict(item,target_id=target_id)
      phase='-'
      primary=None
      if encounter_id==0x4D6:
       stages={
        str(marker[0]).upper()
        for marker in phase_markers
        if marker
       }

       if stages & {'1C','1D','05','06','07','08'}:
        phase='P4'
       elif stages & {'1A','1B','0C','0D','0B'}:
        phase='P3'
       else:
        phase='P2'

       phase_enemy={
        'P2':'\u30b7\u30f4\u30a1\u30fb\u30df\u30c8\u30ed\u30f3',
        'P3':'\u95c7\u306e\u5deb\u5973',
       }.get(phase)

       if phase_enemy and phase_enemy in by_name:
        primary=by_name[phase_enemy]
       elif (
        '\u30d5\u30a7\u30a4\u30c8\u30d6\u30ec\u30a4\u30ab\u30fc'
        in by_name
       ):
        primary=by_name[
         '\u30d5\u30a7\u30a4\u30c8\u30d6\u30ec\u30a4\u30ab\u30fc'
        ]
      if primary is None and enemy_stats:
       primary=max(enemy_stats.values(),key=lambda x:(x['hits'],x['max_hp']))
      enemy_name=primary['name'] if primary else '\u4e0d\u660e'
      progress=f'{primary["min_ratio"]:.0%}' if primary else '-'
      if encounter_id==0x4D6:
       result='\u8a0e\u4f10' if phase=='P5' else '\u5168\u6ec5'
      else:
       result=(
        '\u8a0e\u4f10'
        if primary and primary.get('target_id') in deaths
        else '\u672a\u8a0e\u4f10'
       )
      started=first_time[:19].replace('T',' ') if first_time else '-'
      total_seconds=int(max(float(end)-float(start),0)/1000)
      duration=f'{total_seconds//60:02d}:{total_seconds%60:02d}'
      self.fights.insert(
       groups[content], 'end',
       text='',
       values=(started,fid,enemy_name,progress,phase,duration,result,rh,fid)
      )
     stats['clear_fights']=db.execute('select count(*) from fights').fetchone()[0]
    if 'comparison_cells' in tables:
     for r in db.execute('select cell_key,job,sample_count,confidence,median_active_ratio,median_actions_per_min,median_damage_per_min from comparison_cells order by sample_count desc limit 1000'):self.cells_tree.insert('','end',values=(r[0],r[1],r[2],r[3],f'{r[4]:.1%}',f'{r[5]:.2f}',f'{r[6]:.0f}'))
     stats['comparison_cells']=db.execute('select count(*) from comparison_cells').fetchone()[0]
    if 'effective_time' in tables:stats['effective_time_rows']=db.execute('select count(*) from effective_time').fetchone()[0]
    if 'eligibility_results' in tables:
     stats['hard_eligible']=db.execute('select count(*) from eligibility_results where hard_eligible=1').fetchone()[0]
     stats['review_flags']=db.execute('select count(*) from eligibility_results where review_flag=1').fetchone()[0]
    if 'baseline_versions' in tables:
     row=db.execute('select version_id,cell_count,sample_count from baseline_versions order by created_at desc limit 1').fetchone()
     if row:stats['latest_baseline']={'version':row[0],'cells':row[1],'samples':row[2]}
    if 'job_analysis_runs' in tables:
     row=db.execute('select run_id,players,findings from job_analysis_runs order by run_id desc limit 1').fetchone()
     if row:stats['latest_job_analysis']={'run':row[0],'players':row[1],'findings':row[2]}
    if 'boss_analysis_runs' in tables:
     row=db.execute('select run_id,fights,findings from boss_analysis_runs order by run_id desc limit 1').fetchone()
     if row:stats['latest_boss_analysis']={'run':row[0],'fights':row[1],'findings':row[2]}
    if 'healing_runs' in tables:
     row=db.execute('select run_id,fights,events,warnings from healing_runs order by run_id desc limit 1').fetchone()
     if row:stats['latest_healing']={'run':row[0],'fights':row[1],'events':row[2],'warnings':row[3]}
    if 'allocation_runs' in tables:
     row=db.execute('select run_id,fights,events,allocated_damage,warnings from allocation_runs order by run_id desc limit 1').fetchone()
     if row:stats['latest_allocation']={'run':row[0],'fights':row[1],'events':row[2],'allocated':row[3],'warnings':row[4]}

    db.close()
   except Exception as e:stats['read_error']=str(e)
  self.info.delete('1.0','end');self.info.insert('end',json.dumps(stats,ensure_ascii=False,indent=2))
if __name__=='__main__':App().mainloop()
