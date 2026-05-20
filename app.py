import re
from dataclasses import dataclass
from typing import Any

import pandas as pd
import streamlit as st


CSV_URL = "https://docs.google.com/spreadsheets/d/1T2-wAn_MW66wyBnng5dH8BG5ZHf13Qvr/export?format=csv&gid=997481158"


@dataclass(frozen=True)
class MetricSpec:
    label: str
    aliases: tuple[str, ...]
    unit: str = ""
    decimals: int = 0


CURRENT_METRICS = [
    MetricSpec("人口", ("人口", "総人口"), "人"),
    MetricSpec("65歳以上人口", ("65歳以上人口", "高齢者人口"), "人"),
    MetricSpec("総面積", ("総面積", "総面積(k㎡)", "総面積(km2)"), "km2", 2),
    MetricSpec("可住地面積", ("可住地面積", "可住地面積(k㎡)", "可住地面積(km2)"), "km2", 2),
    MetricSpec("人口密度", ("人口密度", "可住地人口密度"), "人/km2", 1),
    MetricSpec("高齢者可住地密度", ("高齢者可住地密度", "高齢者可住地密度(人/k㎡)"), "人/km2", 1),
    MetricSpec("訪問介護事業所数", ("訪問介護事業所数",), "事業所"),
    
]

POST_ENTRY_METRICS = [

]


st.set_page_config(
    page_title="訪問介護市場分析",
    page_icon="📈",
    layout="wide",
)


def normalize_key(value: Any) -> str:
    return (
        str(value)
        .strip()
        .lower()
        .replace("　", "")
        .replace(" ", "")
        .replace("_", "")
        .replace("-", "")
        .replace("／", "/")
        .replace("（", "")
        .replace("）", "")
        .replace("(", "")
        .replace(")", "")
        .replace("㎢", "")
        .replace("㎡", "")
        .replace("平方キロメートル", "")
    )


def parse_number(value: Any) -> float | None:
    if value is None or pd.isna(value):
        return None

    if isinstance(value, (int, float)):
        return float(value)

    text = str(value).strip().replace(",", "")
    if not text:
        return None

    match = re.search(r"-?\d+(?:\.\d+)?", text)
    if not match:
        return None

    return float(match.group(0))


def format_value(value: Any, spec: MetricSpec) -> str:
    number = parse_number(value)

    if number is None:
        if value is None or str(value).strip() == "":
            return "-"
        return str(value)

    if spec.decimals == 0:
        formatted = f"{number:,.0f}"
    else:
        formatted = f"{number:,.{spec.decimals}f}"

    return f"{formatted} {spec.unit}".strip()


@st.cache_data(ttl=600, show_spinner=False)
def load_data(csv_url: str) -> pd.DataFrame:
    df = pd.read_csv(csv_url)
    df.columns = [str(column).strip() for column in df.columns]
    return df


def find_name_column(df: pd.DataFrame) -> str | None:
    candidates = [
        "市町村名",
        "市区町村名",
        "自治体名",
        "市町村",
        "市区町村",
        "municipality",
        "name",
    ]

    normalized_columns = {normalize_key(column): column for column in df.columns}

    for candidate in candidates:
        column = normalized_columns.get(normalize_key(candidate))
        if column:
            return column

    for column in df.columns:
        column_text = str(column)
        if "市町村" in column_text or "市区町村" in column_text or "自治体" in column_text:
            return column

    return None


def search_municipality(df: pd.DataFrame, query: str) -> pd.DataFrame:
    name_column = find_name_column(df)

    if name_column is None or not query.strip():
        return pd.DataFrame()

    normalized_query = query.strip().replace("　", " ").lower()
    names = (
        df[name_column]
        .astype(str)
        .str.strip()
        .str.replace("　", " ", regex=False)
        .str.lower()
    )

    exact_matches = df[names == normalized_query]
    if not exact_matches.empty:
        return exact_matches

    return df[names.str.contains(re.escape(normalized_query), na=False)]


def make_column_map(df: pd.DataFrame) -> dict[str, str]:
    return {normalize_key(column): column for column in df.columns}


def get_metric_raw_value(row: pd.Series, columns: dict[str, str], spec: MetricSpec) -> Any:
    for alias in (spec.label, *spec.aliases):
        normalized_alias = normalize_key(alias)

        exact_column = columns.get(normalized_alias)
        if exact_column is not None:
            return row.get(exact_column)

        if len(normalized_alias) >= 5:
            for normalized_column, original_column in columns.items():
                if normalized_alias in normalized_column:
                    return row.get(original_column)

    return None


def collect_metrics(row: pd.Series, df: pd.DataFrame, metric_specs: list[MetricSpec]) -> list[dict[str, Any]]:
    columns = make_column_map(df)
    metrics = []

    for spec in metric_specs:
        raw_value = get_metric_raw_value(row, columns, spec)
        metrics.append(
            {
                "指標": spec.label,
                "値": format_value(raw_value, spec),
                "数値": parse_number(raw_value),
                "単位": spec.unit,
            }
        )

    return metrics


def metric_number(metrics: list[dict[str, Any]], label: str) -> float | None:
    for metric in metrics:
        if metric["指標"] == label:
            return metric["数値"]
    return None


def create_market_comment(metrics: list[dict[str, Any]]) -> tuple[str, list[str]]:
    comments = []
    score = 0

    capacity_ratio = metric_number(metrics, "達成余力倍率")
    post_entry_ratio = metric_number(metrics, "参入後達成余力倍率")
    elderly_density = metric_number(metrics, "高齢者可住地密度")
    competitors = metric_number(metrics, "実質競合数")
    population_density = metric_number(metrics, "人口密度")

    if capacity_ratio is None:
        comments.append("達成余力倍率が確認できないため、収益余力の判断には追加確認が必要です。")
    elif capacity_ratio >= 2:
        score += 2
        comments.append("達成余力倍率が2以上であり、250万円の安定運営ラインに対して有望な水準です。")
    else:
        score -= 1
        comments.append("達成余力倍率が2未満のため、250万円達成には慎重な利用者獲得計画が必要です。")

    if post_entry_ratio is None:
        comments.append("参入後達成余力倍率が確認できないため、参入後の需要余力は別途確認してください。")
    elif post_entry_ratio >= 2:
        score += 1
        comments.append("参入後達成余力倍率も2以上で、参入後も一定の市場余力が残る見立てです。")
    else:
        score -= 1
        comments.append("参入後達成余力倍率が2未満で、参入後の競争影響を慎重に見る必要があります。")

    if elderly_density is None:
        comments.append("高齢者可住地密度が確認できないため、移動効率の評価には追加データが必要です。")
    elif elderly_density < 80:
        score -= 1
        comments.append("高齢者可住地密度が80未満のため、移動効率や訪問ルート設計に注意が必要です。")
    else:
        score += 1
        comments.append("高齢者可住地密度が80以上で、訪問効率の面では一定のまとまりが期待できます。")

    if competitors is None:
        comments.append("実質競合数が確認できないため、競争環境の判断には注意が必要です。")
    elif competitors >= 5:
        score -= 1
        comments.append("実質競合数が多く、都市部競争地域では営業難易度が高くなる可能性があります。")
    elif competitors <= 2:
        score += 1
        comments.append("実質競合数が少なく、地方供給不足地域であればシフト調整しやすい可能性があります。")
    else:
        comments.append("実質競合数は中程度で、サービス品質や営業力による差別化が重要です。")

    if population_density is not None and competitors is not None:
        if population_density >= 1000 and competitors >= 5:
            comments.append("人口密度と競合数がともに高く、都市部型の営業戦略が求められます。")
        elif population_density < 300 and elderly_density is not None and elderly_density < 80:
            comments.append("人口密度が低く高齢者可住地密度も低いため、移動時間の管理が重要です。")

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

st.caption(
    "Googleスプレッドシートの公開CSVを読み込み、市町村ごとの訪問介護市場データと簡易コメントを表示します。"
)

with st.sidebar:
    st.header("データ設定")
    csv_url = st.text_input("Googleスプレッドシート公開CSV URL", value=CSV_URL)
    reload_button = st.button("CSVを再読み込み")

    st.divider()

    st.header("判定の考え方")
    st.write("- 達成余力倍率2以上を有望ライン")
    st.write("- 高齢者可住地密度80未満は移動効率注意")
    st.write("- 都市部競争地域は営業難易度高")
    st.write("- 地方供給不足地域はシフト調整しやすい")
    st.write("- 250万円を安定運営ラインとする")

if reload_button:
    st.cache_data.clear()

try:
    df = load_data(csv_url)
except Exception as exc:
    st.error(f"CSVの読み込みに失敗しました: {exc}")
    st.stop()

name_column = find_name_column(df)

if name_column is None:
    st.error("市町村名に該当する列が見つかりません。")
    st.write("列名に「市町村名」「市区町村名」「自治体名」などを含めてください。")
    st.write("読み込んだ列名:")
    st.write(list(df.columns))
    st.stop()

municipality_query = st.text_input("市町村名を入力", placeholder="例: 横浜市")
search_button = st.button("検索して市場分析を表示", type="primary")

if not municipality_query:
    st.info("市町村名を入力して検索してください。")

    with st.expander("読み込んだデータの先頭5行"):
        st.dataframe(df.head(), use_container_width=True)

    st.stop()

matches = search_municipality(df, municipality_query)

if matches.empty:
    st.warning("該当する市町村データが見つかりませんでした。")
    st.stop()

display_names = [
    f"{index}: {row.get(name_column, '名称不明')}"
    for index, row in matches.iterrows()
]

selected_label = st.selectbox("該当データ", display_names)
selected_index = int(selected_label.split(":", 1)[0])
selected_row = matches.loc[selected_index]
municipality_name = str(selected_row.get(name_column, municipality_query))

current_metrics = collect_metrics(selected_row, df, CURRENT_METRICS)
post_entry_metrics = collect_metrics(selected_row, df, POST_ENTRY_METRICS)

# 不足している指標をアプリ側で計算
elderly = metric_number(current_metrics, "65歳以上人口")
competitors = metric_number(current_metrics, "実質競合数")

if competitors is None or competitors == 0:
    for keyword in ["採用する実質競合数", "競合度4以上", "全国版", "実質競合", "競合"]:
        for column_name in selected_row.index:
            if keyword in str(column_name):
                value = parse_number(selected_row.get(column_name))
                if value is not None and value > 0:
                    competitors = value
                    break
        if competitors is not None and competitors > 0:
            break
                
offices = metric_number(current_metrics, "訪問介護事業所数")

estimated_users = elderly * 0.2 * 0.2 if elderly is not None else None
needed_users = 2500000 / 40000

users_per_competitor = (
    estimated_users / competitors
    if estimated_users is not None and competitors not in (None, 0)
    else None
)

capacity_ratio = (
    users_per_competitor / needed_users
    if users_per_competitor is not None
    else None
)

post_competitors = competitors + 1 if competitors is not None else None
post_offices = offices + 1 if offices is not None else None

post_users_per_competitor = (
    estimated_users / post_competitors
    if estimated_users is not None and post_competitors not in (None, 0)
    else None
)

post_capacity_ratio = (
    post_users_per_competitor / needed_users
    if post_users_per_competitor is not None
    else None
)

current_metrics.extend([
    {"指標": "実質競合数", "値": f"{competitors:,.1f} 事業所" if competitors is not None else "-", "数値": competitors, "単位": "事業所"},

    {"指標": "推定訪問介護利用者数", "値": f"{estimated_users:,.0f} 人" if estimated_users is not None else "-", "数値": estimated_users, "単位": "人"},

    {"指標": "1事業所あたり潜在利用者数", "値": f"{users_per_competitor:,.1f} 人/事業所" if users_per_competitor is not None else "-", "数値": users_per_competitor, "単位": "人/事業所"},

    {"指標": "250万円達成必要人数", "値": f"{needed_users:,.1f} 人", "数値": needed_users, "単位": "人"},

    {"指標": "達成余力倍率", "値": f"{capacity_ratio:,.2f} 倍" if capacity_ratio is not None else "-", "数値": capacity_ratio, "単位": "倍"},
])
post_entry_metrics.extend([
    {"指標": "参入後事業所数", "値": f"{post_offices:,.0f} 事業所" if post_offices is not None else "-", "数値": post_offices, "単位": "事業所"},
    {"指標": "参入後実質競合数", "値": f"{post_competitors:,.1f} 事業所" if post_competitors is not None else "-", "数値": post_competitors, "単位": "事業所"},
    {"指標": "参入後1事業所市場", "値": f"{post_users_per_competitor:,.1f} 人/事業所" if post_users_per_competitor is not None else "-", "数値": post_users_per_competitor, "単位": "人/事業所"},
    {"指標": "参入後達成余力倍率", "値": f"{post_capacity_ratio:,.2f} 倍" if post_capacity_ratio is not None else "-", "数値": post_capacity_ratio, "単位": "倍"},
])
headline, comments = create_market_comment(current_metrics + post_entry_metrics)

st.success(f"市場判定: {headline}")



st.subheader("現状の市場指標")





st.subheader("現状の市場指標")
st.dataframe(
    pd.DataFrame(current_metrics)[["指標", "値"]],
    use_container_width=True,
    hide_index=True,
)

st.markdown(
    """
    <div style="
        background-color:#e8f4ff;
        padding:20px;
        border-radius:10px;
    ">
    <h3>新規参入後シミュレーション</h3>
    """,
    unsafe_allow_html=True
)

st.dataframe(
    pd.DataFrame(post_entry_metrics)[["指標", "値"]],
    use_container_width=True,
    hide_index=True,
)

st.markdown("</div>", unsafe_allow_html=True)

st.subheader("市場分析コメント")

for comment in comments:
    st.write(f"- {comment}")

download_text = (
    f"# {municipality_name} 訪問介護市場分析\n\n"
    f"## 市場判定\n{headline}\n\n"
    f"## 主要指標\n{metrics_to_markdown(all_metrics)}\n\n"
    "## 市場分析コメント\n"
    + "\n".join(f"- {comment}" for comment in comments)
    + "\n"
)

st.download_button(
    "分析結果をMarkdownでダウンロード",
    download_text,
    file_name=f"{municipality_name}_訪問介護市場分析.md",
    mime="text/markdown",
)
