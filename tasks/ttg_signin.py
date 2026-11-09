#!/usr/bin/env python3
# name: TTG 签到
# cron: 29 9 * * *
"""TTG（totheglory.im）每日签到，签到结果通过面板通知推送。

环境变量：
    TTG_COOKIE  必填，totheglory.im 的 Cookie，至少包含 uid=xxx; pass=xxx
                多账号用换行或 & 分隔；可由 cookiecloud_sync.py 自动写入

签到流程：
    1. GET  /          首页内联 JS 里有 signed_timestamp 和 signed_token
    2. POST /signed.php，表单带上这两个值，返回一段纯文本结果
       重复签到时首页照样有 token，服务端会回「今天已签到过」，不用自己判断
"""

import os
import re
import sys
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from lib.daidai import notify  # noqa: E402

BASE = "https://totheglory.im/"
UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36"
)


def request(cookie, path, form=None):
    data = None if form is None else urllib.parse.urlencode(form).encode()
    req = urllib.request.Request(BASE + path, data=data)
    req.add_header("User-Agent", UA)
    req.add_header("Referer", BASE)
    req.add_header("Cookie", cookie)
    if form is not None:
        req.add_header("X-Requested-With", "XMLHttpRequest")
    with urllib.request.urlopen(req, timeout=20) as resp:
        return resp.geturl(), resp.read().decode("utf-8", "replace")


def signin(cookie):
    """签到一个账号，返回一行结果描述；Cookie 失效等异常直接抛出。"""
    url, html = request(cookie, "")
    if "login.php" in url:
        raise RuntimeError("Cookie 已失效，请重新登录后更新 TTG_COOKIE")

    name = re.search(r"欢迎回来，\s*(?:<[^>]+>\s*)*([^<\s]+)", html)
    name = name.group(1) if name else "未知用户"

    params = re.search(r'signed_timestamp:\s*"(\d+)",\s*signed_token:\s*"(\w+)"', html)
    if not params:
        raise RuntimeError(f"{name}：首页没找到签到参数，站点结构可能变了")

    _, text = request(
        cookie, "signed.php", {"signed_timestamp": params.group(1), "signed_token": params.group(2)}
    )
    text = re.sub(r"<[^>]+>", "", text).strip()
    return f"{name}：{text}"


def main():
    raw = os.environ.get("TTG_COOKIE", "")
    cookies = [c.strip() for c in re.split(r"[\n&]", raw) if c.strip()]
    if not cookies:
        print("未设置 TTG_COOKIE")
        sys.exit(1)

    lines, failed = [], False
    for index, cookie in enumerate(cookies, 1):
        try:
            line = signin(cookie)
        except Exception as err:  # noqa: BLE001 单个账号出错不影响其他账号
            line, failed = f"账号 {index}：{err}", True
        print(line)
        lines.append(line)

    notify("TTG 签到失败" if failed else "TTG 签到", "\n".join(lines))
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
