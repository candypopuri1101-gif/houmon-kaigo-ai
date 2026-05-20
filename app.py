    competitors = metric_number(metrics, "実質競合数")
    population_density = metric_number(metrics, "人口密度")
    potential_users = metric_number(metrics, "1事業所あたり潜在利用者数")

    score = 0

    if capacity_ratio is None:
        comments.append("達成余力倍率が未取得のため、有望度は補助指標とあわせて確認してください。")
    elif capacity_ratio >= 2:
        score += 2
        comments.append("達成余力倍率が2以上で、250万円の安定運営ラインに対して有望水準です。")
    else:
        score -= 1
        comments.append("達成余力倍率が2未満で、250万円達成には慎重な利用者獲得計画が必要です。")

    if post_entry_ratio is not None:
        if post_entry_ratio >= 2:
            score += 1
            comments.append("参入後達成余力倍率も2以上で、参入後も一定の需要余力が残る見立てです。")
        else:
            score -= 1
            comments.append("参入後達成余力倍率が2未満で、参入後の競争影響を強めに見る必要があります。")

    if elderly_density is not None:
        if elderly_density < 80:
            score -= 1
            comments.append("高齢者可住地密度が80未満のため、移動効率と訪問ルート設計に注意が必要です。")
        else:
            score += 1
            comments.append("高齢者可住地密度は80以上で、訪問効率の面では一定のまとまりが期待できます。")

    if competitors is not None:
        if competitors >= 5:
            score -= 1
            comments.append("実質競合数が多く、都市部競争地域では営業難易度が高くなる可能性があります。")
        elif competitors <= 2:
            score += 1
            comments.append("実質競合数が少なく、地方供給不足地域であればシフト調整しやすい可能性があります。")
        else:
            comments.append("実質競合数は中程度で、競争環境は個別事業所のサービス品質に左右されます。")

    if population_density is not None and population_density >= 1_000 and competitors is not None and competitors >= 5:
        comments.append("人口密度と競合数の両方が高く、都市部型の営業・差別化戦略が重要です。")

    if potential_users is not None and potential_users >= 30:
        score += 1
        comments.append("1事業所あたり潜在利用者数は一定以上あり、利用者獲得余地が見込めます。")

    if score >= 3:
        headline = "有望"
    elif score >= 1:
        headline = "条件付き有望"
    elif score == 0:
        headline = "中立"
    else:
        headline = "慎重検討"

    return headline, comments


def metrics_to_markdown(metrics: list[dict[str, Any]]) -> str:
    return "\n".join(f"- {metric['指標']}: {metric['値']}" for metric in metrics)


st.title("訪問介護市場分析")
st.caption("Googleスプレッドシートの公開CSVを読み込み、市町村ごとの市場指標と簡易判定を表示します。")

with st.sidebar:
    st.header("データ設定")
    csv_url = st.text_input("公開CSV URL", value=CSV_URL)
    reload_data = st.button("CSVを再読み込み")

    st.divider()
    st.write("判定ルール")
    st.write("- 達成余力倍率2以上を有望ライン")
    st.write("- 高齢者可住地密度80未満は移動効率注意")
    st.write("- 都市部競争地域は営業難易度高")
    st.write("- 地方供給不足地域はシフト調整しやすい")
    st.write("- 250万円を安定運営ラインとする")

if reload_data:
    st.cache_data.clear()

try:
    df = load_data(csv_url)
except Exception as exc:
    st.error(f"CSVの読み込みに失敗しました: {exc}")
    st.stop()

name_column = find_name_column(df)
if name_column is None:
    st.error("市町村名に該当する列が見つかりません。列名に「市町村名」「市区町村名」「自治体名」などを含めてください。")
    st.write("読み込んだ列名:")
    st.write(list(df.columns))
    st.stop()

municipality_query = st.text_input("市町村名を入力", placeholder="例: 横浜市")
search_button = st.button("検索して市場分析を表示", type="primary")

if not municipality_query and not search_button:
    st.info("市町村名を入力して検索してください。")
    with st.expander("読み込んだデータの先頭5行"):
        st.dataframe(df.head(), use_container_width=True)
    st.stop()

if not municipality_query:
    st.warning("市町村名を入力してください。")
    st.stop()

matches = search_municipality(df, municipality_query)
if matches.empty:
    st.warning("該当する市町村データが見つかりませんでした。")
    st.stop()

display_names = [f"{index}: {row.get(name_column, '名称不明')}" for index, row in matches.iterrows()]
selected_label = st.selectbox("該当データ", display_names)
selected_index = int(selected_label.split(":", 1)[0])
selected_row = matches.loc[selected_index]
municipality_name = str(selected_row.get(name_column, municipality_query))

metrics = collect_metrics(selected_row, df)
headline, comments = judge_market(metrics)

st.subheader(f"{municipality_name} の市場分析")
st.success(f"簡易市場判定: {headline}")

metric_columns = st.columns(3)
for index, metric in enumerate(metrics):
    with metric_columns[index % 3]:
        st.metric(metric["指標"], metric["値"])

st.subheader("指標一覧")
st.dataframe(
    pd.DataFrame(metrics)[["指標", "値"]],
    use_container_width=True,
    hide_index=True,
)

st.subheader("簡易市場判定コメント")
for comment in comments:
    st.write(f"- {comment}")

st.subheader("取得した元データ")
st.dataframe(
    pd.DataFrame([selected_row]),
    use_container_width=True,
    hide_index=True,
)

download_text = (
    f"# {municipality_name} 訪問介護市場分析\n\n"
    f"## 簡易市場判定\n{headline}\n\n"
    f"## 指標\n{metrics_to_markdown(metrics)}\n\n"
    "## コメント\n"
    + "\n".join(f"- {comment}" for comment in comments)
    + "\n"
)

st.download_button(
    "分析結果をMarkdownでダウンロード",
    download_text,
    file_name=f"{municipality_name}_訪問介護市場分析.md",
    mime="text/markdown",
)
