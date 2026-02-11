# X (Twitter) Search MCP Server

xAI の [Responses API](https://docs.x.ai/developers/tools/overview) + [x_search サーバーサイドツール](https://docs.x.ai/developers/tools/x-search)を利用して、Claude Desktop / claude.ai から X (Twitter) の投稿をリアルタイム検索できる MCP サーバーです。

## 機能

| ツール名 | 機能 |
|---|---|
| `x_search_posts` | キーワード・ハッシュタグ・トピックで X の投稿を検索 |
| `x_get_user_posts` | 特定ユーザーの最近の投稿を取得（`allowed_x_handles` で絞り込み） |
| `x_get_trending` | トレンドトピックを取得 |

## セットアップ

### 前提条件

- Python 3.10 以上
- xAI API キー（ https://console.x.ai/ から取得）

### 1. リポジトリのクローンと仮想環境の作成

```bash
git clone https://github.com/toocheap/x-search-mcp.git
cd x-search-mcp

# 仮想環境を作成
python3 -m venv .venv

# 仮想環境を有効化
# macOS / Linux:
source .venv/bin/activate
# Windows:
# .venv\Scripts\activate

# 依存パッケージをインストール
pip install -r requirements.txt
```

### 2. 仮想環境の Python パスを確認

Claude Desktop の設定にはフルパスが必要です。以下のコマンドで確認してください：

```bash
# macOS / Linux
which python3
# 例: /Users/yourname/src/x-search-mcp/.venv/bin/python3

# Windows
# where python
# 例: C:\Users\yourname\src\x-search-mcp\.venv\Scripts\python.exe
```

### 3. Claude Desktop の設定

`claude_desktop_config.json` を開いて `mcpServers` に以下を追加します。

設定ファイルの場所：
- **macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Windows**: `%APPDATA%\Claude\claude_desktop_config.json`

```json
{
    "mcpServers": {
        "x_search": {
            "command": "/absolute/path/to/x-search-mcp/.venv/bin/python3",
            "args": ["/absolute/path/to/x-search-mcp/x_search_mcp.py"],
            "env": {
                "XAI_API_KEY": "xai-xxxxxxxxxxxxxxxxxxxxxxxx"
            }
        }
    }
}
```

> **重要**:
> - `command` には **手順2で確認した仮想環境の Python フルパス**を指定してください。システムの `python3` ではなく `.venv` 内のものを使います。
> - `args` には `x_search_mcp.py` の**絶対パス**を指定してください。
> - `XAI_API_KEY` には https://console.x.ai/ で取得した API キーを設定してください。

### 4. Claude Desktop を再起動

設定を保存したら Claude Desktop を再起動してください。MCP サーバーが認識され、X 検索ツールが使えるようになります。

### トラブルシューティング

接続エラーが出る場合は、Claude Desktop のログを確認してください：

```bash
# macOS
cat ~/Library/Logs/Claude/mcp-server-x_search.log
```

よくあるエラー：
| エラー | 原因 | 対処 |
|---|---|---|
| `Failed to spawn process: No such file or directory` | Python パスが間違っている | `.venv/bin/python3` のフルパスを `command` に指定 |
| `status 400: model not supported` | grok-3 系モデルを使用 | `XAI_MODEL` を `grok-4-1-fast` に変更（デフォルトで設定済み） |
| `status 401` | API キーが無効 | `XAI_API_KEY` を確認 |
| `status 410: Live search is deprecated` | 旧 API を使用 | 最新版に更新（`git pull`） |

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
