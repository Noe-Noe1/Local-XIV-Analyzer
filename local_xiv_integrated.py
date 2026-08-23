#!/usr/bin/env python3
"""Local XIV Analyzer integrated desktop shell.
P0-1 public Clear collector and P0-2 comparison-cell builder are internal modules.
Secrets are accepted in-memory only and are never persisted by this application.
"""
from __future__ import annotations
import csv,json,os,sqlite3,threading,time,tkinter as tk
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

APP='Local XIV Analyzer 1.2.0'; HOME=Path.home()/'LocalXIVAnalyzer'; DB=HOME/'fflogs_clear.sqlite3'; CACHE=HOME/'fflogs_cache'; DATA=HOME/'fflogs_dataset'; BASELINE_DB=HOME/'baseline_reference.sqlite3'

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
  result_page=ttk.Frame(self.tabs)
  self.tabs.add(result_page,text='\u89e3\u6790\u7d50\u679c')
  self.result_tabs=ttk.Notebook(result_page)
  self.result_tabs.pack(fill='both',expand=True)
  self.result_views={}
  for key,label in (
   ('overview','\u6226\u95d8\u6982\u8981'),
   ('findings','\u30c1\u30a7\u30c3\u30af\u30ea\u30b9\u30c8'),
   ('damage','rDPS\u30fb\u30b7\u30ca\u30b8\u30fc'),
   ('deaths','\u6226\u95d8\u4e0d\u80fd'),
   ('healing','\u56de\u5fa9\u30fb\u8efd\u6e1b'),
  ):
   page=ttk.Frame(self.result_tabs)
   self.result_tabs.add(page,text=label)
   view=tk.Text(
    page,
    wrap='word',
    font=('Yu Gothic UI',10),
    padx=14,
    pady=14,
    spacing1=4,
    spacing3=8
   )
   view.pack(fill='both',expand=True)
   if key=='findings':
    view.tag_configure(
     'critical',
     background='#ffe5e5',
     foreground='#8b0000',
     font=('Yu Gothic UI',10,'bold'),
     lmargin1=12,lmargin2=12,rmargin=12,
     spacing1=10,spacing3=10
    )
    view.tag_configure(
     'warning',
     background='#fff4d6',
     foreground='#6b4d00',
     font=('Yu Gothic UI',10,'bold'),
     lmargin1=12,lmargin2=12,rmargin=12,
     spacing1=10,spacing3=10
    )
    view.tag_configure(
     'info',
     background='#e8f3ff',
     foreground='#174a73',
     font=('Yu Gothic UI',10),
     lmargin1=12,lmargin2=12,rmargin=12,
     spacing1=10,spacing3=10
    )
    view.tag_configure(
     'success',
     background='#e4f6e8',
     foreground='#165c2a',
     font=('Yu Gothic UI',10,'bold'),
     lmargin1=12,lmargin2=12,rmargin=12,
     spacing1=10,spacing3=10
    )
   self.result_views[key]=view
 def work(self,label,fn):
  self.status.set(label);self.pb.start(10)
  def run():
   try:r=fn();self.after(0,lambda:self.done(r))
   except Exception as e:self.after(0,lambda: self.failed(e))
  threading.Thread(target=run,daemon=True).start()
 def done(self,r):
  self.pb.stop()
  if isinstance(r,dict) and r.get('kind')=='analysis_result':
   self.status.set(r['message'])
   self.render_analysis_result(r['report_hash'],r['fight_id'])
   self.refresh()
   return
  self.status.set(str(r))
  self.refresh()
 def failed(self,e):self.pb.stop();self.status.set('失敗');messagebox.showerror(APP,str(e))
 def set_result_text(self,key,text):
  view=self.result_views[key]
  view.delete('1.0','end')
  view.insert('end',text)

 def render_analysis_result(self,report_hash,fight_id):
  db=sqlite3.connect(DB)
  fight=db.execute(
   'select name,start,end from fights where report_hash=? and fight_id=?',
   (report_hash,fight_id)
  ).fetchone()
  if not fight:
   db.close();return
  content,start,end=fight
  player_jobs=dict(db.execute(
   'select actor_hash,job from fight_players '
   'where report_hash=? and fight_id=? and job<>?',
   (report_hash,fight_id,'UNKNOWN')
  ).fetchall())

  def actor_label(actor):
   job=player_jobs.get(actor)
   return (f'{job} [{actor[:6]}]' if job else f'\u4e0d\u660e [{actor[:6]}]')

  warning_labels={
   'crit_dh_allocation_estimated':'\u30af\u30ea\u30c6\u30a3\u30ab\u30eb\u30fb\u30c0\u30a4\u30ec\u30af\u30c8\u30d2\u30c3\u30c8\u5bc4\u4e0e\u306f\u671f\u5f85\u5024\u63a8\u5b9a',
   'action_value_fallback_used':'\u30a2\u30af\u30b7\u30e7\u30f3\u56fa\u6709\u5024\u3092\u53d6\u5f97\u3067\u304d\u305a\u65e2\u5b9a\u5024\u3092\u4f7f\u7528',
  }

  def warning_text(codes):
   return ' / '.join(
    warning_labels.get(code,code)
    for code in str(codes).split(',')
    if code
   )

  ability_names={}
  for payload, in db.execute(
   'select payload from events '
   'where report_hash=? and fight_id=?',
   (report_hash,fight_id)
  ):
   try:
    event=json.loads(payload)
   except Exception:
    continue
   ability_id=event.get('abilityGameID')
   ability_name=event.get('abilityName')
   if ability_id and ability_name:
    ability_names[str(ability_id)]=ability_name

  def ability_label(ability_id):
   key=str(ability_id)
   return ability_names.get(key,f'ID {key}')

  seconds=int(max(float(end)-float(start),0)/1000)
  overview=(
   f'\u30b3\u30f3\u30c6\u30f3\u30c4: {content}\n'
   f'Pull: {fight_id}\n'
   f'\u6226\u95d8\u6642\u9593: {seconds//60:02d}:{seconds%60:02d}\n'
  )
  self.set_result_text('overview',overview)

  boss_run=db.execute(
   'select max(run_id) from boss_analysis_results '
   'where report_hash=? and fight_id=?',
   (report_hash,fight_id)
  ).fetchone()[0]
  finding_lines=[]
  if boss_run is not None:
   rows=db.execute(
    'select severity,category,message,timestamp '
    'from boss_analysis_results '
    'where run_id=? and report_hash=? and fight_id=? '
    'order by timestamp',
    (boss_run,report_hash,fight_id)
   ).fetchall()
   for severity,category,message,timestamp in rows:
    elapsed=max(0,int((float(timestamp)-float(start))/1000))
    finding_lines.append(
     f'[{severity.upper()}] {elapsed//60:02d}:{elapsed%60:02d} '
     f'{category}: {message}'
    )
  finding_view=self.result_views['findings']
  finding_view.delete('1.0','end')

  def checklist_card(tag,title,detail):
   finding_view.insert('end',title+'\n'+detail+'\n',tag)
   finding_view.insert('end','\n')

  latest_death_run=db.execute(
   'select max(run_id) from death_windows '
   'where report_hash=? and fight_id=?',
   (report_hash,fight_id)
  ).fetchone()[0]
  death_count=0
  if latest_death_run is not None:
   death_count=db.execute(
    'select count(*) from death_windows '
    'where run_id=? and report_hash=? and fight_id=?',
    (latest_death_run,report_hash,fight_id)
   ).fetchone()[0]
  if death_count==0:
   checklist_card('success','\u9054\u6210  \u6226\u95d8\u4e0d\u80fd\u3092\u907f\u3051\u308b','\u6226\u95d8\u4e0d\u80fd\u306f\u691c\u51fa\u3055\u308c\u307e\u305b\u3093\u3067\u3057\u305f\u3002')
  else:
   checklist_card('critical',f'\u91cd\u5927  \u6226\u95d8\u4e0d\u80fd\u3092\u907f\u3051\u308b',f'{death_count}\u56de\u306e\u6226\u95d8\u4e0d\u80fd\u3092\u691c\u51fa\u3057\u307e\u3057\u305f\u3002\u8a73\u7d30\u306f\u300c\u6226\u95d8\u4e0d\u80fd\u300d\u3092\u78ba\u8a8d\u3057\u3066\u304f\u3060\u3055\u3044\u3002')

  player_count=len(player_jobs)
  if player_count==8:
   checklist_card('success','\u9054\u6210  \u30d1\u30fc\u30c6\u30a3\u69cb\u6210','8\u540d\u5168\u54e1\u306e\u30b8\u30e7\u30d6\u3092\u8b58\u5225\u3067\u304d\u307e\u3057\u305f\u3002')
  else:
   checklist_card('warning','\u6ce8\u610f  \u30d1\u30fc\u30c6\u30a3\u69cb\u6210',f'\u8b58\u5225\u3067\u304d\u305f\u30d7\u30ec\u30a4\u30e4\u30fc\u306f {player_count}/8 \u540d\u3067\u3059\u3002')

  metric_run=db.execute(
   'select max(run_id) from dps_metrics '
   'where report_hash=? and fight_id=?',
   (report_hash,fight_id)
  ).fetchone()[0]
  metric_count=low_count=0
  if metric_run is not None:
   metric_count=db.execute(
    "select count(*) from dps_metrics d "
    "join fight_players p "
    "on p.report_hash=d.report_hash "
    "and p.fight_id=d.fight_id "
    "and p.actor_hash=d.actor_hash "
    "where d.run_id=? and d.report_hash=? and d.fight_id=? "
    "and p.job<>'UNKNOWN'",
    (metric_run,report_hash,fight_id)
   ).fetchone()[0]
   low_count=db.execute(
    "select count(*) from dps_metrics d "
    "join fight_players p "
    "on p.report_hash=d.report_hash "
    "and p.fight_id=d.fight_id "
    "and p.actor_hash=d.actor_hash "
    "where d.run_id=? and d.report_hash=? and d.fight_id=? "
    "and p.job<>'UNKNOWN' and d.confidence='low'",
    (metric_run,report_hash,fight_id)
   ).fetchone()[0]
  if metric_count>=player_count and low_count==0:
   checklist_card('success','\u9054\u6210  rDPS\u30fb\u30b7\u30ca\u30b8\u30fc','\u30d7\u30ec\u30a4\u30e4\u30fc\u5168\u54e1\u306erDPS\u6307\u6a19\u3092\u751f\u6210\u3067\u304d\u307e\u3057\u305f\u3002')
  else:
   checklist_card('warning','\u6ce8\u610f  rDPS\u30fb\u30b7\u30ca\u30b8\u30fc',f'\u6307\u6a19 {metric_count}\u4ef6 / \u4f4e\u4fe1\u983c\u5ea6 {low_count}\u4ef6\u3002\u63a8\u5b9a\u5024\u3092\u542b\u3080\u5834\u5408\u304c\u3042\u308a\u307e\u3059\u3002')

  healing_rows=db.execute(
   'select count(*) from healing_metrics '
   'where report_hash=? and fight_id=?',
   (report_hash,fight_id)
  ).fetchone()[0]
  mitigation_rows=db.execute(
   'select count(*) from mitigation_metrics '
   'where report_hash=? and fight_id=?',
   (report_hash,fight_id)
  ).fetchone()[0]
  if healing_rows or mitigation_rows:
   checklist_card('success','\u9054\u6210  \u56de\u5fa9\u30fb\u8efd\u6e1b',f'\u56de\u5fa9 {healing_rows}\u4ef6 / \u8efd\u6e1b {mitigation_rows}\u4ef6\u306e\u6307\u6a19\u3092\u751f\u6210\u3057\u307e\u3057\u305f\u3002')
  else:
   checklist_card('info','\u60c5\u5831  \u56de\u5fa9\u30fb\u8efd\u6e1b','\u73fe\u5728\u306eACT\u53d6\u8fbc\u30c7\u30fc\u30bf\u3067\u306f\u8a73\u7d30\u6307\u6a19\u3092\u751f\u6210\u3067\u304d\u307e\u305b\u3093\u3002')

  if boss_run is not None and rows:
   grouped={}
   for severity,category,message,timestamp in rows:
    if category=='survival':
     continue
    grouped.setdefault((severity,category,message),[]).append(timestamp)
   for (severity,category,message),timestamps in grouped.items():
    tag='critical' if severity in {'critical','major'} else 'warning'
    times=[]
    for timestamp in timestamps:
     elapsed=max(0,int((float(timestamp)-float(start))/1000))
     times.append(f'{elapsed//60:02d}:{elapsed%60:02d}')
    checklist_card(tag,f'\u8ffd\u52a0\u6240\u898b  {len(times)}\u4ef6',f'{message}\n\u767a\u751f\u6642\u523b: {chr(44).join(times)}')


  # JOB_CHECKLIST_CARDS
  job_run=db.execute(
   'select max(run_id) from job_analysis_results '
   'where report_hash=? and fight_id=?',
   (report_hash,fight_id)
  ).fetchone()[0]

  if job_run is not None:
   job_rows=db.execute(
    'select actor_hash,job,code,severity,actual,'
    'expected_low,evidence_json '
    'from job_analysis_results '
    'where run_id=? and report_hash=? and fight_id=? '
    "and job<>'UNKNOWN'",
    (job_run,report_hash,fight_id)
   ).fetchall()

   grouped_job={}
   for actor,job,code,severity,actual,low,evidence in job_rows:
    grouped_job.setdefault(
     (actor,job,code),[]
    ).append((severity,actual,low,evidence))

   code_labels={
    'long_action_gap':'GCD\u30fb\u884c\u52d5\u505c\u6b62',
    'low_action_usage':'\u4e3b\u8981\u30a2\u30af\u30b7\u30e7\u30f3\u4f7f\u7528',
    'below_actions_per_min':'\u884c\u52d5\u983b\u5ea6',
    'below_active_ratio':'\u7a3c\u50cd\u7387',
    'below_damage_per_min':'\u30c0\u30e1\u30fc\u30b8\u53c2\u8003\u5024',
    'combo_incomplete':'\u30b3\u30f3\u30dc\u5b8c\u9042',
    'cooldown_delay':'\u30ea\u30ad\u30e3\u30b9\u30c8\u4f7f\u7528',
    'required_action_missing':'\u5fc5\u9808\u30a2\u30af\u30b7\u30e7\u30f3',
   }

   for (actor,job,code),items in grouped_job.items():
    label=code_labels.get(code,code)
    major=any(
     str(item[0]).lower() in {'major','critical'}
     for item in items
    )
    tag='critical' if major else 'warning'
    title=(
     ('\u91cd\u5927' if major else '\u6ce8\u610f')
     + f'  {actor_label(actor)}  {label}'
    )

    if code=='long_action_gap':
     gaps=[]
     for _,_,_,evidence in items:
      try:
       gaps.extend(
        json.loads(evidence or '{}').get('gaps_ms',[])
       )
      except Exception:
       pass
     maximum=max(gaps,default=0)/1000
     detail=(
      f'\u9577\u3044\u884c\u52d5\u505c\u6b62\u3092 {len(gaps)}'
      f'\u56de\u691c\u51fa\u3057\u307e\u3057\u305f\u3002'
      f' \u6700\u5927 {maximum:.1f}\u79d2\u3067\u3059\u3002'
     )

    elif code=='low_action_usage':
     abilities=[]
     for _,_,_,evidence in items:
      try:
       ability=json.loads(
        evidence or '{}'
       ).get('ability_id')
       if ability:
        abilities.append(str(ability))
      except Exception:
       pass
     unique=sorted(set(abilities))
     detail=(
      f'\u6bd4\u8f03\u57fa\u6e96\u3088\u308a\u4f7f\u7528\u983b\u5ea6'
      f'\u304c\u4f4e\u3044\u30a2\u30af\u30b7\u30e7\u30f3\u304c '
      f'{len(unique)}\u4ef6\u3042\u308a\u307e\u3059\u3002'
     )
     if unique:
      names=[ability_label(ability_id) for ability_id in unique]
      detail+=f' ??: {", ".join(names)}'

    elif code=='below_active_ratio':
     actual=items[0][1]
     low=items[0][2]
     detail=(
      f'\u7a3c\u50cd\u7387 {float(actual or 0):.1%}\u3002'
      f' \u6bd4\u8f03\u57fa\u6e96\u306e\u4e0b\u9650\u306f '
      f'{float(low or 0):.1%}\u3067\u3059\u3002'
     )

    elif code=='below_actions_per_min':
     actual=items[0][1]
     low=items[0][2]
     detail=(
      f'1\u5206\u3042\u305f\u308a\u306e\u884c\u52d5\u6570 '
      f'{float(actual or 0):.1f}\u3002'
      f' \u6bd4\u8f03\u57fa\u6e96\u306e\u4e0b\u9650\u306f '
      f'{float(low or 0):.1f}\u3067\u3059\u3002'
     )

    elif code=='below_damage_per_min':
     actual=items[0][1]
     low=items[0][2]
     detail=(
      f'1\u5206\u3042\u305f\u308a\u30c0\u30e1\u30fc\u30b8 '
      f'{float(actual or 0):,.0f}\u3002'
      f' \u6bd4\u8f03\u57fa\u6e96\u306e\u4e0b\u9650\u306f '
      f'{float(low or 0):,.0f}\u3067\u3059\u3002'
     )

    else:
     detail=(
      f'{len(items)}\u4ef6\u306e\u6539\u5584\u5019\u88dc\u3092'
      f'\u691c\u51fa\u3057\u307e\u3057\u305f\u3002'
     )

    checklist_card(tag,title,detail)

  allocation_run=db.execute(
   'select max(run_id) from dps_metrics '
   'where report_hash=? and fight_id=?',
   (report_hash,fight_id)
  ).fetchone()[0]
  damage_lines=[]
  if allocation_run is not None:
   rows=db.execute(
    'select d.actor_hash,d.dps,d.rdps,d.external_gain,'
    'd.own_contribution,d.confidence,d.warnings '
    'from dps_metrics d '
    'join fight_players p '
    'on p.report_hash=d.report_hash '
    'and p.fight_id=d.fight_id '
    'and p.actor_hash=d.actor_hash '
    'where d.run_id=? and d.report_hash=? and d.fight_id=? '
    "and p.job<>'UNKNOWN' "
    'order by d.rdps desc',
    (allocation_run,report_hash,fight_id)
   ).fetchall()
   damage_lines.append(
    '\u30a2\u30af\u30bf\u30fc                 DPS       rDPS      '
    '\u53d7\u3051\u305f\u30b7\u30ca\u30b8\u30fc   \u4e0e\u3048\u305f\u30b7\u30ca\u30b8\u30fc  \u4fe1\u983c\u5ea6'
   )
   for actor,dps,rdps,gain,given,confidence,warnings in rows:
    damage_lines.append(
     f'{actor_label(actor):14} {dps:10.1f} {rdps:10.1f} '
     f'{gain:10.0f} {given:12.0f}  {confidence}'
    )
    if warnings:
     damage_lines.append(f'  \u6ce8\u610f: {warning_text(warnings)}')
  self.set_result_text(
   'damage',
   '\n'.join(damage_lines) or 'rDPS\u30fb\u30b7\u30ca\u30b8\u30fc\u30c7\u30fc\u30bf\u306f\u3042\u308a\u307e\u305b\u3093\u3002'
  )

  death_run=db.execute(
   'select max(run_id) from death_windows '
   'where report_hash=? and fight_id=?',
   (report_hash,fight_id)
  ).fetchone()[0]
  death_lines=[]
  if death_run is not None:
   rows=db.execute(
    'select target_actor,death_timestamp,incoming_damage,'
    'effective_healing,last_hit_ability,last_hit_amount '
    'from death_windows where run_id=? and report_hash=? and fight_id=? '
    'order by death_timestamp',
    (death_run,report_hash,fight_id)
   ).fetchall()
   for actor,timestamp,incoming,healing,ability,last_amount in rows:
    elapsed=max(0,int((float(timestamp)-float(start))/1000))
    death_lines.append(
     f'{elapsed//60:02d}:{elapsed%60:02d} {actor_label(actor)} '
     f'\u88ab\u30c0\u30e1\u30fc\u30b8 {incoming:.0f} / '
     f'\u6709\u52b9\u56de\u5fa9 {healing:.0f} / '
     f'\u6700\u7d42 {ability_label(ability)} ({last_amount:.0f})'
    )
  self.set_result_text(
   'deaths',
   '\n'.join(death_lines) or '\u6226\u95d8\u4e0d\u80fd\u306f\u691c\u51fa\u3055\u308c\u307e\u305b\u3093\u3067\u3057\u305f\u3002'
  )

  healing_count=db.execute(
   'select count(*) from healing_metrics '
   'where report_hash=? and fight_id=?',
   (report_hash,fight_id)
  ).fetchone()[0]
  mitigation_count=db.execute(
   'select count(*) from mitigation_metrics '
   'where report_hash=? and fight_id=?',
   (report_hash,fight_id)
  ).fetchone()[0]
  healing_text=(
   f'\u56de\u5fa9\u6307\u6a19: {healing_count}\u4ef6\n'
   f'\u8efd\u6e1b\u6307\u6a19: {mitigation_count}\u4ef6'
  )
  if healing_count==0 and mitigation_count==0:
   healing_text+='\n\u73fe\u5728\u306eACT\u53d6\u8fbc\u30c7\u30fc\u30bf\u3067\u306f\u8a73\u7d30\u6307\u6a19\u3092\u751f\u6210\u3067\u304d\u307e\u305b\u3093\u3002'
  self.set_result_text('healing',healing_text)
  db.close()
  self.tabs.select(self.tabs.index('end')-1)

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
   messagebox.showinfo(APP,'\u89e3\u6790\u3059\u308b\u6226\u95d8\u3092\u4e00\u89a7\u304b\u3089\u9078\u629e\u3057\u3066\u304f\u3060\u3055\u3044\u3002')
   return None
  values=self.fights.item(selected[0],'values')
  if len(values)<9:
   messagebox.showinfo(APP,'\u30b3\u30f3\u30c6\u30f3\u30c4\u898b\u51fa\u3057\u3067\u306f\u306a\u304fPull\u884c\u3092\u9078\u629e\u3057\u3066\u304f\u3060\u3055\u3044\u3002')
   return None
  return str(values[7]),int(values[8])

 def analyze_selected_fight(self):
  selected=self.selected_fight()
  if not selected:return
  report_hash,fight_id=selected
  rules_path=Path(__file__).with_name('allocation_rules.example.json')
  def task():
   timings={}
   started=time.perf_counter()
   build_cells(
    DB,
    report_hash=report_hash,
    fight_id=fight_id
   )
   timings['build_cells']=time.perf_counter()-started
   started=time.perf_counter()
   job=run_job_analysis(
    DB,
    report_hash=report_hash,
    fight_id=fight_id,
    baseline_db_path=BASELINE_DB
   )
   timings['job_analysis']=time.perf_counter()-started
   started=time.perf_counter()
   boss=run_boss_analysis(
    DB,report_hash=report_hash,fight_id=fight_id
   )
   timings['boss_analysis']=time.perf_counter()-started
   started=time.perf_counter()
   allocation=run_allocation(
    DB,
    str(rules_path) if rules_path.exists() else None,
    report_hash=report_hash,
    fight_id=fight_id
   )
   timings['damage_allocation']=time.perf_counter()-started
   started=time.perf_counter()
   healing=run_healing(
    DB,report_hash=report_hash,fight_id=fight_id
   )
   timings['healing_mitigation']=time.perf_counter()-started
   Path('logs/analysis_timing.txt').write_text(
    '\n'.join(f'{k}={v:.3f}s' for k,v in timings.items())+'\n',
    encoding='utf-8'
   )
   message=(
    f'\u6226\u95d8 {fight_id} \u89e3\u6790\u5b8c\u4e86: '
    f'????? {job["findings"]}? / '
    f'???? {boss["findings"]}? / '
    f'rDPS\u30fb\u30b7\u30ca\u30b8\u30fc {allocation["allocated_damage"]:.0f} / '
    f'\u56de\u5fa9\u30fb\u8efd\u6e1b\u8b66\u544a {healing["warnings"]}\u4ef6'
   )
   return {
    'kind':'analysis_result',
    'message':message,
    'report_hash':report_hash,
    'fight_id':fight_id,
   }
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
