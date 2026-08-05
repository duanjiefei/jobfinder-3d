# -*- coding: utf-8 -*-
"""抓取适配器基类：统一接口 + UA轮换 / 限速 / 指数退避重试 / 缓存 / 混合 requests+Playwright。

子类实现 fetch_raw(company, url) 返回原始条目列表，然后 normalize() 转成 schema。
"""
import asyncio
import hashlib
import pathlib
import random
import time
import typing

import httpx

CACHE_DIR = pathlib.Path(__file__).resolve().parents[2] / ".cache"

UA_POOL = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:127.0) Gecko/20100101 Firefox/127.0",
]


def cache_path(url):
    h = hashlib.md5(url.encode()).hexdigest()[:16]
    return CACHE_DIR / ("%s.html" % h)


class BaseAdapter:
    source = "base"
    use_playwright = False  # 子类覆盖：True=走 Playwright，False=httpx

    def __init__(self, config, cache_ttl_days=7):
        self.config = config or {}
        self.cache_ttl = cache_ttl_days * 86400
        self.results = []
        self.errors = []

    # ---------------- 对外入口 ----------------
    async def run(self, targets=None):
        targets = targets if targets is not None else self.config.get("targets", {})
        for company, url in (targets or {}).items():
            try:
                raw = await self.fetch_raw(company, url)
                for item in raw:
                    job = self.normalize(item, company)
                    if job:
                        self.results.append(job)
            except Exception as e:  # noqa: BLE001
                self.errors.append("%s/%s: %s" % (self.source, company, e))
                print("[WARN] %s: %s" % (self.source, e))
            await asyncio.sleep(random.uniform(2, 5))
        return self.results

    # ---------------- 子类实现 ----------------
    async def fetch_raw(self, company, url):
        raise NotImplementedError

    def normalize(self, raw, company):
        raise NotImplementedError

    # ---------------- 混合抓取基元 ----------------
    async def fetch_html(self, url, use_playwright=None):
        """httpx 优先；失败或需 JS 时降级 Playwright。带 7 天 URL 缓存。"""
        use_playwright = self.use_playwright if use_playwright is None else use_playwright
        cp = cache_path(url)
        if cp.exists() and time.time() - cp.stat().st_mtime < self.cache_ttl:
            return cp.read_text(encoding="utf-8", errors="ignore")
        html = None
        if not use_playwright:
            html = await self._fetch_httpx(url)
        if html is None and use_playwright:
            html = await self._fetch_playwright(url)
        if html:
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            cp.write_text(html, encoding="utf-8")
        return html

    async def _fetch_httpx(self, url):
        headers = {
            "User-Agent": random.choice(UA_POOL),
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Referer": "https://www.google.com/",
        }
        for attempt in range(3):
            try:
                async with httpx.AsyncClient(headers=headers, timeout=20,
                                             follow_redirects=True) as client:
                    r = await client.get(url)
                    r.raise_for_status()
                    return r.text
            except Exception as e:  # noqa: BLE001
                wait = [5, 15, 60][attempt]
                print("  [retry] %s 后重试 %s (%s)" % (wait, url, e))
                await asyncio.sleep(wait)
        return None

    async def _fetch_playwright(self, url):
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            print("  [skip] 未安装 playwright（pip install playwright && playwright install chromium）")
            return None
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            ctx = await browser.new_context(user_agent=random.choice(UA_POOL), locale="zh-CN")
            page = await ctx.new_page()
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(2500)  # 等 JS 渲染
            html = await page.content()
            await browser.close()
            return html
