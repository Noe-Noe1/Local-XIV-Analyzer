# Local XIV Analyzer Roadmap

## Current Version

- Version: 1.2.0
- Status: Active Development

---

# Phase P0 (Core Foundation)

## Completed

- P0-1 FFLogs収集
- P0-2 比較セル生成
- P0-3 有効戦闘時間正規化
- P0-4 適格性判定
- P0-5 ACTログ取込
- P0-6 統計基準生成
- P0-7 ジョブ解析
- P0-8 ボス解析
- P0-9 火力配賦実装
- P0-10 回復・軽減解析

## Pending

- P0-9 正式統合: Completed / Tested / Merged

---

# Phase P1 (Analysis Architecture)

## P1-1 Registry

- Buff Registry
- Mitigation Registry
- Job Registry
- Encounter Registry
- Alias Registry
- Version Registry

Status: Designed

---

## P1-2 ActionEffect Framework

- Decoder Framework
- Effect Type Detection
- Rule Engine
- Unknown Collector
- Shield State Management

Status: Designed

Waiting:
- ACT実ログ
- Shield検証
- Crit検証
- Direct Hit検証

---

## P1-3 Job Analysis Expansion

### Burst Analyzer

- Burst Window
- Drift Analysis
- Coverage Analysis
- Synergy Alignment

### Resource Analyzer

- Resource Tracking
- Overcap Detection
- Burst Resource Scoring

### Proc Analyzer

- Usage Rate
- Loss Rate
- Delay Analysis
- Burst Proc Alignment

### DoT/Uptime Analyzer

- DoT Uptime
- Gap Detection
- Refresh Analysis
- Burst Alignment

Status: Designed

---

## P1-4 Encounter Registry

- Encounter Database
- Phase Database
- Mechanic Database
- Raidwide Registry
- Tankbuster Registry
- Downtime Registry

Status: Designed

---

## P1-5 Death Analyzer

- Death Timeline
- Damage Timeline
- Healing Timeline
- Mitigation Timeline
- Shield Timeline
- Cause Classification
- Confidence Score

Status: Designed

---

## P1-6 Report Engine

- Feedback Generation
- Improvement Suggestions
- Summary Generation

Status: Designed

---

## P1-7 Scoring Engine

- Burst Score
- Resource Score
- Proc Score
- DoT Score
- Death Score
- Overall Grade

Status: Designed

---

## P1-8 Unified Report Format

- JSON Export
- CSV Export
- HTML Export
- PDF Export

Status: Designed

---

## P1-9 UI / UX

### Completed Design

- Dashboard
- Reports
- Job Analysis
- Encounter Analysis
- Healing & Mitigation
- Death Review

### Remaining

- Improvement Plan
- History View
- Export UI

Status: In Progress

---

# Phase P2 (Validation)

## Log Validation

- ACT実ログ検証
- ActionEffect解析
- Shield解析
- Crit解析
- Direct Hit解析

Status: Waiting

---

## FFLogs Compatibility

- Damage Validation
- Buff Validation
- Mitigation Validation
- rDPS Validation
- nDPS Validation
- aDPS Validation
- cDPS Validation

Status: Waiting

---

# Phase P3 (Advanced Features)

## XIVAnalysis Equivalent System

- Automated Feedback
- Rotation Evaluation
- Encounter-Specific Advice
- Job-Specific Advice

Status: Planned

---

## Long-Term Goals

- Local XIVAnalysis Equivalent
- Offline Raid Review
- FFLogs Comparison
- Personal Progress Tracking
- Full Encounter Knowledge Base

---

# Current Integration Status

- Last Updated: 2026-08-23
- Branch: `feature/analysis-results-view`
- P0-9 integration: Completed / Tested / Merged
- Selected-fight workflow: Implemented / GUI Tested
- Comparison-cell optimization: Implemented / Regression Tested
- `build_cells`: 36.017s -> 9.252s
- Regression result: PASS
- Current priority:
  1. Review source diffs
  2. Exclude local logs, databases, caches, and backups from Git
  3. Run final validation
  4. Commit, Push, PR, merge, and synchronize main

## Latest Completion State

- PR #12: MERGED
- Main commit: `04e9a5e`
- `origin/main`: synchronized
- Working tree: clean
- Selected-fight workflow: implemented and tested
- Comparison-cell optimization: regression tested
- Next: select the next prioritized development task
