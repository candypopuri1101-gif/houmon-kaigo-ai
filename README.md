# 訪問介護市場分析 Streamlit アプリ

Googleスプレッドシートの `市町村データ` シートを読み込み、市町村名に一致する行データをもとに、訪問介護市場の主要指標とAIコメントを表示するアプリです。

## セットアップ

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

`.env` を編集して、少なくとも次を設定してください。

```dotenv
OPENAI_API_KEY=sk-...
GOOGLE_SPREADSHEET_ID=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
GOOGLE_WORKSHEET_NAME=市町村データ
GOOGLE_APPLICATION_CREDENTIALS=C:\path\to\service-account.json
```

Google Sheets はサービスアカウントで読み込みます。対象スプレッドシートをサービスアカウントの `client_email` に閲覧権限で共有してください。

Streamlit Cloud などで使う場合は、`.streamlit/secrets.toml.example` を参考に secrets を設定できます。ローカルでは画面のサイドバーからサービスアカウントJSONをアップロードして使うこともできます。

## 起動

```powershell
streamlit run app.py
```

ブラウザで表示された画面から、市町村名を入力して `市場分析を表示` を押してください。

OpenAI APIキーを設定している場合は、取得した指標と一次判定をもとに `AIコメントを生成` できます。

## シート形式

1行目をヘッダーとして扱います。市町村名の列は次のような列名を自動検出します。

- `市町村名`
- `市区町村名`
- `自治体名`
- `市町村`
- `市区町村`

## 表示する指標

次の列名、または近い列名を自動検出します。

- 人口
- 65歳以上人口
- 総面積
- 可住地面積
- 人口密度
- 高齢者可住地密度
- 訪問介護事業所数
- 実質競合数
- 推定訪問介護利用者数
- 1事業所あたり潜在利用者数
- 250万円達成必要人数
- 達成余力倍率
- 参入後達成余力倍率

`人口密度` は `人口 / 総面積`、`高齢者可住地密度` は `65歳以上人口 / 可住地面積` で補完できます。その他の採算系指標は前提条件が必要なため、シート上の値を優先します。

## AIコメントの考え方

AIコメントは、次のルールをプロンプトに含めて生成します。

- 達成余力倍率2以上を有望ライン
- 高齢者可住地密度80未満は移動効率注意
- 都市部競争地域は営業難易度高
- 地方供給不足地域はシフト調整しやすい
- 250万円を安定運営ラインとする
