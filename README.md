# cron-scripts

我的定时任务脚本集合，通过 [呆呆面板](https://github.com/linzixuanzz/daidai-panel) 的订阅管理拉取并调度执行。

## 目录结构

```
cron-scripts/
├── lib/            # 公共方法，订阅时作为依赖文件拉取，不建任务
│   └── daidai.py   # 发通知、读写面板环境变量
└── tasks/          # 定时任务脚本，每个文件对应面板里的一个任务
    ├── jpy_rate.py         # 日元汇率推送
    ├── hdwing_signin.py    # HDWinG 每日签到
    ├── rousi_signin.py     # RousiPro 每日签到
    ├── ttg_signin.py       # TTG 每日签到
    └── cookiecloud_sync.py # 从 CookieCloud 同步 Cookie 到面板环境变量
```

## 约定

- 每个任务一个文件，放在 `tasks/` 下，文件名用小写加下划线
- 脚本头部声明任务名和执行时间，面板拉取订阅时据此自动建任务：

  ```python
  # name: 日元汇率
  # cron: 0 9 * * *
  ```

  Shell 脚本同样用 `#` 注释，JS / TS 用 `// cron: 0 9 * * *`。没有声明 `cron` 的脚本不会建任务

- Cookie、Token、密码等敏感信息一律放在面板的「环境变量」里，脚本通过 `os.environ` 读取，不要写进仓库
- Python 脚本优先只用标准库；需要第三方依赖时在面板「依赖管理」里安装，并在脚本 docstring 里注明
- 通知统一走 `lib.daidai.notify`，本地运行时只打印，不会真的推送

## 在呆呆面板中订阅

「订阅管理」→ 新建订阅：

| 字段 | 值 |
| --- | --- |
| 类型 | Git 仓库（私有仓库配置 SSH Key 或 Token） |
| 地址 | 本仓库地址 |
| 分支 | `main` |
| 白名单 | `tasks/` |
| 依赖规则 | `lib/` |
| 定时规则 | 例如 `0 */6 * * *`，定期同步仓库 |

白名单决定哪些文件建成任务，依赖规则让 `lib/` 也被拉到面板里供脚本 import，但不会建成任务。不要填「指定子目录」，否则只会检出 `tasks/`，`lib/` 拉不下来。

## 本地调试

```bash
python3 tasks/jpy_rate.py
RATE_ALERT=0.045 python3 tasks/jpy_rate.py
HDWING_COOKIE="hdchina=xxx" python3 tasks/hdwing_signin.py
```

## 任务所需环境变量

| 任务 | 变量 | 说明 |
| --- | --- | --- |
| `jpy_rate.py` | `RATE_ALERT` | 可选，汇率提醒阈值 |
| `hdwing_signin.py` | `HDWING_COOKIE` | 必填，hdwing.org 的 Cookie，只需 `hdchina=xxx`；多账号换行或 `&` 分隔。可由 `cookiecloud_sync.py` 自动写入 |
| `rousi_signin.py` | `ROUSI_COOKIE` | 必填，rousi.pro 的 Cookie，即 `__Host-peergo_session=xxx`；多账号换行或 `&` 分隔。可由 `cookiecloud_sync.py` 自动写入 |
| `rousi_signin.py` | `ROUSI_MODE` | 可选，`fixed`（默认，固定 100 魔力）或 `random`（随机 1~300） |
| `ttg_signin.py` | `TTG_COOKIE` | 必填，totheglory.im 的 Cookie，至少 `uid=xxx; pass=xxx`；多账号换行或 `&` 分隔。可由 `cookiecloud_sync.py` 自动写入 |
| `cookiecloud_sync.py` | `COOKIECLOUD_URL` / `COOKIECLOUD_UUID` / `COOKIECLOUD_PASSWORD` | 必填，CookieCloud 服务地址和插件里的 UUID、加密密码 |
| `cookiecloud_sync.py` | `COOKIECLOUD_MAP` | 必填，每行一条 `环境变量名=域名`，如 `HDWING_COOKIE=hdwing.org` |

## Cookie 自动同步

浏览器装 CookieCloud 插件，把要同步的域名加进插件的同步列表，Cookie 会定时上传到自建服务。`cookiecloud_sync.py` 每天在各签到任务之前运行，把 `COOKIECLOUD_MAP` 里列出的域名的 Cookie 写回对应的环境变量。以后新增签到脚本，只要在 `COOKIECLOUD_MAP` 里加一行，浏览器保持登录，就不用再手动更新 Cookie。

同步任务按名字 upsert，所以映射到的变量只能有一条记录，多账号变量（同名多条）不要放进 `COOKIECLOUD_MAP`。

不在面板中运行时没有 `DAIDAI_API_BASE` / `DAIDAI_TOKEN`，`notify` 只打印到终端。
