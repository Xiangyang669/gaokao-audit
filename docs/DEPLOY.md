# 部署

## 本地（已验证 ✅）

```bash
py scripts/build_db.py          # 先建库（data/gaokao.db，镜像要用）
cp .env.example .env            # 填 DEEPSEEK_API_KEY
docker compose up -d --build
curl localhost:8000/healthz     # → {"status":"ok","spent_yuan":0.0}
```

**实测结果**（2026-10-11，Docker 29.7.2）：

```
[healthz]   200  {"status":"ok","spent_yuan":0.0}
[example]   200  返回解析好的示例表（走缓存，不调模型）
[agent-card] 200  返回 A2A Agent Card
容器日志:   Uvicorn running on http://0.0.0.0:8000
```

> ⚠️ **默认只听本机。容器里必须 `HOST=0.0.0.0`**（Dockerfile 里已设）。
> 这个坑是"起容器真访问"那一步抓出来的：日志显示 uvicorn 绑在 `127.0.0.1`，
> **端口映射形同虚设**，宿主 curl 直接空回复。

## 💰 演示路径**零 API 花费**（已实测）

响应缓存（`llm_cache/`）**被打进了镜像**。所以：

| 访客做什么 | 花不花钱 |
|---|---|
| 点「载入示例」→ 看确认表格 | **¥0** |
| 点「开始审计」→ 出报告 | **¥0**（意图分类与报告都在缓存里） |
| 上传**自己的新截图** | 真调模型（受配额与封顶约束） |

实测：容器里 `GET /example` → 12 条；`POST /confirm` → 2 处发现 + 355 字报告，
**全程没有任何模型调用**。

> ⚠️ 上传截图那条路仍然需要 `DEEPSEEK_API_KEY` —— 也就是说，
> **公开演示时这个 key 是活的**，护栏（每 IP 3 次 / 全局 ¥10）就是为它准备的。

## 🔴 为什么是常驻容器，不是 serverless

多 agent **串行**调 LLM（意图分类 → 若干检查 → supervisor → 报告），一次审计可能几十秒。
Vercel / Lambda 免费档有**执行时长上限**，直接用不了。所以从设计阶段就避开了 serverless 的写法。

## 🔴 上公网前的检查清单（每一步都有实测证据）

| 检查 | 命令 | 结果 |
|---|---|---|
| 有没有密钥类文件被 git 跟踪 | `git ls-files \| grep -iE "\.env$\|secret\|\.pem"` | 只有 `.env.example`（**只有变量名，无值**）✅ |
| 有没有硬编码 key | `git grep -nE "sk-[A-Za-z0-9]{16,}"` | 无 ✅ |
| `.env` 是否被忽略 | `git check-ignore -v .env` | `.gitignore:7` ✅ |
| `.dockerignore` 是否排除 `.env` | `grep "^\.env$" .dockerignore` | 命中 ✅ |
| **镜像里到底有没有 `.env`** | `docker run --rm <img> ls -a /app \| grep env` | **无** ✅ |

> ⚠️ 最后一条最关键：**镜像会被推到镜像仓库，一旦 `.env` 进去就洗不干净了。**
> 前四条都是"配置写对了"，只有这条是"真的没进去"。

## 配额（公网部署前必须设成真实值）

```yaml
environment:
  PER_IP_DAILY: "3"          # 每个 IP 每天
  GLOBAL_CAP_YUAN: "10"      # 全局封顶，到顶自动转演示模式
```

一次请求估算 ≈ **¥0.02**（全系统 4 处 LLM 调用；无异常时 supervisor 不调，更少）。
**这些默认值适合小规模演示，不是生产参数。** 公开前请按自己的承受能力调。

## 托管：**尚未确定**（需要决策）

候选与实测考量：

| 方案 | 成本 | 国内可访问性 | 备注 |
|---|---|---|---|
| 国外 PaaS（Render / Railway / Fly.io） | 免费档或 ~$5/月 | ⚠️ **慢/不稳** | 部署最省事，但**面试官可能打不开** |
| 国内 serverless（阿里云函数计算） | 有免费额度 | ✅ 快 | ⚠️ 冷启动 + **执行时长限制**，与"串行调 LLM"冲突 |
| 国内云轻量服务器 | ~¥60–100/月 | ✅ 快 | 要备案域名 |

> 🔴 **「能不能打开」必须在目标网络下真测过才算数** —— 不能只写"应该可以"。
> 这一条目前**没有证据**，所以本文件不写网址。
