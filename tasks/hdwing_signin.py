#!/usr/bin/env python3
# name: HDWinG 签到
# cron: 17 9 * * *
"""HDWinG（hdwing.org）每日签到，签到结果通过面板通知推送。

环境变量：
    HDWING_COOKIE  必填，浏览器里 hdwing.org 的 Cookie，至少包含 hdchina=xxx
                   多账号用换行或 & 分隔

签到流程（站点是 NexusPHP，签到插件沿用 HDChina 的实现）：
    1. GET  /index.php，从 <meta name="x-csrf"> 取 csrf，同时拿到新的 PHPSESSID
    2. POST /plugin_sign-in.php?cmd=signin，表单 csrf=...
       返回 {"state": "success", "signindays": 连续天数, "integral": 魔力}，失败时带 msg
"""

import json
import os
import re
import sys
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from lib.daidai import notify  # noqa: E402

BASE = "https://hdwing.org/"
UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36"
)


class Site:
    """带 Cookie 的简易会话，会把响应里的 Set-Cookie 合并进后续请求。"""

    def __init__(self, cookie):
        self.cookies = {}
        for pair in cookie.split(";"):
            if "=" in pair:
                key, value = pair.split("=", 1)
                self.cookies[key.strip()] = value.strip()

    def request(self, path, form=None):
        data = None if form is None else urllib.parse.urlencode(form).encode()
        req = urllib.request.Request(BASE + path, data=data)
        req.add_header("User-Agent", UA)
        req.add_header("Referer", BASE + "index.php")
        req.add_header("Cookie", "; ".join(f"{k}={v}" for k, v in self.cookies.items()))
        if form is not None:
            req.add_header("X-Requested-With", "XMLHttpRequest")

        with urllib.request.urlopen(req, timeout=20) as resp:
            for header in resp.headers.get_all("Set-Cookie") or []:
                key, _, value = header.split(";", 1)[0].partition("=")
                self.cookies[key.strip()] = value
            return resp.geturl(), resp.read().decode("utf-8", "replace")


def signin(cookie):
    """签到一个账号，返回一行结果描述；Cookie 失效等异常直接抛出。"""
    site = Site(cookie)
    url, html = site.request("index.php")
    if "login.php" in url:
        raise RuntimeError("Cookie 已失效，请重新登录后更新 HDWING_COOKIE")

    name = re.search(r"userdetails\.php\?id=\d+[^>]*><b>([^<]+)</b>", html)
    name = name.group(1) if name else "未知用户"

    if "do_signin(" not in html:
        return f"{name}：今天已经签到过了"

    csrf = re.search(r'<meta name="x-csrf" content="([^"]+)"', html)
    if not csrf:
        raise RuntimeError(f"{name}：页面里没找到 csrf，站点结构可能变了")

    _, body = site.request("plugin_sign-in.php?cmd=signin", {"csrf": csrf.group(1)})
    result = json.loads(body)
    if result.get("state") == "success":
        return f"{name}：签到成功，连续 {result['signindays']} 天，魔力 +{result['integral']}"
    return f"{name}：签到失败，{result.get('msg') or body}"


def main():
    raw = os.environ.get("HDWING_COOKIE", "")
    cookies = [c.strip() for c in re.split(r"[\n&]", raw) if c.strip()]
    if not cookies:
        print("未设置 HDWING_COOKIE")
        sys.exit(1)

    lines, failed = [], False
    for index, cookie in enumerate(cookies, 1):
        try:
            line = signin(cookie)
        except Exception as err:  # noqa: BLE001 单个账号出错不影响其他账号
            line, failed = f"账号 {index}：{err}", True
        if "签到失败" in line:
            failed = True
        print(line)
        lines.append(line)

    notify("HDWinG 签到失败" if failed else "HDWinG 签到", "\n".join(lines))
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
