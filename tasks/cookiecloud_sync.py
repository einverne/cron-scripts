#!/usr/bin/env python3
# name: CookieCloud 同步
# cron: 0 9 * * *
"""从自建 CookieCloud 拉取浏览器 Cookie，按映射写回面板环境变量。

浏览器装 CookieCloud 插件定时上传 Cookie，本任务把指定域名的 Cookie 拼成
`k1=v1; k2=v2` 写进对应的环境变量，签到类脚本照常读环境变量即可，不用改。

环境变量：
    COOKIECLOUD_URL       必填，服务地址，例如 https://cookiecloud.example.com
    COOKIECLOUD_UUID      必填，插件里的「用户 KEY · UUID」
    COOKIECLOUD_PASSWORD  必填，插件里的「端对端加密密码」
    COOKIECLOUD_MAP       必填，每行一条 `环境变量名=域名`，例如：
                              HDWING_COOKIE=hdwing.org
                          域名会同时匹配 .hdwing.org 和子域名

解密交给服务端：POST /get/{uuid} 带上 password，返回明文 JSON，所以只用标准库。
"""

import json
import os
import sys
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from lib.daidai import notify, upsert_env  # noqa: E402


def fetch_cookies(url, uuid, password):
    """返回 {域名: [cookie, ...]}，域名是浏览器里的原样，可能带前导点。"""
    req = urllib.request.Request(
        f"{url.rstrip('/')}/get/{uuid}",
        data=json.dumps({"password": password}).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.load(resp)
    return data.get("cookie_data") or {}


def cookie_header(cookie_data, domain):
    """把某个域名（含子域名）下的 Cookie 拼成请求头格式，同名时后出现的覆盖前面的。"""
    pairs = {}
    for host, cookies in cookie_data.items():
        host = host.lstrip(".")
        if host == domain or host.endswith("." + domain):
            for cookie in cookies:
                pairs[cookie["name"]] = cookie["value"]
    return "; ".join(f"{k}={v}" for k, v in pairs.items())


def parse_map(raw):
    mapping = []
    for line in raw.splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            name, _, domain = line.partition("=")
            mapping.append((name.strip(), domain.strip()))
    return mapping


def main():
    env = os.environ
    required = ["COOKIECLOUD_URL", "COOKIECLOUD_UUID", "COOKIECLOUD_PASSWORD", "COOKIECLOUD_MAP"]
    missing = [name for name in required if not env.get(name)]
    if missing:
        print("缺少环境变量：" + ", ".join(missing))
        sys.exit(1)

    cookie_data = fetch_cookies(env["COOKIECLOUD_URL"], env["COOKIECLOUD_UUID"], env["COOKIECLOUD_PASSWORD"])
    print(f"CookieCloud 返回 {len(cookie_data)} 个域名")

    errors = []
    for name, domain in parse_map(env["COOKIECLOUD_MAP"]):
        value = cookie_header(cookie_data, domain)
        if not value:
            errors.append(f"{name}：CookieCloud 里没有 {domain} 的 Cookie，检查插件的同步域名")
            continue
        upsert_env(name, value)
        print(f"{name} ← {domain}（{len(value.split('; '))} 个 Cookie）")

    if errors:
        print("\n".join(errors))
        notify("CookieCloud 同步失败", "\n".join(errors))
        sys.exit(1)


if __name__ == "__main__":
    main()
