# Task: xurl 対応（moa の実装を参照）

## 目的
x-search-mcp は現状 xAI Grok API (`x_search` サーバーサイドツール) のみを X データ源にしている。
moa (`/Users/too/src/my_obsidian_assistant/moa/xurl_client.py`) と同じ設計で、公式 `xurl` CLI
（OAuth2 認証済みの実 X API v2）をデータ源として追加し、選択可能にする。

## 設計判断
- **backend 選択**: 環境変数 `X_SEARCH_BACKEND` ∈ {`auto`, `xurl`, `xai`}（既定 `auto`）
  - `auto`: xurl が認証済みなら xurl を使い、未対応操作・xurl 失敗時は xAI にフォールバック
  - `xurl`: xurl 強制（失敗はエラー返却）
  - `xai`: 従来通り xAI 強制
- **xurl_client.py**: moa から移植・整理。`Runner` 注入契約でテストはサブプロセス無し
- **ツール対応**:
  - `x_search_posts` → `/2/tweets/search/recent`（lang→`lang:` 演算子, from/to→start_time/end_time）
  - `x_get_user_posts` → `/2/users/by/username/:u` で id 解決 → `/2/users/:id/tweets`
  - `x_get_trending` → xurl に確実なトレンド API が無く課金/権限要件が重いため xAI 継続（明記）
- **新ツール** `x_auth_status` → xurl 認証状態 + 有効 backend を報告（読み取り専用）
- **整形**: X API v2 JSON → 共通 post dict → markdown / json

## チェックリスト
- [x] `xurl_client.py` 実装（error 階層, Runner, _run_json, available, whoami, search_recent,
      get_user_by_username, get_user_tweets, JSON→post 整形, format_posts）
- [x] `tests/test_xurl_client.py`（Runner フェイクで正常系・異常系・リトライ・整形 / 60件）
- [x] `x_search_mcp.py` に backend 選択 + xurl 経路 + `x_auth_status` ツール統合
- [x] conftest に autouse `default_xai_backend` を追加し既存テストの決定性を担保
- [x] `tests/test_backend.py` で backend 分岐・xurl 経路・auto フォールバック・auth_status を検証
- [x] ユニットテスト全緑（148件）+ カバレッジ（xurl_client 100% / x_search_mcp 99%、未カバーは `mcp.run()` のみ）
- [x] README / CLAUDE.md 追記（backend 設定, xurl セットアップ, アーキ図, トラブルシュート）
- [x] 統合テスト追加 + 実 xurl で動作証明（whoami / user_posts / search を実 X API で確認、3件 pass）

## レビュー

### 実装サマリ
- moa の `xurl_client.py` を依存無し（ScrapedTweet 非依存）に移植し、`posts_from_response` /
  `format_posts` で markdown・json 整形を追加。`Runner` 注入契約によりテストはサブプロセス無し。
- backend は `X_SEARCH_BACKEND` ∈ {auto, xurl, xai}（既定 auto）。auto は xurl 認証時に xurl、
  失敗時は xAI へ黙ってフォールバック。xurl 強制時はエラー JSON（`source: "xurl"`）を返す。
- ツール統合: `x_search_posts`→`/2/tweets/search/recent`（language→`lang:` 演算子）、
  `x_get_user_posts`→username 解決→`/2/users/:id/tweets`（topic_filter はクライアント側）。
  `x_get_trending` は xurl に安定 API が無く xAI 継続。`x_auth_status` ツールを新設。
- ツールは `asyncio.to_thread` で xurl 同期呼び出しをラップし、イベントループをブロックしない。

### 動作証明（実 X API / `X_SEARCH_BACKEND=xurl`）
- whoami → `@toocheap` 取得成功
- x_get_user_posts(@xai) → 実ポスト 2 件を URL・メトリクス付き markdown で整形
- x_search_posts(from:xai, json) → 構造化 2 件、`url`/`likes` 正常

### 設計判断の根拠
- 既存テストが auto モードで実 xurl にヒットしマシン依存になる問題を、conftest の autouse
  fixture で `xai` 既定に固定して解消（CI 非認証環境でも決定的）。
- セキュリティ: `-v` 非使用・トークン非ログ・`~/.xurl` 非読込（moa の方針を踏襲）。
