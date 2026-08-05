"""tushare 代理连通性测试脚本（临时工具）。

用法：密钥从环境变量读取，避免硬编码泄露：
    TUSHARE_AGENT_KEY=... .venv/bin/python notebooks/test_tushare.py

密钥配置在项目 .env（已 gitignore）：TUSHARE_AGENT_KEY=<key>
"""

import os

import requests

os.environ["NO_PROXY"] = "*"

API_KEY = os.environ.get("TUSHARE_AGENT_KEY", "")
PROXY_URL = os.environ.get("TUSHARE_AGENT_URL", "http://175.27.156.38")

if not API_KEY:
    raise ValueError("TUSHARE_AGENT_KEY 未设置，请在 .env 中配置或环境变量注入")


def Q(a, p={}, f=""):
    data = requests.post(
        f"{PROXY_URL}/v1/tushare/query",
        headers={
            "X-API-Key": API_KEY,
            "Content-Type": "application/json",
        },
        json={"api_name": a, "params": p, "fields": f},
        timeout=60,
    ).json()["data"]
    return [dict(zip(d["fields"], r)) for r in d["items"]] if data else []


# 用法
print(Q("daily", {"ts_code": "000001.SZ", "start_date": "20260701", "end_date": "20260804"})[:3])
