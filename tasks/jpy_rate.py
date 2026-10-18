#!/usr/bin/env python3
# name: 日元汇率
# cron: 0 9 * * *
"""每天查询日元兑人民币汇率并推送，低于 RATE_ALERT 阈值时标题改为提醒。

环境变量：
    RATE_ALERT  可选，1 日元兑人民币的提醒阈值，例如 0.045
"""

import json
import os
import sys
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from lib.daidai import notify  # noqa: E402

RATE_API = "https://open.er-api.com/v6/latest/JPY"


def get_rate():
    with urllib.request.urlopen(RATE_API, timeout=15) as resp:
        data = json.load(resp)
    return data["rates"]["CNY"], data["time_last_update_utc"]


def main():
    rate_alert = float(os.environ.get("RATE_ALERT") or 0)
    rate, updated = get_rate()
    cny_per_10000 = rate * 10000
    print(f"1 JPY = {rate} CNY，1 万日元 ≈ {cny_per_10000:.2f} 元（{updated}）")

    title = "日元汇率提醒" if rate < rate_alert else "今日日元汇率"
    notify(title, f"1 万日元 ≈ {cny_per_10000:.2f} 人民币\n更新时间：{updated}")


if __name__ == "__main__":
    main()
