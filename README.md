# DDR 内存行情速递

DDR 内存价格追踪 + 每日 AI 早报，部署在 GitHub Pages。

## 功能

- **今日概览** — DDR4/DDR5 代表规格 KPI 卡片
- **价格行情** — 颗粒 / 模组 / 合约价格表格
- **每日早报** — AI 生成的行情简报，支持历史回看
- **趋势分析** — 多系列价格走势图 + 供需分析
- **厂商动态** — Samsung / SK Hynix / Micron / CXMT 新闻

## 架构

```
GitHub Actions (每天北京时间 09:23)
  → Claude API (web_search 自动调研)
  → 生成 JSON 数据文件 → git commit
  → GitHub Pages 自动发布静态页面
```

## 目录结构

| 路径 | 说明 |
|---|---|
| `index.html` | 单页前端 |
| `data/prices/` | 每日价格快照 |
| `data/briefings/` | 每日早报 |
| `data/news/` | 厂商动态 |
| `data/history.json` | 聚合时间序列（自动生成） |
| `data/latest.json` | 今日数据合集（自动生成） |
| `scripts/daily_update.py` | Claude 调用主管线 |
| `scripts/aggregate.py` | 重建 history.json / latest.json |
| `scripts/validate.py` | JSON Schema 校验 |
| `.github/workflows/daily-update.yml` | 定时任务工作流 |

## 配置

### 1. 设置 API Key

仓库 → Settings → Secrets and variables → Actions → **New repository secret**:

- Name: `ANTHROPIC_API_KEY`
- Value: 你的 Anthropic API Key

### 2. 启用 GitHub Pages

仓库 → Settings → Pages → Source: **Deploy from a branch** → Branch: `main`, Folder: `/ (root)`

### 3. 首次运行

仓库 → Actions → **Daily DDR price update** → **Run workflow**（手动触发一次）

## 手动操作

### 回填某天数据

Actions → Daily DDR price update → Run workflow → 填入 `date=2026-09-28`

### 仅重建聚合（不调 API）

Actions → Run workflow → `mode=aggregate`

### 手动修正数据

1. 直接编辑 `data/prices/2026-09-28.json` 等文件
2. Actions → Run workflow → `mode=aggregate`（重建聚合）

### 本地开发

```bash
# 启动本地服务器（fetch 需要 HTTP，不能用 file://）
python -m http.server 8080

# 打开 http://localhost:8080

# 本地跑管线（需要 API Key）
ANTHROPIC_API_KEY=sk-... python scripts/daily_update.py

# 重建聚合
python scripts/aggregate.py

# 校验数据
python scripts/validate.py
```

## 数据 Schema

所有日期为北京时间 `YYYY-MM-DD`。价格为数字（无货币符号），缺数据填 `null`。

固定 series ID（图表连续性保证）：
- 颗粒: `ddr4_8gbit`, `ddr4_16gbit`, `ddr5_8gbit`, `ddr5_16gbit`
- 模组: `ddr4_udimm_16gb`, `ddr5_udimm_16gb`, `ddr5_rdimm_32gb`, `ddr5_rdimm_64gb`
- 合约: `ddr4_8gbit_contract`, `ddr5_8gbit_contract`

完整 Schema 见 `scripts/schema/`。

## 免责声明

数据由 AI 每日自动采集整理，仅供参考。价格来源见各条目链接。投资/采购决策请以官方报价为准。
