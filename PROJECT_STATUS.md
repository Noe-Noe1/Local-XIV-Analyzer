# Local XIV Analyzer

## Current Status

- Version: 1.2.0
- Last Updated: 2026-08-22
- Branch: main
- Repository Status: origin/main と同期済み
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