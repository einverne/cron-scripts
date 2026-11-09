#!/usr/bin/env python3
# name: Rousi 签到
# cron: 23 9 * * *
"""RousiPro（rousi.pro）每日签到，签到结果通过面板通知推送。

环境变量：
    ROUSI_COOKIE  必填，rousi.pro 的 Cookie，即 __Host-peergo_session=xxx
                  多账号用换行或 & 分隔；可由 cookiecloud_sync.py 自动写入
    ROUSI_MODE    可选，fixed（默认，固定 100 魔力）或 random（随机 1~300 魔力）

签到流程（站点是 JSON API，日期按 Asia/Shanghai 划分）：
    1. GET  /api/v1/session         拿 csrf_token 和用户名
    2. GET  /api/v1/me/attendance   claimed_today 为 true 时说明今天签过了
    3. POST /api/v1/me/attendance   头部带 X-CSRF-Token、Idempotency-Key，body {"mode": ...}
"""

import json
import os
import re
import sys
import urllib.error
import urllib.request
import uuid

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from lib.daidai import notify  # noqa: E402

BASE = "https://rousi.pro"
UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36"
)


def api(cookie, method, path, payload=None, headers=None):
    """调用站点接口，返回 (状态码, JSON)；204 等空响应返回 None。"""
    data = None if payload is None else json.dumps(payload).encode()
    req = urllib.request.Request(BASE + path, data=data, method=method)
    req.add_header("User-Agent", UA)
    req.add_header("Cookie", cookie)
    req.add_header("Accept", "application/json")
    req.add_header("Origin", BASE)
    req.add_header("Referer", BASE + "/")
    if data is not None:
        req.add_header("Content-Type", "application/json")
    for key, value in (headers or {}).items():
        req.add_header(key, value)

    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            status, body = resp.status, resp.read().decode()
    except urllib.error.HTTPError as err:
        status, body = err.code, err.read().decode("utf-8", "replace")
    try:
        return status, json.loads(body) if body else None
    except ValueError:
        return status, {"raw": body[:200]}


def signin(cookie, mode):
    """签到一个账号，返回一行结果描述；Cookie 失效等异常直接抛出。"""
    _, session = api(cookie, "GET", "/api/v1/session")
    if not session or not session.get("csrf_token"):
        raise RuntimeError("Cookie 已失效，请重新登录后更新 ROUSI_COOKIE")
    name = session["user"]["username"]

    _, status = api(cookie, "GET", "/api/v1/me/attendance")
    if status and status.get("claimed_today"):
        return f"{name}：今天已经签到过了，连续 {status['current_streak']} 天，累计 {status['total_days']} 天"

    code, result = api(
        cookie,
        "POST",
        "/api/v1/me/attendance",
        {"mode": mode},
        {"X-CSRF-Token": session["csrf_token"], "Idempotency-Key": str(uuid.uuid4())},
    )
    if code >= 400 or not result:
        return f"{name}：签到失败，HTTP {code} {json.dumps(result, ensure_ascii=False)}"

    # 返回 201 和这次的签到记录：total_reward = base_reward + streak_reward
    return (
        f"{name}：签到成功（{mode}），魔力 +{result['total_reward']}，"
        f"连续 {result['current_streak']} 天，累计 {result['total_days']} 天"
    )


def main():
    raw = os.environ.get("ROUSI_COOKIE", "")
    cookies = [c.strip() for c in re.split(r"[\n&]", raw) if c.strip()]
    if not cookies:
        print("未设置 ROUSI_COOKIE")
        sys.exit(1)
    mode = os.environ.get("ROUSI_MODE") or "fixed"

    lines, failed = [], False
    for index, cookie in enumerate(cookies, 1):
        try:
            line = signin(cookie, mode)
        except Exception as err:  # noqa: BLE001 单个账号出错不影响其他账号
            line, failed = f"账号 {index}：{err}", True
        if "签到失败" in line:
            failed = True
        print(line)
        lines.append(line)

    notify("Rousi 签到失败" if failed else "Rousi 签到", "\n".join(lines))
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
