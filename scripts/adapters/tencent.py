# -*- coding: utf-8 -*-
"""腾讯官方招聘 API 适配器（已实测可用）。

腾讯 careers 提供公开 JSON API，能直接拿到岗位名/城市/部门/JD，无需反爬。
覆盖全部腾讯岗位，再用关键词 + 城市过滤出与深大 GIS 背景相关的算法岗。
"""
import asyncio

from .base import BaseAdapter
from .. import parsers as P
from ..schema import make_id, compute_match_score

API = "https://careers.tencent.com/tencentcareer/api/post/Query"
DETAIL = "https://careers.tencent.com/tencentcareer/detail.html?postId=%s"

EXCLUDE_CATEGORY = ("营销", "公关", "销售", "市场", "财务", "人力", "行政", "法务", "客服", "产品运营", "设计")


class TencentAdapter(BaseAdapter):
    source = "tencent"
    use_playwright = False

    def __init__(self, config, **kw):
        super().__init__(config, **kw)
        cfg = (config or {}).get("tencent", {})
        self.keywords = cfg.get("keywords", ["三维重建", "SLAM", "点云", "NeRF", "3DGS", "GIS", "摄影测量", "视觉SLAM"])
        self.cities = cfg.get("cities", [])

    async def run(self, targets=None):
        import httpx
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126.0 Safari/537.36",
            "Referer": "https://careers.tencent.com/",
        }
        seen = set()
        async with httpx.AsyncClient(headers=headers, timeout=20, follow_redirects=True) as c:
            for kw in self.keywords:
                try:
                    # 每个关键词抓 2 页，扩大覆盖
                    for page in (1, 2):
                        r = await c.get(API, params={
                            "pageIndex": page, "pageSize": 30, "language": "zh-cn", "area": "cn", "keyword": kw,
                        })
                        r.raise_for_status()
                        data = r.json().get("Data") or {}
                        posts = data.get("Posts") or []
                        for p in posts:
                            pid = str(p.get("PostId") or p.get("RecruitPostId"))
                            if not pid or pid in seen:
                                continue
                            seen.add(pid)
                            job = self.normalize(p)
                            if job:
                                self.results.append(job)
                        if len(posts) < 30:
                            break
                except Exception as e:  # noqa: BLE001
                    self.errors.append("tencent/%s: %s" % (kw, e))
                await asyncio.sleep(1.5)
        return self.results

    def normalize(self, p):
        title = (p.get("RecruitPostName") or "").strip()
        if not title:
            return None
        city_raw = p.get("LocationName") or ""
        if self.cities and city_raw not in self.cities:
            return None
        req = (p.get("Responsibility") or "") + " " + (p.get("Requirement") or "")
        category = p.get("CategoryName") or ""
        if any(x in category for x in EXCLUDE_CATEGORY):
            return None
        pid = str(p.get("PostId") or p.get("RecruitPostId"))
        url = DETAIL % pid
        cities, regions = P.parse_cities(city_raw)
        salary = P.parse_salary("")  # 腾讯不公开薪资
        hire = P.parse_hire_type(title, req)
        exp = P.parse_experience(title, req)
        tags, primary = P.parse_tags(title, req, "腾讯 3D视觉 SLAM 三维重建")
        stars = 4
        return {
            "id": make_id("腾讯", title, url),
            "source": self.source, "source_url": url,
            "first_seen": None, "last_seen": None,
            "title_raw": title, "city_raw": city_raw, "salary_raw": "", "requirement_raw": req[:300],
            "company": "腾讯", "title": " ".join(title.split()),
            "cities": cities, "regions": regions, "salary": salary,
            "hire_type": hire, "experience": exp, "tags": tags, "tags_primary": primary,
            "priority": {"tier": 0, "size_tier": 10, "sal_tier": 50, "stars": stars,
                         "match_score": compute_match_score(tags, hire, regions, stars)},
            "apply_text": "投递", "notes": "",
        }
