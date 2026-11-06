# X Search MCP Server

X (Twitter) の投稿をリアルタイム検索する MCP サーバー。xAI の Responses API + `x_search` サーバーサイドツールを使用。

## 開発ルール
開発ルール（委譲・スコープ・レビュー・テスト・規約）は `~/.hermes/AGENTS.md` が正本。本ファイルはリポ固有情報のみ。矛盾があれば正本が優先。

## 構成・認証

- `XAI_API_KEY` 環境変数が必要（https://console.x.ai/ から取得）。
- 単一ファイル構成: `x_search_mcp.py`。
- エントリーポイント: `mcp.run()` (`if __name__ == "__main__"`)。

## アーキテクチャ

```text
MCP Client <-> MCP Server (stdio) <-> xAI Responses API (/v1/responses)
                                              |
                                         x_search tool
                                        (server-side)
                                              |
                                         X (Twitter) data
```

- モデル: `grok-4-1-fast`（`XAI_MODEL` 定数で変更可）。
- `grok-3` 系は非対応（400 エラー）。

## ツール一覧 — 3ツール（すべて読み取り専用）

| ツール | 入力モデル | 説明 |
|--------|-----------|------|
| `x_search_posts` | `XSearchPostsInput` | キーワード・ハッシュタグ・トピックで投稿を検索 |
| `x_get_user_posts` | `XGetUserPostsInput` | 特定ユーザーの最近の投稿を取得 |
| `x_get_trending` | `XTrendingInput` | トレンドトピックを取得 |

### 共通パラメータ

- `response_format`: `"markdown"`（デフォルト）または `"json"`（`ResponseFormat` enum）。
- `max_results`: 1〜30（デフォルト 10）。
- `from_date` / `to_date`: `YYYY-MM-DD` 形式の日付フィルタ。

## 内部ヘルパー・技術的注意事項

| 関数 | 説明 |
|------|------|
| `_get_api_key()` | 環境変数 `XAI_API_KEY` を取得（未設定時は `RuntimeError`） |
| `_call_responses_api()` | xAI `/v1/responses` エンドポイントを呼び出し |
| `_build_x_search_config()` | `x_search` ツール設定 dict を構築 |
| `_handle_api_error()` | API エラーをユーザー向けメッセージに変換 |

- ツール入力は Pydantic `BaseModel`、ツール関数は `async def`。
- `@mcp.tool(name="tool_name", annotations={...})` デコレータを使用。
- HTTP 通信はタイムアウト付き `httpx.AsyncClient` を使用。
- API エラーは `_handle_api_error()` で統一的に処理し、JSON 形式で返す。

## 依存パッケージ

```text
mcp>=1.26.0
httpx>=0.28.0
pydantic>=2.12.0
```

## セットアップ

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 実行（MCP サーバー、stdio）
XAI_API_KEY="xai-xxx" python3 x_search_mcp.py
```

## テスト実行

```bash
pip install pytest pytest-asyncio pytest-cov pytest-timeout
export PYTHONPATH=$PYTHONPATH:.

# デフォルトスイート（外部サービス接続テストを除く）
pytest tests/ --ignore=tests/integration/

# 同スイートのカバレッジ計測
pytest tests/ --ignore=tests/integration/ --cov=. --cov-report=term-missing

# 外部 xAI API 接続テスト（要 XAI_API_KEY）
XAI_API_KEY="xai-xxx" pytest tests/integration/ -m integration --timeout=30

# 全テスト（外部 API 接続を含む。要 XAI_API_KEY）
XAI_API_KEY="xai-xxx" pytest tests/ --timeout=30
```

## 関連文書

- `task.md` / `implementation_plan.md`: 実装内容・計画。
