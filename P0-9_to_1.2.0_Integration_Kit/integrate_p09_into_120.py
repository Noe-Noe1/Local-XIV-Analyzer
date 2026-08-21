from pathlib import Path
import re,sys
root=Path(sys.argv[1] if len(sys.argv)>1 else '.')
app=root/'local_xiv_integrated.py';spec=root/'LocalXIVAnalyzer.spec'
if not app.exists() or not spec.exists():raise SystemExit('Run inside the extracted LocalXIVAnalyzer 1.2.0 source folder.')
s=app.read_text(encoding='utf-8')
if 'run as run_allocation' not in s:
    marker='from healing_mitigation_engine import run as run_healing'
    if marker not in s:raise SystemExit('1.2.0 import marker not found.')
    s=s.replace(marker,marker+'\nfrom damage_allocation_engine import run as run_allocation')
s=re.sub(r"APP='Local XIV Analyzer [^']+'","APP='Local XIV Analyzer 1.3.0'",s,1)
if 'P0-9 火力配賦' not in s:
    marker="ttk.Button(top,text='P0-10 回復・軽減',command=self.healing_analysis).pack(side='right',padx=8)"
    if marker not in s:raise SystemExit('1.2.0 button marker not found.')
    s=s.replace(marker,marker+";ttk.Button(top,text='P0-9 火力配賦',command=self.allocate_damage).pack(side='right',padx=8)")
if 'def allocate_damage' not in s:
    marker=' def healing_analysis(self):\n'
    method=" def allocate_damage(self):\n  if not DB.exists():return messagebox.showinfo(APP,'先にログを取り込んでください。')\n  self.work('火力配賦を計算中...',lambda:(lambda r:f\"火力配賦完了: {r['fights']}戦闘 / {r['allocated_damage']:.0f}配賦\")(run_allocation(DB)))\n"
    if marker not in s:raise SystemExit('1.2.0 method marker not found.')
    s=s.replace(marker,method+marker)
if "'allocation_runs' in tables" not in s:
    marker="if row:stats['latest_healing']={'run':row[0],'fights':row[1],'events':row[2],'warnings':row[3]}"
    add="\n    if 'allocation_runs' in tables:\n     row=db.execute('select run_id,fights,events,allocated_damage,warnings from allocation_runs order by run_id desc limit 1').fetchone()\n     if row:stats['latest_allocation']={'run':row[0],'fights':row[1],'events':row[2],'allocated':row[3],'warnings':row[4]}"
    if marker not in s:raise SystemExit('1.2.0 status marker not found.')
    s=s.replace(marker,marker+add)
app.write_text(s,encoding='utf-8')
t=spec.read_text(encoding='utf-8')
if "'damage_allocation_engine'" not in t:t=t.replace("'healing_mitigation_engine'","'healing_mitigation_engine','damage_allocation_engine'")
spec.write_text(t,encoding='utf-8')
(root/'damage_allocation_engine.py').write_text((Path(__file__).parent/'damage_allocation_engine.py').read_text(encoding='utf-8'),encoding='utf-8')
(root/'allocation_rules.example.json').write_text((Path(__file__).parent/'allocation_rules.example.json').read_text(encoding='utf-8'),encoding='utf-8')
print('Integrated P0-9. Build label updated to 1.3.0.')
