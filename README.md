# X (Twitter) Search MCP Server

MCP 対応クライアントから X (Twitter) の投稿をリアルタイム検索できる MCP サーバーです。2 つのデータ源 backend を選べます：

1. **xAI backend** — [Responses API](https://docs.x.ai/developers/tools/overview) + [x_search サーバーサイドツール](https://docs.x.ai/developers/tools/x-search)。Grok が自律的に X を検索・分析（セマンティック検索）。
2. **xurl backend** — 公式 [`xurl`](https://github.com/xdevplatform/xurl) CLI 経由の認証済み実 X API v2。生のポストデータを直接取得。

backend は環境変数 `X_SEARCH_BACKEND` で切り替えます（既定 `auto`）。

## 機能

| ツール名 | 機能 |
|---|---|
| `x_search_posts` | キーワード・ハッシュタグ・トピックで X の投稿を検索 |
| `x_get_user_posts` | 特定ユーザーの最近の投稿を取得 |
| `x_get_trending` | トレンドトピックを取得（常に xAI backend を使用） |
| `x_auth_status` | 有効な backend と xurl 認証状態を確認 |

## backend の選択（`X_SEARCH_BACKEND`）

| 値 | 挙動 |
|---|---|
| `auto`（既定） | `xurl` が認証済みなら xurl を使用、未認証 / 失敗時は xAI にフォールバック |
| `xurl` | `xurl` CLI を強制（実 X API v2） |
| `xai` | xAI Responses API を強制 |

- **xAI backend** には `XAI_API_KEY` が必要です。
- **xurl backend** には `xurl` CLI が PATH 上にあり OAuth2 認証済み（`xurl auth`）であることが必要です。
- `auto` で xurl が利用できない環境では自動的に xAI にフォールバックするため、どちらか一方だけの構成でも動作します。
- `x_get_trending` は xurl に安定したトレンド API が無いため常に xAI backend を使用します。

## 対応クライアント

stdio トランスポートに対応した MCP クライアントであれば利用できます。代表的なものを以下に挙げます：

| クライアント | 種類 |
|---|---|
| [Claude Desktop](https://claude.ai/download) | デスクトップアプリ |
| [Claude Code](https://docs.anthropic.com/en/docs/claude-code) | CLI |
| [Cursor](https://www.cursor.com/) | コードエディタ |
| [Windsurf](https://codeium.com/windsurf) | コードエディタ |
| [VS Code (GitHub Copilot)](https://code.visualstudio.com/) | コードエディタ |
| [Cline](https://github.com/cline/cline) | VS Code 拡張 |
| [Roo Code](https://github.com/RooVetGit/Roo-Code) | VS Code 拡張 |
| [Cherry Studio](https://github.com/kangfenmao/cherry-studio) | デスクトップアプリ |
| [5ire](https://github.com/nanbingxyz/5ire) | デスクトップアプリ |

その他の MCP 対応クライアントは [MCP Clients 一覧](https://modelcontextprotocol.io/clients) を参照してください。

## セットアップ

### 前提条件

- Python 3.10 以上
- xAI API キー（ https://console.x.ai/ から取得）— xAI backend を使う場合
- `xurl` CLI（ https://github.com/xdevplatform/xurl ）を導入し `xurl auth` で認証 — xurl backend を使う場合

> いずれか一方だけでも動作します。両方を用意して `X_SEARCH_BACKEND=auto`（既定）にすると、xurl 優先・xAI フォールバックになります。

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

MCP クライアントの設定にはフルパスが必要です。以下のコマンドで確認してください：

```bash
# macOS / Linux（venv を有効化した状態で）
which python3
# 例: /Users/yourname/src/x-search-mcp/.venv/bin/python3

# Windows
# where python
# 例: C:\Users\yourname\src\x-search-mcp\.venv\Scripts\python.exe
```

### 3. MCP クライアントの設定

ほとんどの MCP クライアントは同じ JSON 形式の設定に対応しています。
以下の内容をお使いのクライアントの MCP 設定に追加してください：

```json
{
    "mcpServers": {
        "x_search": {
            "command": "/absolute/path/to/x-search-mcp/.venv/bin/python3",
            "args": ["/absolute/path/to/x-search-mcp/x_search_mcp.py"],
            "env": {
                "XAI_API_KEY": "xai-xxxxxxxxxxxxxxxxxxxxxxxx",
                "X_SEARCH_BACKEND": "auto"
            }
        }
    }
}
```

> **重要**:
> - `command` には **手順2で確認した仮想環境の Python フルパス**を指定してください。システムの `python3` ではなく `.venv` 内のものを使います。
> - `args` には `x_search_mcp.py` の**絶対パス**を指定してください。
> - `XAI_API_KEY` には https://console.x.ai/ で取得した API キーを設定してください（xAI backend 用）。
> - `X_SEARCH_BACKEND` は `auto`（既定）/ `xurl` / `xai` から選びます。省略時は `auto`。xurl backend は MCP サーバーを起動するユーザーの `xurl` 認証情報（`~/.xurl`）を使うため、`env` に資格情報を書く必要はありません。

<details>
<summary>クライアント別の設定ファイルの場所</summary>

| クライアント | 設定ファイル |
|---|---|
| Claude Desktop (macOS) | `~/Library/Application Support/Claude/claude_desktop_config.json` |
| Claude Desktop (Windows) | `%APPDATA%\Claude\claude_desktop_config.json` |
| Claude Code | `~/.claude/settings.json` または `claude mcp add` コマンド |
| Cursor | Settings → MCP → Add Server |
| Windsurf | Settings → Advanced Settings → Cascade |
| VS Code (Copilot) | Settings → MCP → Edit in settings.json |

</details>

### 4. クライアントを再起動

設定を保存したらクライアントを再起動してください。MCP サーバーが認識され、X 検索ツールが使えるようになります。

## 使用例

MCP クライアントで以下のように話しかけるだけです：

- 「AIに関する最新のツイートを検索して」
- 「@elonmusk の最近の投稿を見せて」
- 「日本でのトレンドを教えて」
- 「#cybersecurity のツイートを日本語で検索」

## アーキテクチャ

```
                          ┌─ (xai)  xAI Responses API (/v1/responses) ─ x_search tool ─┐
MCP Client <-> MCP Server ┤                                                            ├─> X (Twitter) data
        (stdio)           └─ (xurl) xurl CLI ─ X API v2 (/2/tweets/search/recent 等) ──┘
```

- **xAI backend**: xAI の **Responses API** と **x_search サーバーサイドツール**を使用。Grok がサーバーサイドで自律的に X を検索・分析し、結果を返すエージェンティックな仕組みです。旧 Live Search API (`search_parameters`) は 2026年1月に廃止されたため、新しい Agent Tools API を使用しています。
- **xurl backend**: 公式 `xurl` CLI 経由で認証済みの X API v2 エンドポイント（`/2/tweets/search/recent`, `/2/users/:id/tweets` 等）を直接呼び出し、生のポストを取得します。アダプタは `xurl_client.py` に実装されています。

## モデル

`x_search` サーバーサイドツールは **grok-4 系モデルのみ**で利用可能です。

| モデル | 特徴 |
|---|---|
| `grok-4-1-fast` | ツール呼び出し最適化・高速（**デフォルト**） |
| `grok-4-1-fast-reasoning` | 推論付き・より高精度 |

モデルを変更する場合は `x_search_mcp.py` 内の `XAI_MODEL` 定数を編集してください。

> **注意**: `grok-3` 系モデルでは x_search ツールは利用できません（400 エラーになります）。

## トラブルシューティング

| エラー | 原因 | 対処 |
|---|---|---|
| `Failed to spawn process: No such file or directory` | Python パスが間違っている | `.venv/bin/python3` のフルパスを `command` に指定 |
| `status 400: model not supported` | grok-3 系モデルを使用 | `XAI_MODEL` を `grok-4-1-fast` に変更（デフォルトで設定済み） |
| `status 401` | API キーが無効 | `XAI_API_KEY` を確認 |
| `status 410: Live search is deprecated` | 旧 API を使用 | 最新版に更新（`git pull`） |
| `{"error": "xurl is not authenticated...", "source": "xurl"}` | `X_SEARCH_BACKEND=xurl` だが xurl 未認証 | `xurl auth` で認証する、または `X_SEARCH_BACKEND=xai` に変更 |
| `{"error": "...HTTP 429...", "source": "xurl"}` | xurl のレート制限 | 時間をおいて再試行（429 は内部でバックオフ再試行済み） |

`x_auth_status` ツールを呼ぶと、現在有効な backend と xurl の認証状態を確認できます。

Claude Desktop の場合、ログは以下で確認できます：

```bash
# macOS
cat ~/Library/Logs/Claude/mcp-server-x_search.log
```

## 料金

xAI API の利用料金が発生します。詳細は [xAI Pricing](https://docs.x.ai/developers/models) を参照してください。

## ライセンス

MIT
