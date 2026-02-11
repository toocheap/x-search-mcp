# X Search MCP Server

X (Twitter) の投稿をリアルタイム検索する MCP サーバー。xAI の Responses API + `x_search` サーバーサイドツールを使用。

- `XAI_API_KEY` 環境変数が必要（https://console.x.ai/ から取得）
- 単一ファイル構成: `x_search_mcp.py`
- エントリーポイント: `mcp.run()` (`if __name__ == "__main__"`)

## アーキテクチャ

```
MCP Client <-> MCP Server (stdio) <-> xAI Responses API (/v1/responses)
                                              |
                                         x_search tool
                                        (server-side)
                                              |
                                         X (Twitter) data
```

- モデル: `grok-4-1-fast`（`XAI_MODEL` 定数で変更可）
- `grok-3` 系は非対応（400 エラー）

## ツール一覧 — 3ツール（すべて読み取り専用）

| ツール | 入力モデル | 説明 |
|--------|-----------|------|
| `x_search_posts` | `XSearchPostsInput` | キーワード・ハッシュタグ・トピックで投稿を検索 |
| `x_get_user_posts` | `XGetUserPostsInput` | 特定ユーザーの最近の投稿を取得 |
| `x_get_trending` | `XTrendingInput` | トレンドトピックを取得 |

### 共通パラメータ

- `response_format`: `"markdown"`（デフォルト）または `"json"`（`ResponseFormat` enum）
- `max_results`: 1〜30（デフォルト 10）
- `from_date` / `to_date`: `YYYY-MM-DD` 形式の日付フィルタ

## 内部ヘルパー

| 関数 | 説明 |
|------|------|
| `_get_api_key()` | 環境変数 `XAI_API_KEY` を取得（未設定時は `RuntimeError`） |
| `_call_responses_api()` | xAI `/v1/responses` エンドポイントを呼び出し |
| `_build_x_search_config()` | `x_search` ツール設定 dict を構築 |
| `_handle_api_error()` | API エラーをユーザー向けメッセージに変換 |

## 依存パッケージ

```
mcp>=1.26.0
httpx>=0.28.0
pydantic>=2.12.0
```

## コーディング規約

- コメントは英語で統一
- すべての関数に型ヒントを記述（制約付き文字列には `Literal` / `Enum` を使用）
- すべてのツール入力に Pydantic `BaseModel` を使用し、`ConfigDict(extra="forbid")` を設定
- すべてのツール関数は `async def` とする
- `@mcp.tool(name="tool_name", annotations={...})` デコレータを使用
- エラーメッセージは具体的なアクションを示唆するものにする
- HTTP 通信は `httpx.AsyncClient` を使用し、タイムアウトを設定する
- 環境変数はモジュールレベルではなく、関数内（`_get_api_key` 等）で動的に取得し、テスト容易性を確保する
- APIエラーは `_handle_api_error()` で統一的にハンドリングし、JSON 形式で返す

## セットアップ

```bash
# 仮想環境作成 & 依存インストール
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 実行（MCP サーバーとして /stdio で起動）
XAI_API_KEY="xai-xxx" python3 x_search_mcp.py
```

## テストと品質保証

テストは `pytest` と `pytest-asyncio` を使用する。

### テスト方針
1. **カバレッジ 100% を目標**: コードカバレッジ 100% を目指す。未カバー行がある場合は理由を明記する
2. **正常系テスト**: 各ツール・ヘルパー関数について、期待される入力に対して正しい出力が返ることを検証する
3. **異常系テスト**: 無効な入力、API エラー（401/429/500）、タイムアウト、環境変数未設定など、エラーケースを網羅的にテストする
4. **リアルな検証 (No Mocks)**: 外部 API 呼び出しを除き、モックに頼らず実際の挙動を検証する
5. **環境の隔離 (Isolation)**: テストケース間で環境変数やグローバル状態が漏洩しないよう `monkeypatch` 等で隔離する
6. **入力バリデーション**: Pydantic モデルによるバリデーション（必須フィールド、範囲制約、`extra="forbid"`）のテストを重視する

### ユニットテストと統合テストの分離

- **ユニットテスト** (`tests/`): モック・スタブは極力使わず、実際の挙動を検証する。外部 API 呼び出し部分も可能な限りテスト用の軽量サーバーやフェイクを用いる。やむを得ずモック/スタブを使用する場合は理由をコメントに明記する。CI で常時実行する
- **統合テスト** (`tests/integration/`): 実際の xAI API を呼び出して E2E 検証を行う。`@pytest.mark.integration` マーカーで識別する

### 統合テスト方針
1. **実 API 呼び出し**: 統合テスト時は実際の外部 API を呼び出し、レスポンスの構造・ステータスを検証する
2. **サブプロセス実行**: 統合テストは `subprocess` 経由で実行し、ハングアップや無限ループに対応する。タイムアウトを設定し、超過時はプロセスを強制終了する
3. **タイムアウト制御**: 各テストケースに `pytest.mark.timeout` またはサブプロセスの `timeout` 引数で上限時間を設定する（デフォルト 30 秒）
4. **API キー必須**: `XAI_API_KEY` 環境変数が未設定の場合は統合テストを自動スキップする

### テスト実行方法
```bash
pip install pytest pytest-asyncio pytest-cov pytest-timeout
export PYTHONPATH=$PYTHONPATH:.

# ユニットテストのみ実行
pytest tests/ --ignore=tests/integration/

# カバレッジ計測付きで実行
pytest tests/ --ignore=tests/integration/ --cov=. --cov-report=term-missing

# 統合テスト実行（実 API 呼び出し、要 XAI_API_KEY）
XAI_API_KEY="xai-xxx" pytest tests/integration/ -m integration --timeout=30

# 全テスト実行
XAI_API_KEY="xai-xxx" pytest tests/ --timeout=30
```

## 開発ワークフロー

以下のワークフローは `.agent/workflows/` にも定義されており、スラッシュコマンドで呼び出せる。

| コマンド | ワークフロー | 説明 |
|---------|------------|------|
| `/develop` | `develop.md` | 計画→協議→実装→テスト→検証の全サイクル |
| `/qa` | `qa.md` | ユニットテスト・カバレッジ計測・統合テスト |
| `/review` | `review.md` | 3視点（実装者・QA・計画担当）レビュー + リーダー判断 |

1. **計画 (Plan)**: `task.md` および `implementation_plan.md` を更新し、実装内容を定義する
   - **チーム協議**: 実装者、品質管理（QA）、計画担当で実装方針を議論する（実装計画が必要な場合）
   - **リーダー判断**: リーダーがハイレベルな観点から、その実装が目的に合致しているか、一時しのぎの修正になっていないかを判断し、方針を決定する
2. **実装 (Implement)**: コードを作成・修正する。動的な設定読み込みを意識する
3. **テスト (Test)**: テストを実行し、リグレッションがないか確認する（`/qa`）
4. **検証 (Verify)**: 手動検証またはレポートの更新を行い、品質を担保する
