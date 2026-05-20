from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Any

import gspread
import pandas as pd
import streamlit as st
from dotenv import load_dotenv
from google.oauth2.service_account import Credentials
from openai import OpenAI


load_dotenv()

DEFAULT_SHEET_NAME = "市町村データ"
DEFAULT_MODEL = os.getenv("OPENAI_MODEL", "gpt-5")
SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]


@dataclass(frozen=True)
class MetricSpec:
    label: str
    aliases: tuple[str, ...]
    unit: str = ""
    decimals: int = 0


METRICS = [
    MetricSpec("人口", ("人口", "総人口", "総人口数"), "人"),
    MetricSpec("65歳以上人口", ("65歳以上人口", "高齢者人口", "65歳以上", "老年人口"), "人"),
    MetricSpec("総面積", ("総面積", "面積", "総面積km2", "総面積_km2", "総面積（km2）", "総面積(km2)"), "km2", 2),
    MetricSpec("可住地面積", ("可住地面積", "可住面積", "可住地面積km2", "可住地面積（km2）", "可住地面積(km2)"), "km2", 2),
    MetricSpec("人口密度", ("人口密度", "総人口密度"), "人/km2", 1),
    MetricSpec("高齢者可住地密度", ("高齢者可住地密度", "65歳以上可住地密度", "高齢者密度"), "人/km2", 1),
    MetricSpec("訪問介護事業所数", ("訪問介護事業所数", "訪問介護事業者数", "事業所数"), "事業所"),
    MetricSpec("実質競合数", ("実質競合数", "競合数", "実質競合事業所数"), "事業所", 1),
    MetricSpec("推定訪問介護利用者数", ("推定訪問介護利用者数", "推定利用者数", "訪問介護利用者数"), "人"),
    MetricSpec("1事業所あたり潜在利用者数", ("1事業所あたり潜在利用者数", "一事業所あたり潜在利用者数", "事業所あたり潜在利用者数"), "人/事業所", 1),
    MetricSpec("250万円達成必要人数", ("250万円達成必要人数", "250万達成必要人数", "月商250万円達成必要人数"), "人"),
    MetricSpec("達成余力倍率", ("達成余力倍率", "余力倍率"), "倍", 2),
    MetricSpec("参入後達成余力倍率", ("参入後達成余力倍率", "参入後余力倍率"), "倍", 2),
]


st.set_page_config(
    page_title="訪問介護市場分析",
    page_icon="📈",
    layout="wide",
)


def get_secret(name: str, default: Any = None) -> Any:
    try:
        return st.secrets.get(name, default)
    except Exception:
        return default


def extract_spreadsheet_id(value: str) -> str:
    value = value.strip()
    match = re.search(r"/spreadsheets/d/([a-zA-Z0-9-_]+)", value)
    return match.group(1) if match else value


def normalize_key(value: str) -> str:
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

    text = str(value).strip()
    if not text:
        return None
    text = text.replace(",", "")
    match = re.search(r"-?\d+(?:\.\d+)?", text)
    if match:
        return float(match.group())
