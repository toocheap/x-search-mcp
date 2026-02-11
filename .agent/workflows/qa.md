---
description: QAワークフロー — ユニットテスト・統合テスト・カバレッジ検証
---

# QA ワークフロー

コード変更後のテスト実行と品質検証を行う。

## 1. テスト環境の準備

// turbo
1. 依存パッケージがインストールされていることを確認する
```bash
cd /Users/too/src/x-search-mcp && source .venv/bin/activate && pip install pytest pytest-asyncio pytest-cov pytest-timeout
```

## 2. ユニットテスト実行

// turbo
2. ユニットテストを実行する（モック・スタブは極力使わない。使用する場合は理由をコメントに明記すること）
```bash
cd /Users/too/src/x-search-mcp && source .venv/bin/activate && PYTHONPATH=. pytest tests/ --ignore=tests/integration/ -v
```

## 3. カバレッジ計測

// turbo
3. カバレッジ計測付きでテストを実行し、100% を目指す
```bash
cd /Users/too/src/x-search-mcp && source .venv/bin/activate && PYTHONPATH=. pytest tests/ --ignore=tests/integration/ --cov=. --cov-report=term-missing
```

4. カバレッジ結果を確認する:
   - **100%**: 次のステップへ進む
   - **100% 未満**: 未カバー行を特定し、テストを追加する。カバーできない行がある場合は理由を明記する

## 4. テスト品質チェック

5. 以下の観点でテストの品質を確認する:
   - **正常系**: 各ツール・ヘルパー関数で期待入力に対する正しい出力を検証しているか
   - **異常系**: 無効入力、API エラー（401/429/500）、タイムアウト、環境変数未設定をテストしているか
   - **入力バリデーション**: Pydantic の必須フィールド、範囲制約、`extra="forbid"` をテストしているか
   - **環境隔離**: `monkeypatch` 等でテスト間の状態漏洩を防止しているか
   - **モック/スタブ不使用**: モック・スタブを使っている箇所がある場合、理由がコメントに明記されているか

## 5. 統合テスト（オプション）

6. `XAI_API_KEY` が利用可能な場合、統合テストを実行する。サブプロセスで実行し、ハングアップに対応する
```bash
cd /Users/too/src/x-search-mcp && source .venv/bin/activate && PYTHONPATH=. pytest tests/integration/ -m integration --timeout=30 -v
```

7. 統合テストの確認項目:
   - 実 API レスポンスの構造・ステータスが正しいか
   - タイムアウト設定が適切か（デフォルト 30 秒）
   - `XAI_API_KEY` 未設定時に自動スキップされるか
