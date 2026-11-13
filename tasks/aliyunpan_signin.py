#!/usr/bin/env python3
# name: 阿里云盘签到
# cron: 35 9 * * *
"""阿里云盘每日签到，结果和当天奖励状态通过面板通知推送。

阿里云盘的登录态不在 Cookie 里，而是网页版 localStorage 的 `token` 项（JSON，含
refresh_token）。refresh_token 每次换 access_token 都会轮换，旧值随之作废，所以本脚本
每次成功后都把新值写回面板的 ALIYUN_REFRESH_TOKEN，下次接着用。

token 来源按顺序尝试：
    1. ALIYUN_REFRESH_TOKEN  本脚本上次运行写回的值
    2. ALIYUN_BROWSER_TOKEN  浏览器网页版的 token，由「CookieCloud 同步」任务写入，
                             COOKIECLOUD_MAP 里加一行 ALIYUN_BROWSER_TOKEN=alipan.com@token
只有 1 失效时才动用 2，避免和浏览器抢同一个 token；用了浏览器的 token 后，浏览器那边
下次刷新可能要求重新登录。两个变量分开，是因为同步任务每天都会覆盖 2，而 1 只有
本脚本会写。

环境变量：
    ALIYUN_REFRESH_TOKEN  可选，首次可留空，之后由本脚本自动维护
    ALIYUN_BROWSER_TOKEN  可选，localStorage 里 token 项的原始 JSON，也可以直接填 refresh_token
"""

import json
import os
import sys
import time
import urllib.error
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from lib.daidai import in_panel, notify, upsert_env  # noqa: E402

ENV_NAME = "ALIYUN_REFRESH_TOKEN"
BROWSER_ENV_NAME = "ALIYUN_BROWSER_TOKEN"
UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36"
)


class TokenInvalid(Exception):
    """refresh_token 被服务端拒绝，换下一个来源。"""


def post(url, payload, access_token=None, retries=3):
    """POST JSON，网络超时之类的错误重试几次；HTTP 错误原样返回响应体给调用方判断。"""
    headers = {"Content-Type": "application/json", "User-Agent": UA}
    if access_token:
        headers["Authorization"] = "Bearer " + access_token
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers=headers)
    for attempt in range(1, retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                return resp.status, json.load(resp)
        except urllib.error.HTTPError as err:
            body = err.read().decode("utf-8", "replace")
            try:
                return err.code, json.loads(body)
            except ValueError:
                return err.code, {"message": body[:200]}
        except (urllib.error.URLError, TimeoutError) as err:
            if attempt == retries:
                raise RuntimeError(f"请求 {url} 失败：{err}") from err
            print(f"请求 {url} 出错（{err}），{attempt * 5} 秒后重试")
            time.sleep(attempt * 5)


def refresh(refresh_token):
    status, data = post(
        "https://auth.alipan.com/v2/account/token",
        {"grant_type": "refresh_token", "refresh_token": refresh_token},
    )
    if status != 200 or not data.get("access_token"):
        raise TokenInvalid(f"{status} {data.get('code', '')} {data.get('message', '')}".strip())
    return data


def browser_token():
    """从 ALIYUN_BROWSER_TOKEN 取 refresh_token，兼容 localStorage 原始 JSON 和裸 token。"""
    raw = os.environ.get(BROWSER_ENV_NAME, "").strip()
    if not raw.startswith("{"):
        return raw
    try:
        return json.loads(raw).get("refresh_token") or ""
    except ValueError:
        return ""


def login():
    """依次尝试各来源，返回换到的 token 数据；全部失败时抛出带原因的异常。"""
    reasons = []

    saved = os.environ.get(ENV_NAME, "").strip()
    if saved:
        try:
            return refresh(saved)
        except TokenInvalid as err:
            reasons.append(f"{ENV_NAME} 失效：{err}")

    token = browser_token()
    if token and token != saved:
        try:
            print(f"改用 {BROWSER_ENV_NAME}（浏览器的 token）")
            return refresh(token)
        except TokenInvalid as err:
            reasons.append(f"{BROWSER_ENV_NAME} 失效：{err}")
    elif not token:
        reasons.append(f"{BROWSER_ENV_NAME} 为空，检查 COOKIECLOUD_MAP 和「CookieCloud 同步」任务")

    raise RuntimeError("；".join(reasons) + "。请在浏览器重新登录 www.alipan.com，等 CookieCloud 同步后再试")


def save_token(new_token):
    """把轮换后的 refresh_token 写回面板，写不回去下次就会失效，所以失败要报出来。"""
    if not in_panel():
        print(f"本地运行，不写回面板，新 token 末四位：{new_token[-4:]}")
        return
    upsert_env(ENV_NAME, new_token)
    print("新 refresh_token 已写回面板")


def signin(access_token):
    status, data = post("https://member.alipan.com/v1/activity/sign_in_list?_rx-s=mobile", {"isReward": False}, access_token)
    if status != 200 or not data.get("success", True) or "result" not in data:
        raise RuntimeError(f"签到失败：{status} {data.get('code', '')} {data.get('message', '')}".strip())

    lines = [f"本月已签到 {data['result'].get('signInCount', 0)} 天"]

    # 签到奖励现在随签到自动发放，旧的 v1/activity/sign_in_reward 只认官方客户端（403「请升级最新客户端访问」），
    # 这里只查询并展示奖励状态；查询失败不影响签到结果
    status, info = post("https://member.alipan.com/v2/activity/sign_in_info?_rx-s=mobile", {}, access_token)
    if status == 200 and isinstance(info.get("result"), dict):
        for reward in info["result"].get("rewards") or []:
            state = "已获得" if reward.get("status") == "finished" else "未完成"
            lines.append(f"{reward.get('name')}：{state}（{reward.get('remind')}）")
    else:
        lines.append(f"奖励状态查询失败：{status}")
    return lines


def main():
    try:
        token = login()
        save_token(token["refresh_token"])
        name = token.get("nick_name") or token.get("user_name") or "未知用户"
        lines = [f"账号：{name}", *signin(token["access_token"])]
    except Exception as err:  # noqa: BLE001 任何错误都要推送出来，并让面板标记失败
        print(err)
        notify("阿里云盘签到失败", str(err))
        sys.exit(1)

    print("\n".join(lines))
    notify("阿里云盘签到", "\n".join(lines))


if __name__ == "__main__":
    main()
