import html
import math
import re
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any

import pandas as pd
import streamlit as st


CSV_URL = "https://docs.google.com/spreadsheets/d/1T2-wAn_MW66wyBnng5dH8BG5ZHf13Qvr/export?format=csv&gid=997481158"
BASE_REVENUE_PER_USER = 40_000
ESTIMATED_HOME_CARE_USER_RATE = 0.08
ESTIMATED_HOME_CARE_USER_RATE_LABEL = f"{ESTIMATED_HOME_CARE_USER_RATE * 100:g}％"
ESTIMATED_HOME_CARE_USER_RATE_SOURCE_LABEL = f"{ESTIMATED_HOME_CARE_USER_RATE * 100:g}%"
TARGET_MONTHLY_REVENUE = 2_500_000
BASE_REVENUE_NOTE = (
    "利用者1人あたり売上は、地域区分・特定事業所加算を反映しない"
    f"保守的な基準値として{BASE_REVENUE_PER_USER:,}円/月で計算しています。"
)
ESTIMATED_USERS_NOTE = (
    f"訪問介護利用者数は、65歳以上人口の{ESTIMATED_HOME_CARE_USER_RATE_LABEL}を仮の推定値として計算しています。"
    "実際の利用者数とは異なる可能性があります。"
)
DATA_QUALITY_NOTE_PARAGRAPHS = [
    "本診断で使用している訪問介護事業所数・サ高住系事業所数などは、情報公表システム等を参考にした近似値・参考値です。",
    "休止事業所・外部対応消極事業所・サ高住内専用事業所などが含まれる可能性があります。",
    "そのため、絶対的な実数ではなく、市場構造・競争傾向・地域特性を把握するための参考指標としてご利用ください。",
]

REQUIRED_USER_REVENUE_LINES = {
    "minimum_line": 1_200_000,
    "stable_line": 2_000_000,
    "family_stable_line": 2_500_000,
    "high_return_line": 3_000_000,
}

REQUIRED_USER_REGION_MULTIPLIERS = {
    "地方都市型": 0.92,
    "供給不足型過疎地": 0.95,
    "超過疎地型": 0.75,
    "大都市型": 1.15,
    "超高密集競争型": 1.25,
}

REFERENCE_REGION_TYPES = {
    "松江市": "地方都市型",
    "安来市": "供給不足型過疎地",
    "美郷町": "超過疎地型",
    "西宮市": "大都市型",
    "高石市": "超高密集競争型",
}

DESIGNATED_CITY_WARDS = {
    "札幌市": ["中央区", "北区", "東区", "白石区", "豊平区", "南区", "西区", "厚別区", "手稲区", "清田区"],
    "仙台市": ["青葉区", "宮城野区", "若林区", "太白区", "泉区"],
    "さいたま市": ["西区", "北区", "大宮区", "見沼区", "中央区", "桜区", "浦和区", "南区", "緑区", "岩槻区"],
    "千葉市": ["中央区", "花見川区", "稲毛区", "若葉区", "緑区", "美浜区"],
    "横浜市": ["鶴見区", "神奈川区", "西区", "中区", "南区", "保土ケ谷区", "磯子区", "金沢区", "港北区", "戸塚区", "港南区", "旭区", "緑区", "瀬谷区", "栄区", "泉区", "青葉区", "都筑区"],
    "川崎市": ["川崎区", "幸区", "中原区", "高津区", "多摩区", "宮前区", "麻生区"],
    "相模原市": ["緑区", "中央区", "南区"],
    "新潟市": ["北区", "東区", "中央区", "江南区", "秋葉区", "南区", "西区", "西蒲区"],
    "静岡市": ["葵区", "駿河区", "清水区"],
    "浜松市": ["中央区", "浜名区", "天竜区"],
    "名古屋市": ["千種区", "東区", "北区", "西区", "中村区", "中区", "昭和区", "瑞穂区", "熱田区", "中川区", "港区", "南区", "守山区", "緑区", "名東区", "天白区"],
    "京都市": ["北区", "上京区", "左京区", "中京区", "東山区", "下京区", "南区", "右京区", "伏見区", "山科区", "西京区"],
    "大阪市": ["都島区", "福島区", "此花区", "西区", "港区", "大正区", "天王寺区", "浪速区", "西淀川区", "東淀川区", "東成区", "生野区", "旭区", "城東区", "阿倍野区", "住吉区", "東住吉区", "西成区", "淀川区", "鶴見区", "住之江区", "平野区", "北区", "中央区"],
    "堺市": ["堺区", "中区", "東区", "西区", "南区", "北区", "美原区"],
    "神戸市": ["東灘区", "灘区", "兵庫区", "長田区", "須磨区", "垂水区", "北区", "中央区", "西区"],
    "岡山市": ["北区", "中区", "東区", "南区"],
    "広島市": ["中区", "東区", "南区", "西区", "安佐南区", "安佐北区", "安芸区", "佐伯区"],
    "北九州市": ["門司区", "若松区", "戸畑区", "小倉北区", "小倉南区", "八幡東区", "八幡西区"],
    "福岡市": ["東区", "博多区", "中央区", "南区", "西区", "城南区", "早良区"],
    "熊本市": ["中央区", "東区", "西区", "南区", "北区"],
}

def calculate_effective_revenue_per_user(metrics: list[dict[str, Any]] | None = None) -> int:
    """
    将来拡張用:
    現在は地域区分・特定事業所加算を反映せず、
    保守的な基準値である BASE_REVENUE_PER_USER をそのまま返す。
    """
    return BASE_REVENUE_PER_USER


@dataclass(frozen=True)
class MetricSpec:
    label: str
    aliases: tuple[str, ...]
    unit: str = ""
    decimals: int = 0


METRICS = [
    MetricSpec("人口", ("人口", "総人口", "総人口数"), "人"),
    MetricSpec("高齢者人口", ("高齢者人口", "65歳以上人口", "65歳以上", "老年人口"), "人"),
    MetricSpec("総面積", ("総面積", "面積", "総面積km2", "総面積_km2", "総面積(k㎡)", "総面積(km2)"), "km2", 2),
    MetricSpec("可住地面積", ("可住地面積", "可住面積", "可住地面積km2", "可住地面積（km2）", "可住地面積(km2)", "可住地面積(k㎡)"), "km2", 2),
    MetricSpec("人口密度", ("人口密度", "総人口密度", "人口密度(人/k㎡)", "人口密度(人/km2)"), "人/km2", 1),
    MetricSpec(
        "高齢者可住地密度",
        ("高齢者可住地密度", "65歳以上可住地密度", "高齢者密度", "高齢者人口密度"),
        "人/km2",
        1,
    ),
    MetricSpec("実質競合数", ("実質競合数", "競合数", "実質競合事業所数", "全国版_実質競合推定", "競合度4以上", "競合度5"), "事業所", 1),
    MetricSpec(
        "従来型訪問介護事業所数",
        (
            "従来型訪問介護事業所数",
            "従来型事業所数",
            "訪問介護事業所数",
            "訪問介護",
            "居宅サービス_訪問介護",
            "事業所数_訪問介護",
        ),
        "事業所",
    ),
    MetricSpec(
        "サ高住系事業所数",
        (
            "サ高住系事業所数",
            "住宅型有料・サ高住系事業所数",
            "サ高住系競合",
            "サ高住競合",
            "サ高住数",
            "定員あり事業所数",
            "サービス付き高齢者向け住宅",
            "サ高住",
        ),
        "件",
        1,
    ),
    MetricSpec(
        "訪問介護利用者数",
        ("訪問介護利用者数", "実訪問介護利用者数", "実利用者数", "訪問介護実利用者数"),
        "人",
    ),
    MetricSpec("1競合あたり潜在利用者", ("1競合あたり潜在利用者", "一競合あたり潜在利用者", "競合あたり潜在利用者"), "人/競合", 1),
    MetricSpec("市場規模", ("市場規模", "推定市場規模", "市場規模人数", "潜在市場規模"), "万円/月", 1),
    MetricSpec("理論市場余力倍率", ("理論市場余力倍率", "達成余力倍率", "余力倍率"), "倍", 2),
    MetricSpec("競争後達成余力倍率", ("競争後達成余力倍率", "競争後余力倍率", "競合後達成余力倍率"), "倍", 2),
    MetricSpec("参入後達成余力倍率", ("参入後達成余力倍率", "参入後余力倍率"), "倍", 2),
    MetricSpec(
        "訪問介護事業所数",
        ("訪問介護事業所数", "訪問介護事業者数", "訪問介護", "居宅サービス_訪問介護", "事業所数_訪問介護", "事業所数"),
        "事業所",
    ),
    MetricSpec(
        "推定訪問介護利用者数",
        ("推定訪問介護利用者数", "推定利用者数", "推計訪問介護利用者数", "推計利用者数"),
        "人",
    ),
    MetricSpec(
        "1事業所あたり潜在利用者数",
        ("1事業所あたり潜在利用者数", "一事業所あたり潜在利用者数", "事業所あたり潜在利用者数"),
        "人/事業所",
        1,
    ),
MetricSpec("250万円達成必要人数", ("250万円達成必要人数", "250万達成必要人数", "月商250万円達成必要人数"), "人"),
]

METRIC_SPECS_BY_LABEL = {spec.label: spec for spec in METRICS}


REGION_CLASSIFICATION_CONFIG = {
    "super_sparse": {
        "max_users": 60,
        "max_market_size": 2_500_000,
        "max_elderly_population": 3_000,
        "max_capacity_ratio": 1.6,
    },
    "supply_shortage_sparse": {
        "min_habitable_area": 80,
        "min_users_per_office": 40,
        "max_effective_competitors": 2,
    },
    "local_city": {
        "min_elderly_density": 700,
        "max_elderly_density": 1500,
    },
    "large_city": {
        "min_elderly_density": 200,
        "min_market_size": 10_000_000,
        "min_effective_competitors": 5,
    },
    "dense_competitive": {
        "max_habitable_area": 15,
        "max_users_per_office": 25,
        "min_effective_competitors": 6,
        "max_capacity_ratio": 2,
    },
    "sakoju": {
        "cover_area_per_facility": 0.785,
        "weak_threshold": 0.10,
        "medium_threshold": 0.30,
        "competition_weights": {
            "地方都市型": 0.20,
            "大都市型": 0.30,
            "供給不足型過疎地": 0.50,
            "超過疎地型": 0.25,
            "超高密集競争型": 0.65,
            "判定保留": 0.30,
        },
    },
}


st.set_page_config(
    page_title="訪問介護市場分析",
    page_icon="📈",
    layout="wide",
)

st.markdown(
    """
    <style>
    .diagnosis-card {
        background-color: #f4f6f8;
        color: #111827;
        border: 1px solid #d7dde5;
        border-radius: 10px;
        padding: 1rem;
        margin: 0.75rem 0 1rem;
        box-shadow: 0 1px 2px rgba(17, 24, 39, 0.08);
    }
    .diagnosis-card h3,
    .diagnosis-card h4,
    .diagnosis-card p {
        color: inherit;
    }
    .diagnosis-card h3 {
        margin: 0 0 0.85rem;
        font-size: 1.15rem;
        line-height: 1.35;
    }
    .summary-grid {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
        gap: 0.7rem;
    }
    .summary-item {
        background-color: #ffffff;
        color: #111827;
        border: 1px solid #d8dee8;
        border-radius: 8px;
        padding: 0.7rem 0.75rem;
    }
    .summary-label {
        color: #4b5563;
        font-size: 0.8rem;
        font-weight: 700;
        margin-bottom: 0.25rem;
    }
    .summary-value {
        color: #111827;
        font-size: 0.98rem;
        font-weight: 700;
        line-height: 1.45;
        overflow-wrap: anywhere;
    }
    .summary-comment {
        background-color: #fff7ed;
        color: #3f2a12;
        border: 1px solid #d6a45d;
        border-radius: 8px;
        padding: 0.85rem;
        margin-top: 0.8rem;
        line-height: 1.65;
    }
    .section-card-title {
        border-radius: 8px;
        padding: 0.65rem 0.85rem;
        margin: 0 0 0.75rem;
        font-weight: 800;
        line-height: 1.4;
    }
    .tone-good {
        background-color: #e7f3e8;
        color: #123524;
        border: 1px solid #6da879;
    }
    .tone-warning {
        background-color: #f7eddc;
        color: #3f2a12;
        border: 1px solid #bd8b42;
    }
    .tone-danger {
        background-color: #f6e4df;
        color: #4a1f17;
        border: 1px solid #b66a58;
    }
    .tone-info {
        background-color: #eef1f5;
        color: #172033;
        border: 1px solid #9aa6b2;
    }
    .compact-card {
        background-color: #f8fafc;
        color: #111827;
        border: 1px solid #d7dde5;
        border-radius: 9px;
        padding: 0.9rem 1rem;
        margin: 0.75rem 0;
    }
    .compact-card-title {
        color: #374151;
        font-size: 0.85rem;
        font-weight: 800;
        margin-bottom: 0.35rem;
    }
    .compact-card-value {
        color: #111827;
        font-size: 1.08rem;
        font-weight: 800;
        line-height: 1.5;
        overflow-wrap: anywhere;
    }
    .compact-card.tone-good {
        background-color: #e7f3e8;
        color: #123524;
        border-color: #6da879;
    }
    .compact-card.tone-warning {
        background-color: #f7eddc;
        color: #3f2a12;
        border-color: #bd8b42;
    }
    .compact-card.tone-danger {
        background-color: #f6e4df;
        color: #4a1f17;
        border-color: #b66a58;
    }
    .compact-card.tone-info {
        background-color: #eef1f5;
        color: #172033;
        border-color: #9aa6b2;
    }
    .compact-card.tone-good .compact-card-title,
    .compact-card.tone-good .compact-card-value,
    .compact-card.tone-warning .compact-card-title,
    .compact-card.tone-warning .compact-card-value,
    .compact-card.tone-danger .compact-card-title,
    .compact-card.tone-danger .compact-card-value,
    .compact-card.tone-info .compact-card-title,
    .compact-card.tone-info .compact-card-value {
        color: inherit;
    }
    @media (max-width: 640px) {
        .diagnosis-card {
            padding: 0.85rem;
            border-radius: 8px;
        }
        .summary-grid {
            grid-template-columns: 1fr;
        }
        .summary-value {
            font-size: 0.95rem;
        }
    }
    </style>
    """,
    unsafe_allow_html=True,
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
        return "-" if value is None or str(value).strip() == "" else str(value)

    if spec.label == "市場規模":
        return f"{number / 10_000:,.1f} 万円/月"

    formatted = f"{number:,.{spec.decimals}f}"
    if spec.decimals == 0:
        formatted = f"{number:,.0f}"
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
    names = df[name_column].astype(str).str.strip().str.replace("　", " ", regex=False).str.lower()
    display_names = build_search_display_names(df, name_column).str.lower()

    exact_matches = df[(names == normalized_query) | (display_names == normalized_query)]
    if not exact_matches.empty and normalized_query not in [city.lower() for city in DESIGNATED_CITY_WARDS]:
        return exact_matches

    return df[
        names.str.contains(re.escape(normalized_query), na=False)
        | display_names.str.contains(re.escape(normalized_query), na=False)
    ]


def find_parent_designated_city(row: pd.Series, df: pd.DataFrame) -> str | None:
    name_column = find_name_column(df)
    prefecture_column = find_column_by_aliases(df, ("都道府県", "都道府県名"))
    if name_column is None or prefecture_column is None:
        return None

    row_name = str(row.get(name_column, "")).strip()
    if not row_name:
        return None

    for city_name, ward_names in DESIGNATED_CITY_WARDS.items():
        if row_name not in ward_names:
            continue

        city_rows = df[df[name_column].astype(str).eq(city_name)]
        for _, city_row in city_rows.iterrows():
            if str(city_row.get(prefecture_column)) != str(row.get(prefecture_column)):
                continue
            ward_rows = get_designated_city_ward_rows(city_row, df, name_column, prefecture_column, ward_names)
            if row.name in ward_rows.index:
                return city_name

    return None


def get_search_display_name(row: pd.Series, df: pd.DataFrame, name_column: str) -> str:
    row_name = str(row.get(name_column, "名称不明")).strip()
    parent_city = find_parent_designated_city(row, df)
    if parent_city:
        return f"{parent_city} {row_name}"
    return row_name


def build_search_display_names(df: pd.DataFrame, name_column: str) -> pd.Series:
    return df.apply(lambda row: get_search_display_name(row, df, name_column), axis=1).astype(str)


def get_diagnosis_scope(row: pd.Series, df: pd.DataFrame, metrics: list[dict[str, Any]]) -> dict[str, str]:
    name_column = find_name_column(df)
    raw_name = str(row.get(name_column, "")).strip() if name_column else ""
    parent_city = find_parent_designated_city(row, df)

    if parent_city:
        return {
            "mode": "行政区モード",
            "label": "行政区単位で診断",
            "display_name": f"{parent_city} {raw_name}",
        }

    if raw_name in DESIGNATED_CITY_WARDS:
        uses_ward_total = any(
            str((metric_item(metrics, label) or {}).get("取得元列", "")).startswith("行政区合算")
            for label in ("従来型訪問介護事業所数", "サ高住系事業所数", "実質競合数")
        )
        if uses_ward_total:
            return {
                "mode": "市全体モード",
                "label": "行政区合算で市全体を診断",
                "display_name": raw_name,
            }

    return {
        "mode": "通常市町村モード",
        "label": "市町村単位で診断",
        "display_name": raw_name,
    }


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


def get_metric_raw_value_and_source(row: pd.Series, columns: dict[str, str], spec: MetricSpec) -> tuple[Any, str | None]:
    for alias in (spec.label, *spec.aliases):
        normalized_alias = normalize_key(alias)

        exact_column = columns.get(normalized_alias)
        if exact_column is not None:
            return row.get(exact_column), exact_column

        if len(normalized_alias) >= 5:
            for normalized_column, original_column in columns.items():
                if normalized_alias in normalized_column:
                    return row.get(original_column), original_column

    return None, None


def collect_metrics(row: pd.Series, df: pd.DataFrame) -> list[dict[str, Any]]:
    columns = make_column_map(df)
    metrics = []

    for spec in METRICS:
        raw_value, source_column = get_metric_raw_value_and_source(row, columns, spec)
        metrics.append(
            {
                "指標": spec.label,
                "値": format_value(raw_value, spec),
                "数値": parse_number(raw_value),
                "単位": spec.unit,
                "取得元列": source_column or "",
                "推計": False,
            }
        )

    fill_designated_city_ward_totals(row, df, metrics)
    fill_derived_metrics(metrics)
    return metrics


def set_metric(metrics: list[dict[str, Any]], label: str, number: float) -> None:
    for metric in metrics:
        if metric["指標"] == label:
            spec = METRIC_SPECS_BY_LABEL.get(label)
            if spec is None:
                return
            metric["数値"] = number
            metric["値"] = format_value(number, spec)
            metric["単位"] = spec.unit
            return


def set_metric_with_source(
    metrics: list[dict[str, Any]],
    label: str,
    number: float,
    source: str,
    *,
    is_derived: bool = False,
) -> None:
    set_metric(metrics, label, number)
    for metric in metrics:
        if metric["指標"] == label:
            metric["取得元列"] = source
            metric["推計"] = is_derived
            return


def set_metric_derived(metrics: list[dict[str, Any]], label: str, number: float, source: str) -> None:
    set_metric_with_source(metrics, label, number, source, is_derived=True)


def metric_number(metrics: list[dict[str, Any]], label: str) -> float | None:
    if label == "達成余力倍率":
        competitive_ratio = metric_number(metrics, "競争後達成余力倍率")
        if competitive_ratio is not None:
            return competitive_ratio
        return metric_number(metrics, "理論市場余力倍率")
    for metric in metrics:
        if metric["指標"] == label:
            return metric["数値"]
    return None


def metric_item(metrics: list[dict[str, Any]], label: str) -> dict[str, Any] | None:
    for metric in metrics:
        if metric["指標"] == label:
            return metric
    return None


def has_competition_data_issue(metrics: list[dict[str, Any]]) -> bool:
    office_metric = metric_item(metrics, "従来型訪問介護事業所数") or {}
    sakoju_metric = metric_item(metrics, "サ高住系事業所数") or {}
    office_value = metric_number(metrics, "従来型訪問介護事業所数")
    sakoju_value = metric_number(metrics, "サ高住系事業所数")

    office_source = str(office_metric.get("取得元列", ""))
    sakoju_source = str(sakoju_metric.get("取得元列", ""))
    office_missing = office_value is None or (office_value <= 0 and not office_source.startswith("行政区合算"))
    sakoju_missing = sakoju_value is None or (sakoju_value <= 0 and not sakoju_source.startswith("行政区合算"))
    return office_missing and sakoju_missing


def uses_estimated_home_care_users(metrics: list[dict[str, Any]]) -> bool:
    user_metric = metric_item(metrics, "訪問介護利用者数")
    if not user_metric:
        return False
    source = str(user_metric.get("取得元列", ""))
    return bool(user_metric.get("推計")) and "65歳以上人口" in source


def calculate_estimated_home_care_users(metrics: list[dict[str, Any]]) -> float | None:
    elderly_population = metric_number(metrics, "高齢者人口")
    if elderly_population is None:
        return None
    return elderly_population * ESTIMATED_HOME_CARE_USER_RATE


def find_column_by_aliases(df: pd.DataFrame, aliases: tuple[str, ...]) -> str | None:
    columns = make_column_map(df)
    for alias in aliases:
        column = columns.get(normalize_key(alias))
        if column is not None:
            return column
    return None


def get_designated_city_ward_rows(
    row: pd.Series,
    df: pd.DataFrame,
    name_column: str,
    prefecture_column: str,
    ward_names: list[str],
) -> pd.DataFrame:
    prefecture = str(row.get(prefecture_column))
    ward_set = set(ward_names)
    collected_indices: list[Any] = []

    try:
        start_position = df.index.get_loc(row.name)
    except KeyError:
        start_position = None

    if isinstance(start_position, int):
        following_rows = df.iloc[start_position + 1 :]
        for index, candidate in following_rows.iterrows():
            if str(candidate.get(prefecture_column)) != prefecture:
                if collected_indices:
                    break
                continue

            candidate_name = str(candidate.get(name_column, "")).strip()
            if candidate_name in ward_set:
                collected_indices.append(index)
                if len(collected_indices) >= len(ward_set):
                    break
                continue

            if collected_indices:
                break

    if collected_indices:
        return df.loc[collected_indices]

    return df[
        df[prefecture_column].astype(str).eq(prefecture)
        & df[name_column].astype(str).isin(ward_names)
    ]


def fill_designated_city_ward_totals(row: pd.Series, df: pd.DataFrame, metrics: list[dict[str, Any]]) -> None:
    name_column = find_name_column(df)
    prefecture_column = find_column_by_aliases(df, ("都道府県", "都道府県名"))
    if name_column is None or prefecture_column is None:
        return

    municipality_name = str(row.get(name_column, "")).strip()
    ward_names = DESIGNATED_CITY_WARDS.get(municipality_name)
    if not ward_names:
        return

    ward_rows = get_designated_city_ward_rows(row, df, name_column, prefecture_column, ward_names)
    if ward_rows.empty:
        return

    aggregate_specs = [
        ("従来型訪問介護事業所数", ("訪問介護事業所数", "訪問介護", "居宅サービス_訪問介護", "事業所数_訪問介護")),
        ("訪問介護事業所数", ("訪問介護事業所数", "訪問介護", "居宅サービス_訪問介護", "事業所数_訪問介護")),
        ("サ高住系事業所数", ("定員あり事業所数", "サ高住系事業所数", "住宅型有料・サ高住系事業所数")),
        ("実質競合数", ("全国版_実質競合推定", "実質競合数", "競合数")),
    ]

    for metric_label, aliases in aggregate_specs:
        source_column = find_column_by_aliases(df, aliases)
        if source_column is None:
            continue

        current_value = metric_number(metrics, metric_label)
        if current_value is not None and current_value > 0:
            continue

        total = pd.to_numeric(ward_rows[source_column], errors="coerce").fillna(0).sum()
        if total > 0:
            set_metric_with_source(
                metrics,
                metric_label,
                float(total),
                f"行政区合算：{source_column}",
                is_derived=False,
            )


def fill_derived_metrics(metrics: list[dict[str, Any]]) -> None:
    elderly_population = metric_number(metrics, "高齢者人口")
    habitable_area = metric_number(metrics, "可住地面積")
    users = metric_number(metrics, "訪問介護利用者数")
    competitors = metric_number(metrics, "実質競合数")
    offices = metric_number(metrics, "従来型訪問介護事業所数")
    sakoju_offices = metric_number(metrics, "サ高住系事業所数")
    market_size = metric_number(metrics, "市場規模")
    revenue_per_user = calculate_effective_revenue_per_user(metrics)

    estimated_users = metric_number(metrics, "推定訪問介護利用者数")
    estimated_user_metric = metric_item(metrics, "推定訪問介護利用者数") or {}
    estimated_source = str(estimated_user_metric.get("取得元列", ""))
    formula_estimated_users = calculate_estimated_home_care_users(metrics)
    formula_source_label = f"65歳以上人口×推計利用率{ESTIMATED_HOME_CARE_USER_RATE_SOURCE_LABEL}"

    if estimated_users is None and formula_estimated_users is not None:
        estimated_users = formula_estimated_users
        estimated_source = formula_source_label
        set_metric_derived(metrics, "推定訪問介護利用者数", estimated_users, estimated_source)

    if users is None and estimated_users is not None:
        users = estimated_users
        set_metric_derived(metrics, "訪問介護利用者数", users, estimated_source or "推定訪問介護利用者数")

    if competitors is None and offices is not None:
        competitors = offices
        set_metric_derived(metrics, "実質競合数", competitors, "訪問介護事業所数")

    if metric_number(metrics, "高齢者可住地密度") is None and elderly_population is not None and habitable_area:
        set_metric_derived(metrics, "高齢者可住地密度", elderly_population / habitable_area, "高齢者人口÷可住地面積")

    if metric_number(metrics, "1競合あたり潜在利用者") is None and users is not None and competitors:
        set_metric_derived(metrics, "1競合あたり潜在利用者", users / competitors, "訪問介護利用者数÷実質競合数")

    if metric_number(metrics, "1事業所あたり潜在利用者数") is None and users is not None and offices:
        set_metric_derived(metrics, "1事業所あたり潜在利用者数", users / offices, "訪問介護利用者数÷従来型訪問介護事業所数")

    if market_size is None and users is not None:
        market_size = users * revenue_per_user
        set_metric_derived(metrics, "市場規模", market_size, "訪問介護利用者数×基準売上単価")

    if metric_number(metrics, "理論市場余力倍率") is None and market_size is not None:
        set_metric_derived(metrics, "理論市場余力倍率", market_size / TARGET_MONTHLY_REVENUE, "市場規模÷250万円")

    if metric_number(metrics, "競争後達成余力倍率") is None and market_size is not None and competitors:
        set_metric_derived(
            metrics,
            "競争後達成余力倍率",
            (market_size / competitors) / TARGET_MONTHLY_REVENUE,
            "市場規模÷実質競合数÷250万円",
        )

    if metric_number(metrics, "参入後達成余力倍率") is None and market_size is not None and competitors is not None:
        set_metric_derived(
            metrics,
            "参入後達成余力倍率",
            market_size / (TARGET_MONTHLY_REVENUE * (competitors + 1)),
            "市場規模÷250万円÷参入後競合数",
        )

    if metric_number(metrics, "250万円達成必要人数") is None:
        set_metric_derived(
            metrics,
            "250万円達成必要人数",
            math.ceil(TARGET_MONTHLY_REVENUE / revenue_per_user),
            "250万円÷基準売上単価",
        )


def value_or_zero(value: float | None) -> float:
    return 0.0 if value is None else value


def is_missing_positive_number(value: float | None) -> bool:
    return value is None or value <= 0


def collect_region_missing_fields(metrics: list[dict[str, Any]]) -> list[str]:
    required_positive_fields = [
        "高齢者人口",
        "可住地面積",
        "訪問介護利用者数",
        "従来型訪問介護事業所数",
    ]
    missing_fields = [
        field for field in required_positive_fields if is_missing_positive_number(metric_number(metrics, field))
    ]

    if metric_number(metrics, "サ高住系事業所数") is None:
        missing_fields.append("サ高住系事業所数")

    return missing_fields


def sakoju_competition_weight(region_type: str) -> float:
    weights = REGION_CLASSIFICATION_CONFIG["sakoju"]["competition_weights"]
    return float(weights.get(region_type, weights["判定保留"]))


def apply_sakoju_competition_adjustment(metrics: list[dict[str, Any]], region_type: str) -> dict[str, float | None]:
    base_competitors = metric_number(metrics, "実質競合数")
    sakoju_offices = metric_number(metrics, "サ高住系事業所数")
    users = metric_number(metrics, "訪問介護利用者数")
    market_size = metric_number(metrics, "市場規模")
    weight = sakoju_competition_weight(region_type)

    if base_competitors is None:
        return {
            "sakoju_competition_weight": weight,
            "sakoju_competition_count": None,
        }

    sakoju_competition_count = (sakoju_offices or 0) * weight
    effective_competitors = base_competitors + sakoju_competition_count
    set_metric_derived(
        metrics,
        "実質競合数",
        effective_competitors,
        f"基礎実質競合数＋サ高住競合化係数{weight:g}",
    )

    if users is not None and effective_competitors:
        set_metric_derived(
            metrics,
            "1競合あたり潜在利用者",
            users / effective_competitors,
            "訪問介護利用者数÷実質競合数",
        )

    if market_size is not None and effective_competitors:
        set_metric_derived(
            metrics,
            "競争後達成余力倍率",
            (market_size / effective_competitors) / TARGET_MONTHLY_REVENUE,
            "市場規模÷実質競合数÷250万円",
        )
        set_metric_derived(
            metrics,
            "参入後達成余力倍率",
            market_size / (TARGET_MONTHLY_REVENUE * (effective_competitors + 1)),
            "市場規模÷250万円÷参入後競合数",
        )

    return {
        "sakoju_competition_weight": weight,
        "sakoju_competition_count": sakoju_competition_count,
    }


def calculate_competition_density_penalty(competitors: float | None) -> dict[str, Any]:
    if competitors is None:
        return {
            "level": "不明",
            "score_penalty": 0,
            "difficulty_points": 0,
            "profitability_points": 0,
            "is_battlefield": False,
            "comment": "実質競合数が未取得のため、競争密度ペナルティは未判定です。",
        }

    if competitors >= 80:
        return {
            "level": "強",
            "score_penalty": -2,
            "difficulty_points": 20,
            "profitability_points": 18,
            "is_battlefield": True,
            "comment": f"実質競合数が{competitors:.1f}事業所と極めて多く、市場規模が大きくても激戦市場です。",
        }
    if competitors >= 50:
        return {
            "level": "中",
            "score_penalty": -1,
            "difficulty_points": 12,
            "profitability_points": 10,
            "is_battlefield": True,
            "comment": f"実質競合数が{competitors:.1f}事業所と多く、競争密度による参入難易度上昇があります。",
        }
    if competitors >= 20:
        return {
            "level": "やや",
            "score_penalty": -1,
            "difficulty_points": 6,
            "profitability_points": 5,
            "is_battlefield": False,
            "comment": f"実質競合数が{competitors:.1f}事業所あり、一定の競争密度を考慮する必要があります。",
        }

    return {
        "level": "なし",
        "score_penalty": 0,
        "difficulty_points": 0,
        "profitability_points": 0,
        "is_battlefield": False,
        "comment": "実質競合数は20未満で、競争密度による追加ペナルティは小さいです。",
    }


def cap_score(score: int) -> int:
    return max(0, min(100, score))


def calculate_region_type_scores(
    elderly_population: float | None,
    elderly_density: float | None,
    habitable_area: float | None,
    competitors: float | None,
    users_per_office: float | None,
    market_size: float | None,
    capacity_ratio: float | None,
    sakoju_cover_rate: float | None,
) -> tuple[dict[str, int], dict[str, list[str]]]:
    scores = {
        "大都市型": 0,
        "地方都市型": 0,
        "供給不足型過疎地": 0,
        "超過疎地型": 0,
        "超高密集競争型": 0,
    }
    details = {region_type: [] for region_type in scores}

    def add(region_type: str, points: int, reason: str) -> None:
        scores[region_type] += points
        details[region_type].append(f"+{points}点：{reason}")

    if elderly_density is not None:
        if elderly_density >= 1500:
            add("大都市型", 30, "高齢者人口密度が高い")
        elif elderly_density >= 700:
            add("大都市型", 18, "高齢者人口密度が一定以上ある")

        if 700 <= elderly_density <= 1500:
            add("地方都市型", 30, "高齢者人口密度が中程度")
        elif 200 <= elderly_density < 700 or 1500 < elderly_density <= 2500:
            add("地方都市型", 15, "高齢者人口密度が地方都市型に近い")

    if market_size is not None:
        if market_size >= 20_000_000:
            add("大都市型", 25, "市場規模が大きい")
        elif market_size >= 10_000_000:
            add("大都市型", 15, "市場規模が一定以上ある")

        if market_size >= 10_000_000:
            add("地方都市型", 30, "市場規模が一定以上あり、新規事業所を吸収しやすい")
        elif market_size >= 5_000_000:
            add("地方都市型", 18, "小規模運営なら検討できる市場規模がある")

        if market_size < 2_500_000:
            add("超過疎地型", 45, "市場規模が小さい")
        elif market_size < 4_000_000:
            add("超過疎地型", 28, "市場規模がやや小さい")

    if competitors is not None:
        if competitors >= 8:
            add("大都市型", 25, "実質競合数が多い")
            add("超高密集競争型", 25, "実質競合数が多い")
        elif competitors >= 5:
            add("大都市型", 15, "実質競合数が一定以上ある")
            add("超高密集競争型", 15, "競合がやや多い")

        if 3 <= competitors <= 7:
            add("地方都市型", 20, "競合はあるが過密ではない")
        elif 8 <= competitors < 50:
            add("地方都市型", 25, "競合は多いが、一定規模市場なら新規参入を吸収できる")
        elif competitors <= 2:
            add("地方都市型", 8, "競合が少なく地方型の余地がある")
            add("供給不足型過疎地", 30, "実質競合数が少ない")
        elif competitors <= 5:
            add("供給不足型過疎地", 15, "競合数が比較的少ない")

        if competitors >= 50:
            add("大都市型", 20, "実質競合数が50以上で、地方都市型より都市部型の競争構造に近い")
            add("地方都市型", -15, "実質競合数が50以上で、軽量参入だけでは拾いにくい")

    if habitable_area is not None:
        if habitable_area <= 30:
            add("大都市型", 20, "可住地面積が比較的小さい")
        elif habitable_area <= 80:
            add("大都市型", 10, "可住地面積が広すぎない")

        if habitable_area >= 80:
            add("供給不足型過疎地", 15, "可住地面積が広め")
            add("超過疎地型", 15, "可住地面積が広く移動効率に注意が必要")
        elif habitable_area >= 40:
            add("供給不足型過疎地", 6, "可住地面積に広がりがある")
            add("超過疎地型", 8, "可住地面積に広がりがある")

        if habitable_area <= 15:
            add("超高密集競争型", 30, "可住地面積が極端に小さい")
        elif habitable_area <= 30:
            add("超高密集競争型", 20, "可住地面積が小さい")

    if users_per_office is not None:
        if users_per_office >= 80:
            add("供給不足型過疎地", 25, "1事業所あたり潜在利用者数が多い")
        elif users_per_office >= 40:
            add("供給不足型過疎地", 12, "1事業所あたり潜在利用者数が一定以上ある")

        if users_per_office < 25:
            add("超高密集競争型", 25, "1事業所あたり潜在利用者数が少ない")
        elif users_per_office < 40:
            add("超高密集競争型", 15, "1事業所あたり潜在利用者数がやや少ない")

    if capacity_ratio is not None:
        if capacity_ratio >= 2:
            add("地方都市型", 20, "競争後達成余力倍率が残っている")
            add("供給不足型過疎地", 20, "市場余力が残っている")
        elif capacity_ratio >= 1.2:
            add("地方都市型", 18, "競争後達成余力倍率が一定程度あり、地方都市として需要余力がある")
            add("供給不足型過疎地", 6, "市場余力が一定程度ある")

        if capacity_ratio < 1:
            add("超過疎地型", 25, "競争後達成余力倍率が低い")
        elif capacity_ratio < 1.6:
            add("超過疎地型", 15, "競争後達成余力倍率がやや低い")

    if elderly_population is not None:
        if elderly_population < 3_000:
            add("超過疎地型", 25, "高齢者絶対数が少ない")
        elif elderly_population < 6_000:
            add("超過疎地型", 15, "高齢者絶対数がやや少ない")

    if sakoju_cover_rate is not None:
        if sakoju_cover_rate >= 0.30:
            add("超高密集競争型", 20, "サ高住500m圏カバー率が高い")
        elif sakoju_cover_rate >= 0.10:
            add("超高密集競争型", 10, "サ高住500m圏カバー率が一定以上ある")

    return {key: cap_score(value) for key, value in scores.items()}, details


def reasons_for_region_type(region_type: str) -> list[str]:
    reasons_by_type = {
        "大都市型": [
            "高齢者人口密度・市場規模・競合数の組み合わせが都市部型に近い",
            "市場は大きい一方で、営業難易度と差別化が重要になる",
        ],
        "地方都市型": [
            "市場規模と競合数のバランスが比較的良い",
            "固定費を抑えた小規模運営と相性が良い",
        ],
        "供給不足型過疎地": [
            "競合が少なく、1事業所あたり潜在利用者数が多い",
            "可住地面積が広く、訪問範囲の絞り込みが重要になる",
        ],
        "超過疎地型": [
            "高齢者絶対数や市場規模が小さく、売上上限に注意が必要",
            "移動効率と低固定費運営を慎重に見る必要がある",
        ],
        "超高密集競争型": [
            "狭い可住地面積に競合が集中している可能性がある",
            "1事業所あたり潜在利用者数やサ高住影響から伸びしろを慎重に見る必要がある",
        ],
    }
    return reasons_by_type.get(region_type, ["取得できている指標だけで暫定的に確認してください"])


def calculate_business_model_scores(
    region_type: str,
    elderly_density: float | None,
    habitable_area: float | None,
    competitors: float | None,
    users_per_office: float | None,
    market_size: float | None,
    capacity_ratio: float | None,
    sakoju_cover_rate: float | None,
) -> tuple[dict[str, int], dict[str, list[str]]]:
    scores = {
        "夫婦経営型": 20,
        "自宅兼事務所型": 20,
        "居宅介護支援併設型": 20,
        "承継・引継ぎ型": 20,
        "高密度都市集中型": 20,
        "超低固定費型": 20,
    }
    details = {model: ["+20点：基本点"] for model in scores}

    def add(model: str, points: int, reason: str) -> None:
        scores[model] += points
        details[model].append(f"+{points}点：{reason}")

    def subtract(model: str, points: int, reason: str) -> None:
        scores[model] -= points
        details[model].append(f"-{points}点：{reason}")

    if region_type == "地方都市型":
        add("夫婦経営型", 35, "地方都市型と夫婦経営の相性が良い")
        add("自宅兼事務所型", 35, "地方都市型では住居兼事務所で固定費を抑えやすい")
        add("超低固定費型", 15, "低固定費運営の効果が出やすい")
    elif region_type == "供給不足型過疎地":
        add("自宅兼事務所型", 30, "供給不足地域では低固定費で入りやすい")
        add("夫婦経営型", 25, "小さく始める夫婦経営と相性がある")
        add("超低固定費型", 25, "固定費を抑えるほど成立余地が上がる")
    elif region_type == "超過疎地型":
        add("超低固定費型", 45, "超過疎地型では低固定費が最重要")
        add("夫婦経営型", 25, "夫婦中心で現場に出る前提なら成立余地が残る")
        add("自宅兼事務所型", 20, "事務所費を極小化しやすい")
        subtract("高密度都市集中型", 20, "高密度運営には向きにくい")
    elif region_type == "大都市型":
        add("居宅介護支援併設型", 35, "大都市型では紹介競争への対応が重要")
        add("承継・引継ぎ型", 35, "0スタート難易度が高く承継・引継ぎが有効")
        add("高密度都市集中型", 30, "高密度エリアに集中しやすい")
        subtract("自宅兼事務所型", 10, "都市部は固定費が高くなりやすい")
    elif region_type == "超高密集競争型":
        add("居宅介護支援併設型", 40, "紹介競争が激しく居宅併設の必要性が高い")
        add("承継・引継ぎ型", 40, "既存地盤なしの0スタートが難しい")
        add("高密度都市集中型", 20, "移動距離を短くした集中運営と相性がある")
        subtract("自宅兼事務所型", 15, "競合過多では低固定費だけでは勝ちにくい")

    if competitors is not None:
        if competitors >= 8:
            add("居宅介護支援併設型", 20, "実質競合数が多く紹介導線が重要")
            add("承継・引継ぎ型", 20, "競合が多く既存地盤の価値が高い")
        elif competitors <= 2:
            add("夫婦経営型", 10, "競合が少なく小規模運営で入りやすい")
            add("自宅兼事務所型", 10, "競合が少なく固定費を抑えた参入と相性が良い")

    if habitable_area is not None:
        if habitable_area <= 30:
            add("高密度都市集中型", 20, "可住地面積が狭く集中運営しやすい")
        if habitable_area >= 80:
            add("超低固定費型", 15, "広域訪問になりやすく固定費抑制が重要")

    if elderly_density is not None:
        if elderly_density >= 1500:
            add("高密度都市集中型", 20, "高齢者人口密度が高い")
        elif elderly_density < 80:
            add("超低固定費型", 15, "移動効率に注意が必要で固定費を抑えたい")

    if market_size is not None:
        if market_size < 4_000_000:
            add("超低固定費型", 25, "市場規模が小さく低固定費が必要")
            subtract("居宅介護支援併設型", 10, "市場規模が小さく併設投資は重くなりやすい")
        elif market_size >= 20_000_000:
            add("居宅介護支援併設型", 10, "市場規模が大きく紹介導線を作る価値がある")
            add("高密度都市集中型", 10, "市場規模が大きく集中戦略の余地がある")

    if users_per_office is not None and users_per_office >= 40:
        add("夫婦経営型", 10, "1事業所あたり潜在利用者数が一定以上ある")
        add("自宅兼事務所型", 10, "潜在利用者を拾えれば低固定費運営と相性が良い")

    if capacity_ratio is not None:
        if capacity_ratio < 1.5:
            add("超低固定費型", 15, "競争後達成余力倍率が低く固定費抑制が重要")
        elif capacity_ratio >= 2:
            add("夫婦経営型", 10, "競争後の達成余力があり小規模運営でも狙いやすい")
            add("自宅兼事務所型", 10, "競争後の達成余力があり低固定費モデルと相性が良い")

        if region_type in {"地方都市型", "供給不足型過疎地"}:
            if capacity_ratio >= 1.8:
                subtract("居宅介護支援併設型", 45, "需要余力が大きく、居宅併設は固定費・管理負荷・常勤消費のデメリットが目立つ")
                add("夫婦経営型", 15, "紹介が回りやすい市場では軽量な小規模高稼働モデルが強い")
                add("自宅兼事務所型", 15, "居宅を抱えず固定費を抑える運営と相性が良い")
            elif capacity_ratio >= 1.4:
                subtract("居宅介護支援併設型", 35, "需要余力があり、居宅併設よりケアマネを抱えない軽量運営が有利になりやすい")
                add("夫婦経営型", 10, "需要余力があり小規模高密度運営を組みやすい")
                add("自宅兼事務所型", 10, "固定費を抑えた軽量運営の優位性が出やすい")
            elif capacity_ratio >= 1.1:
                subtract("居宅介護支援併設型", 15, "中間市場のため、居宅併設は地域構造を見て慎重に判断したい")
            elif capacity_ratio >= 0.8:
                add("居宅介護支援併設型", 15, "市場が厳しく、紹介導線として居宅併設が強く有利になりやすい")
            else:
                add("居宅介護支援併設型", 25, "激戦市場では居宅併設・地盤・承継の重要性が高い")

            if competitors is not None and competitors >= 80:
                add("居宅介護支援併設型", 20, "実質競合数が80以上の激戦市場では、需要余力があっても紹介導線の確保が重要")
                add("承継・引継ぎ型", 15, "競争密度が高く、既存地盤の引継ぎ価値が上がる")

        if region_type in {"大都市型", "超高密集競争型"}:
            if capacity_ratio < 0.8:
                add("居宅介護支援併設型", 25, "競争後達成余力倍率が低く、デメリット承知でも居宅併設が必要になりやすい")
            elif capacity_ratio < 1.1:
                add("居宅介護支援併設型", 15, "厳しい都市部市場では、紹介導線の確保が黒字化の前提になりやすい")

    if sakoju_cover_rate is not None and sakoju_cover_rate >= 0.30:
        add("居宅介護支援併設型", 10, "サ高住影響が強く紹介導線の確保が重要")
        add("承継・引継ぎ型", 10, "サ高住影響が強く既存地盤の価値が高い")

    return {key: cap_score(value) for key, value in scores.items()}, details


def classify_region(metrics: list[dict[str, Any]], municipality_name: str | None = None) -> dict[str, Any]:
    config = REGION_CLASSIFICATION_CONFIG
    super_sparse_config = config["super_sparse"]
    shortage_config = config["supply_shortage_sparse"]
    large_city_config = config["large_city"]
    dense_config = config["dense_competitive"]
    sakoju_config = config["sakoju"]

    elderly_population = metric_number(metrics, "高齢者人口")
    elderly_density = metric_number(metrics, "高齢者可住地密度")
    habitable_area = metric_number(metrics, "可住地面積")
    competitors = metric_number(metrics, "実質競合数")
    sakoju_offices = metric_number(metrics, "サ高住系事業所数")
    users = metric_number(metrics, "訪問介護利用者数")
    users_per_office = metric_number(metrics, "1事業所あたり潜在利用者数")
    market_size = metric_number(metrics, "市場規模")
    theoretical_capacity_ratio = metric_number(metrics, "理論市場余力倍率")
    capacity_ratio = metric_number(metrics, "競争後達成余力倍率")
    missing_fields = collect_region_missing_fields(metrics)

    competitor_count = value_or_zero(competitors)
    elderly_count = value_or_zero(elderly_population)
    user_count = value_or_zero(users)
    market_amount = value_or_zero(market_size)
    sakoju_cover_rate = None
    if sakoju_offices is not None and habitable_area:
        sakoju_cover_rate = sakoju_offices * sakoju_config["cover_area_per_facility"] / habitable_area

    type_scores, type_score_details = calculate_region_type_scores(
        elderly_population=elderly_population,
        elderly_density=elderly_density,
        habitable_area=habitable_area,
        competitors=competitors,
        users_per_office=users_per_office,
        market_size=market_size,
        capacity_ratio=capacity_ratio,
        sakoju_cover_rate=sakoju_cover_rate,
    )

    if any(field in missing_fields for field in ["高齢者人口", "可住地面積", "訪問介護利用者数"]):
        region_type = "判定保留"
        reasons = [
            "地域タイプ分類に必要な主要データが不足している",
            "取得できている指標だけで暫定的に確認してください",
        ]

    elif (
        market_amount < super_sparse_config["max_market_size"]
        and user_count < super_sparse_config["max_users"]
        and elderly_count < super_sparse_config["max_elderly_population"]
    ):
        region_type = "超過疎地型"
        reasons = [
            "高齢者人口の絶対数が少ない",
            "市場規模と訪問介護利用者数が小さく、安定運営ラインへの到達余地を慎重に見る必要がある",
        ]

    elif (
        habitable_area is not None
        and habitable_area >= shortage_config["min_habitable_area"]
        and competitor_count <= shortage_config["max_effective_competitors"]
        and users_per_office is not None
        and users_per_office >= shortage_config["min_users_per_office"]
    ):
        region_type = "供給不足型過疎地"
        reasons = [
            "可住地面積が広く、既存競合が少ない",
            "1事業所あたり潜在利用者数が多く、供給不足の可能性がある",
        ]

    elif (
        habitable_area is not None
        and habitable_area <= dense_config["max_habitable_area"]
        and competitor_count >= dense_config["min_effective_competitors"]
        and users_per_office is not None
        and users_per_office < dense_config["max_users_per_office"]
        and (capacity_ratio is None or capacity_ratio < dense_config["max_capacity_ratio"])
    ):
        region_type = "超高密集競争型"
        reasons = [
            "可住地面積が小さく、競合が密集している",
            "1事業所あたり潜在利用者数が少なく、伸びしろが限定的に見える",
        ]

    elif (
        elderly_density is not None
        and elderly_density >= large_city_config["min_elderly_density"]
        and market_amount >= large_city_config["min_market_size"]
        and competitor_count >= large_city_config["min_effective_competitors"]
    ):
        region_type = "大都市型"
        reasons = [
            "高齢者人口密度が高く、市場規模も大きい",
            "競合も多く、都市部型の営業・差別化が必要になる",
        ]

    else:
        region_type = "地方都市型"
        reasons = [
            "可住地面積に対して高齢者人口が一定以上ある",
            "市場規模があり、競合もあるが余力が残っている",
        ]

    reference_region_type = REFERENCE_REGION_TYPES.get(str(municipality_name or "").strip())
    if region_type != "判定保留" and reference_region_type:
        region_type = reference_region_type
        for score_type, score_value in list(type_scores.items()):
            if score_type != region_type and score_value >= 80:
                type_scores[score_type] = 80
        type_scores[region_type] = 100
        type_score_details.setdefault(region_type, []).append(
            f"+100点：基準地域（教師データ）として{region_type}に固定"
        )
        reasons = reasons_for_region_type(region_type)
        reasons.insert(0, f"{municipality_name}は基準地域として{region_type}に固定")
    elif region_type != "判定保留":
        region_type = max(type_scores, key=type_scores.get)
        reasons = reasons_for_region_type(region_type)

    sakoju_adjustment = apply_sakoju_competition_adjustment(metrics, str(region_type))
    competitors = metric_number(metrics, "実質競合数")
    capacity_ratio = metric_number(metrics, "競争後達成余力倍率")
    competition_density_penalty = calculate_competition_density_penalty(competitors)

    sakoju_impact, sakoju_view = classify_sakoju_influence(sakoju_cover_rate, region_type)
    business_model_scores, business_model_score_details = calculate_business_model_scores(
        region_type=region_type,
        elderly_density=elderly_density,
        habitable_area=habitable_area,
        competitors=competitors,
        users_per_office=users_per_office,
        market_size=market_size,
        capacity_ratio=capacity_ratio,
        sakoju_cover_rate=sakoju_cover_rate,
    )

    return {
        "type": region_type,
        "reasons": reasons,
        "elderly_density": elderly_density,
        "effective_competitors": competitors,
        "users_per_office": users_per_office,
        "market_size": market_size,
        "theoretical_capacity_ratio": theoretical_capacity_ratio,
        "capacity_ratio": capacity_ratio,
        "sakoju_cover_rate": sakoju_cover_rate,
        "sakoju_competition_weight": sakoju_adjustment.get("sakoju_competition_weight"),
        "sakoju_competition_count": sakoju_adjustment.get("sakoju_competition_count"),
        "competition_density_penalty": competition_density_penalty,
        "sakoju_impact": sakoju_impact,
        "sakoju_view": sakoju_view,
        "missing_fields": missing_fields,
        "type_scores": type_scores,
        "type_score_details": type_score_details,
        "business_model_scores": business_model_scores,
        "business_model_score_details": business_model_score_details,
    }


def classify_sakoju_influence(sakoju_cover_rate: float | None, region_type: str) -> tuple[str, str]:
    if sakoju_cover_rate is None:
        return "不明", "不明"

    sakoju_config = REGION_CLASSIFICATION_CONFIG["sakoju"]
    if sakoju_cover_rate < sakoju_config["weak_threshold"]:
        impact = "弱い"
        view = "紹介元寄り"
    elif sakoju_cover_rate < sakoju_config["medium_threshold"]:
        impact = "一部競合"
        view = "一部競合"
    else:
        impact = "強い競合"
        view = "競合寄り"

    if region_type in {"地方都市型", "供給不足型過疎地"}:
        view = f"{view}（競合というより紹介元になりやすい）"

    return impact, view


def judge_market(metrics: list[dict[str, Any]], region: dict[str, Any]) -> tuple[str, list[str]]:
    comments = []

    capacity_ratio = metric_number(metrics, "達成余力倍率")
    post_entry_ratio = metric_number(metrics, "参入後達成余力倍率")
    elderly_density = metric_number(metrics, "高齢者可住地密度")
    competitors = metric_number(metrics, "実質競合数")
    population_density = metric_number(metrics, "人口密度")
    potential_users = metric_number(metrics, "1事業所あたり潜在利用者数")
    competition_penalty = region.get("competition_density_penalty", calculate_competition_density_penalty(competitors))
    region_type = region.get("type", "地方都市型")

    score = 0

    if capacity_ratio is None:
        comments.append("競争後達成余力倍率が未取得のため、有望度は補助指標とあわせて確認してください。")
    elif capacity_ratio >= 2:
        score += 2
        comments.append("競争後達成余力倍率が2以上で、250万円の安定運営ラインに対して有望水準です。")
    else:
        score -= 1
        comments.append("競争後達成余力倍率が2未満で、250万円達成には慎重な利用者獲得計画が必要です。")

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
            comments.append(f"実質競合ベースの競合負荷は{competitors:.1f}で、営業難易度が高くなる可能性があります。")
        elif competitors <= 2:
            score += 1
            comments.append(f"実質競合ベースの競合負荷は{competitors:.1f}で、供給不足地域ではシフト調整しやすい可能性があります。")
        else:
            comments.append(f"実質競合ベースの競合負荷は{competitors:.1f}で、競争環境は中程度です。")

    score += int(competition_penalty.get("score_penalty", 0))
    if competition_penalty.get("level") in {"やや", "中", "強"}:
        comments.append(str(competition_penalty.get("comment")))

    if population_density is not None and population_density >= 1_000 and competitors is not None and competitors >= 5:
        comments.append("人口密度と競合数の両方が高く、都市部型の営業・差別化戦略が重要です。")

    if potential_users is not None and potential_users >= 30:
        score += 1
        comments.append("1事業所あたり潜在利用者数は一定以上あり、利用者獲得余地が見込めます。")

    if region_type == "供給不足型過疎地" and capacity_ratio is not None and capacity_ratio >= 2:
        if competitors is not None and competitors < 20 and potential_users is not None and potential_users >= 40:
            score += 2
            comments.append("供給不足型で利用者獲得難易度が低く、0から立ち上がりやすい市場として強く評価できます。")
    elif region_type == "地方都市型" and capacity_ratio is not None and capacity_ratio >= 1.4:
        if competitors is not None and competitors < 50:
            score += 1
            comments.append("地方都市型で需要余力があり、小規模でも訪問介護の灯を維持しやすい点を加点します。")

    if score >= 3:
        headline = "有望"
    elif score >= 1:
        headline = "条件付き有望"
    elif score == 0:
        headline = "中立"
    else:
        headline = "慎重検討"

    headline, judgment_reasons = adjust_headline_by_region(headline, score, metrics, region)
    comments.extend([f"判定理由：{reason}" for reason in judgment_reasons])
    comments.extend(region_market_comments(region, metrics))
    return headline, comments


def adjust_headline_by_region(
    current_headline: str,
    score: int,
    metrics: list[dict[str, Any]],
    region: dict[str, Any],
) -> tuple[str, list[str]]:
    region_type = region.get("type", "地方都市型")
    capacity_ratio = metric_number(metrics, "達成余力倍率")
    theoretical_capacity_ratio = metric_number(metrics, "理論市場余力倍率")
    market_size = metric_number(metrics, "市場規模")
    competitors = metric_number(metrics, "実質競合数")
    users_per_office = metric_number(metrics, "1事業所あたり潜在利用者数")

    capacity = value_or_zero(capacity_ratio)
    market = value_or_zero(market_size)
    competitor_count = value_or_zero(competitors)
    users_per = value_or_zero(users_per_office)
    competition_penalty = region.get("competition_density_penalty", calculate_competition_density_penalty(competitors))
    penalty_level = competition_penalty.get("level")
    is_battlefield = bool(competition_penalty.get("is_battlefield"))

    if region_type == "判定保留":
        return "判定保留", [
            "地域タイプ分類に必要なデータが一部不足しています。",
            "不足項目を補完してから、総合判定を再確認してください。",
        ]

    if region_type == "地方都市型":
        if competitor_count >= 80 and capacity < 2:
            return "△ 普通だが工夫が必要", [
                "地方都市型としての市場余力はありますが、実質競合数が80以上で競争密度が非常に高い地域です。",
                "市場全体ではなく、特定エリア・特定紹介元に絞った戦い方が必要です。",
            ]
        if capacity >= 2.5 and competitor_count < 30:
            return "◯ 有望", [
                "地方都市型で市場余力が高く、一定の新規参入を吸収できる見立てです。",
                "自宅兼事務所などで固定費を抑え、小規模高密度に回る戦い方と相性があります。",
            ]
        if capacity < 1.2 or competitor_count >= 50:
            return "△ 普通だが工夫が必要", [
                "地方都市型としての相性はありますが、競争後達成余力または競合環境に注意が必要です。",
                "商圏を絞り、移動効率と紹介ルートを丁寧に作る必要があります。",
            ]
        return "◯ 有望", [
            "地方都市型として、低固定費運営と紹介ルート開拓が噛み合えば有望です。",
        ]

    if region_type == "供給不足型過疎地":
        if market < 2_500_000:
            return "△ 普通だが工夫が必要", [
                "供給不足の可能性はありますが、市場規模が小さく売上上限に注意が必要です。",
            ]
        if is_battlefield and capacity < 2:
            return "△ 普通だが工夫が必要", [
                "市場規模は大きい一方、実質競合数が多く競争密度が高い激戦市場です。",
                "供給不足型に見えても、市場全体を取りに行くより紹介元と対応エリアを絞る必要があります。",
            ]
        if users_per >= 80 and competitor_count <= 6 and capacity >= 2:
            return "◎ かなり有望", [
                "競合が少なく、1事業所あたり潜在利用者数も多いため、0から立ち上がりやすい市場です。",
                "市場規模の大きさよりも、小さく生き残りやすく、地域の訪問介護の灯を維持しやすい点を高く評価できます。",
            ]
        if users_per >= 40 and competitor_count < 20 and capacity >= 1.5:
            return "◯ 有望", [
                "供給不足型として、利用者獲得難易度が比較的低く、立ち上がりやすい市場です。",
                "大きく伸ばすより、低固定費で小さく安定運営する戦い方に向いています。",
            ]
        return "◯ 有望", [
            "供給不足型として需要を拾いやすい可能性がありますが、訪問範囲の絞り込みが重要です。",
        ]

    if region_type == "超過疎地型":
        if market < 2_500_000 or capacity < 1:
            return "× 厳しいので参入非推奨", [
                "超過疎地型で、全体市場を取っても250万円達成が難しい可能性があります。",
                "高齢者絶対数と移動効率の両面で厳しい見立てです。",
            ]
        return "△ 普通だが工夫が必要", [
            "超過疎地型のため、所有物件・夫婦フル稼働・低固定費が前提になります。",
        ]

    if region_type == "大都市型":
        if penalty_level == "強" and capacity < 2:
            return "× 厳しいので参入非推奨", [
                "市場規模は大きい一方、実質競合数が80以上で激戦市場です。",
                "競争後達成余力倍率も十分とはいえず、0スタートはかなり厳しい見立てです。",
            ]
        if theoretical_capacity_ratio is not None and theoretical_capacity_ratio >= 20 and capacity < 1.2:
            return "× 厳しいので参入非推奨", [
                "理論市場余力は大きい一方、競争後達成余力倍率が低く、激戦市場です。",
            ]
        if competitor_count >= 10 and capacity < 1.5:
            return "× 厳しいので参入非推奨", [
                "大都市型ですが競合過多で、競争後達成余力も低いため0スタートは厳しい見立てです。",
            ]
        return "△ 普通だが工夫が必要", [
            "市場規模はありますが、大都市型は0スタートの参入難易度が高い地域です。",
            "居宅併設・承継・既存地盤がない前提では慎重に見るべきです。",
        ]

    if region_type == "超高密集競争型":
        if theoretical_capacity_ratio is not None and theoretical_capacity_ratio >= 10 and capacity < 1.2:
            return "× 厳しいので参入非推奨", [
                "理論市場余力はあっても競争後達成余力倍率が低く、激戦市場です。",
                "地盤引継ぎやケアマネ併設がない新規参入は非推奨です。",
            ]
        return "× 厳しいので参入非推奨", [
            "超高密集競争型は市場が狭く競合過多になりやすいため、基本的に厳しめの判定です。",
            "地盤引継ぎやケアマネ併設がない新規参入は非推奨です。",
        ]

    if current_headline == "有望":
        return "◯ 有望", ["既存指標上は一定の市場余力があります。"]
    if current_headline == "条件付き有望":
        return "△ 普通だが工夫が必要", ["一定の余地はありますが、条件整理が必要です。"]
    if current_headline == "慎重検討":
        return "× 厳しいので参入非推奨", ["主要指標上、慎重に見るべき要素が多いです。"]
    return "△ 普通だが工夫が必要", ["地域タイプと主要指標を合わせて追加確認が必要です。"]


def get_region_type_comments(region_type: str, metrics: list[dict[str, Any]], region: dict[str, Any]) -> dict[str, Any]:
    sakoju_view = region.get("sakoju_view", "不明")
    sakoju_impact = region.get("sakoju_impact", "不明")

    templates = {
        "地方都市型": {
            "type_summary": "自宅兼事務所・夫婦経営と相性が良く、固定費を抑えれば小規模でも成立しやすい地域です。",
            "strengths": [
                "市場規模と競合数のバランスが比較的良い",
                "サ高住は競合より紹介元になりやすい",
                "住居兼事務所として固定費を抑えやすい",
            ],
            "risks": [
                "エリアを広げすぎると移動効率が悪化する",
                "固定費が高くなると一気に収益性が落ちる",
            ],
            "strategies": [
                "自宅兼事務所で固定費を抑える",
                "サ高住や居宅との関係構築を重視する",
                "狭いエリアに集中する",
            ],
        },
        "供給不足型過疎地": {
            "type_summary": "需要が供給を上回りやすく、対応エリアを絞れば軽量運営で利用者を拾いやすい地域です。",
            "strengths": [
                "1事業所あたりの潜在利用者が多い",
                "新規参入が歓迎されやすい",
                "早期に軌道化できる可能性がある",
            ],
            "risks": [
                "エリアを広げすぎると移動効率と人材確保が崩れやすい",
                "人口密集エリアを外すと移動効率が悪化する",
            ],
            "strategies": [
                "人口密集エリアに絞る",
                "地域分担型の戦い方を意識する",
                "居宅を抱えず軽量に運営し、紹介元との関係構築に集中する",
                "過度な拡大より安定運営を優先する",
            ],
        },
        "超過疎地型": {
            "type_summary": "高齢化率が高く見えても高齢者の絶対数が少なく、移動効率と売上上限の面で厳しい地域です。",
            "strengths": [
                "競合が少なければ一定の需要を拾える可能性はある",
            ],
            "risks": [
                "全域を取っても売上上限が低い可能性がある",
                "山間部や線状集落では移動効率が悪い",
                "利用者1人の離脱が売上に大きく響く",
            ],
            "strategies": [
                "所有物件や低固定費を前提にする",
                "夫婦中心で現場に出る",
                "250万円ではなく低めの損益分岐点を前提に考える",
            ],
        },
        "大都市型": {
            "type_summary": "市場規模は大きい一方、既存事業所・居宅併設・サ高住との競争が激しく、0スタートの難易度が高い地域です。",
            "strengths": [
                "市場規模が大きく、軌道化できれば伸びしろがある",
                "高齢者人口が多く需要自体は存在する",
            ],
            "risks": [
                "ケアマネ関係なしの新規獲得が難しい",
                "居宅併設事業所同士の紹介構造が強い",
                "サ高住も実質競合になりやすい",
            ],
            "strategies": [
                "居宅介護支援併設を検討する",
                "承継や既存地盤の引継ぎを優先する",
                "0スタートならエリア集中と強い差別化が必須",
            ],
        },
        "超高密集競争型": {
            "type_summary": "移動効率は良いものの、市場規模に対して競合が多く、伸びしろが小さいため新規単独参入は厳しい地域です。",
            "strengths": [
                "移動距離は短く、高密度運営はしやすい",
            ],
            "risks": [
                "競合過多で利用者獲得が難しい",
                "サ高住の500m圏カバー率が高いと実質競合が強い",
                "市場拡張余地が小さい",
            ],
            "strategies": [
                "地盤引継ぎや承継がない限り参入慎重",
                "ケアマネ併設や既存利用者引継ぎを前提にする",
                "新規0スタートは原則避ける",
            ],
        },
        "判定保留": {
            "type_summary": "地域タイプ分類に必要なデータが一部不足しているため、地域タイプは判定保留です。取得できている指標をもとに、暫定的な確認として見てください。",
            "strengths": [
                "取得できている指標の範囲では、個別項目の確認は可能です",
            ],
            "risks": [
                "高齢者人口、可住地面積、利用者数などが不足すると、密度・市場規模・余力倍率の精度が落ちます",
                "不足項目を補完するまでは、地域タイプと総合判定を確定判断に使わない方が安全です",
            ],
            "strategies": [
                "不足している列名や空欄を先に確認する",
                "可住地面積と訪問介護利用者数を優先して補完する",
                "補完後に地域タイプと市場判定を再確認する",
            ],
        },
    }

    selected = templates.get(region_type, templates["地方都市型"])
    if region_type in {"地方都市型", "供給不足型過疎地"}:
        selected = selected.copy()
        selected["strengths"] = [*selected["strengths"], f"サ高住の見方は「{sakoju_view}」"]
    if region_type == "超高密集競争型":
        selected = selected.copy()
        selected["risks"] = [*selected["risks"], f"現在のサ高住競合影響は「{sakoju_impact}」"]

    return selected


def region_market_comments(region: dict[str, Any], metrics: list[dict[str, Any]]) -> list[str]:
    region_type = region.get("type", "地方都市型")
    selected = get_region_type_comments(region_type, metrics, region)

    return [
        f"**地域タイプを踏まえた判定**\n{selected['type_summary']}",
        "**強み**\n" + "\n".join(f"- {item}" for item in selected["strengths"]),
        "**リスク**\n" + "\n".join(f"- {item}" for item in selected["risks"]),
        "**推奨戦略**\n" + "\n".join(f"- {item}" for item in selected["strategies"]),
    ]


def get_entry_conditions(region_type: str, metrics: list[dict[str, Any]], region: dict[str, Any]) -> dict[str, list[str]]:
    conditions = {
        "地方都市型": {
            "required": [
                "固定費を抑えた運営",
                "狭いエリアに集中すること",
            ],
            "recommended": [
                "住居兼事務所モデル",
                "夫婦経営または小規模高稼働モデル",
                "サ高住・居宅との関係構築",
            ],
            "avoid": [
                "事務所家賃だけで高額な物件を借りる",
                "最初から広範囲に営業する",
                "登録ヘルパー頼みで固定利用者を持たない",
            ],
        },
        "供給不足型過疎地": {
            "required": [
                "人口密集エリアに絞る",
                "移動距離を増やしすぎない",
                "固定費を低く抑える",
            ],
            "recommended": [
                "地域包括・居宅との関係構築",
                "地域分担型の運営",
                "少人数で安定稼働する体制",
            ],
            "avoid": [
                "市町村全域を面で取りに行く",
                "大きな事務所を借りる",
                "利用者分布を見ずに開業する",
            ],
        },
        "超過疎地型": {
            "required": [
                "所有物件または極端に低い固定費",
                "夫婦または家族中心で現場に出る",
                "250万円未満の損益分岐点を想定する",
            ],
            "recommended": [
                "既存事業所の撤退・閉鎖後の受け皿",
                "地域全体の支援役として動く",
                "行政・包括との強い関係",
            ],
            "avoid": [
                "通常の250万円売上モデルを前提にする",
                "人を雇って拡大する前提で始める",
                "家賃・人件費を都市部並みに考える",
            ],
        },
        "大都市型": {
            "required": [
                "ケアマネ関係構築",
                "強い差別化",
                "開業初期の赤字耐性",
            ],
            "recommended": [
                "居宅介護支援併設",
                "承継・暖簾分け・既存地盤の引継ぎ",
                "高密度エリア集中",
            ],
            "avoid": [
                "利用者ゼロ・ケアマネ関係ゼロの0スタート",
                "ただ開業すれば紹介が来るという前提",
                "高額家賃で固定費を膨らませる",
            ],
        },
        "超高密集競争型": {
            "required": [
                "既存地盤の引継ぎ",
                "ケアマネ関係または居宅併設",
                "競合との差別化",
            ],
            "recommended": [
                "承継型",
                "既存利用者付き独立",
                "高密度巡回モデル",
            ],
            "avoid": [
                "完全0スタート",
                "競合数を軽視する",
                "サ高住の外部派遣圏を軽視する",
            ],
        },
        "判定保留": {
            "required": [
                "不足している基礎データを確認する",
                "可住地面積・利用者数・高齢者人口を補完する",
            ],
            "recommended": [
                "補完後に地域タイプと経営モデル適性を再判定する",
                "取得できている指標は暫定情報として扱う",
            ],
            "avoid": [
                "データ不足のまま参入可否を確定する",
                "市場規模や移動効率を推測だけで判断する",
            ],
        },
    }

    return conditions.get(region_type, conditions["地方都市型"])


def get_sales_strategy(metrics: list[dict[str, Any]], region: dict[str, Any]) -> dict[str, list[str]]:
    region_type = region.get("type", "地方都市型")
    sakoju_view = str(region.get("sakoju_view", ""))
    client_acquisition = region.get("client_acquisition_difficulty", {})
    client_score = client_acquisition.get("score")

    strategies = {
        "地方都市型": {
            "first_targets": [
                "サ高住・住宅型有料老人ホーム",
                "居宅介護支援事業所",
                "地域包括支援センター",
            ],
            "priority_actions": [
                "サ高住は競合ではなく紹介元として関係構築する",
                "居宅を抱えず、軽量な訪問介護単独モデルで固定費と管理負荷を抑える",
                "月初は実績業務で忙しいため、営業は11日〜20日頃を狙う",
                "空き情報と対応エリアを1枚資料で届ける",
            ],
            "mistakes_to_avoid": [
                "サ高住を一律に競合扱いして関係構築を避ける",
                "最初から広範囲に営業する",
                "ケアマネに空き状況や対応エリアを具体的に伝えない",
            ],
        },
        "供給不足型過疎地": {
            "first_targets": [
                "地域包括支援センター",
                "居宅介護支援事業所",
                "行政・地域のキーパーソン",
            ],
            "priority_actions": [
                "供給不足の受け皿として存在を伝える",
                "人口密集エリアに絞って受ける",
                "居宅併設よりも軽量運営を優先し、常勤・書類・管理負荷を増やしすぎない",
                "地域分担型の姿勢を出す",
            ],
            "mistakes_to_avoid": [
                "市町村全域を最初から取りに行く",
                "移動距離を考えずに依頼を受ける",
                "地域包括や行政との関係構築を後回しにする",
            ],
        },
        "超過疎地型": {
            "first_targets": [
                "地域包括支援センター",
                "行政",
                "既存事業所・撤退予定事業所",
            ],
            "priority_actions": [
                "通常の営業より地域インフラの受け皿として動く",
                "行政・包括との信頼関係を最優先にする",
                "250万円達成より維持可能性を重視する",
            ],
            "mistakes_to_avoid": [
                "通常の都市部型営業で利用者を取りに行く",
                "250万円達成を前提に営業計画を組む",
                "撤退・閉鎖情報や地域課題の把握を怠る",
            ],
        },
        "大都市型": {
            "first_targets": [
                "居宅介護支援事業所",
                "既存人脈",
                "承継・引継ぎ先",
            ],
            "priority_actions": [
                "ケアマネとの関係作りを最優先にする",
                "居宅併設や承継がない場合は差別化を明確にする",
                "高密度に回れる小さな商圏から始める",
            ],
            "mistakes_to_avoid": [
                "利用者ゼロ・ケアマネ関係ゼロで飛び込み営業だけに頼る",
                "ただ開業すれば紹介が来ると考える",
                "競合が多いエリアで差別化なしに営業する",
            ],
        },
        "超高密集競争型": {
            "first_targets": [
                "既存地盤",
                "引継ぎ可能な事業所",
                "ケアマネ人脈",
            ],
            "priority_actions": [
                "新規営業より地盤引継ぎを優先する",
                "サ高住外部派遣圏を避けて商圏を絞る",
                "高密度巡回できる既存利用者付きの導線を探す",
            ],
            "mistakes_to_avoid": [
                "完全0スタートで参入する",
                "競合数を軽視して営業する",
                "サ高住の外部派遣圏を軽視する",
            ],
        },
        "判定保留": {
            "first_targets": [
                "地域包括支援センター",
                "居宅介護支援事業所",
                "行政・地域の相談窓口",
            ],
            "priority_actions": [
                "不足データを補完してから営業範囲を決める",
                "空き情報と対応可能エリアだけ先に整理する",
                "地域の供給不足・撤退情報をヒアリングする",
            ],
            "mistakes_to_avoid": [
                "地域タイプ不明のまま広範囲に営業する",
                "市場規模や利用者分布を確認せずに固定費をかける",
                "不足データを推測だけで埋めて営業判断する",
            ],
        },
    }

    selected = {key: list(value) for key, value in strategies.get(region_type, strategies["地方都市型"]).items()}

    if "紹介元寄り" in sakoju_view and "サ高住・住宅型有料老人ホーム" not in selected["first_targets"]:
        selected["first_targets"].insert(0, "サ高住・住宅型有料老人ホーム")
        selected["priority_actions"].append("サ高住は紹介元寄りに見て、関係構築を優先する")

    if client_score is not None and client_score >= 70:
        selected["priority_actions"].append("紹介元を作ってから利用者獲得に入る")
        selected["mistakes_to_avoid"].append("紹介元なしで利用者獲得を始める")

    return selected


def get_startup_pattern_recommendation(metrics: list[dict[str, Any]], region: dict[str, Any]) -> dict[str, Any]:
    region_type = region.get("type", "地方都市型")
    patterns = {
        "地方都市型": {
            "best": [
                "自宅兼事務所 × 夫婦経営",
                "小規模高稼働型",
            ],
            "possible": [
                "賃貸事務所型",
                "単独開業型",
            ],
            "avoid": [
                "高額事務所家賃型",
                "広範囲営業型",
            ],
            "comment": "固定費を抑え、狭い商圏で稼働率を高める開業パターンと相性が良い地域です。",
        },
        "供給不足型過疎地": {
            "best": [
                "自宅兼事務所 × 地域密着型",
                "小規模地域分担型",
            ],
            "possible": [
                "夫婦経営型",
                "既存事業所撤退後の受け皿型",
            ],
            "avoid": [
                "市町村全域を最初から取りに行く型",
                "人を雇って拡大する前提の開業",
            ],
            "comment": "需要の受け皿になりやすい一方、広域対応で崩れやすいため、人口密集エリアに絞る開業が現実的です。",
        },
        "超過疎地型": {
            "best": [
                "所有物件 × 夫婦現場型",
                "超低固定費型",
            ],
            "possible": [
                "既存事業所撤退後の受け皿型",
            ],
            "avoid": [
                "通常の250万円売上モデル",
                "賃貸事務所型",
                "人材雇用拡大型",
            ],
            "comment": "通常の売上拡大型ではなく、固定費と損益分岐点を極端に下げる開業パターンでなければ厳しい地域です。",
        },
        "大都市型": {
            "best": [
                "居宅介護支援併設型",
                "承継・暖簾分け型",
                "既存地盤引継ぎ型",
            ],
            "possible": [
                "高密度都市集中型",
                "強い差別化を持つ単独開業",
            ],
            "avoid": [
                "利用者ゼロ・ケアマネ関係ゼロの完全0スタート",
                "高額家賃での単独開業",
            ],
            "comment": "市場は大きいものの紹介競争が強いため、居宅併設・承継・既存地盤のいずれかを持つ開業が向いています。",
        },
        "超高密集競争型": {
            "best": [
                "承継・引継ぎ型",
                "既存利用者付き独立型",
            ],
            "possible": [
                "居宅併設型",
                "ケアマネ人脈あり開業",
            ],
            "avoid": [
                "完全0スタート",
                "競合分析なしの新規参入",
                "サ高住外部派遣圏を無視した開業",
            ],
            "comment": "移動効率は良くても競争が強いため、新規開業よりも既存地盤や利用者の引継ぎを前提にした開業が向いています。",
        },
        "判定保留": {
            "best": [
                "データ補完後に再判定",
            ],
            "possible": [
                "小規模・低固定費での暫定検討",
            ],
            "avoid": [
                "データ不足のまま高額投資する開業",
                "利用者分布を確認しない広範囲営業型",
            ],
            "comment": "地域タイプ判定に必要なデータが不足しているため、開業パターンは暫定評価として扱ってください。",
        },
    }

    return patterns.get(region_type, patterns["地方都市型"])


def calculate_client_acquisition_difficulty(
    metrics: list[dict[str, Any]], region: dict[str, Any]
) -> dict[str, Any]:
    region_type = region.get("type", "地方都市型")
    competitors = metric_number(metrics, "実質競合数")
    capacity_ratio = metric_number(metrics, "競争後達成余力倍率")
    users_per_office = metric_number(metrics, "1事業所あたり潜在利用者数")
    sakoju_cover_rate = region.get("sakoju_cover_rate")
    sakoju_view = str(region.get("sakoju_view", ""))
    competition_penalty = region.get("competition_density_penalty", calculate_competition_density_penalty(competitors))

    score = 50
    reasons = []
    barriers = []

    def add(points: int, reason: str, barrier: str | None = None) -> None:
        nonlocal score
        score += points
        reasons.append(reason)
        if barrier and barrier not in barriers:
            barriers.append(barrier)

    def subtract(points: int, reason: str) -> None:
        nonlocal score
        score -= points
        reasons.append(reason)

    if region_type in {"地方都市型", "供給不足型過疎地"}:
        subtract(15, "地方都市・供給不足地域では、需要に対して供給が不足しやすい傾向があります。")
        if capacity_ratio is not None:
            high_competition = competitors is not None and competitors >= 50
            if capacity_ratio >= 1.8 and not high_competition:
                subtract(22, "競争後達成余力倍率が高く、紹介が十分回る余地があるため、軽量運営でも利用者獲得しやすい見立てです。")
            elif capacity_ratio >= 1.4 and not high_competition:
                subtract(18, "競争後達成余力倍率が1.4以上あり、地方・供給不足地域では需要余力を拾いやすい見立てです。")
            elif high_competition:
                add(15, "競争後達成余力倍率は残っていますが、実質競合数が50以上のため紹介獲得は激戦寄りです。", "競争密度")
            elif capacity_ratio >= 1.1:
                subtract(8, "競争後達成余力倍率が中間水準で、地域構造次第では紹介獲得余地があります。")
            elif capacity_ratio < 0.8:
                add(15, "競争後達成余力倍率が低く、地方・供給不足地域でも利用者獲得は厳しめです。", "競合密度")
    if region_type in {"大都市型", "超高密集競争型"}:
        add(20, "都市部・高密集地域では既存事業所との紹介競争が強くなりやすいです。", "ケアマネ紹介構造")
        add(10, "居宅介護支援併設事業所や既存地盤を持つ事業所が優位になりやすいです。", "既存事業所の地盤")
    if region_type == "超過疎地型":
        add(5, "利用者の絶対数が少なく、獲得できる母数が限られやすいです。")

    if competitors is not None:
        if competitors >= 8:
            if (
                region_type in {"地方都市型", "供給不足型過疎地"}
                and capacity_ratio is not None
                and capacity_ratio >= 1.4
                and competitors < 50
            ):
                add(10, f"実質競合数は{competitors:.1f}事業所ありますが、需要余力があり、都市部ほど紹介競争は重く見ません。", "競合密度")
            else:
                add(20, f"実質競合数が{competitors:.1f}事業所と多く、利用者獲得競争が強いです。", "競合密度")
        elif competitors >= 5:
            add(12, f"実質競合数が{competitors:.1f}事業所あり、一定の競争があります。", "競合密度")
        elif competitors <= 2:
            subtract(15, f"実質競合数が{competitors:.1f}事業所と少なく、新規利用者を拾いやすい可能性があります。")

    density_points = int(competition_penalty.get("difficulty_points", 0))
    if (
        region_type in {"地方都市型", "供給不足型過疎地"}
        and capacity_ratio is not None
        and capacity_ratio >= 1.4
        and not (competitors is not None and competitors >= 80)
    ):
        density_points = max(0, density_points - 6)
    if density_points:
        add(density_points, str(competition_penalty.get("comment")), "競争密度")

    if users_per_office is not None:
        if users_per_office >= 80:
            subtract(20, "1事業所あたり潜在利用者数が多く、需要が供給を上回る可能性があります。")
        elif users_per_office >= 40:
            subtract(10, "1事業所あたり潜在利用者数が一定以上あり、獲得余地があります。")
        elif users_per_office < 25:
            add(15, "1事業所あたり潜在利用者数が少なく、伸びしろが限定的です。", "競合密度")

    if sakoju_cover_rate is not None:
        if sakoju_cover_rate >= 0.30:
            add(15, "サ高住500m圏カバー率が高く、外部派遣圏との競合に注意が必要です。", "サ高住外部派遣")
        elif sakoju_cover_rate >= 0.10:
            add(8, "サ高住500m圏カバー率が一定以上あり、一部競合になる可能性があります。", "サ高住外部派遣")

    if "紹介元寄り" in sakoju_view:
        subtract(8, "サ高住は競合より紹介元寄りに見られ、紹介導線になる可能性があります。")

    if region_type in {"大都市型", "超高密集競争型"}:
        for barrier in ["居宅介護支援併設競争", "既存事業所の地盤"]:
            if barrier not in barriers:
                barriers.append(barrier)

    score = cap_score(score)
    if score >= 85:
        level = "非常に高い"
    elif score >= 70:
        level = "高い"
    elif score >= 45:
        level = "普通"
    elif score >= 25:
        level = "低い"
    else:
        level = "非常に低い"

    if not reasons:
        reasons.append("取得できている指標からは、利用者獲得難易度を大きく上下させる要素は限定的です。")
    if not barriers:
        barriers.append("大きな壁は限定的")

    return {
        "level": level,
        "score": score,
        "reasons": reasons,
        "barriers": barriers,
    }


def calculate_movement_efficiency(metrics: list[dict[str, Any]], region: dict[str, Any]) -> dict[str, Any]:
    region_type = region.get("type", "地方都市型")
    elderly_density = region.get("elderly_density")
    habitable_area = metric_number(metrics, "可住地面積")
    competitors = region.get("effective_competitors")
    users_per_office = region.get("users_per_office")

    score = 50
    reasons = []

    def add(points: int, reason: str) -> None:
        nonlocal score
        score += points
        reasons.append(reason)

    def subtract(points: int, reason: str) -> None:
        nonlocal score
        score -= points
        reasons.append(reason)

    if elderly_density is not None:
        if elderly_density >= 1500:
            add(25, "高齢者人口密度が高く、高密度巡回がしやすい地域です。")
        elif elderly_density >= 700:
            add(15, "高齢者人口密度が一定以上あり、訪問先のまとまりが期待できます。")
        elif elderly_density < 80:
            subtract(25, "高齢者人口密度が低く、利用者が分散しやすい地域です。")
        elif elderly_density < 200:
            subtract(10, "高齢者人口密度がやや低く、移動距離が伸びやすい可能性があります。")

    if habitable_area is not None:
        if habitable_area <= 15:
            add(25, "可住地面積が小さく、短距離での巡回がしやすい地域です。")
        elif habitable_area <= 30:
            add(15, "可住地面積が比較的小さく、訪問ルートを組みやすい地域です。")
        elif habitable_area >= 100:
            subtract(25, "可住地面積が広く、利用者分散リスクがあります。")
        elif habitable_area >= 60:
            subtract(12, "可住地面積に広がりがあり、訪問範囲の絞り込みが重要です。")

    if users_per_office is not None:
        if users_per_office >= 80:
            add(10, "1事業所あたり潜在利用者数が多く、まとまった需要を拾える可能性があります。")
        elif users_per_office < 25:
            subtract(8, "1事業所あたり潜在利用者数が少なく、効率的なルート化には工夫が必要です。")

    if competitors is not None:
        if competitors >= 8:
            subtract(5, "実質競合数が多く、近隣利用者を取り切りにくい可能性があります。")
        elif competitors <= 2:
            add(5, "実質競合数が少なく、訪問エリアを組み立てやすい可能性があります。")

    if region_type == "超高密集競争型":
        add(15, "超高密集競争型のため、移動距離自体は短くなりやすい地域です。")
        reasons.append("ただし、移動効率は高い一方で、競争効率は悪い可能性があります。")
    elif region_type == "大都市型":
        add(10, "大都市型の一部では高密度巡回が可能です。")
    elif region_type == "超過疎地型":
        subtract(20, "超過疎地型では山間部・線状集落型の分散リスクに注意が必要です。")
    elif region_type == "供給不足型過疎地":
        subtract(8, "供給不足地域でも、人口密集エリアを外すと移動効率が悪化します。")
    elif region_type == "地方都市型":
        add(5, "地方都市の中心部に絞れば、一定の巡回効率が期待できます。")

    score = cap_score(score)
    if score >= 85:
        level = "非常に良い"
    elif score >= 70:
        level = "良い"
    elif score >= 50:
        level = "普通"
    elif score >= 30:
        level = "悪い"
    else:
        level = "非常に悪い"

    if elderly_density is None:
        elderly_density_factor = "不明"
    elif elderly_density >= 700:
        elderly_density_factor = "高め。訪問先がまとまりやすい"
    elif elderly_density >= 200:
        elderly_density_factor = "中程度。中心部への集中が重要"
    else:
        elderly_density_factor = "低め。利用者分散に注意"

    if habitable_area is None:
        habitable_area_factor = "不明"
    elif habitable_area <= 30:
        habitable_area_factor = "狭め。短距離巡回しやすい"
    elif habitable_area <= 80:
        habitable_area_factor = "中程度。エリア設計次第"
    else:
        habitable_area_factor = "広め。移動距離が伸びやすい"

    if competitors is None:
        competition_factor = "不明"
    elif competitors >= 8:
        competition_factor = "高い。近隣利用者の獲得競争が強い"
    elif competitors >= 4:
        competition_factor = "中程度。競合を意識したルート設計が必要"
    else:
        competition_factor = "低め。エリアを組み立てやすい可能性"

    if score >= 70:
        route_factor = "高密度巡回が可能"
    elif score >= 50:
        route_factor = "中心部に絞れば巡回可能"
    else:
        route_factor = "利用者分散リスクが高い"

    if not reasons:
        reasons.append("取得できている指標からは、移動効率を大きく上下させる要素は限定的です。")

    return {
        "score": score,
        "level": level,
        "reasons": reasons,
        "factors": {
            "高齢者人口密度": elderly_density_factor,
            "可住地面積": habitable_area_factor,
            "競合密度": competition_factor,
            "巡回効率": route_factor,
        },
    }


def risk_level(score: int) -> str:
    if score >= 80:
        return "非常に高い"
    if score >= 60:
        return "高い"
    if score >= 30:
        return "普通"
    return "低い"


def calculate_collapse_risk(metrics: list[dict[str, Any]], region: dict[str, Any]) -> dict[str, Any]:
    region_type = region.get("type", "地方都市型")
    elderly_population = metric_number(metrics, "高齢者人口")
    habitable_area = metric_number(metrics, "可住地面積")
    competitors = metric_number(metrics, "実質競合数")
    users = metric_number(metrics, "訪問介護利用者数")
    market_size = metric_number(metrics, "市場規模")
    capacity_ratio = metric_number(metrics, "達成余力倍率")
    users_per_office = metric_number(metrics, "1事業所あたり潜在利用者数")
    sakoju_cover_rate = region.get("sakoju_cover_rate")
    movement_efficiency = region.get("movement_efficiency", {})
    movement_score = movement_efficiency.get("score")

    risks = {
        "human_resource_risk": 25,
        "fixed_cost_risk": 25,
        "competition_risk": 25,
        "movement_risk": 25,
        "client_concentration_risk": 25,
        "regional_decline_risk": 25,
    }
    reasons_by_key = {key: [] for key in risks}

    def add(key: str, points: int, reason: str) -> None:
        risks[key] += points
        reasons_by_key[key].append(reason)

    if region_type in {"超過疎地型", "供給不足型過疎地"}:
        add("human_resource_risk", 25, "過疎・供給不足地域では採用とシフト維持が難しくなりやすい")
    if region_type == "超過疎地型":
        add("movement_risk", 25, "超過疎地型で利用者が分散しやすい")
        add("client_concentration_risk", 20, "超過疎地型で利用者母数が少ない")
        add("regional_decline_risk", 35, "超過疎地型で地域縮小リスクが高い")
    if region_type in {"大都市型", "超高密集競争型"}:
        add("fixed_cost_risk", 20, "都市部・高密集地域では固定費が高くなりやすい")
        add("competition_risk", 25, "都市部・高密集地域では競争が激しくなりやすい")
    if region_type == "超高密集競争型":
        add("competition_risk", 20, "超高密集競争型で競合過多になりやすい")

    if movement_score is not None:
        if movement_score < 30:
            add("human_resource_risk", 20, "移動効率指数が非常に低く人員負担が大きい")
            add("movement_risk", 35, "移動効率指数が非常に低い")
        elif movement_score < 50:
            add("human_resource_risk", 12, "移動効率指数が低くシフト負担が増えやすい")
            add("movement_risk", 25, "移動効率指数が低い")

    if habitable_area is not None:
        if habitable_area >= 100:
            add("human_resource_risk", 15, "可住地面積が広く移動負担が大きい")
            add("movement_risk", 25, "可住地面積が広く移動効率が崩れやすい")
        elif habitable_area >= 60:
            add("movement_risk", 12, "可住地面積が広めで訪問範囲の管理が必要")

    if market_size is not None:
        if market_size < 2_500_000:
            add("fixed_cost_risk", 35, "市場規模が小さく固定費を吸収しにくい")
            add("client_concentration_risk", 25, "市場規模が小さく少数利用者への依存が強くなりやすい")
            add("regional_decline_risk", 25, "市場規模が小さく地域縮小の影響を受けやすい")
        elif market_size < 5_000_000:
            add("fixed_cost_risk", 20, "市場規模がやや小さく固定費に注意が必要")
            add("client_concentration_risk", 15, "市場規模がやや小さく利用者集中に注意が必要")

    if capacity_ratio is not None:
        if capacity_ratio < 1:
            add("fixed_cost_risk", 30, "競争後達成余力倍率が低く安定運営ラインに届きにくい")
        elif capacity_ratio < 1.6:
            add("fixed_cost_risk", 15, "競争後達成余力倍率がやや低い")

    if competitors is not None:
        if competitors >= 8:
            add("competition_risk", 30, "実質競合数が多い")
        elif competitors >= 5:
            add("competition_risk", 18, "実質競合数が一定以上ある")

    if sakoju_cover_rate is not None:
        if sakoju_cover_rate >= 0.30:
            add("competition_risk", 25, "サ高住500m圏カバー率が高い")
        elif sakoju_cover_rate >= 0.10:
            add("competition_risk", 12, "サ高住500m圏カバー率が一定以上ある")

    if users is not None:
        if users < 60:
            add("client_concentration_risk", 25, "訪問介護利用者数が少ない")
        elif users < 120:
            add("client_concentration_risk", 12, "訪問介護利用者数がやや少ない")

    if users_per_office is not None and users_per_office < 25:
        add("movement_risk", 10, "利用者密度が低く効率的な巡回が組みにくい")

    if elderly_population is not None:
        if elderly_population < 3_000:
            add("regional_decline_risk", 30, "高齢者絶対数が少ない")
        elif elderly_population < 6_000:
            add("regional_decline_risk", 15, "高齢者絶対数がやや少ない")

    risks = {key: cap_score(value) for key, value in risks.items()}
    pattern_names = {
        "human_resource_risk": "人材崩壊型",
        "fixed_cost_risk": "固定費崩壊型",
        "competition_risk": "競争崩壊型",
        "movement_risk": "移動効率崩壊型",
        "client_concentration_risk": "利用者集中崩壊型",
        "regional_decline_risk": "地域縮小崩壊型",
    }
    highest_key = max(risks, key=risks.get)
    main_reasons = reasons_by_key.get(highest_key) or ["主要指標の組み合わせから相対的にリスクが高い項目です。"]

    return {
        **risks,
        "main_collapse_pattern": pattern_names[highest_key],
        "reasons": main_reasons,
        "risk_levels": {key: risk_level(score) for key, score in risks.items()},
    }


def calculate_staffing_difficulty(metrics: list[dict[str, Any]], region: dict[str, Any]) -> dict[str, Any]:
    region_type = region.get("type", "地方都市型")
    habitable_area = metric_number(metrics, "可住地面積")
    competitors = metric_number(metrics, "実質競合数")
    market_size = metric_number(metrics, "市場規模")
    users_per_office = metric_number(metrics, "1事業所あたり潜在利用者数")
    movement_efficiency = region.get("movement_efficiency", {})
    movement_score = movement_efficiency.get("score")

    score = 45
    reasons = []
    recommended_actions = []

    def add(points: int, reason: str) -> None:
        nonlocal score
        score += points
        reasons.append(reason)

    def subtract(points: int, reason: str) -> None:
        nonlocal score
        score -= points
        reasons.append(reason)

    def recommend(action: str) -> None:
        if action not in recommended_actions:
            recommended_actions.append(action)

    if region_type == "超過疎地型":
        add(25, "超過疎地型で地域内の人材母数が少なくなりやすいです。")
        recommend("夫婦・家族中心で現場に出る前提を強める")
        recommend("地域在住ヘルパーを優先して確保する")
    elif region_type == "供給不足型過疎地":
        add(18, "供給不足型過疎地では需要があっても担い手確保が課題になりやすいです。")
        recommend("曜日・エリア固定で仕事を作る")
        recommend("人口密集エリア内で採用と訪問を完結させる")
    elif region_type == "地方都市型":
        subtract(8, "地方都市型では、エリアを絞れば固定シフトを組みやすい可能性があります。")
        recommend("狭いエリアで固定シフトを組む")
    elif region_type == "大都市型":
        add(15, "大都市型では競合が多く、ヘルパー採用競争が強くなりやすいです。")
        recommend("給与条件だけでなく働きやすい固定ルートを提示する")
        recommend("居宅・紹介元と連動して安定した稼働枠を作る")
    elif region_type == "超高密集競争型":
        add(20, "超高密集競争型では競合密度が高く、採用競争が激しくなりやすいです。")
        recommend("短距離・高密度巡回を採用条件として打ち出す")
        recommend("既存利用者付きの承継や引継ぎを優先する")

    if habitable_area is not None:
        if habitable_area >= 100:
            add(20, "可住地面積が広く、移動負担が大きくなりやすいです。")
            recommend("訪問エリアを分け、曜日ごとに担当範囲を固定する")
        elif habitable_area >= 60:
            add(10, "可住地面積が広めで、訪問範囲を広げるほどシフト負担が増えます。")
            recommend("開業初期は中心部に訪問範囲を絞る")
        elif habitable_area <= 30:
            subtract(8, "可住地面積が狭く、短距離で固定ルートを作りやすいです。")

    if movement_score is not None:
        if movement_score < 30:
            add(25, "移動効率指数が非常に低く、ヘルパーの移動負担が大きいです。")
            recommend("長距離訪問を避け、近距離案件を優先して受ける")
        elif movement_score < 50:
            add(15, "移動効率指数が低く、シフト維持に負担が出やすいです。")
            recommend("曜日・時間帯をまとめて訪問ルートを固定する")
        elif movement_score >= 70:
            subtract(10, "移動効率が良く、固定シフトを組みやすい可能性があります。")

    if market_size is not None:
        if market_size < 4_000_000:
            add(15, "市場規模が小さく、十分な稼働時間を提示しにくい可能性があります。")
            recommend("短時間勤務でも成立する低固定費体制を作る")
        elif market_size >= 10_000_000:
            subtract(8, "一定の市場規模があり、稼働枠を作りやすい可能性があります。")

    if competitors is not None:
        if competitors >= 8:
            add(18, "実質競合数が多く、ヘルパー採用競争が激しくなりやすいです。")
            recommend("待遇だけでなく、移動距離・曜日固定など働きやすさで差別化する")
        elif competitors <= 2 and region_type in {"供給不足型過疎地", "超過疎地型"}:
            add(8, "競合が少ない一方で、地域内の人材母数も少ない可能性があります。")

    if users_per_office is not None and users_per_office < 25:
        add(8, "利用者が分散し、安定した稼働枠を作りにくい可能性があります。")

    if not recommended_actions:
        recommended_actions.extend(
            [
                "曜日・エリア固定で仕事を作る",
                "地域在住ヘルパーを優先して確保する",
            ]
        )
    if not reasons:
        reasons.append("取得できている指標からは、人材確保難易度を大きく上下させる要素は限定的です。")

    score = cap_score(score)
    if score >= 80:
        level = "非常に高い"
    elif score >= 60:
        level = "高い"
    elif score >= 30:
        level = "普通"
    else:
        level = "低い"

    return {
        "score": score,
        "level": level,
        "reasons": reasons,
        "recommended_actions": recommended_actions,
    }


def calculate_profitability_difficulty(metrics: list[dict[str, Any]], region: dict[str, Any]) -> dict[str, Any]:
    region_type = region.get("type", "地方都市型")
    capacity_ratio = metric_number(metrics, "達成余力倍率")
    market_size = metric_number(metrics, "市場規模")
    competitors = metric_number(metrics, "実質競合数")
    client_acquisition = region.get("client_acquisition_difficulty", {})
    staffing = region.get("staffing_difficulty", {})
    movement = region.get("movement_efficiency", {})
    collapse_risk = region.get("collapse_risk", {})
    business_model_scores = region.get("business_model_scores", {})
    competition_penalty = region.get("competition_density_penalty", calculate_competition_density_penalty(competitors))

    client_score = client_acquisition.get("score")
    staffing_score = staffing.get("score")
    movement_score = movement.get("score")
    fixed_cost_risk = collapse_risk.get("fixed_cost_risk")
    home_office_score = business_model_scores.get("自宅兼事務所型", 0)
    couple_score = business_model_scores.get("夫婦経営型", 0)

    score = 50
    reasons = []
    actions = []

    def add(points: int, reason: str) -> None:
        nonlocal score
        score += points
        reasons.append(reason)

    def subtract(points: int, reason: str) -> None:
        nonlocal score
        score -= points
        reasons.append(reason)

    def action(item: str) -> None:
        if item not in actions:
            actions.append(item)

    if region_type in {"地方都市型", "供給不足型過疎地"}:
        subtract(10, "地域タイプ上、低固定費で始めれば黒字化を狙いやすい地域です。")
        action("自宅兼事務所で固定費を抑える")
        action("初期は狭いエリアに絞って利用者密度を高める")
    elif region_type == "超過疎地型":
        add(25, "超過疎地型で市場規模と利用者母数に限界が出やすいです。")
        action("250万円未満の低い損益分岐点を前提にする")
        action("夫婦・家族中心で人件費を抑える")
    elif region_type == "大都市型":
        add(15, "大都市型は0スタートの場合、利用者獲得までの赤字期間が長くなりやすいです。")
        action("居宅併設・承継・既存地盤の引継ぎを検討する")
    elif region_type == "超高密集競争型":
        add(25, "超高密集競争型で競合過多になりやすく、黒字化までの難易度が高いです。")
        action("完全0スタートを避け、承継や既存利用者引継ぎを優先する")

    if capacity_ratio is not None:
        if capacity_ratio >= 2.5:
            subtract(20, "競争後達成余力倍率が高く、目標売上までの余裕があります。")
        elif capacity_ratio >= 2:
            subtract(12, "競争後達成余力倍率が有望ライン以上です。")
        elif capacity_ratio < 1:
            add(25, "競争後達成余力倍率が低く、目標売上までの余裕が小さいです。")
            action("固定費を極限まで下げて損益分岐点を下げる")
        elif capacity_ratio < 1.6:
            add(15, "競争後達成余力倍率がやや低く、利用者獲得計画に余裕がありません。")
            action("初期投資を抑え、黒字化ラインを低く設定する")

    if market_size is not None and market_size < 4_000_000:
        add(18, "市場規模が小さく、売上上限が低い可能性があります。")
        action("通常の250万円売上モデルにこだわらず、小さく黒字化する")

    profitability_points = int(competition_penalty.get("profitability_points", 0))
    if profitability_points:
        add(profitability_points, str(competition_penalty.get("comment")))
        action("市場全体ではなく、勝てる紹介元・曜日・対応エリアに絞る")

    if client_score is not None:
        if client_score >= 80:
            add(20, "利用者獲得難易度が非常に高いです。")
            action("ケアマネ・居宅・サ高住など紹介元を先に作る")
        elif client_score >= 60:
            add(12, "利用者獲得難易度が高いです。")
            action("開業初期から紹介ルート開拓を優先する")
        elif client_score < 30:
            subtract(10, "利用者獲得難易度が低く、立ち上がりやすい可能性があります。")

    if staffing_score is not None:
        if staffing_score >= 80:
            add(18, "人材確保難易度が非常に高く、稼働制限が出やすいです。")
            action("採用前提ではなく、まず少人数高稼働で設計する")
        elif staffing_score >= 60:
            add(10, "人材確保難易度が高く、シフト維持に注意が必要です。")
            action("曜日・エリア固定でヘルパーが働きやすい案件を作る")

    if movement_score is not None:
        if movement_score >= 70:
            subtract(10, "移動効率指数が高く、訪問件数を積み上げやすい可能性があります。")
        elif movement_score < 50:
            add(15, "移動効率指数が低く、移動時間で収益性が落ちやすいです。")
            action("訪問範囲を狭くし、移動時間を売上計画に織り込む")

    if fixed_cost_risk is not None:
        if fixed_cost_risk >= 80:
            add(20, "固定費崩壊リスクが非常に高いです。")
            action("家賃・人件費・車両費を固定化しすぎない")
        elif fixed_cost_risk >= 60:
            add(12, "固定費崩壊リスクが高いです。")
            action("住居兼事務所や小規模事務所で固定費を抑える")

    if max(home_office_score, couple_score) >= 75:
        subtract(12, "自宅兼事務所型・夫婦経営型との相性が良く、低固定費で黒字化を狙いやすいです。")
        action("自宅兼事務所・夫婦経営型を軸に初期固定費を抑える")

    if not actions:
        actions.extend(
            [
                "固定費を抑えて損益分岐点を下げる",
                "初期は狭いエリアに絞って利用者密度を高める",
            ]
        )
    if not reasons:
        reasons.append("取得できている指標からは、黒字化難易度を大きく上下させる要素は限定的です。")

    score = cap_score(score)
    if score >= 80:
        level = "非常に高い"
    elif score >= 60:
        level = "高い"
    elif score >= 30:
        level = "普通"
    else:
        level = "低い"

    return {
        "score": score,
        "level": level,
        "reasons": reasons,
        "actions": actions,
    }


def calculate_market_recovery(metrics: list[dict[str, Any]], region: dict[str, Any]) -> dict[str, Any]:
    region_type = str(region.get("type", "判定保留"))
    capacity_ratio = metric_number(metrics, "競争後達成余力倍率")
    market_size = metric_number(metrics, "市場規模")
    competitors = metric_number(metrics, "実質競合数")
    users_per_office = metric_number(metrics, "1事業所あたり潜在利用者数")
    client_acquisition = region.get("client_acquisition_difficulty", {})
    movement_efficiency = region.get("movement_efficiency", {})
    collapse_risk = region.get("collapse_risk", {})
    business_model_scores = region.get("business_model_scores", {})

    client_score = client_acquisition.get("score") if isinstance(client_acquisition, dict) else None
    movement_score = movement_efficiency.get("score") if isinstance(movement_efficiency, dict) else None
    regional_decline_risk = collapse_risk.get("regional_decline_risk") if isinstance(collapse_risk, dict) else None
    high_density_score = business_model_scores.get("高密度都市集中型", 0) if isinstance(business_model_scores, dict) else 0

    score = 50
    reasons: list[str] = []
    risks: list[str] = []

    def add(points: int, reason: str) -> None:
        nonlocal score
        score += points
        if reason not in reasons:
            reasons.append(reason)

    def subtract(points: int, risk: str) -> None:
        nonlocal score
        score -= points
        if risk not in risks:
            risks.append(risk)

    if region_type == "地方都市型":
        add(25, "地方都市型で、利用者が減っても地域包括・居宅から紹介を戻しやすい余地があります。")
        add(10, "小規模高密度型と相性があり、狭い商圏で利用者密度を戻しやすい地域です。")
    elif region_type == "供給不足型過疎地":
        add(18, "需要が供給を上回りやすく、減少後も受け皿として再紹介されやすい地域です。")
        add(8, "地域に歓迎されやすく、立ち上がり直しの初速を作りやすい可能性があります。")
    elif region_type == "超過疎地型":
        subtract(30, "超過疎地型では、利用者減少がそのまま市場縮小になりやすいです。")
        subtract(15, "高齢者絶対数が少なく、減少後に代替利用者を見つけにくい地域です。")
    elif region_type == "大都市型":
        subtract(10, "大都市型では地盤競争が強く、一度減った利用者を取り戻すには紹介元再構築が必要です。")
    elif region_type == "超高密集競争型":
        subtract(28, "超高密集競争型では競合密度が高く、減少後の再獲得が難しくなりやすいです。")

    if client_score is not None:
        if client_score <= 30:
            add(25, "利用者獲得難易度が低く、減っても比較的短期間で戻せる可能性があります。")
        elif client_score <= 45:
            add(15, "利用者獲得難易度が低めで、紹介導線を保てば回復しやすい市場です。")
        elif client_score >= 80:
            subtract(25, "利用者獲得難易度が非常に高く、減少後の回復に時間がかかりやすいです。")
        elif client_score >= 60:
            subtract(15, "利用者獲得難易度が高く、紹介元なしでは回復しにくい市場です。")

    if capacity_ratio is not None:
        if capacity_ratio >= 2:
            add(15, "競争後達成余力倍率が高く、需要余力から回復余地を見込みやすいです。")
        elif capacity_ratio >= 1.4:
            add(10, "競争後達成余力倍率が一定以上あり、減少後の再獲得余地があります。")
        elif capacity_ratio < 1:
            subtract(15, "競争後達成余力倍率が低く、回復前に競合へ流れやすい可能性があります。")

    if users_per_office is not None:
        if users_per_office >= 80:
            add(15, "1事業所あたり潜在利用者数が多く、供給不足による回復余地があります。")
        elif users_per_office >= 40:
            add(8, "1事業所あたり潜在利用者数が一定以上あり、利用者の補充余地があります。")
        elif users_per_office < 25:
            subtract(15, "1事業所あたり潜在利用者数が少なく、代替利用者を拾いにくい市場です。")

    if competitors is not None:
        if competitors >= 80:
            subtract(28, "実質競合数が非常に多く、回復局面でも利用者の取り合いが強くなります。")
        elif competitors >= 50:
            subtract(18, "実質競合数が多く、減少後の再獲得は紹介元競争になりやすいです。")
        elif competitors <= 6:
            add(10, "競合が少なく、地域内の受け皿として利用者が戻りやすい可能性があります。")

    if market_size is not None:
        if market_size < 2_500_000:
            subtract(20, "市場規模が小さく、利用者減少が売上上限の低下に直結しやすいです。")
        elif market_size < 4_000_000:
            subtract(10, "市場規模が小さめで、回復できる利用者母数に限界があります。")
        elif market_size >= 10_000_000:
            add(8, "一定以上の市場規模があり、利用者補充の母数があります。")

    if movement_score is not None:
        if movement_score >= 70:
            add(8, "移動効率が高く、既存ルートへ新規利用者を組み込みやすいです。")
        elif movement_score < 50:
            subtract(10, "移動効率が低く、回復しても広域分散で収益性が戻りにくい可能性があります。")

    if regional_decline_risk is not None and regional_decline_risk >= 60:
        subtract(15, "地域縮小リスクが高く、利用者減少後の自然回復は見込みにくいです。")

    if high_density_score >= 70:
        add(8, "小規模高密度型との相性が高く、利用者密度を再構築しやすいです。")

    if region_type == "超過疎地型":
        score = min(score, 40)
        if "超過疎地型では、回復余地が一部あっても利用者減少が市場縮小に直結しやすいため、上限を低めに見ます。" not in risks:
            risks.append("超過疎地型では、回復余地が一部あっても利用者減少が市場縮小に直結しやすいため、上限を低めに見ます。")

    if not reasons:
        reasons.append("取得できている指標からは、一定の市場回復余地があります。")
    if not risks:
        risks.append("大きな回復阻害要因は限定的ですが、紹介元との関係維持は必要です。")

    score = cap_score(score)
    if score >= 85:
        level = "非常に高い"
    elif score >= 70:
        level = "高い"
    elif score >= 50:
        level = "普通"
    elif score >= 30:
        level = "低い"
    else:
        level = "非常に低い"

    return {
        "score": score,
        "level": level,
        "reasons": reasons,
        "risks": risks,
    }


def calculate_market_future_potential(metrics: list[dict[str, Any]], region: dict[str, Any]) -> dict[str, Any]:
    region_type = str(region.get("type", "判定保留"))
    theoretical_capacity_ratio = metric_number(metrics, "理論市場余力倍率")
    competitive_capacity_ratio = metric_number(metrics, "競争後達成余力倍率")
    market_size = metric_number(metrics, "市場規模")
    competitors = metric_number(metrics, "実質競合数")
    users_per_office = metric_number(metrics, "1事業所あたり潜在利用者数")
    elderly_population = metric_number(metrics, "高齢者人口")
    market_recovery = region.get("market_recovery", {})
    staffing_difficulty = region.get("staffing_difficulty", {})
    business_model_scores = region.get("business_model_scores", {})

    recovery_score = market_recovery.get("score") if isinstance(market_recovery, dict) else None
    staffing_score = staffing_difficulty.get("score") if isinstance(staffing_difficulty, dict) else None
    high_density_score = business_model_scores.get("高密度都市集中型", 0) if isinstance(business_model_scores, dict) else 0
    succession_score = business_model_scores.get("承継・引継ぎ型", 0) if isinstance(business_model_scores, dict) else 0

    score = 50
    reasons: list[str] = []
    risks: list[str] = []

    def add(points: int, reason: str) -> None:
        nonlocal score
        score += points
        if reason not in reasons:
            reasons.append(reason)

    def subtract(points: int, risk: str) -> None:
        nonlocal score
        score -= points
        if risk not in risks:
            risks.append(risk)

    if region_type == "地方都市型":
        add(28, "地方中心都市として、医療・サ高住・介護資源・家族アクセスが集まりやすい地域です。")
        add(18, "中途半端な事業所が減っても需要そのものは残りやすく、生き残った事業所へ利用者・人材が集まりやすい見立てです。")
    elif region_type == "供給不足型過疎地":
        add(12, "短中期では供給不足の受け皿として立ち上がりやすい地域です。")
        subtract(10, "周辺中核都市へ利用者・人材が流れる可能性があり、市場容量は有限です。")
        subtract(8, "同タイプの新規事業所が1件増えるだけでも、市場バランスが変わりやすい地域です。")
    elif region_type == "超過疎地型":
        subtract(35, "高齢者絶対数が少なく、10年後は利用者減少が市場縮小に直結しやすい地域です。")
        subtract(20, "行政・医療・介護資源が中核都市へ集約される可能性が高い地域です。")
    elif region_type == "大都市型":
        add(12, "市場そのものは残りやすく、高密度戦略や承継があれば将来性があります。")
        subtract(12, "競争が強く、地盤・承継・紹介導線がない新規単独参入の将来性は限定的です。")
    elif region_type == "超高密集競争型":
        subtract(28, "市場容量に対して競合が多く、飽和状態が続きやすい地域です。")
        subtract(15, "新規参入では、将来も地盤競争・サ高住圏・紹介元競争に巻き込まれやすい地域です。")

    if recovery_score is not None:
        if recovery_score >= 85:
            add(18, "市場回復性が非常に高く、減少後も需要を戻しやすい基盤があります。")
        elif recovery_score >= 70:
            add(12, "市場回復性が高く、紹介導線を維持できれば長期的にも戻しやすい市場です。")
        elif recovery_score < 30:
            subtract(20, "市場回復性が非常に低く、一度減ると長期的に戻りにくい地域です。")
        elif recovery_score < 50:
            subtract(12, "市場回復性が低く、長期の安定性には慎重な見方が必要です。")

    if theoretical_capacity_ratio is not None:
        if theoretical_capacity_ratio >= 20:
            add(10, "理論市場余力倍率が高く、需要母数そのものは残りやすい見立てです。")
        elif theoretical_capacity_ratio < 2:
            subtract(10, "理論市場余力倍率が低く、長期の市場容量に限界があります。")

    if competitive_capacity_ratio is not None:
        if competitive_capacity_ratio >= 2:
            add(12, "競争後達成余力倍率が高く、淘汰後に残る事業所へ需要が集まりやすい可能性があります。")
        elif competitive_capacity_ratio < 1:
            subtract(15, "競争後達成余力倍率が低く、長期的にも競争に埋もれやすい地域です。")
        elif competitive_capacity_ratio < 1.4:
            subtract(8, "競争後達成余力倍率が中低位で、長期的な余裕は大きくありません。")

    if market_size is not None:
        if market_size >= 10_000_000:
            add(10, "一定以上の市場規模があり、人口減少後も需要母数が残りやすい地域です。")
        elif market_size < 4_000_000:
            subtract(15, "市場規模が小さく、人口減少後の事業継続余地は限定的です。")

    if elderly_population is not None:
        if elderly_population >= 20_000:
            add(8, "高齢者絶対数があり、長期的な需要母数が残りやすい地域です。")
        elif elderly_population < 5_000:
            subtract(12, "高齢者絶対数が少なく、長期的な利用者母数に不安があります。")

    if staffing_score is not None:
        if staffing_score >= 80:
            subtract(15, "人材確保難易度が非常に高く、10年後の継続運営では人材制約が重くなります。")
        elif staffing_score >= 60:
            subtract(8, "人材確保難易度が高く、長期的な成長には採用・定着戦略が必要です。")

    if competitors is not None:
        if competitors >= 80:
            subtract(18, "実質競合数が非常に多く、将来も地盤競争が続きやすい地域です。")
        elif competitors >= 50:
            subtract(10, "実質競合数が多く、淘汰後優位に立つには紹介元・承継・差別化が必要です。")
        elif competitors <= 6 and region_type in {"地方都市型", "供給不足型過疎地"}:
            add(8, "競合が少なく、地域の受け皿として残りやすい可能性があります。")

    if users_per_office is not None and users_per_office >= 80:
        add(8, "1事業所あたり潜在利用者数が多く、供給不足が続く場合は残存事業所に需要が集まりやすいです。")

    if high_density_score >= 70:
        add(8, "高密度運営との相性があり、介護資源集約後も効率的に残りやすい可能性があります。")
    if succession_score >= 70 and region_type in {"大都市型", "超高密集競争型"}:
        add(8, "承継・引継ぎ型との相性があり、地盤を取れれば長期的な残存可能性があります。")

    if region_type == "供給不足型過疎地":
        reasons.append("短中期は有望ですが、10年単位では市場容量と中核都市への流出を見ながら運営する必要があります。")

    if region_type == "供給不足型過疎地":
        score = min(score, 78)

    if not reasons:
        reasons.append("取得できている指標からは、一定の将来性があります。")
    if not risks:
        risks.append("大きな将来リスクは限定的ですが、人材確保と紹介元維持は継続課題です。")

    score = cap_score(score)
    if score >= 85:
        level = "非常に高い"
    elif score >= 70:
        level = "高い"
    elif score >= 50:
        level = "普通"
    elif score >= 30:
        level = "低い"
    else:
        level = "非常に低い"

    return {
        "score": score,
        "level": level,
        "reasons": reasons,
        "risks": risks,
    }


def calculate_required_users(metrics: list[dict[str, Any]], region: dict[str, Any]) -> dict[str, Any]:
    region_type = region.get("type", "地方都市型")
    users = metric_number(metrics, "訪問介護利用者数")
    client_acquisition = region.get("client_acquisition_difficulty", {})
    client_score = client_acquisition.get("score")
    revenue_per_user = calculate_effective_revenue_per_user(metrics)

    multiplier = REQUIRED_USER_REGION_MULTIPLIERS.get(str(region_type), 1.0)
    comment = "保守的な利用者単価をもとに、標準的な必要利用者数を推定しています。"

    if region_type == "地方都市型":
        comment = "地方都市型は固定費を抑えやすく、狭いエリアに集中できれば標準より少ない利用者数でも成立余地があります。"
    elif region_type == "供給不足型過疎地":
        comment = "供給不足型過疎地は利用者を拾いやすい一方、市場規模上限を見ながら低固定費で運営する必要があります。"
    elif region_type == "超過疎地型":
        comment = "超過疎地型では250万円モデルを前提にせず、低い損益分岐ラインを重視する必要があります。"
    elif region_type == "大都市型":
        comment = "大都市型は固定費と競争を考慮し、標準より多めの利用者数を見込む必要があります。"
    elif region_type == "超高密集競争型":
        comment = "超高密集競争型は利用者獲得難易度が高く、黒字化には標準より多めの利用者確保が必要です。"
    elif region_type == "判定保留":
        comment = "地域タイプ判定に必要なデータが不足しているため、必要利用者数は暫定値として確認してください。"

    if client_score is not None and client_score >= 80:
        multiplier += 0.08
        comment += " 利用者獲得難易度が非常に高いため、余裕を持った利用者数設定が必要です。"
    elif client_score is not None and client_score <= 30:
        multiplier -= 0.05
        comment += " 利用者獲得難易度が低めのため、立ち上がり次第では必要利用者数を少し抑えられる可能性があります。"

    required_users = {
        key: round((target / revenue_per_user) * multiplier)
        for key, target in REQUIRED_USER_REVENUE_LINES.items()
    }

    if users is not None:
        stable_line = required_users["stable_line"]
        if users < stable_line:
            comment += f" 現在の推定利用者数は安定運営ライン約{stable_line}人を下回るため、獲得計画を慎重に見る必要があります。"
        else:
            comment += f" 現在の推定利用者数は安定運営ライン約{stable_line}人以上あり、獲得できれば運営余地があります。"

    return {
        **required_users,
        "comment": comment,
    }


def calculate_estimation_accuracy(metrics: list[dict[str, Any]]) -> dict[str, Any] | None:
    actual_metric = metric_item(metrics, "訪問介護利用者数")
    if not actual_metric:
        return None

    source = str(actual_metric.get("取得元列", ""))
    actual_users = actual_metric.get("数値")
    if actual_users is None or actual_metric.get("推計") or not source or "推定" in source:
        return None

    estimated_users = calculate_estimated_home_care_users(metrics)
    if estimated_users is None:
        return None
    difference = estimated_users - actual_users
    difference_rate = abs(difference) / actual_users * 100 if actual_users else None
    if difference_rate is None:
        return None

    if difference_rate <= 5:
        accuracy_level = "非常に近い"
    elif difference_rate <= 10:
        accuracy_level = "比較的近い"
    elif difference_rate <= 20:
        accuracy_level = "ややズレあり"
    else:
        accuracy_level = "推計見直し推奨"

    return {
        "estimated_users": round(estimated_users),
        "actual_users": round(actual_users),
        "difference": round(difference),
        "difference_rate": difference_rate,
        "accuracy_level": accuracy_level,
    }


def generate_strategy_comment(metrics: list[dict[str, Any]], region: dict[str, Any]) -> str:
    region_type = str(region.get("type", "判定保留"))
    business_model_scores = region.get("business_model_scores", {})
    client_acquisition = region.get("client_acquisition_difficulty", {})
    movement_efficiency = region.get("movement_efficiency", {})
    collapse_risk = region.get("collapse_risk", {})
    staffing_difficulty = region.get("staffing_difficulty", {})
    profitability_difficulty = region.get("profitability_difficulty", {})
    sales_strategy = region.get("sales_strategy", {})
    startup_patterns = region.get("startup_patterns", {})
    competition_penalty = region.get("competition_density_penalty", {})
    market_recovery = region.get("market_recovery", {})
    market_future_potential = region.get("market_future_potential", {})

    top_models = []
    if isinstance(business_model_scores, dict):
        top_models = [
            model_name
            for model_name, _ in sorted(business_model_scores.items(), key=lambda item: item[1], reverse=True)[:2]
        ]
    if not top_models:
        top_models = startup_patterns.get("best", [])[:2] if isinstance(startup_patterns, dict) else []

    best_patterns = startup_patterns.get("best", [])[:2] if isinstance(startup_patterns, dict) else []
    avoid_patterns = startup_patterns.get("avoid", [])[:2] if isinstance(startup_patterns, dict) else []
    first_targets = sales_strategy.get("first_targets", [])[:3] if isinstance(sales_strategy, dict) else []
    priority_actions = sales_strategy.get("priority_actions", [])[:2] if isinstance(sales_strategy, dict) else []

    top_model_text = "、".join(top_models) if top_models else "低固定費で小さく始めるモデル"
    best_pattern_text = "、".join(best_patterns) if best_patterns else "小規模で固定費を抑えた開業"
    avoid_pattern_text = "、".join(avoid_patterns) if avoid_patterns else "高固定費・広範囲営業"
    target_text = "、".join(first_targets) if first_targets else "地域包括・居宅介護支援事業所"
    action_text = "、".join(priority_actions) if priority_actions else "紹介元づくりと対応エリアの絞り込み"

    client_level = client_acquisition.get("level", "-")
    movement_level = movement_efficiency.get("level", "-")
    staffing_level = staffing_difficulty.get("level", "-")
    profitability_level = profitability_difficulty.get("level", "-")
    recovery_level = market_recovery.get("level", "-") if isinstance(market_recovery, dict) else "-"
    future_level = market_future_potential.get("level", "-") if isinstance(market_future_potential, dict) else "-"
    recovery_score = market_recovery.get("score") if isinstance(market_recovery, dict) else None
    future_score = market_future_potential.get("score") if isinstance(market_future_potential, dict) else None
    collapse_pattern = collapse_risk.get("main_collapse_pattern", "-")
    competition_density_comment = ""
    if isinstance(competition_penalty, dict) and competition_penalty.get("level") in {"中", "強"}:
        competition_density_comment = (
            f"\n\nまた、{competition_penalty.get('comment')} "
            "市場余力だけを見ると大きく見えますが、実際には紹介元・利用者・人材の取り合いが強く、"
            "激戦市場として慎重に見る必要があります。"
        )

    recovery_future_comment = ""
    if region_type == "地方都市型" and (recovery_score or 0) >= 70 and (future_score or 0) >= 70:
        recovery_future_comment = (
            f"市場回復性は「{recovery_level}」、市場将来性は「{future_level}」です。"
            "利用者が一時的に減っても、地域包括・居宅との関係を維持できれば戻しやすく、"
            "淘汰後に残る事業所へ利用者・ヘルパーが集まりやすい地域です。"
            "大きく拡大するより、生き残ることで長期的に強くなる戦い方が向いています。"
        )
    elif region_type == "供給不足型過疎地":
        recovery_future_comment = (
            f"市場回復性は「{recovery_level}」、市場将来性は「{future_level}」です。"
            "短中期では立ち上がりやすい一方、同タイプの積極型事業所が増えると市場バランスが崩れやすい地域です。"
            "無理な拡大より、地域分担・低固定費・安定運営を優先する方が長く残りやすくなります。"
        )
    elif region_type == "超過疎地型" and ((recovery_score is not None and recovery_score < 50) or (future_score is not None and future_score < 50)):
        recovery_future_comment = (
            f"市場回復性は「{recovery_level}」、市場将来性は「{future_level}」です。"
            "利用者が減ると戻しづらく、減少がそのまま市場縮小につながりやすい地域です。"
            "通常の250万円モデルではなく、超低固定費・家族中心・地域インフラ維持型として考える必要があります。"
        )
    elif region_type == "超高密集競争型" and (future_score is not None and future_score < 50):
        recovery_future_comment = (
            f"市場回復性は「{recovery_level}」、市場将来性は「{future_level}」です。"
            "市場容量に対して競合が多く、飽和状態が続きやすいため、完全0スタートは避けるべき地域です。"
            "承継・既存利用者引継ぎ・ケアマネ人脈がない場合は、長期的にも回復しづらい見立てです。"
        )
    elif isinstance(market_recovery, dict) and isinstance(market_future_potential, dict):
        recovery_future_comment = (
            f"市場回復性は「{recovery_level}」、市場将来性は「{future_level}」です。"
            "短期の市場余力だけでなく、利用者減少後に戻せるか、10年後に残れるかを見ながら戦い方を決める必要があります。"
        )

    type_summaries = {
        "地方都市型": "この地域は地方都市型として、固定費を抑えた小規模高稼働モデルと相性が良い地域です。巨大化よりも、小さく立ち上がって地域の訪問介護の灯を維持できること自体に価値があります。需要余力が残る場合は、ケアマネを抱えず軽量に動く方が、管理負荷と固定費を抑えて強みを出しやすいです。",
        "供給不足型過疎地": "この地域は供給不足型過疎地として、地域インフラの受け皿になれる可能性があります。都市部ほど大きく伸ばす市場ではなくても、顧客獲得難易度が低く、0から立ち上がりやすい点が強みです。人口がまとまっているエリアに絞り、居宅併設より軽量な訪問介護単独運営を優先する方が現実的です。",
        "超過疎地型": "この地域は超過疎地型として、売上拡大型ではなく維持可能性を最優先に考えるべき地域です。高齢化率よりも高齢者の絶対数と移動効率を重視する必要があります。",
        "大都市型": "この地域は大都市型として、市場規模は見込める一方で、既存事業所や居宅併設事業所との競争が強い地域です。0スタートではなく、差別化とケアマネ関係構築を前提に見るべきです。",
        "超高密集競争型": "この地域は超高密集競争型として、移動効率は高くても競争効率が悪くなりやすい地域です。完全0スタートより、地盤承継や既存利用者の引継ぎを前提に考えるべきです。",
        "判定保留": "この地域は地域タイプ判定に必要なデータが不足しているため、現時点では暫定評価として見る必要があります。追加データを確認しながら、小さく検証する進め方が安全です。",
    }

    type_strategies = {
        "地方都市型": "戦い方としては、自宅兼事務所や夫婦経営を軸に固定費を抑え、居宅を抱えない軽さを活かして小規模高稼働で訪問密度を高める形が向いています。大きく勝つより、狭い商圏で確実に残る設計が重要です。",
        "供給不足型過疎地": "戦い方としては、供給不足の受け皿として存在を明確にし、地域包括や居宅と連携しながら密集エリアに集中する形が向いています。紹介が回る余地があるなら、居宅併設で常勤・書類・保管スペースを増やすより、軽量運営で受け皿機能を磨く方が強く、小さく生き残りやすい市場です。",
        "超過疎地型": "戦い方としては、所有物件や超低固定費を前提に、行政・包括との関係を重視して地域維持型の運営を組み立てる必要があります。",
        "大都市型": "戦い方としては、居宅併設・承継・既存地盤の活用を優先し、ケアマネ関係と明確な差別化を先に作る必要があります。",
        "超高密集競争型": "戦い方としては、新規営業で正面突破するより、承継・引継ぎ・ケアマネ人脈を活用して競争を避ける設計が重要です。",
        "判定保留": "戦い方としては、追加データを確認しながら、固定費を抑えた暫定プランで成立可能性を検証するのが現実的です。",
    }

    paragraphs = [
        type_summaries.get(region_type, type_summaries["判定保留"]),
        f"強みとしては、{top_model_text}との相性を軸に、{best_pattern_text}を組み立てやすい点です。営業面では、まず{target_text}に対して、{action_text}を進めるのが現実的です。",
        f"一方で、利用者獲得難易度は「{client_level}」、人材確保難易度は「{staffing_level}」、黒字化難易度は「{profitability_level}」です。特に崩壊リスクでは「{collapse_pattern}」に注意し、{avoid_pattern_text}に寄せると利益が崩れやすくなります。",
        competition_density_comment,
        recovery_future_comment,
        f"移動効率指数は「{movement_level}」です。訪問介護では市場規模だけでなく、どれだけ短い移動で固定利用者を積み上げられるかが重要なので、対応エリアを広げすぎず、利用者密度を高める設計が必要です。",
        type_strategies.get(region_type, type_strategies["判定保留"]),
    ]
    return "\n\n".join(paragraph for paragraph in paragraphs if paragraph)


def generate_existing_operator_advice(metrics: list[dict[str, Any]], region: dict[str, Any]) -> dict[str, list[str]]:
    region_type = str(region.get("type", "判定保留"))
    movement_efficiency = region.get("movement_efficiency", {})
    collapse_risk = region.get("collapse_risk", {})
    staffing_difficulty = region.get("staffing_difficulty", {})
    profitability_difficulty = region.get("profitability_difficulty", {})
    client_acquisition = region.get("client_acquisition_difficulty", {})
    sales_strategy = region.get("sales_strategy", {})
    startup_patterns = region.get("startup_patterns", {})

    movement_score = movement_efficiency.get("score") if isinstance(movement_efficiency, dict) else None
    staffing_score = staffing_difficulty.get("score") if isinstance(staffing_difficulty, dict) else None
    profitability_score = profitability_difficulty.get("score") if isinstance(profitability_difficulty, dict) else None
    client_score = client_acquisition.get("score") if isinstance(client_acquisition, dict) else None
    fixed_cost_risk = collapse_risk.get("fixed_cost_risk") if isinstance(collapse_risk, dict) else None
    competition_risk = collapse_risk.get("competition_risk") if isinstance(collapse_risk, dict) else None
    movement_risk = collapse_risk.get("movement_risk") if isinstance(collapse_risk, dict) else None
    main_collapse_pattern = collapse_risk.get("main_collapse_pattern", "-") if isinstance(collapse_risk, dict) else "-"
    priority_actions = sales_strategy.get("priority_actions", []) if isinstance(sales_strategy, dict) else []
    avoid_patterns = startup_patterns.get("avoid", []) if isinstance(startup_patterns, dict) else []

    review_points: list[str] = []
    quick_actions: list[str] = []
    mid_long_term_actions: list[str] = []

    def add(items: list[str], value: str) -> None:
        if value not in items:
            items.append(value)

    if movement_score is not None and movement_score < 50 or movement_risk is not None and movement_risk >= 60:
        add(review_points, "利用者数を増やす前に、対応エリアが広がりすぎていないかを見直す")
        add(quick_actions, "遠方利用者の新規受け入れを一度止め、曜日・エリア別に訪問ルートを組み直す")
        add(mid_long_term_actions, "サービス提供範囲を絞り、利用者密度を高める運営へ切り替える")

    if staffing_score is not None and staffing_score >= 60:
        add(review_points, "ヘルパーにとって働きにくい移動距離・空き時間・不規則シフトが増えていないかを確認する")
        add(quick_actions, "曜日固定・エリア固定の訪問枠を作り、地域在住ヘルパーを優先して配置する")
        add(mid_long_term_actions, "広範囲対応を前提にした採用ではなく、固定ルートで働ける小さな稼働圏を作る")

    if fixed_cost_risk is not None and fixed_cost_risk >= 60:
        add(review_points, "事務所家賃・車両費・管理費が、現在の利用者密度に対して重すぎないかを見直す")
        add(quick_actions, "固定費一覧を作り、すぐ下げられる車両費・外注費・管理費から削減する")
        add(mid_long_term_actions, "自宅兼事務所や小規模事務所への移行を含め、損益分岐点を下げる")

    if competition_risk is not None and competition_risk >= 60 or client_score is not None and client_score >= 60:
        add(review_points, "競合と同じ営業先・同じ訴求で戦っていないかを見直す")
        add(quick_actions, "特定エリア・特定曜日・特定ニーズに絞った空き情報を居宅へ届ける")
        add(mid_long_term_actions, "ケアマネ関係を再構築し、選ばれる理由を1つに絞って磨く")

    if profitability_score is not None and profitability_score >= 60:
        add(review_points, "売上拡大だけで黒字化しようとしていないか、固定費と移動効率を確認する")
        add(quick_actions, "新規利用者の受け入れ条件を、距離・曜日・時間帯で明確にする")
        add(mid_long_term_actions, "高売上化より、利用者密度と固定費圧縮を優先した黒字化モデルへ寄せる")

    if region_type == "地方都市型":
        add(review_points, "地方都市型の強みを活かせず、商圏を広げすぎていないかを確認する")
        add(review_points, "居宅併設によって常勤・書類・保管スペース・管理負荷が重くなりすぎていないかを確認する")
        add(quick_actions, "ケアマネを抱えず、空き枠と対応エリアを明確にした軽量営業へ寄せる")
        add(mid_long_term_actions, "自宅兼事務所・小規模高稼働型に寄せ、中心エリアで稼働率を高める")
    elif region_type == "供給不足型過疎地":
        add(review_points, "供給不足を受けすぎて、移動負担が過大になっていないかを確認する")
        add(review_points, "居宅併設で固定費と管理負荷を増やすより、訪問介護単独の軽さを活かせているかを確認する")
        add(quick_actions, "紹介が回る地域では、居宅併設より地域包括・居宅との関係維持に時間を使う")
        add(mid_long_term_actions, "地域分担型の運営に切り替え、人口密集エリアを優先する")
    elif region_type == "超過疎地型":
        add(review_points, "通常の250万円売上モデルを前提にしていないかを見直す")
        add(mid_long_term_actions, "行政・包括と連携し、地域維持型の超低固定費モデルへ寄せる")
    elif region_type == "大都市型":
        add(review_points, "紹介元との関係構築が弱いまま、広告や飛び込み営業に偏っていないかを確認する")
        add(mid_long_term_actions, "居宅併設・承継・既存地盤の引継ぎを含め、紹介構造の中に入る")
    elif region_type == "超高密集競争型":
        add(review_points, "競合密度が高い中で、完全0スタート型の営業を続けていないかを見直す")
        add(mid_long_term_actions, "地盤承継・既存利用者引継ぎ・ケアマネ人脈を前提に、競争回避型へ転換する")

    for action in priority_actions[:2]:
        add(quick_actions, action)
    for pattern in avoid_patterns[:2]:
        add(review_points, f"避けるべき開業・運営パターンとして「{pattern}」に近づいていないか確認する")

    if not review_points:
        add(review_points, "利用者密度・固定費・紹介元との関係を定期的に見直す")
    if not quick_actions:
        add(quick_actions, "直近1か月の訪問ルートを確認し、移動時間が長い利用者の受け方を見直す")
        add(quick_actions, "空き枠・対応エリア・得意な支援内容を1枚にまとめて居宅へ共有する")
    if not mid_long_term_actions:
        add(mid_long_term_actions, "売上規模よりも、固定費を抑えた高密度運営に寄せる")

    add(review_points, f"最も注意すべき崩壊パターンは「{main_collapse_pattern}」です")

    return {
        "review_points": review_points[:6],
        "quick_actions": quick_actions[:6],
        "mid_long_term_actions": mid_long_term_actions[:6],
    }


def generate_priority_actions(metrics: list[dict[str, Any]], region: dict[str, Any]) -> dict[str, list[str]]:
    region_type = str(region.get("type", "判定保留"))
    headline = str(region.get("headline", ""))
    movement_efficiency = region.get("movement_efficiency", {})
    collapse_risk = region.get("collapse_risk", {})
    staffing_difficulty = region.get("staffing_difficulty", {})
    profitability_difficulty = region.get("profitability_difficulty", {})
    client_acquisition = region.get("client_acquisition_difficulty", {})
    sales_strategy = region.get("sales_strategy", {})
    startup_patterns = region.get("startup_patterns", {})
    operator_advice = region.get("existing_operator_advice", {})

    movement_score = movement_efficiency.get("score") if isinstance(movement_efficiency, dict) else None
    staffing_score = staffing_difficulty.get("score") if isinstance(staffing_difficulty, dict) else None
    profitability_score = profitability_difficulty.get("score") if isinstance(profitability_difficulty, dict) else None
    client_score = client_acquisition.get("score") if isinstance(client_acquisition, dict) else None
    fixed_cost_risk = collapse_risk.get("fixed_cost_risk") if isinstance(collapse_risk, dict) else None
    competition_risk = collapse_risk.get("competition_risk") if isinstance(collapse_risk, dict) else None
    movement_risk = collapse_risk.get("movement_risk") if isinstance(collapse_risk, dict) else None
    first_targets = sales_strategy.get("first_targets", []) if isinstance(sales_strategy, dict) else []
    sales_actions = sales_strategy.get("priority_actions", []) if isinstance(sales_strategy, dict) else []
    possible_patterns = startup_patterns.get("possible", []) if isinstance(startup_patterns, dict) else []
    avoid_patterns = startup_patterns.get("avoid", []) if isinstance(startup_patterns, dict) else []
    quick_actions = operator_advice.get("quick_actions", []) if isinstance(operator_advice, dict) else []
    mid_long_actions = operator_advice.get("mid_long_term_actions", []) if isinstance(operator_advice, dict) else []

    first: list[str] = []
    second: list[str] = []
    later: list[str] = []

    def add(items: list[str], value: str) -> None:
        if value and value not in items:
            items.append(value)

    if movement_score is not None and movement_score < 50 or movement_risk is not None and movement_risk >= 60:
        add(first, "対応エリアを絞り、曜日・地域ごとの訪問ルートを見直す")
        add(first, "遠方利用者を増やしすぎない受け入れ基準を作る")

    if client_score is not None and client_score >= 60:
        add(first, "ケアマネ関係を再構築し、紹介元を絞り込む")
        add(first, "既存地盤・承継・引継ぎルートの有無を確認する")
        add(second, "空き情報と対応エリアを1枚資料にして、優先紹介元へ定期共有する")

    if staffing_score is not None and staffing_score >= 60:
        add(first, "ヘルパーが働きやすい固定ルートを作る")
        add(first, "地域在住ヘルパーを優先して探し、登録ヘルパー依存を下げる")
        add(second, "曜日固定・時間帯固定の案件を増やし、シフトの読みやすさを高める")

    if fixed_cost_risk is not None and fixed_cost_risk >= 60:
        add(first, "事務所家賃・車両費・管理費を見直す")
        add(first, "自宅兼事務所や小規模化で損益分岐点を下げる")

    if competition_risk is not None and competition_risk >= 60:
        add(first, "競合と真正面から戦わず、特定エリア・特定ニーズへ絞る")
        add(second, "ケアマネ営業の切り口を見直し、選ばれる理由を明確にする")

    if profitability_score is not None and profitability_score >= 60:
        add(first, "売上拡大より先に、固定費圧縮と利用者密度の改善を行う")
        add(second, "新規利用者の受け入れ条件を距離・曜日・時間帯で整理する")

    if region_type == "地方都市型":
        add(second, "自宅兼事務所・夫婦経営型を軸に、小規模高稼働へ寄せる")
        add(later, "広域展開や大きな事務所への移転は、利用者密度が上がってから検討する")
    elif region_type == "供給不足型過疎地":
        add(second, "地域包括・居宅と連携し、供給不足の受け皿として認知を作る")
        add(later, "市町村全域への拡大は、固定ルートが安定してから検討する")
    elif region_type == "超過疎地型":
        add(first, "250万円売上モデルにこだわらず、低い損益分岐点を先に設計する")
        add(second, "行政・包括との関係を強め、地域維持型の役割を確認する")
        add(later, "人を雇って拡大する計画は、固定利用者の密度が見えてから判断する")
    elif region_type == "大都市型":
        add(first, "ケアマネ関係・居宅併設・承継のどれで地盤を作るか決める")
        add(second, "差別化できるサービス領域と営業先を絞り込む")
        add(later, "広告や広範囲の飛び込み営業は、紹介導線ができてから検討する")
    elif region_type == "超高密集競争型":
        add(first, "完全0スタートを避け、地盤承継・既存利用者引継ぎを最優先で確認する")
        add(second, "サ高住外部派遣圏や高競争エリアを避ける営業設計にする")
        add(later, "競合分析なしの新規拡大は後回しにする")

    if "×" in headline or "厳しい" in headline:
        add(first, "新規投資や固定費増加を止め、撤退ライン・縮小ラインを先に決める")
    elif "◎" in headline or "かなり有望" in headline:
        add(second, "有望エリアを狭く定め、早期に固定利用者を集める")

    for action in quick_actions[:2]:
        add(first if len(first) < 4 else second, action)
    for action in sales_actions[:2]:
        add(second, action)
    for target in first_targets[:2]:
        add(second, f"{target}への営業優先順位を決める")
    for action in mid_long_actions[:2]:
        add(second if len(second) < 5 else later, action)
    for pattern in possible_patterns[:2]:
        add(later, f"条件が整った後に「{pattern}」を検討する")
    for pattern in avoid_patterns[:2]:
        add(later, f"「{pattern}」に近い投資や拡大は後回しにする")

    if not first:
        add(first, "対応エリア・固定費・紹介元の3点を先に点検する")
        add(first, "直近の訪問ルートを確認し、移動時間が長い案件を洗い出す")
    if not second:
        add(second, "空き情報・対応エリア・得意な支援内容を整理して紹介元へ共有する")
    if not later:
        add(later, "大きな事務所移転や人員拡大は、利用者密度と採算が見えてから判断する")

    return {
        "first": first[:5],
        "second": second[:5],
        "later": later[:5],
    }


def generate_diagnosis_summary(metrics: list[dict[str, Any]], region: dict[str, Any]) -> dict[str, str]:
    region_type = str(region.get("type", "-"))
    headline = str(region.get("headline", "-"))
    business_model_scores = region.get("business_model_scores", {})
    startup_patterns = region.get("startup_patterns", {})
    collapse_risk = region.get("collapse_risk", {})
    priority_actions = region.get("priority_actions", {})

    best_model = "-"
    if isinstance(startup_patterns, dict) and startup_patterns.get("best"):
        best_model = str(startup_patterns["best"][0])
    elif isinstance(business_model_scores, dict) and business_model_scores:
        best_model = str(max(business_model_scores.items(), key=lambda item: item[1])[0])

    risk_labels = {
        "human_resource_risk": "人材崩壊リスク",
        "fixed_cost_risk": "固定費崩壊リスク",
        "competition_risk": "競争崩壊リスク",
        "movement_risk": "移動効率崩壊リスク",
        "client_concentration_risk": "利用者集中リスク",
        "regional_decline_risk": "地域縮小リスク",
    }
    max_risk = "-"
    if isinstance(collapse_risk, dict):
        risk_scores = {
            key: collapse_risk.get(key)
            for key in risk_labels
            if isinstance(collapse_risk.get(key), (int, float))
        }
        if risk_scores:
            max_key = max(risk_scores.items(), key=lambda item: item[1])[0]
            max_risk = risk_labels.get(max_key, max_key)
        else:
            max_risk = str(collapse_risk.get("main_collapse_pattern", "-"))

    first_action = "-"
    if isinstance(priority_actions, dict) and priority_actions.get("first"):
        first_action = str(priority_actions["first"][0])

    short_comments = {
        "地方都市型": "固定費を抑えて高密度に回れば、小規模でも成立しやすい地域です。",
        "供給不足型過疎地": "需要の受け皿になれる一方、人口密集エリアに絞ることが重要な地域です。",
        "超過疎地型": "通常の売上拡大より、超低固定費で維持可能性を優先すべき地域です。",
        "大都市型": "市場規模はありますが、ケアマネ関係と差別化なしの0スタートは厳しい地域です。",
        "超高密集競争型": "移動効率は良くても競争が強く、地盤承継や紹介導線が重要な地域です。",
        "判定保留": "データ不足があるため、追加確認を前提に暫定判断すべき地域です。",
    }

    return {
        "headline": headline,
        "region_type": region_type,
        "best_model": best_model,
        "max_risk": max_risk,
        "first_action": first_action,
        "short_comment": short_comments.get(region_type, "固定費・移動効率・紹介元を確認しながら、無理のない参入条件を見極める地域です。"),
    }


def metrics_to_markdown(metrics: list[dict[str, Any]]) -> str:
    return "\n".join(f"- {metric['指標']}: {metric['値']}" for metric in metrics)


def revenue_assumption_to_markdown() -> str:
    return f"## 計算前提\n\n- {BASE_REVENUE_NOTE}\n"


def data_quality_note_to_markdown() -> str:
    return "## データについての注意\n\n" + "\n\n".join(DATA_QUALITY_NOTE_PARAGRAPHS) + "\n"


def estimated_users_note_to_markdown(metrics: list[dict[str, Any]]) -> str:
    if not uses_estimated_home_care_users(metrics):
        return ""
    return f"\n- {ESTIMATED_USERS_NOTE}\n"


def region_to_markdown(region: dict[str, Any]) -> str:
    region_type = region.get("type", "-")
    reasons = region.get("reasons", [])
    market_size = region.get("market_size")
    market_size_man_yen = market_size / 10_000 if market_size is not None else None
    sakoju_cover_rate = region.get("sakoju_cover_rate")
    sakoju_cover_percent = sakoju_cover_rate * 100 if sakoju_cover_rate is not None else None

    reason_lines = "\n".join(f"- {reason}" for reason in reasons) if reasons else "- -"

    type_scores = region.get("type_scores", {})
    type_score_lines = (
        "\n".join(
            f"- {region_name}：{score}点"
            for region_name, score in sorted(type_scores.items(), key=lambda item: item[1], reverse=True)
        )
        if type_scores
        else "- -"
    )

    return (
        "## 地域タイプ分析\n\n"
        f"地域タイプ：{region_type}\n\n"
        "### 分類理由\n"
        f"{reason_lines}\n\n"
        "### 主要指標\n"
        f"- 高齢者人口密度：{format_region_number(region.get('elderly_density'), 1)}人/km²\n"
        f"- 実質競合数：{format_region_number(region.get('effective_competitors'), 1)}事業所\n"
        f"- 1事業所あたり潜在利用者数：{format_region_number(region.get('users_per_office'), 1)}人\n"
        f"- 市場規模：{format_region_number(market_size_man_yen, 1)}万円/月\n"
        f"- 理論市場余力倍率：{format_region_number(region.get('theoretical_capacity_ratio'), 2)}倍\n"
        f"- 競争後達成余力倍率：{format_region_number(region.get('capacity_ratio'), 2)}倍\n"
        f"- サ高住500m圏カバー率：{format_region_number(sakoju_cover_percent, 1)}％\n"
        f"- サ高住競合影響：{region.get('sakoju_impact', '-')}\n"
        f"- サ高住の見方：{region.get('sakoju_view', '-')}\n\n"
        "### 地域タイプ判定スコア\n"
        f"{type_score_lines}\n"
    )


def markdown_list(items: Any) -> str:
    if not items:
        return "- -"
    return "\n".join(f"- {item}" for item in items)


def score_dict_to_markdown(scores: Any) -> str:
    if not isinstance(scores, dict) or not scores:
        return "- -"
    return "\n".join(f"- {key}：{value}点" for key, value in scores.items())


def business_models_to_markdown(region: dict[str, Any]) -> str:
    scores = region.get("business_model_scores", {})
    ordered_models = [
        "夫婦経営型",
        "自宅兼事務所型",
        "居宅介護支援併設型",
        "承継・引継ぎ型",
        "高密度都市集中型",
        "超低固定費型",
    ]
    lines = [f"- {model}：{scores.get(model, '-')}点" for model in ordered_models]
    return "## 経営モデル適性\n\n" + "\n".join(lines) + "\n"


def diagnosis_summary_to_markdown(region: dict[str, Any]) -> str:
    summary = region.get("diagnosis_summary", {})
    return (
        "## 診断サマリー\n\n"
        f"- 総合判定：{summary.get('headline', '-')}\n"
        f"- 地域タイプ：{summary.get('region_type', '-')}\n"
        f"- 向いている経営モデル：{summary.get('best_model', '-')}\n"
        f"- 最大リスク：{summary.get('max_risk', '-')}\n"
        f"- 最優先アクション：{summary.get('first_action', '-')}\n"
        f"- 一言コメント：{summary.get('short_comment', '-')}\n"
    )


def entry_conditions_to_markdown(entry_conditions: dict[str, Any]) -> str:
    return (
        "## 参入条件\n\n"
        "### 必須条件\n"
        f"{markdown_list(entry_conditions.get('required'))}\n\n"
        "### 推奨条件\n"
        f"{markdown_list(entry_conditions.get('recommended'))}\n\n"
        "### 避けるべき条件\n"
        f"{markdown_list(entry_conditions.get('avoid'))}\n"
    )


def client_acquisition_to_markdown(client_acquisition: dict[str, Any]) -> str:
    return (
        "## 利用者獲得難易度\n\n"
        f"- 難易度：{client_acquisition.get('level', '-')}（{client_acquisition.get('score', '-')}点）\n\n"
        "### 主な理由\n"
        f"{markdown_list(client_acquisition.get('reasons'))}\n\n"
        "### 利用者獲得上の壁\n"
        f"{markdown_list(client_acquisition.get('barriers'))}\n"
    )


def market_recovery_to_markdown(market_recovery: dict[str, Any]) -> str:
    return (
        "## 市場回復性\n\n"
        f"- 回復性：{market_recovery.get('level', '-')}（{market_recovery.get('score', '-')}点）\n\n"
        "### 回復しやすい理由\n"
        f"{markdown_list(market_recovery.get('reasons'))}\n\n"
        "### 回復を難しくする要因\n"
        f"{markdown_list(market_recovery.get('risks'))}\n"
    )


def market_future_potential_to_markdown(market_future_potential: dict[str, Any]) -> str:
    return (
        "## 市場将来性\n\n"
        f"- 将来性：{market_future_potential.get('level', '-')}（{market_future_potential.get('score', '-')}点）\n\n"
        "### 将来性がある理由\n"
        f"{markdown_list(market_future_potential.get('reasons'))}\n\n"
        "### 将来性を下げる要因\n"
        f"{markdown_list(market_future_potential.get('risks'))}\n"
    )


def movement_efficiency_to_markdown(movement_efficiency: dict[str, Any]) -> str:
    factors = movement_efficiency.get("factors", {})
    factor_lines = (
        "\n".join(f"- {key}：{value}" for key, value in factors.items())
        if isinstance(factors, dict) and factors
        else "- -"
    )
    return (
        "## 移動効率指数\n\n"
        f"- 指数：{movement_efficiency.get('level', '-')}（{movement_efficiency.get('score', '-')}点）\n\n"
        "### 主な理由\n"
        f"{markdown_list(movement_efficiency.get('reasons'))}\n\n"
        "### 影響する要因\n"
        f"{factor_lines}\n"
    )


def collapse_risk_to_markdown(collapse_risk: dict[str, Any]) -> str:
    labels = {
        "human_resource_risk": "人材崩壊リスク",
        "fixed_cost_risk": "固定費崩壊リスク",
        "competition_risk": "競争崩壊リスク",
        "movement_risk": "移動効率崩壊リスク",
        "client_concentration_risk": "利用者集中リスク",
        "regional_decline_risk": "地域縮小リスク",
    }
    risk_levels = collapse_risk.get("risk_levels", {})
    risk_lines = []
    for key, label in labels.items():
        score = collapse_risk.get(key, "-")
        level = risk_levels.get(key, "-") if isinstance(risk_levels, dict) else "-"
        risk_lines.append(f"- {label}：{level}（{score}点）")

    return (
        "## 崩壊リスク分析\n\n"
        "### 各崩壊リスク\n"
        f"{chr(10).join(risk_lines)}\n\n"
        "### 最も危険な崩壊パターン\n"
        f"{collapse_risk.get('main_collapse_pattern', '-')}\n\n"
        "### 主な理由\n"
        f"{markdown_list(collapse_risk.get('reasons'))}\n"
    )


def staffing_difficulty_to_markdown(staffing_difficulty: dict[str, Any]) -> str:
    return (
        "## 人材確保難易度\n\n"
        f"- 難易度：{staffing_difficulty.get('level', '-')}（{staffing_difficulty.get('score', '-')}点）\n\n"
        "### 主な理由\n"
        f"{markdown_list(staffing_difficulty.get('reasons'))}\n\n"
        "### 対策\n"
        f"{markdown_list(staffing_difficulty.get('recommended_actions'))}\n"
    )


def profitability_difficulty_to_markdown(profitability_difficulty: dict[str, Any]) -> str:
    return (
        "## 黒字化難易度\n\n"
        f"- 難易度：{profitability_difficulty.get('level', '-')}（{profitability_difficulty.get('score', '-')}点）\n\n"
        "### 黒字化を難しくする要因\n"
        f"{markdown_list(profitability_difficulty.get('reasons'))}\n\n"
        "### 黒字化のための打ち手\n"
        f"{markdown_list(profitability_difficulty.get('actions'))}\n"
    )


def required_users_to_markdown(region: dict[str, Any]) -> str:
    required_users = region.get("required_users", {})
    return (
        "## 推定必要利用者数\n\n"
        f"- 最低維持ライン：約{required_users.get('minimum_line', '-')}人\n"
        f"- 安定運営ライン：約{required_users.get('stable_line', '-')}人\n"
        f"- 夫婦経営安定ライン：約{required_users.get('family_stable_line', '-')}人\n"
        f"- 小規模高還元ライン：約{required_users.get('high_return_line', '-')}人\n\n"
        "### コメント\n"
        f"{required_users.get('comment', '-')}\n\n"
        "### 計算前提\n"
        f"- {BASE_REVENUE_NOTE}\n"
    )


def sales_strategy_to_markdown(sales_strategy: dict[str, Any]) -> str:
    return (
        "## 推奨営業戦略\n\n"
        "### 最初に狙う営業先\n"
        f"{markdown_list(sales_strategy.get('first_targets'))}\n\n"
        "### 営業の優先順位\n"
        f"{markdown_list(sales_strategy.get('priority_actions'))}\n\n"
        "### 注意すべき営業ミス\n"
        f"{markdown_list(sales_strategy.get('mistakes_to_avoid'))}\n"
    )


def startup_patterns_to_markdown(startup_patterns: dict[str, Any]) -> str:
    return (
        "## 向いている開業パターン\n\n"
        "### 最適パターン\n"
        f"{markdown_list(startup_patterns.get('best'))}\n\n"
        "### 条件付きで可能なパターン\n"
        f"{markdown_list(startup_patterns.get('possible'))}\n\n"
        "### 避けるべきパターン\n"
        f"{markdown_list(startup_patterns.get('avoid'))}\n\n"
        "### コメント\n"
        f"{startup_patterns.get('comment', '-')}\n"
    )


def strategy_comment_to_markdown(region: dict[str, Any]) -> str:
    return (
        "## 総合戦略コメント\n\n"
        f"{region.get('strategy_comment', '-')}\n"
    )


def existing_operator_advice_to_markdown(region: dict[str, Any]) -> str:
    advice = region.get("existing_operator_advice", {})
    return (
        "## 既存事業所向け改善提案\n\n"
        "### 見直すべきポイント\n"
        f"{markdown_list(advice.get('review_points'))}\n\n"
        "### すぐにできる改善策\n"
        f"{markdown_list(advice.get('quick_actions'))}\n\n"
        "### 中長期で見直すべき戦い方\n"
        f"{markdown_list(advice.get('mid_long_term_actions'))}\n"
    )


def priority_actions_to_markdown(region: dict[str, Any]) -> str:
    priority_actions = region.get("priority_actions", {})
    return (
        "## 優先アクション順位\n\n"
        "### 1. 最優先でやること\n"
        f"{markdown_list(priority_actions.get('first'))}\n\n"
        "### 2. 次にやること\n"
        f"{markdown_list(priority_actions.get('second'))}\n\n"
        "### 3. 後回しでよいこと\n"
        f"{markdown_list(priority_actions.get('later'))}\n"
    )


def detailed_report_to_markdown(region: dict[str, Any], entry_conditions: dict[str, Any]) -> str:
    sections = [
        diagnosis_summary_to_markdown(region),
        strategy_comment_to_markdown(region),
        priority_actions_to_markdown(region),
        startup_patterns_to_markdown(region),
        business_models_to_markdown(region),
        client_acquisition_to_markdown(region.get("client_acquisition_difficulty", {})),
        sales_strategy_to_markdown(region.get("sales_strategy", {})),
        market_recovery_to_markdown(region.get("market_recovery", {})),
        market_future_potential_to_markdown(region.get("market_future_potential", {})),
        profitability_difficulty_to_markdown(region.get("profitability_difficulty", {})),
        staffing_difficulty_to_markdown(region.get("staffing_difficulty", {})),
        movement_efficiency_to_markdown(region.get("movement_efficiency", {})),
        collapse_risk_to_markdown(region.get("collapse_risk", {})),
        existing_operator_advice_to_markdown(region),
        region_to_markdown(region),
        entry_conditions_to_markdown(entry_conditions),
        required_users_to_markdown(region),
    ]
    return "\n\n".join(sections)


def format_region_number(value: Any, decimals: int = 0) -> str:
    number = parse_number(value)
    if number is None:
        return "-"
    return f"{number:,.{decimals}f}"


def ui_tone_from_text(value: str) -> str:
    if any(marker in value for marker in ("◎", "かなり有望", "有望", "良い", "低い")) and "△" not in value and "×" not in value:
        return "good"
    if any(marker in value for marker in ("×", "厳しい", "非推奨", "非常に高い")):
        return "danger"
    if any(marker in value for marker in ("△", "注意", "高い", "普通")):
        return "warning"
    return "info"


def section_header(title: str, tone: str = "info") -> None:
    st.markdown(
        f'<div class="section-card-title tone-{tone}">{html.escape(title)}</div>',
        unsafe_allow_html=True,
    )


def render_compact_card(title: str, value: Any, tone: str = "info") -> None:
    st.markdown(
        (
            f'<div class="compact-card tone-{tone}">'
            f'<div class="compact-card-title">{html.escape(title)}</div>'
            f'<div class="compact-card-value">{html.escape(str(value))}</div>'
            "</div>"
        ),
        unsafe_allow_html=True,
    )


def render_diagnosis_summary_card(summary: dict[str, Any]) -> None:
    items = [
        ("総合判定", summary.get("headline", "-")),
        ("地域タイプ", summary.get("region_type", "-")),
        ("向いている経営モデル", summary.get("best_model", "-")),
        ("最大リスク", summary.get("max_risk", "-")),
        ("最優先アクション", summary.get("first_action", "-")),
    ]
    item_html = "".join(
        (
            '<div class="summary-item">'
            f'<div class="summary-label">{html.escape(label)}</div>'
            f'<div class="summary-value">{html.escape(str(value))}</div>'
            "</div>"
        )
        for label, value in items
    )
    comment = html.escape(str(summary.get("short_comment", "-")))
    st.markdown(
        (
            '<div class="diagnosis-card">'
            "<h3>診断サマリー</h3>"
            f'<div class="summary-grid">{item_html}</div>'
            f'<div class="summary-comment"><strong>一言コメント：</strong>{comment}</div>'
            "</div>"
        ),
        unsafe_allow_html=True,
    )


@contextmanager
def card_section(title: str, tone: str = "info"):
    with st.container(border=True):
        section_header(title, tone)
        yield


st.title("訪問介護市場分析")
st.caption("市町村ごとの市場指標と簡易判定を表示します。")

csv_url = CSV_URL
with st.sidebar:
    st.header("データ操作")
    reload_data = st.button("CSVを再読み込み")
    display_level = st.radio(
        "表示レベル",
        ["簡易版", "詳細版", "開発者向け"],
        index=1,
    )
    simple_view = display_level == "簡易版"
    detailed_view = display_level in {"詳細版", "開発者向け"}
    developer_view = display_level == "開発者向け"

    if developer_view:
        st.divider()
        st.write("判定ルール")
        st.write("- 競争後達成余力倍率2以上を有望ライン")
        st.write("- 高齢者可住地密度80未満は移動効率注意")
        st.write("- 都市部競争地域は営業難易度高")
        st.write("- 地方供給不足地域はシフト調整しやすい")
        st.write("- 250万円を安定運営ラインとする")
        st.caption(BASE_REVENUE_NOTE)

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
    render_compact_card("検索待ち", "市町村名を入力して検索してください。", "info")
    if developer_view:
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

search_display_names = build_search_display_names(df, name_column)
display_names = [
    f"{index}: {search_display_names.loc[index]}"
    for index, row in matches.iterrows()
]
selected_label = st.selectbox("該当データ", display_names)
selected_index = int(selected_label.split(":", 1)[0])
selected_row = matches.loc[selected_index]
municipality_name = str(selected_row.get(name_column, municipality_query))

metrics = collect_metrics(selected_row, df)
diagnosis_scope = get_diagnosis_scope(selected_row, df, metrics)
display_municipality_name = diagnosis_scope.get("display_name") or municipality_name
region = classify_region(metrics, municipality_name)
competition_data_issue = has_competition_data_issue(metrics)
region["competition_data_issue"] = competition_data_issue
region["diagnosis_scope"] = diagnosis_scope
region["estimated_home_care_users"] = calculate_estimated_home_care_users(metrics)
st.session_state["region_type"] = region
headline, comments = judge_market(metrics, region)
region["headline"] = headline
judgment_reasons = [comment.replace("判定理由：", "", 1) for comment in comments if comment.startswith("判定理由：")]
display_comments = [
    comment
    for comment in comments
    if not comment.startswith("判定理由：")
    and not comment.startswith("**地域タイプを踏まえた判定**")
    and not comment.startswith("**強み**")
    and not comment.startswith("**リスク**")
    and not comment.startswith("**推奨戦略**")
]

st.subheader(f"{display_municipality_name} の市場分析")
region_type = region.get("type", region)
region_comments = get_region_type_comments(str(region_type), metrics, region)
home_care_user_metric = metric_item(metrics, "訪問介護利用者数") or {}
uses_estimated_users = uses_estimated_home_care_users(metrics)
client_acquisition = calculate_client_acquisition_difficulty(metrics, region)
movement_efficiency = calculate_movement_efficiency(metrics, region)
region["client_acquisition_difficulty"] = client_acquisition
sales_strategy = get_sales_strategy(metrics, region)
region["sales_strategy"] = sales_strategy
startup_patterns = get_startup_pattern_recommendation(metrics, region)
region["startup_patterns"] = startup_patterns
entry_conditions = get_entry_conditions(str(region_type), metrics, region)
region["movement_efficiency"] = movement_efficiency
staffing_difficulty = calculate_staffing_difficulty(metrics, region)
region["staffing_difficulty"] = staffing_difficulty
collapse_risk = calculate_collapse_risk(metrics, region)
region["collapse_risk"] = collapse_risk
market_recovery = calculate_market_recovery(metrics, region)
region["market_recovery"] = market_recovery
market_future_potential = calculate_market_future_potential(metrics, region)
region["market_future_potential"] = market_future_potential
profitability_difficulty = calculate_profitability_difficulty(metrics, region)
region["profitability_difficulty"] = profitability_difficulty
required_users = calculate_required_users(metrics, region)
region["required_users"] = required_users
estimation_accuracy = calculate_estimation_accuracy(metrics)
region["estimation_accuracy"] = estimation_accuracy
strategy_comment = generate_strategy_comment(metrics, region)
region["strategy_comment"] = strategy_comment
existing_operator_advice = generate_existing_operator_advice(metrics, region)
region["existing_operator_advice"] = existing_operator_advice
priority_actions = generate_priority_actions(metrics, region)
region["priority_actions"] = priority_actions
diagnosis_summary = generate_diagnosis_summary(metrics, region)
region["diagnosis_summary"] = diagnosis_summary

render_diagnosis_summary_card(diagnosis_summary)

render_compact_card("総合判定", headline, ui_tone_from_text(str(headline)))
if judgment_reasons and not simple_view:
    with st.container(border=True):
        section_header("判定理由", "info")
        for reason in judgment_reasons[:3]:
            st.write(f"- {reason}")

if simple_view:
    render_compact_card("地域タイプ", region_type, "info")
missing_fields = region.get("missing_fields", [])
if missing_fields:
    if developer_view:
        st.warning(
            "地域タイプ分類に必要なデータが一部不足しています。\n\n"
            f"不足項目：{', '.join(missing_fields)}"
        )
    else:
        st.warning("地域タイプ分類に必要なデータが一部不足しています。")

if competition_data_issue:
    with card_section("競合事業所数データ未取得", "warning"):
        st.write("競合事業所数が未取得のため、競争後評価は参考値です。")
        if developer_view:
            office_metric = metric_item(metrics, "従来型訪問介護事業所数") or {}
            sakoju_metric = metric_item(metrics, "サ高住系事業所数") or {}
            st.write(f"- 訪問介護事業所数の取得元：{office_metric.get('取得元列') or '未取得'}")
            st.write(f"- サ高住系事業所数の取得元：{sakoju_metric.get('取得元列') or '未取得'}")

if uses_estimated_users:
    with card_section("推計値に関する注記", "warning"):
        st.write(ESTIMATED_USERS_NOTE)

if developer_view:
    with st.expander("訪問介護利用者数の取得元"):
        source = home_care_user_metric.get("取得元列") or "未取得"
        source_label = source
        if home_care_user_metric.get("推計"):
            source_label = f"{source}による推計"
        else:
            source_label = f"CSV列：{source}"
        st.write(f"取得元：{source_label}")
        st.write(f"推計利用率：{ESTIMATED_HOME_CARE_USER_RATE_SOURCE_LABEL}")
        st.write(f"値：{home_care_user_metric.get('値', '-')}")
        estimated_home_care_users = region.get("estimated_home_care_users")
        if estimated_home_care_users is not None:
            st.write(f"補助推計値：約{estimated_home_care_users:,.0f}人")

    with st.expander("診断対象モード"):
        st.write(diagnosis_scope.get("label", "市町村単位で診断"))
        st.write(f"表示名：{display_municipality_name}")
        st.write(f"CSV行名：{municipality_name}")

if simple_view:
    with card_section("一言コメント", "info"):
        st.write(diagnosis_summary.get("short_comment", "-"))

    with card_section("強み", "good"):
        for strength in region_comments["strengths"][:2]:
            st.write(f"- {strength}")

    with card_section("リスク", "warning"):
        for risk in region_comments["risks"][:2]:
            st.write(f"- {risk}")

    with card_section("推奨戦略", "good"):
        for strategy in region_comments["strategies"][:2]:
            st.write(f"- {strategy}")

    with card_section("詳細版で確認できること", "info"):
        st.write(
            "詳細版では、サ高住500m圏カバー率、崩壊リスク、人材確保難易度、"
            "黒字化難易度、推奨営業戦略、既存事業所向け改善提案などを確認できます。"
        )

if detailed_view:
    with card_section("総合戦略コメント", "info"):
        for paragraph in strategy_comment.split("\n\n"):
            st.write(paragraph)

    with card_section("優先アクション順位", "danger"):
        st.markdown("#### 1. 最優先でやること")
        for item in priority_actions["first"]:
            st.write(f"- {item}")

        st.markdown("#### 2. 次にやること")
        for item in priority_actions["second"]:
            st.write(f"- {item}")

        st.markdown("#### 3. 後回しでよいこと")
        for item in priority_actions["later"]:
            st.write(f"- {item}")

    with card_section("向いている開業パターン", "good"):
        st.markdown("#### 最適パターン")
        for item in startup_patterns["best"]:
            st.write(f"- {item}")

        st.markdown("#### 条件付きで可能なパターン")
        for item in startup_patterns["possible"]:
            st.write(f"- {item}")

        st.markdown("#### 避けるべきパターン")
        for item in startup_patterns["avoid"]:
            st.write(f"- {item}")

        st.markdown("#### コメント")
        st.write(startup_patterns["comment"])

    with card_section("経営モデル適性", "good"):
        business_model_scores = region.get("business_model_scores", {})
        if business_model_scores:
            sorted_business_models = sorted(business_model_scores.items(), key=lambda item: item[1], reverse=True)
            for model_name, score in sorted_business_models:
                st.write(f"- {model_name}：{score}点")

            top_models = sorted_business_models[:2]
            if top_models:
                top_model_names = "、".join(model_name for model_name, _ in top_models)
                render_compact_card("相性の良い経営モデル", f"この地域では{top_model_names}との相性が良いです。", "good")

            if developer_view:
                business_model_score_details = region.get("business_model_score_details", {})
                with st.expander("経営モデル適性スコアの内訳"):
                    for model_name, score in sorted_business_models:
                        st.markdown(f"**{model_name}：{score}点**")
                        details = business_model_score_details.get(model_name, [])
                        if details:
                            for detail in details:
                                st.write(f"- {detail}")
                        else:
                            st.write("- 加点条件に該当する項目はありません")

    with card_section("利用者獲得難易度", ui_tone_from_text(str(client_acquisition["level"]))):
        st.write(f"{client_acquisition['level']}（{client_acquisition['score']}点）")

        st.markdown("#### 主な理由")
        for reason in client_acquisition["reasons"]:
            st.write(f"- {reason}")

        st.markdown("#### 利用者獲得上の壁")
        for barrier in client_acquisition["barriers"]:
            st.write(f"- {barrier}")

    with card_section("推奨営業戦略", "good"):
        st.markdown("#### 最初に狙う営業先")
        for target in sales_strategy["first_targets"]:
            st.write(f"- {target}")

        st.markdown("#### 営業の優先順位")
        for action in sales_strategy["priority_actions"]:
            st.write(f"- {action}")

        st.markdown("#### 注意すべき営業ミス")
        for mistake in sales_strategy["mistakes_to_avoid"]:
            st.write(f"- {mistake}")

    if market_recovery["score"] >= 70:
        recovery_tone = "good"
    elif market_recovery["score"] < 50:
        recovery_tone = "danger"
    else:
        recovery_tone = "warning"
    with card_section("市場回復性", recovery_tone):
        st.write(f"{market_recovery['level']}（{market_recovery['score']}点）")

        st.markdown("#### 回復しやすい理由")
        for reason in market_recovery["reasons"]:
            st.write(f"- {reason}")

        st.markdown("#### 回復を難しくする要因")
        for risk in market_recovery["risks"]:
            st.write(f"- {risk}")

    if market_future_potential["score"] >= 70:
        future_tone = "good"
    elif market_future_potential["score"] < 50:
        future_tone = "danger"
    else:
        future_tone = "warning"
    with card_section("市場将来性", future_tone):
        st.write(f"{market_future_potential['level']}（{market_future_potential['score']}点）")

        st.markdown("#### 将来性がある理由")
        for reason in market_future_potential["reasons"]:
            st.write(f"- {reason}")

        st.markdown("#### 将来性を下げる要因")
        for risk in market_future_potential["risks"]:
            st.write(f"- {risk}")

    with card_section("黒字化難易度", ui_tone_from_text(str(profitability_difficulty["level"]))):
        st.write(f"{profitability_difficulty['level']}（{profitability_difficulty['score']}点）")

        st.markdown("#### 黒字化を難しくする要因")
        for reason in profitability_difficulty["reasons"]:
            st.write(f"- {reason}")

        st.markdown("#### 黒字化のための打ち手")
        for action in profitability_difficulty["actions"]:
            st.write(f"- {action}")

    with card_section("人材確保難易度", ui_tone_from_text(str(staffing_difficulty["level"]))):
        st.write(f"{staffing_difficulty['level']}（{staffing_difficulty['score']}点）")

        st.markdown("#### 主な理由")
        for reason in staffing_difficulty["reasons"]:
            st.write(f"- {reason}")

        st.markdown("#### 対策")
        for action in staffing_difficulty["recommended_actions"]:
            st.write(f"- {action}")

    with card_section("移動効率指数", ui_tone_from_text(str(movement_efficiency["level"]))):
        st.write(f"{movement_efficiency['level']}（{movement_efficiency['score']}点）")

        st.markdown("#### 主な理由")
        for reason in movement_efficiency["reasons"]:
            st.write(f"- {reason}")

        st.markdown("#### 移動効率に影響する要因")
        for factor_name, factor_value in movement_efficiency["factors"].items():
            st.write(f"- {factor_name}：{factor_value}")

    with card_section("崩壊リスク分析", ui_tone_from_text(str(collapse_risk["main_collapse_pattern"]))):
        collapse_labels = {
            "human_resource_risk": "人材崩壊リスク",
            "fixed_cost_risk": "固定費崩壊リスク",
            "competition_risk": "競争崩壊リスク",
            "movement_risk": "移動効率崩壊リスク",
            "client_concentration_risk": "利用者集中リスク",
            "regional_decline_risk": "地域縮小リスク",
        }
        for risk_key, label in collapse_labels.items():
            score = collapse_risk[risk_key]
            level = collapse_risk["risk_levels"][risk_key]
            st.write(f"- {label}：{level}（{score}点）")

        st.markdown("#### 最も危険な崩壊パターン")
        st.write(collapse_risk["main_collapse_pattern"])

        st.markdown("#### 主な理由")
        for reason in collapse_risk["reasons"]:
            st.write(f"- {reason}")

    with card_section("既存事業所向け改善提案", "warning"):
        st.markdown("#### 見直すべきポイント")
        for item in existing_operator_advice["review_points"]:
            st.write(f"- {item}")

        st.markdown("#### すぐにできる改善策")
        for item in existing_operator_advice["quick_actions"]:
            st.write(f"- {item}")

        st.markdown("#### 中長期で見直すべき戦い方")
        for item in existing_operator_advice["mid_long_term_actions"]:
            st.write(f"- {item}")

    with card_section("地域タイプ分析", "info"):
        st.markdown("**分類理由：**")
        for reason in region.get("reasons", []):
            st.write(f"・{reason}")

        market_size = region.get("market_size")
        market_size_man_yen = market_size / 10_000 if market_size is not None else None

        st.markdown("**主要指標：**")
        st.write(f"・高齢者人口密度：{format_region_number(region.get('elderly_density'), 1)}人/km²")
        st.write(f"・実質競合数：{format_region_number(region.get('effective_competitors'), 1)}事業所")
        st.write(f"・1事業所あたり潜在利用者数：{format_region_number(region.get('users_per_office'), 1)}人")
        st.write(f"・市場規模：{format_region_number(market_size_man_yen, 1)}万円/月")
        st.write(f"・理論市場余力倍率：{format_region_number(region.get('theoretical_capacity_ratio'), 2)}倍")
        st.write(f"・競争後達成余力倍率：{format_region_number(region.get('capacity_ratio'), 2)}倍")

        sakoju_cover_rate = region.get("sakoju_cover_rate")
        sakoju_cover_percent = sakoju_cover_rate * 100 if sakoju_cover_rate is not None else None
        st.markdown("**サ高住影響：**")
        st.write(f"・サ高住500m圏カバー率：{format_region_number(sakoju_cover_percent, 1)}％")
        st.write(f"・サ高住競合影響：{region.get('sakoju_impact', '-')}")
        st.write(f"・サ高住の見方：{region.get('sakoju_view', '-')}")

        type_scores = region.get("type_scores", {})
        if type_scores:
            section_header("地域タイプ判定スコア", "info")
            for scored_type, score in sorted(type_scores.items(), key=lambda item: item[1], reverse=True):
                st.write(f"- {scored_type}：{score}点")

            if developer_view:
                type_score_details = region.get("type_score_details", {})
                with st.expander("地域タイプ判定スコアの内訳"):
                    for scored_type, score in sorted(type_scores.items(), key=lambda item: item[1], reverse=True):
                        st.markdown(f"**{scored_type}：{score}点**")
                        details = type_score_details.get(scored_type, [])
                        if details:
                            for detail in details:
                                st.write(f"- {detail}")
                        else:
                            st.write("- 加点条件に該当する項目はありません")

        section_header("参入条件", "warning")
        st.markdown("#### 必須条件")
        for item in entry_conditions["required"]:
            st.write(f"- {item}")

        st.markdown("#### 推奨条件")
        for item in entry_conditions["recommended"]:
            st.write(f"- {item}")

        st.markdown("#### 避けるべき条件")
        for item in entry_conditions["avoid"]:
            st.write(f"- {item}")

    with card_section("推定必要利用者数", "info"):
        st.write(f"- 最低維持ライン：約{required_users.get('minimum_line', '-')}人")
        st.write(f"- 安定運営ライン：約{required_users.get('stable_line', '-')}人")
        st.write(f"- 夫婦経営安定ライン：約{required_users.get('family_stable_line', '-')}人")
        st.write(f"- 小規模高還元ライン：約{required_users.get('high_return_line', '-')}人")

        st.markdown("#### コメント")
        st.write(required_users.get("comment", "-"))
        st.caption(BASE_REVENUE_NOTE)

        if estimation_accuracy:
            section_header("推計精度検証", ui_tone_from_text(str(estimation_accuracy["accuracy_level"])))
            st.write(f"- 推計利用者数：約{estimation_accuracy['estimated_users']:,}人")
            st.write(f"- 実利用者数：約{estimation_accuracy['actual_users']:,}人")
            st.write(f"- 誤差人数：約{estimation_accuracy['difference']:,}人")
            st.write(f"- 誤差率：{estimation_accuracy['difference_rate']:.1f}%")
            st.write(f"- 精度判定：{estimation_accuracy['accuracy_level']}")

    with card_section("データについての注意", "warning"):
        for paragraph in DATA_QUALITY_NOTE_PARAGRAPHS:
            st.write(paragraph)

if detailed_view:
    with card_section("詳細指標", "info"):
        st.dataframe(
            pd.DataFrame(metrics)[["指標", "値", "取得元列", "推計"]],
            use_container_width=True,
            hide_index=True,
        )

if developer_view:
    st.subheader("詳細指標・その他")
    metric_columns = st.columns(3)
    for index, metric in enumerate(metrics):
        with metric_columns[index % 3]:
            st.metric(metric["指標"], metric["値"])

    st.subheader("指標一覧")
    st.dataframe(
        pd.DataFrame(metrics)[["指標", "値", "取得元列", "推計"]],
        use_container_width=True,
        hide_index=True,
    )

    st.subheader("CSV列マッピング確認")
    st.markdown("#### 政令指定都市の行政区合算")
    for label in ("従来型訪問介護事業所数", "サ高住系事業所数"):
        metric = metric_item(metrics, label) or {}
        source = str(metric.get("取得元列", ""))
        display_label = "訪問介護事業所数" if label == "従来型訪問介護事業所数" else label
        if source.startswith("行政区合算"):
            st.write(f"- {display_label}：行政区合算で取得")
        else:
            st.write(f"- {display_label}：{source or '未取得'}")

    mapping_rows = [
        {
            "指標": metric["指標"],
            "取得元列": metric.get("取得元列") or "未取得",
            "取得方法": (
                "行政区合算"
                if str(metric.get("取得元列", "")).startswith("行政区合算")
                else "推計・派生計算"
                if metric.get("推計")
                else "CSV列"
            ),
        }
        for metric in metrics
    ]
    st.dataframe(
        pd.DataFrame(mapping_rows),
        use_container_width=True,
        hide_index=True,
    )

    unresolved_metrics = [
        metric["指標"]
        for metric in metrics
        if metric.get("数値") is None and not metric.get("取得元列")
    ]
    if unresolved_metrics:
        with st.expander("未取得の指標"):
            st.write("以下の指標はCSV列から取得できず、推計もできませんでした。")
            for item in unresolved_metrics:
                st.write(f"- {item}")

CHECKPOINTS_BY_REGION = {
    "地方都市型": [
        "自宅兼事務所・夫婦経営との相性が表現できているか",
        "サ高住を競合ではなく紹介元寄りに見られているか",
        "家賃・固定費の説明が誤解なく表示されているか",
    ],
    "供給不足型過疎地": [
        "競合が少ないことによる有望性が出ているか",
        "一事業所増加による市場バランス崩れリスクが出ているか",
    ],
    "超過疎地型": [
        "高齢化率ではなく高齢者絶対数不足が表現されているか",
        "移動効率の悪さが出ているか",
        "250万円達成困難という視点が出ているか",
    ],
    "大都市型": [
        "市場規模はあるが、0スタートが危険という説明が出ているか",
        "ケアマネ関係や居宅併設の必要性が出ているか",
    ],
    "超高密集競争型": [
        "移動効率は良いが市場が狭く競合過多という説明が出ているか",
        "地盤引継ぎなしの新規参入非推奨が出ているか",
    ],
}

if developer_view and display_comments:
    st.subheader("その他の判定コメント")
    for comment in display_comments:
        st.write(f"- {comment}")

if developer_view:
    st.subheader("取得した元データ")
    st.dataframe(
        pd.DataFrame([selected_row]),
        use_container_width=True,
        hide_index=True,
    )

download_text = (
    f"# {display_municipality_name} 訪問介護市場分析\n\n"
    f"## 簡易市場判定\n{headline}\n\n"
    f"{revenue_assumption_to_markdown()}\n"
    f"{data_quality_note_to_markdown()}\n"
    f"{estimated_users_note_to_markdown(metrics)}"
    f"{detailed_report_to_markdown(region, entry_conditions)}\n\n"
    f"## 指標\n{metrics_to_markdown(metrics)}\n\n"
    "## コメント\n"
    + "\n".join(f"- {comment}" for comment in comments)
    + "\n"
)

if detailed_view:
    st.download_button(
        "分析結果をMarkdownでダウンロード",
        download_text,
        file_name=f"{display_municipality_name}_訪問介護市場分析.md",
        mime="text/markdown",
    )

if developer_view:
    with st.expander("判定チェックポイント"):
        st.write("- 地域タイプは肌感覚と合っているか")
        st.write("- 総合判定は厳しすぎないか／甘すぎないか")
        st.write("- サ高住の見方は地域実態に合っているか")
        st.write("- 競合数に対して市場余力の説明は自然か")
        st.write("- 推奨戦略は現場感と合っているか")

        region_type = region.get("type", "")
        region_checkpoints = CHECKPOINTS_BY_REGION.get(region_type, [])
        if region_checkpoints:
            st.markdown(f"**{region_type} の確認観点：**")
            for checkpoint in region_checkpoints:
                st.write(f"- {checkpoint}")
