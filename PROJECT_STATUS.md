# Local XIV Analyzer

## Current Status

- Version: 1.2.0
- Last Updated: 2026-08-23
- Branch: main
- Repository Status: origin/main synchronized
- Working Tree: clean

---

## P0 Status

| ID | 機能 | 状態 | 確認内容 |
|---|---|---|---|
| P0-1 | FFLogs収集基盤 | Implemented | 実装済み |
| P0-2 | 比較セル生成 | Implemented | 実装済み |
| P0-3 | 有効戦闘時間正規化 | Implemented | 実装済み |
| P0-4 | 適格性・外れ値判定 | Implemented | 実装済み |
| P0-5 | ACTログ取込 | Implemented | 実装済み |
| P0-6 | 統計基準生成 | Implemented | 実装済み |
| P0-7 | ジョブ別解析 | Implemented | 実装済み |
| P0-8 | 全ジョブ・ボス解析 | Implemented | 実装済み |
| P0-9 | 火力配賦解析 | Tested / Merged | 構文検査、単体テスト、GUI確認完了 |
| P0-10 | 回復・軽減解析 | Implemented | 実装済み |

---

## P0-9 Integration Result

- `damage_allocation_engine.py` を統合
- `allocation_rules.example.json` を追加
- `test_damage_allocation_engine.py` を追加
- `LocalXIVAnalyzer.spec` の hiddenimports を更新
- `refresh()` に `allocation_runs` の結果表示を追加
- GUIへ「P0-9 火力配賦」ボタンを追加
- `allocate_damage()` のクラス配置不具合を修正
- 構文検査成功
- 単体テスト結果: `PASS`
- GUI起動確認成功
- 未取込時の案内ダイアログ確認済み
- Pull Request #1: Merged
- Pull Request #2: Merged
- 最新main取得済み

---

## P1 Design Status

以下は主に設計段階であり、実装・テスト完了を意味しない。

- P1-1 Registry
- P1-2 ActionEffect / Unknown Collector
- P1-3 Job Analysis Expansion
  - Burst Analyzer
  - Synergy Alignment
  - Resource Analyzer
  - Proc Analyzer
  - DoT / Uptime Analyzer
- P1-4 Encounter Registry
- P1-5 Death Analyzer
- P1-6 Report Engine
- P1-7 Scoring Engine
- P1-8 Unified Report JSON
- P1-9 UI / UX

---

## Next Tasks
- 正式なバフID・効果量・対象範囲を確認して配賦ルールを整備

### High Priority

- ボタン順を `P0-7 → P0-8 → P0-9 → P0-10` に整理
- P0-8・P0-9・P0-10を画面内で確認できるよう配置を改善
- 表示バージョンを1.3.0へ更新するか確認
- `ROADMAP.md` を更新

### Validation

- 実ACTログによるP0-9火力配賦結果の検証
- warning、confidence、method、evidenceの確認
- FFLogs参照値との差分検証
- 推定値と実測値を区別して記録

### Next Development Candidates

1. P1-1 Registry基盤
2. P1-2 ActionEffect Decoder / Unknown Collector
3. Shield Ledger、Crit、Direct Hitの実ログ検証
4. P1-3 Job Analysis Expansion
5. P1-4 Encounter Registry
6. P1-5 Death Analyzer

---

## Safety and Repository Rules

- ACT実ログをGitHubへ登録しない
- キャラクター名などを匿名化する
- APIキー、Client Secret、Saltをコミットしない
- ZIP、patch、`__pycache__`、`*.pyc`をコミットしない
- mainへ直接変更を加えない
- featureまたはdocsブランチを使用する
- 構文検査とテスト成功後にコミットする
- Pull Request経由でmainへ統合する
- 設計、実装、テスト、Blockedを区別して記録する
### Real ACT Log Validation
### Technical Finish Rule Validation

- Status ID: `1822` (`0x71E`)
- Status name: `Technical Finish`
- Rule type: `damage_percent`
- Provisional value: `5%`
- Targeting: party
- Confidence: medium
- Source method: official job guide and ACT log verification
- ACT log duration: 20 seconds
- Successful steps determine the actual bonus from 1% to 5%
- Current ACT importer does not preserve successful step count
- The provisional rule therefore uses the maximum 4-step value of 5%
- Real-log validation result:
  - Fights: 54
  - Damage events: 79,776
  - Allocation rows: 12,243
  - Allocated damage: 25,875,279.619
  - Warnings: 0
- Engine output and database allocation totals matched
- Remaining task: preserve or infer the successful step count before treating the allocation as fully verified

- Status: Partially Tested
- Source log: `Network_30208_20260818.log`
- Log files were read directly from the ACT folder and were not copied into the repository
- Imported encounters: 54
- Parsed events: 165,381
- Damage events: 79,776
- Example rules result: allocated damage `0.0`
- Synthetic validation rule result:
  - Allocation rows: 24,363
  - Allocated damage: 75,947,424.0
  - Warnings: 0
- Engine output and database allocation totals matched
- The synthetic buff ID and 10% effect were used only to verify the processing path
- Official buff IDs, effect values, and allocation rules remain unverified

---

## Technical Finish Step Detection

- Status: Implemented / Real-log Tested
- Quadruple action IDs: `33218` and `16196`
- Matched allocation rows: 11,804
- Fallback allocation rows: 439
- Total allocated damage: 25,055,897.780
- Fallback warnings: 439
- Unit test: PASS
- Unmatched actions use the provisional 1% value with medium confidence

---

## Battle Litany Validation

- Status: Implemented / Real-log Tested
- Status ID: `786`
- Effect: Critical hit rate +10%
- Targeting: Party
- Method: Expected value estimate
- Confidence: Low
- Additional ACT log:
  - Source size: 428,387,120 bytes
  - Import time: 32.4 seconds
  - Fights: 154
  - Parsed events: 562,144
  - Damage events: 283,879
  - Battle Litany applications: 751
- Allocation result:
  - Battle Litany allocation rows: 15,039
  - Battle Litany allocated damage: 24,943,389.538
  - Total allocated damage: 51,968,139.609
  - Total warnings: 21,206
- Unit test: PASS
- Critical-hit details are unavailable in the current ACT import format
- Battle Litany contribution therefore remains an expected-value estimate

---

## Party Damage Buff Rules Validation

- Status: Implemented / Real-log Tested
- Validation log:
  - Fights: 154
  - Damage events: 283,879
- Added rules:
  - Divination (`1878`): damage +6%
  - Starry Muse (`3685`): damage +5%
  - Brotherhood (`1185`): damage +5%
- Allocation results:
  - Divination: 41,769,159.513
  - Starry Muse: 32,661,541.046
  - Brotherhood: 4,352,869.977
  - Battle Litany: 24,943,389.538
  - Technical Finish: 25,771,618.003
  - Total: 129,498,578.077
- Warnings: 18,447
- Fixed method and confidence leakage between overlapping buffs
- Fixed rule confidence handling
- Unit test: PASS

---

## Enemy Target Debuff Validation

- Status: Implemented / Real-log Tested
- Dokumori status ID: `3849`
- Effect: Target damage taken +5%
- Targeting: Enemy
- Confidence: High
- Validation result:
  - Fights: 154
  - Damage events: 283,879
  - Allocation rows: 14,088
  - Allocated damage: 37,869,194.803
  - Total allocated damage: 166,192,129.961
  - Warnings: 18,447
- Added separate source-buff and target-debuff window handling
- Unit test: PASS

---

## GUI Button Layout

- Status: Implemented / GUI Tested
- Buttons were changed from one row to two rows
- Button order: P0-7 ? P0-8 ? P0-9 ? P0-10
- All buttons are visible within the application window
- Japanese labels display correctly
- Syntax check: PASS

---

## Analyze-style Local Workflow

- Status: Implemented / GUI Tested
- Main workflow:
  - Open ACT log
  - Select a fight
  - Analyze selected fight
- Fight boundaries use OverlayPlugin InCombat (`260`) transitions
- A 20-second preparation window is retained before combat
- Falls back to the previous gap-based method when InCombat records are absent
- Latest validation log:
  - 18 fights
  - Futures Rewritten (Ultimate): 13
  - The Goblet: 2
  - the Wanderer's Palace: 3
- Fight list includes:
  - Content grouping
  - Start time
  - Pull number
  - Main enemy
  - Reached phase
  - Duration in mm:ss
  - Result
- Selected-fight analysis runs boss, damage allocation, and healing/mitigation analysis
- GUI and syntax checks: PASS

---

## Selected-fight Analysis Performance

- Last Updated: 2026-08-23
- Branch: `feature/analysis-results-view`
- Status: Implemented / Regression Tested
- `comparison_cell_builder.py` に戦闘単位フィルターを追加
- イベントを送信元・対象別に索引化
- `build_cells` 実測:
  - Before: `36.017s`
  - After: `9.252s`
  - Reduction: approximately `74.3%`
- Regression validation:
  - `player_features`: 18,205 / 18,205, matched
  - `comparison_cells`: 150 / 150, matched
  - Result: `REGRESSION=PASS`
- Syntax checks: PASS
- Direct test suite: 3 / 3 PASS
- Final validation: PASS
- `git diff --check`: PASS
- テスト対象戦闘では解析結果の同一性を確認
- 残課題:
  - ソース差分の確認
  - ローカルDB・ログ・バックアップのGit除外: PASS
  - 引継ぎ資料の文字・構造検証: PASS
  - ROADMAP同期: PASS
  - 最終テスト後のcommit・Push・PR・merge・main同期

## Execution Log Policy

- 各検証で `logs/result.txt` を生成する
- 匿名化済み `logs/powershell.txt` も同時に生成・確認する
- raw PowerShellログ、ACTログ、DB、個人情報を含む結果はGitへ追加しない

---

---

---

## Latest Repository State

- Last Updated: 2026-08-23
- Branch: `main`
- Repository Status: `origin/main` synchronized
- Working Tree: clean
- Latest merged PR: `#15`
- Main commit: `630c656`
- Selected-fight analysis: implemented and tested
- Comparison-cell optimization: regression tested
- `build_cells`: 36.017s -> 9.252s
- Direct tests: 3 / 3 PASS

## Current Chat Operating Policy

- 各タスク完了時に方針・進捗・TASKS・ROADMAP・引継ぎ資料を同期する
- `logs/result.txt` と匿名化済み `logs/powershell.txt` をセットで確認する
- ACTログ、DB、実行結果、PowerShellログをGitへ追加しない
- 通常操作は「ACTログ取込 -> 戦闘選択 -> 選択戦闘を解析」を中心とする
- 表示用語は可能な限りFFLogsおよびXIVAnalysisに合わせる
- 解析品質を維持しながら処理を高速化する
- テスト後はcommit、Push、PR、merge、main同期まで進める
- 操作案内とファイル更新は可能な限りPowerShellで行う
- チャット移行用資料を随時最新状態に保つ

## Next Development Direction

1. mainを起点に次の機能ブランチを作成する
2. P1-1 Registry基盤を優先候補として詳細化する
3. 解析表示と改善提案を段階的に拡張する
4. 解析品質、速度、個人データ保護を検証する

---

## P1-1 Registry Foundation

- Status: Implemented / Tested
- Branch: `main`
- Common versioned rule loader: `rule_registry.py`
- Supported registries: buff, mitigation, job, encounter, alias
- Existing four JSON formats: compatible
- Four existing engines use the common registry loader
- Default rule behavior: preserved
- Registry and integration tests: 9 PASS
- Existing direct tests: 3 PASS
- Python compile: PASS
- `git diff --check`: PASS
- PyInstaller hidden import: updated
