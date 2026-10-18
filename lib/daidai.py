"""呆呆面板脚本公共方法：发通知、读写面板环境变量。

面板执行任务时会注入 DAIDAI_API_BASE 和 DAIDAI_TOKEN，脚本用它们回调面板接口。
在面板外运行（本地调试）时没有这两个变量，通知只打印到 stdout，环境变量读写直接报错。

接口说明：https://github.com/linzixuanzz/daidai-panel/blob/main/docs/script-api.md
"""

import json
import os
import urllib.error
import urllib.parse
import urllib.request

API_BASE = os.environ.get("DAIDAI_API_BASE")
TOKEN = os.environ.get("DAIDAI_TOKEN")
# 任务在面板里绑定了通知渠道时才有，没有时通知会广播到全部「默认推送」渠道
CHANNEL_ID = os.environ.get("DAIDAI_NOTIFY_CHANNEL_ID")


def in_panel():
    return bool(API_BASE and TOKEN)


def api(method, path, payload=None):
    """调用面板接口，payload 为 None 时不带请求体。"""
    if not in_panel():
        raise RuntimeError("不在呆呆面板中运行，缺少 DAIDAI_API_BASE / DAIDAI_TOKEN")

    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(API_BASE + path, data=data, method=method)
    req.add_header("Authorization", "Bearer " + TOKEN)
    if data is not None:
        req.add_header("Content-Type", "application/json")

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            body = resp.read().decode("utf-8")
    except urllib.error.HTTPError as err:
        # 面板的错误响应统一是 {"error": "原因"}
        detail = err.read().decode("utf-8", "replace")
        raise RuntimeError(f"{method} {path} 失败: {err.code} {detail}") from err

    return json.loads(body) if body else None


def notify(title, content):
    """发送通知；本地运行时只打印。"""
    if not in_panel():
        print(f"[notify] {title}\n{content}")
        return

    payload = {"title": title, "content": content}
    if CHANNEL_ID:
        payload["channel_id"] = int(CHANNEL_ID)
    api("POST", "/notifications/send", payload)


def list_env(name):
    """按名字查环境变量记录，多账号场景下会返回多条。"""
    query = urllib.parse.urlencode({"keyword": name, "all": "1"})
    result = api("GET", "/envs?" + query) or {}
    # keyword 是模糊匹配（名称/备注/值/分组都会命中），这里再按名字精确过滤
    return [item for item in (result.get("data") or []) if item["name"] == name]


def upsert_env(name, value, remarks=None):
    """按名字写回环境变量；同名存在多条时接口会直接报错，不会静默改错一条。"""
    payload = {"name": name, "value": value}
    if remarks is not None:
        payload["remarks"] = remarks
    return api("PUT", "/envs/by-name", payload)
