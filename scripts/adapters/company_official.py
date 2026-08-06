# -*- coding: utf-8 -*-
"""公司官网招聘系统适配器（P0）。

各家官网结构差异大，采取"通用解析 + 可配置选择器"策略：
1. 抓首页/招聘列表页 HTML；
2. 用 BeautifulSoup 按配置的选择器（默认宽松）提取 job 卡片；
3. 解析 title / 城市 / 薪资 / 要求 / 链接，交给 parsers 派生字段。
个别 JS 渲染站（use_playwright=True）自动降级 Playwright。

这是 best-effort：解析不到的站点只告警，不影响其它公司。
"""
import asyncio
import pathlib
import re

from bs4 import BeautifulSoup

from .base import BaseAdapter
from .. import parsers as P
from ..schema import make_id, compute_match_score

# 通用 job 卡片候选选择器（各官网常见 class / 结构）
CARD_SELECTORS = [
    ("a", {"class": re.compile(r"job|position|career", re.I)}),
    ("a", {"href": re.compile(r"job|position|career|detail", re.I)}),
    ("div", {"class": re.compile(r"job|position|card|career", re.I)}),
    ("li", {"class": re.compile(r"job|position", re.I)}),
]


NAV_WORDS = ("致辞", "战略", "招聘", "加入我们", "关于", "联系", "人才", "新闻", "首页",
             "简介", "某", "Copyright", "公司", "团队", "文化", "发展", "福利", "环境")


class CompanyOfficialAdapter(BaseAdapter):
    source = "official"
    use_playwright = False  # 个别站点在 fetch_raw 内按需升级

    def __init__(self, config, **kw):
        super().__init__(config, **kw)
        self.overrides = {  # 站点 → (标题选择器, 链接选择器)；可后续扩展
            "career.huawei.com": None,
        }

    async def fetch_raw(self, company, url):
        html = await self.fetch_html(url)
        if not html:
            return []
        soup = BeautifulSoup(html, "lxml")
        items = []
        seen = set()
        for tag, sel in CARD_SELECTORS:
            for a in soup.find_all(tag, sel):
                title = (a.get("title") or a.get_text(strip=True) or "").strip()
                href = a.get("href") or ""
                if not title or len(title) > 60 or len(title) < 6:
                    continue
                if any(w in title for w in NAV_WORDS):
                    continue
                if not href.startswith("http"):
                    href = urljoin_url(url, href)
                key = (title, href)
                if key in seen:
                    continue
                seen.add(key)
                parent = a.find_parent(["li", "div", "article", "tr"])
                city = salary = req = ""
                if parent:
                    txt = parent.get_text(" ", strip=True)
                    m = re.search(r"([一-龥]{2,4})(?:市)?", txt[:60])
                    city = self._guess_city(txt)
                    salary = self._guess_salary(txt)
                    req = txt[:160]
                items.append({"title": title, "url": href, "city_raw": city,
                              "salary_raw": salary, "requirement_raw": req})
            if len(items) >= 40:  # 足够多即停止
                break
        return items

    def normalize(self, item, company):
        title = item.get("title", "")
        city_raw = item.get("city_raw", "")
        sal_raw = item.get("salary_raw", "")
        req = item.get("requirement_raw", "") or ""
        url = item.get("url", "")
        cities, regions = P.parse_cities(city_raw)
        salary = P.parse_salary(sal_raw)
        hire = P.parse_hire_type(title, req)
        exp = P.parse_experience(title, req)
        tags, primary = P.parse_tags(title, req, "")
        meta = (self.config.get("meta") or {}).get(company, {})
        stars = meta.get("stars", 3)
        return {
            "id": make_id(company, title, url),
            "source": self.source, "source_url": url,
            "first_seen": None, "last_seen": None,
            "title_raw": title, "city_raw": city_raw, "salary_raw": sal_raw, "requirement_raw": req,
            "company": company, "title": " ".join(title.split()),
            "cities": cities, "regions": regions, "salary": salary,
            "hire_type": hire, "experience": exp, "tags": tags, "tags_primary": primary,
            "priority": {"tier": meta.get("tier", 1), "size_tier": meta.get("size", 5),
                         "sal_tier": meta.get("sal", 20), "stars": stars,
                         "match_score": compute_match_score(tags, hire, regions, stars)},
            "apply_text": "投递", "notes": "",
        }

    @staticmethod
    def _guess_city(txt):
        m = re.search(r"(深圳|广州|北京|上海|杭州|武汉|成都|西安|长沙|南京|苏州|合肥|东莞|佛山)", txt)
        return m.group(1) if m else ""

    @staticmethod
    def _guess_salary(txt):
        m = re.search(r"(\d+\.?\d*)\s*[-~至]\s*(\d+\.?\d*)\s*K[×x*]?\d*", txt, re.I) \
            or re.search(r"(\d+\.?\d*)\s*[-~至]\s*(\d+\.?\d*)\s*万", txt)
        return m.group(0) if m else ""


def urljoin_url(base, href):
    from urllib.parse import urljoin
    return urljoin(base, href)
