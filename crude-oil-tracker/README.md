# 原油收盘价日报（crude-oil-tracker）

本文件夹用于「每天自动收集原油收盘价」的云端方案，独立于仓库其他内容。

## 架构
- **采集**：`.github/workflows/collect.yml` 每天北京时间 06:30 在 GitHub 云端运行 `collect.py`，
  抓取 WTI(CL=F) 与 Brent(BZ=F) 收盘价，计算涨跌/下跌比例/原因，写入 `history.json`。
- **历史**：`history.json` 仅保留最近 5 天（脚本自动去重 + 裁剪）。
- **展示**：`index.html` 为云端仪表盘（手机自适应），从 GitHub 官方接口 `api.github.com`
  免密钥读取 `history.json`，无需任何 API key，电脑关机也能运行。

## 本地手动运行
```bash
cd crude-oil-tracker
python collect.py      # 生成/更新 history.json
```

## 自动运行的凭据
定时任务使用 GitHub 自动发放的 `GITHUB_TOKEN`（仓库内置，无需用户管理任何 key）。
初始文件推送需要一次性的 Personal Access Token（细粒度、仅本仓库、可推送后撤销）。

## 备注
- 若仓库设为 Public，云端页面可直接免密钥读取历史；若为 Private 则需额外只读 token。
- GitHub 对 60 天无活动的仓库会暂停定时任务，保持仓库活跃即可持续运行。
