# X (Twitter) Search MCP Server

xAI の [Responses API](https://docs.x.ai/developers/tools/overview) + [x_search サーバーサイドツール](https://docs.x.ai/developers/tools/x-search)を利用して、Claude Desktop / claude.ai から X (Twitter) の投稿をリアルタイム検索できる MCP サーバーです。

## 機能

| ツール名 | 機能 |
|---|---|
| `x_search_posts` | キーワード・ハッシュタグ・トピックで X の投稿を検索 |
| `x_get_user_posts` | 特定ユーザーの最近の投稿を取得（`allowed_x_handles` で絞り込み） |
| `x_get_trending` | トレンドトピックを取得 |

## セットアップ

### 1. 必要なもの

- Python 3.10+
- xAI API キー（ https://console.x.ai/ から取得）

### 2. インストール

```bash
git clone https://github.com/toocheap/x-search-mcp.git
cd x-search-mcp
python3 -m venv .venv
source .venv/bin/activate
pip install mcp httpx pydantic
```

### 3. Claude Desktop の設定

`claude_desktop_config.json` に以下を追加してください：

- **macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Windows**: `%APPDATA%\Claude\claude_desktop_config.json`

```json
{
    "mcpServers": {
        "x_search": {
            "command": "/path/to/x-search-mcp/.venv/bin/python3",
            "args": ["/path/to/x-search-mcp/x_search_mcp.py"],
            "env": {
                "XAI_API_KEY": "xai-xxxxxxxxxxxxxxxxxxxxxxxx"
            }
        }
    }
}
```

> パスは実際の環境に合わせて変更してください。

### 4. Claude Desktop を再起動

設定後、Claude Desktop を再起動すると MCP サーバーが認識されます。

## 使用例

Claude Desktop / claude.ai で以下のように話しかけるだけです：

- 「AIに関する最新のツイートを検索して」
- 「@elonmusk の最近の投稿を見せて」
- 「日本でのトレンドを教えて」
- 「#cybersecurity のツイートを日本語で検索」

## アーキテクチャ

```
Claude <-> MCP Server <-> xAI Responses API (/v1/responses)
                              |
                         x_search tool
                        (server-side)
                              |
                         X (Twitter) data
```

このサーバーは xAI の **Responses API** と **x_search サーバーサイドツール**を使用しています。
Grok がサーバーサイドで自律的に X を検索・分析し、結果を返すエージェンティックな仕組みです。

旧 Live Search API (`search_parameters`) は 2026年1月に廃止されたため、
新しい Agent Tools API を使用しています。

## モデル

`x_search` サーバーサイドツールは **grok-4 系モデルのみ**で利用可能です。

| モデル | 特徴 |
|---|---|
| `grok-4-1-fast` | ツール呼び出し最適化・高速（**デフォルト**） |
| `grok-4-1-fast-reasoning` | 推論付き・より高精度 |

モデルを変更する場合は `x_search_mcp.py` 内の `XAI_MODEL` 定数を編集してください。

> **注意**: `grok-3` 系モデルでは x_search ツールは利用できません（400 エラーになります）。

## 料金

xAI API の利用料金が発生します。詳細は [xAI Pricing](https://docs.x.ai/developers/models) を参照してください。

## ライセンス

MIT
