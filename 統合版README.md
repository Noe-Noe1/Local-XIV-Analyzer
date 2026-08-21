# Local XIV Analyzer 0.8.0 統合版

P0-1からP0-6を同一アプリへ再統合しました。

- P0-1 FFLogs公開Clearログ収集
- P0-2 比較セル生成
- P0-3 有効戦闘時間正規化
- P0-4 適格性・外れ値判定
- P0-5 ACTネットワークログ互換取込
- P0-6 バージョン付き統計基準生成

ACT取込データとFFLogs収集データは共通SQLiteへ保存され、同じP0-2からP0-6の処理へ渡されます。P0-6は最新基準Version、セル数、サンプル数を状態画面へ表示します。

Windowsでは build_integrated_exe.bat を実行し、dist\LocalXIVAnalyzer.exe を生成してください。

制約: Windows実機ビルドとFFLogs実API接続の検証は未完です。ACT ActionEffectは保守的デコードで、rawEffectsを監査用に保存します。
