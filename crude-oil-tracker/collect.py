#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
原油每日收盘价采集脚本（云端 GitHub Actions 运行，无需任何第三方依赖）
- 抓取 WTI(CL=F) 与 Brent(BZ=F) 日线
- 计算较前交易日涨跌、下跌比例、下跌原因（数据面推导 + 新闻面）
- 更新 history.json，仅保留最近 5 天
"""
import json
import urllib.request
import urllib.error
import urllib.parse
import datetime
import os

SYMBOLS = {"wti": "CL=F", "brent": "BZ=F"}
HOSTS = ["https://query1.finance.yahoo.com", "https://query2.finance.yahoo.com"]
HISTORY_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "history.json")
KEEP_DAYS = 5


def fetch_json(url, timeout=20):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def fetch_chart(symbol, range_="2mo"):
    last_err = None
    for host in HOSTS:
        url = f"{host}/v8/finance/chart/{symbol}?interval=1d&range={range_}"
        try:
            data = fetch_json(url)
            res = data["chart"]["result"][0]
            ts = res["timestamp"]
            closes = res["indicators"]["quote"][0]["close"]
            vols = res["indicators"]["quote"][0]["volume"]
            pairs = []
            for t, c, v in zip(ts, closes, vols):
                if c is None:
                    continue
                d = datetime.datetime.fromtimestamp(t, datetime.timezone.utc).strftime("%Y-%m-%d")
                pairs.append((d, float(c), (float(v) if v is not None else 0.0)))
            if pairs:
                return pairs
        except Exception as e:
            last_err = e
    raise last_err or RuntimeError("fetch chart failed for %s" % symbol)


def moving_average(vals, n=20):
    if len(vals) < n:
        return sum(vals) / len(vals)
    return sum(vals[-n:]) / n


def derive_reasons(latest, prev, series):
    """根据数据推导下跌/上涨原因（中文）。"""
    reasons = []
    chg_pct = (latest - prev) / prev * 100.0 if prev else 0.0
    closes = [c for _, c, _ in series]
    # 连跌天数
    streak = 0
    for i in range(len(closes) - 1, 0, -1):
        if closes[i] < closes[i - 1]:
            streak += 1
        else:
            break
    # 20 日均线偏离
    ma20 = moving_average(closes, 20)
    dev = (latest - ma20) / ma20 * 100.0 if ma20 else 0.0
    # 区间位置（近 2 月）
    lo, hi = min(closes), max(closes)
    pos = (latest - lo) / (hi - lo) * 100.0 if hi > lo else 50.0
    # 成交量倍率
    vols = [v for _, _, v in series if v > 0]
    avg_vol = sum(vols[:-1]) / len(vols[:-1]) if len(vols) > 1 else 0
    vol_ratio = (vols[-1] / avg_vol) if avg_vol else 1.0

    direction = "下跌" if chg_pct < 0 else ("上涨" if chg_pct > 0 else "持平")
    reasons.append(f"较前一交易日{direction} {abs(chg_pct):.2f}%"
                   f"（{'-' if chg_pct < 0 else '+'}{abs(latest - prev):.2f} 美元）。")

    if streak >= 2:
        reasons.append(f"已连续 {streak} 个交易日走低，短期弱势延续。")
    if dev < -2:
        reasons.append(f"当前价格低于 20 日均线约 {abs(dev):.1f}%，短线偏弱。")
    elif dev > 2:
        reasons.append(f"当前价格高于 20 日均线约 {dev:.1f}%，短线偏强。")
    if pos < 25:
        reasons.append("处于近两月价格区间低位，下方空间相对有限。")
    elif pos > 75:
        reasons.append("处于近两月价格区间高位，注意回落风险。")
    if vol_ratio > 1.5:
        reasons.append(f"成交量放大至均量的 {vol_ratio:.1f} 倍，多空博弈加剧。")
    elif vol_ratio < 0.6:
        reasons.append("成交量明显萎缩，市场观望情绪浓。")
    return {
        "chg_pct": round(chg_pct, 2),
        "chg_abs": round(latest - prev, 2),
        "drop_streak": streak,
        "ma20_dev": round(dev, 2),
        "range_pos": round(pos, 1),
        "volume_ratio": round(vol_ratio, 2),
        "reasons": reasons,
    }


def fetch_news():
    """尽力抓取原油相关新闻标题（失败不影响主流程）。"""
    news = []
    try:
        url = "https://query1.finance.yahoo.com/v1/finance/search?q=crude%20oil&newsCount=5"
        data = fetch_json(url)
        for n in data.get("news", [])[:4]:
            news.append({"title": n.get("title", ""), "link": n.get("link", "")})
    except Exception:
        pass
    return news


def main():
    today = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
    entry = {
        "date": today,
        "updated_at": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "wti": {}, "brent": {}, "news": [],
    }
    for key, sym in SYMBOLS.items():
        series = fetch_chart(sym)
        d_last, c_last, _ = series[-1]
        d_prev, c_prev, _ = series[-2]
        metrics = derive_reasons(c_last, c_prev, series)
        entry[key] = {
            "close": round(c_last, 2),
            "prev": round(c_prev, 2),
            "chg_pct": metrics["chg_pct"],
            "chg_abs": metrics["chg_abs"],
            "drop_streak": metrics["drop_streak"],
            "ma20_dev": metrics["ma20_dev"],
            "range_pos": metrics["range_pos"],
            "volume_ratio": metrics["volume_ratio"],
            "reasons": metrics["reasons"],
        }
    entry["news"] = fetch_news()

    # 读取既有历史，去重并仅保留最近 KEEP_DAYS 天
    history = []
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                history = json.load(f)
        except Exception:
            history = []
    history = [h for h in history if h.get("date") != today]
    history.append(entry)
    history.sort(key=lambda x: x["date"])
    history = history[-KEEP_DAYS:]

    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)

    print(f"[OK] {today} 已归档 | WTI {entry['wti']['close']} ({entry['wti']['chg_pct']:+.2f}%) "
          f"| Brent {entry['brent']['close']} ({entry['brent']['chg_pct']:+.2f}%) | 历史保留 {len(history)} 天")


if __name__ == "__main__":
    main()
