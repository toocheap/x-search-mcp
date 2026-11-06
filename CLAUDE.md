# X Search MCP Server

X (Twitter) の投稿をリアルタイム検索する MCP サーバー。2 つのデータ源 backend を持つ:

1. **xAI backend** — xAI の Responses API + `x_search` サーバーサイドツール（Grok 経由のセマンティック検索）
2. **xurl backend** — 公式 `xurl` CLI 経由の認証済み実 X API v2（生データ取得）

## 開発ルール
開発ルール（委譲・スコープ・レビュー・テスト・規約）は `~/.hermes/AGENTS.md` が正本。本ファイルはリポ固有情報のみ。矛盾があれば正本が優先。

## 構成・認証

- `XAI_API_KEY` 環境変数（xAI backend 用、https://console.x.ai/ から取得）。
- `xurl` CLI が PATH 上にあり OAuth2 認証済みであること（xurl backend 用、`xurl auth` で設定）。
- 構成: `x_search_mcp.py`（MCP ツール）+ `xurl_client.py`（xurl CLI アダプタ、moa から移植）。
- エントリーポイント: `mcp.run()` (`if __name__ == "__main__"`)。

## backend 選択（環境変数 `X_SEARCH_BACKEND`）

| 値 | 挙動 |
|----|------|
| `auto`（既定） | xurl が認証済みなら xurl を使用。未認証 / xurl 失敗時は xAI にフォールバック |
| `xurl` | xurl を強制（失敗時はエラー JSON を返却） |
| `xai` | 従来通り xAI を強制 |

- `auto` モードでは xurl 呼び出しが `XurlError` を投げると黙って xAI に切替。
- `x_get_trending` は xurl に安定したトレンド API が無いため **常に xAI** を使用。
- `x_auth_status` ツールで有効 backend と xurl 認証状態を確認できる。

## アーキテクチャ

```text
                          ┌─ (xai)  xAI Responses API (/v1/responses) ─ x_search tool ─┐
MCP Client <-> MCP Server ┤                                                            ├─> X (Twitter) data
        (stdio)           └─ (xurl) xurl CLI ─ X API v2 (/2/tweets/search/recent 等) ──┘
```

- モデル: `grok-4-1-fast`（`XAI_MODEL` 定数で変更可）。
- `grok-3` 系は非対応（400 エラー）。

## ツール一覧 — 4ツール（すべて読み取り専用）

| ツール | 入力モデル | 説明 | xurl 経路 |
|--------|-----------|------|-----------|
| `x_search_posts` | `XSearchPostsInput` | キーワード・ハッシュタグ・トピックで投稿を検索 | `/2/tweets/search/recent`（`language`→`lang:` 演算子） |
| `x_get_user_posts` | `XGetUserPostsInput` | 特定ユーザーの最近の投稿を取得 | username 解決→`/2/users/:id/tweets`（`topic_filter` はクライアント側） |
| `x_get_trending` | `XTrendingInput` | トレンドトピックを取得 | 非対応（常に xAI） |
| `x_auth_status` | （引数なし） | 有効 backend と xurl 認証状態を報告 | `xurl auth status`（課金なし） |

### 共通パラメータ

- `response_format`: `"markdown"`（デフォルト）または `"json"`（`ResponseFormat` enum）。
- `max_results`: 1〜30（デフォルト 10）。xurl backend では X API 仕様により内部で 10/5 にフロアされ、結果を上位 `max_results` 件にトリム。
- `from_date` / `to_date`: `YYYY-MM-DD` 形式の日付フィルタ（xurl backend では RFC3339 `start_time`/`end_time` に変換。`to_date` は当日末まで包含）。

## 内部ヘルパー・技術的注意事項

| 関数 | 説明 |
|------|------|
| `_get_api_key()` | 環境変数 `XAI_API_KEY` を取得（未設定時は `RuntimeError`） |
| `_call_responses_api()` | xAI `/v1/responses` エンドポイントを呼び出し |
| `_build_x_search_config()` | `x_search` ツール設定 dict を構築 |
| `_handle_api_error()` | xAI API エラーをユーザー向けメッセージに変換 |
| `_get_backend()` | `X_SEARCH_BACKEND` を取得（不正値は `auto`） |
| `_should_use_xurl()` | backend に応じて xurl を使うか判定（`auto` は `xurl_client.available()`） |
| `_xurl_search_posts()` / `_xurl_user_posts()` | xurl 経路の検索／ユーザー投稿取得（同期。ツールからは `asyncio.to_thread` 経由） |
| `_handle_xurl_error()` | `XurlError` を改善案つき JSON エラーに変換 |

- ツール入力は Pydantic `BaseModel`、ツール関数は `async def`。
- `@mcp.tool(name="tool_name", annotations={...})` デコレータを使用。
- HTTP 通信はタイムアウト付き `httpx.AsyncClient` を使用。
- API エラーは `_handle_api_error()` / `_handle_xurl_error()` で統一的に処理し、JSON 形式で返す。

## `xurl_client.py`（xurl CLI アダプタ）

- `Runner` 注入契約 `(argv, timeout) -> (rc, stdout, stderr)` — 外部境界の fake はここ 1 箇所。
- エラー階層: `XurlError` / `XurlAuthError` / `XurlQuotaError` / `XurlRateLimitError` / `XurlNotFoundError`。
- HTTP 429 は指数バックオフでリトライ（`DEFAULT_MAX_RETRIES`）。401/403/402/404 はリトライしない。
- `available()` は `xurl auth status` のみで認証確認（`~/.xurl` を読まず課金もしない）。
- セキュリティ: `-v`/`--verbose` を渡さない（トークン漏洩防止）、トークンをログ・例外に含めない。
- X API v2 JSON → 共通 post dict (`tweet_json_to_post` / `posts_from_response`) → `format_posts` で markdown/json 整形。

## 依存パッケージ

```text
mcp>=1.26.0
httpx>=0.28.0
pydantic>=2.12.0
```

xurl backend を使う場合は別途 `xurl` CLI（公式 X API CLI、pip 非依存）を PATH 上に用意し `xurl auth` で OAuth2 認証する。未導入でも `auto`/`xai` backend は動作する。

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

# 外部接続テスト（xAI: 要 XAI_API_KEY / xurl: 要 xurl 認証）
XAI_API_KEY="xai-xxx" pytest tests/integration/ -m integration --timeout=30
```

## 関連文書

- `tasks/todo.md`: 進捗。
