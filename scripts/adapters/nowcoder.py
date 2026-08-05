# -*- coding: utf-8 -*-
"""牛客网校招岗位适配器（P1）。

以关键词搜索牛客校招职位页为准（nowcoder 反爬较弱，httpx 可解析）。
"""
import asyncio
import re
import urllib.parse

from bs4 import BeautifulSoup

from .base import BaseAdapter
from .. import parsers as P
from ..schema import make_id, compute_match_score


class NowcoderAdapter(BaseAdapter):
    source = "nowcoder"
    use_playwright = False

    def __init__(self, config, **kw):
        super().__init__(config, **kw)
        self.keywords = (config or {}).get("nowcoder", {}).get("keywords", [])

    async def run(self, targets=None):
        for kw in self.keywords:
            url = "https://www.nowcoder.com/jobs/search?kw=%s" % urllib.parse.quote(kw)
            try:
                html = await self.fetch_html(url)
                for item in self._parse(html, kw):
                    job = self.normalize(item, kw)
                    if job:
                        self.results.append(job)
            except Exception as e:  # noqa: BLE001
                self.errors.append("nowcoder/%s: %s" % (kw, e))
            await asyncio.sleep(2)
        return self.results

    def _parse(self, html, kw):
        if not html:
            return []
        soup = BeautifulSoup(html, "lxml")
        items = []
        seen = set()
        # 牛客职位卡片常见结构：a[href^=/jobs/detail/] 的 title 属性
        for a in soup.find_all("a", href=re.compile(r"/jobs/detail/")):
            title = (a.get("title") or a.get_text(strip=True) or "").strip()
            href = a.get("href") or ""
            if not href.startswith("http"):
                href = "https://www.nowcoder.com" + href
            if not title or (title, href) in seen:
                continue
            seen.add((title, href))
            parent = a.find_parent(["div", "li"])
            txt = parent.get_text(" ", strip=True) if parent else title
            m = re.search(r"(深圳|广州|北京|上海|杭州|武汉|成都|西安|长沙|南京|苏州|合肥)", txt)
            city = m.group(1) if m else ""
            sal = re.search(r"(\d+\.?\d*)\s*[-~至]\s*(\d+\.?\d*)\s*K[×x*]?\d*", txt, re.I)
            items.append({"title": title, "url": href, "city_raw": city,
                          "salary_raw": sal.group(0) if sal else "",
                          "requirement_raw": txt[:160]})
        return items

    def normalize(self, item, kw):
        return _normalize_job(item, self.source, kw)


def _normalize_job(item, source, company):
    title = item.get("title", "")
    url = item.get("url", "")
    req = item.get("requirement_raw", "") or ""
    cities, regions = P.parse_cities(item.get("city_raw", ""))
    salary = P.parse_salary(item.get("salary_raw", ""))
    hire = P.parse_hire_type(title, req)
    exp = P.parse_experience(title, req)
    tags, primary = P.parse_tags(title, req, "")
    stars = 3
    return {
        "id": make_id(company, title, url),
        "source": source, "source_url": url,
        "first_seen": None, "last_seen": None,
        "title_raw": title, "city_raw": item.get("city_raw", ""),
        "salary_raw": item.get("salary_raw", ""), "requirement_raw": req,
        "company": company, "title": " ".join(title.split()),
        "cities": cities, "regions": regions, "salary": salary,
        "hire_type": hire, "experience": exp, "tags": tags, "tags_primary": primary,
        "priority": {"tier": 1, "size_tier": 5, "sal_tier": 20, "stars": stars,
                     "match_score": compute_match_score(tags, hire, regions, stars)},
        "apply_text": "投递", "notes": "",
    }
