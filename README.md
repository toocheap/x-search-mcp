# X (Twitter) Search MCP Server

xAI の Responses API + Agent Tools (x_search) を利用して、Claude Desktop から X (Twitter) の投稿検索ができる MCP サーバーです。

## 機能

| ツール名 | 機能 |
|---|---|
| `x_search_posts` | キーワード・ハッシュタグ・トピックで X の投稿を検索 |
| `x_get_user_posts` | 特定ユーザーの最近の投稿を取得 |
| `x_get_trending` | トレンドトピックを取得 |

## セットアップ

### 1. 必要なもの

- Python 3.10+
- xAI API キー（ https://console.x.ai/ から取得）

### 2. インストール

```bash
cd x-search-mcp
python3 -m venv .venv
source .venv/bin/activate
pip install mcp httpx pydantic
```

### 3. Claude Desktop の設定

`claude_desktop_config.json` に以下を追加してください：

**macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
**Windows**: `%APPDATA%\Claude\claude_desktop_config.json`

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

Claude Desktop で以下のように話しかけるだけです：

- 「AIに関する最新のツイートを検索して」
- 「@elonmusk の最近の投稿を見せて」
- 「日本でのトレンドを教えて」
- 「#cybersecurity のツイートを日本語で検索」

## API について

このサーバーは xAI の **Responses API** (`/v1/responses`) と **x_search サーバーサイドツール**を使用しています。旧 Live Search API (`search_parameters`) は 2026年1月12日に廃止されました。

Grok がサーバーサイドで自律的に X を検索・分析し、結果を返すエージェンティックな仕組みです。

## モデル変更

コスト・精度のバランスに応じて `XAI_MODEL` を変更可能です：

| モデル | 特徴 |
|---|---|
| `grok-3-mini-fast` | 軽量・低コスト（デフォルト） |
| `grok-4-1-fast` | 高精度・ツール呼び出し最適化 |

## ライセンス

MIT
