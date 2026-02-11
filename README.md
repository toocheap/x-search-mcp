# X (Twitter) Search MCP Server

xAI の Grok API を利用して、Claude Desktop から X (Twitter) の投稿検索ができる MCP サーバーです。

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

### 2. 依存パッケージのインストール

```bash
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
            "command": "python",
            "args": ["/path/to/x_search_mcp.py"],
            "env": {
                "XAI_API_KEY": "xai-xxxxxxxxxxxxxxxxxxxxxxxx"
            }
        }
    }
}
```

> `/path/to/x_search_mcp.py` は実際のファイルパスに置き換えてください。

### 4. Claude Desktop を再起動

設定後、Claude Desktop を再起動すると MCP サーバーが認識されます。

## 使用例

Claude Desktop で以下のように話しかけるだけです：

- 「AIに関する最新のツイートを検索して」
- 「@elonmusk の最近の投稿を見せて」
- 「日本でのトレンドを教えて」
- 「#cybersecurity のツイートを日本語で検索」

## 注意事項

- xAI API の利用料金が発生します（Grok API の料金体系に準じます）
- Grok のライブ検索機能を経由するため、リアルタイムのデータに近い結果が返りますが、完全なリアルタイム性は保証されません
- `grok-3-mini` モデルを使用しています。必要に応じてコード内の `XAI_MODEL` を変更できます

## モデル変更

コスト・精度のバランスに応じて `XAI_MODEL` を変更可能です：

| モデル | 特徴 |
|---|---|
| `grok-3-mini` | 軽量・低コスト（デフォルト） |
| `grok-3` | 高精度・高コスト |
