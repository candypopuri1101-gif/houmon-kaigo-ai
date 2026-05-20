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


METRICS = [
    MetricSpec("人口", ("人口", "総人口", "総人口数"), "人"),
    MetricSpec("高齢者人口", ("高齢者人口", "65歳以上人口", "65歳以上", "老年人口"), "人"),
    MetricSpec("人口密度", ("人口密度", "総人口密度"), "人/km2", 1),
    MetricSpec(
        "高齢者可住地密度",
        ("高齢者可住地密度", "65歳以上可住地密度", "高齢者密度"),
        "人/km2",
        1,
    ),
    MetricSpec("実質競合数", ("実質競合数", "競合数", "実質競合事業所数"), "事業所", 1),
    MetricSpec("達成余力倍率", ("達成余力倍率", "余力倍率"), "倍", 2),
    MetricSpec("参入後達成余力倍率", ("参入後達成余力倍率", "参入後余力倍率"), "倍", 2),
    MetricSpec("訪問介護事業所数", ("訪問介護事業所数", "訪問介護事業者数", "事業所数"), "事業所"),
    MetricSpec(
        "推定訪問介護利用者数",
        ("推定訪問介護利用者数", "推定利用者数", "訪問介護利用者数"),
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
        return "-" if value is None or str(value).strip() == "" else str(value)

    formatted = f"{number:,.{spec.decimals}f}"
    if spec.decimals == 0:
        formatted = f"{number:,.0f}"
    return f"{formatted} {spec.unit}".strip()
