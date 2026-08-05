# -*- coding: utf-8 -*-
"""首版数据生成器：把 reorganize_report.py 的 META/POSITIONS 转成 jobs.json。

用法（在 jobfinder/ 目录下）：
    python -m scripts.build_seed_jobs

产出：jobs.json（前端 fetch）+ index.bundle.html（数据内联，双击即用）。
通过 ast 只提取数据定义，不执行 reorganize_report.py（避免其重新写报告）。
"""
import ast
import datetime
import json
import pathlib
import sys

BASE = pathlib.Path(__file__).resolve().parents[1]  # jobfinder/
REORG = BASE.parent / "reorganize_report.py"        # 本地：3D_Info/ 下的原始数据源
DATA_JSON = BASE / "data" / "seed_data.json"        # 便携兜底：已导出的 META/POSITIONS

sys.path.insert(0, str(BASE))

from scripts.parsers import parse_cities, parse_salary, parse_hire_type, parse_experience, parse_tags  # noqa: E402
from scripts.schema import make_id, compute_match_score, SCHEMA_VERSION  # noqa: E402


def load_reorg_data():
    """读取 META/POSITIONS/OVERSEA/tier。优先用 ast 提取本地 reorganize_report.py（避免副作用），
    云端/新机器无该文件时退回 data/seed_data.json。"""
    if REORG.exists():
        tree = ast.parse(REORG.read_text(encoding="utf-8"))
        ns = {}
        wanted = {"META", "POSITIONS", "OVERSEA", "tier", "sort_key"}
        for node in tree.body:
            if isinstance(node, ast.Assign):
                for t in node.targets:
                    if isinstance(t, ast.Name) and t.id in wanted:
                        exec(compile(ast.Module(body=[node], type_ignores=[]), "<reorg>", "exec"), ns)
            elif isinstance(node, ast.FunctionDef) and node.name in wanted:
                exec(compile(ast.Module(body=[node], type_ignores=[]), "<reorg>", "exec"), ns)
        return ns
    # 便携兜底：data/seed_data.json
    import json as _json
    d = _json.loads(DATA_JSON.read_text(encoding="utf-8"))
    oversea = set(d["OVERSEA"])
    return {
        "META": d["META"], "POSITIONS": d["POSITIONS"], "OVERSEA": oversea,
        "tier": (lambda k: 0 if d["META"][k]["gba"] else (2 if k in oversea else 1)),
        "sort_key": None,
    }


def build_job(company, pos, meta, tier):
    title, city_raw, sal_raw, req, url = pos
    cities, regions = parse_cities(city_raw)
    salary = parse_salary(sal_raw)
    hire = parse_hire_type(title, req)
    exp = parse_experience(title, req)
    tags, primary = parse_tags(title, req, meta.get("core", ""))
    match = compute_match_score(tags, hire, regions, meta["stars"])
    return {
        "id": make_id(company, title, url),
        "source": "seed",
        "source_url": url,
        "first_seen": "2026-08-05",
        "last_seen": "2026-08-05",
        "title_raw": title,
        "city_raw": city_raw,
        "salary_raw": sal_raw,
        "requirement_raw": req,
        "company": company,
        "title": " ".join(title.split()),
        "cities": cities,
        "regions": regions,
        "salary": salary,
        "hire_type": hire,
        "experience": exp,
        "tags": tags,
        "tags_primary": primary,
        "priority": {
            "tier": tier(company),
            "size_tier": meta["size"],
            "sal_tier": meta["sal"],
            "stars": meta["stars"],
            "match_score": match,
        },
        "apply_text": "投递",
        "notes": "",
    }


def stats(jobs):
    by_city, by_tag, by_source = {}, {}, {}
    for j in jobs:
        by_source[j["source"]] = by_source.get(j["source"], 0) + 1
        for c in j["cities"]:
            by_city[c] = by_city.get(c, 0) + 1
        for t in j["tags"]:
            by_tag[t] = by_tag.get(t, 0) + 1
    return {
        "total": len(jobs),
        "by_source": by_source,
        "by_city": dict(sorted(by_city.items(), key=lambda x: -x[1])),
        "by_tag": dict(sorted(by_tag.items(), key=lambda x: -x[1])),
    }


def main():
    ns = load_reorg_data()
    META, POSITIONS, tier = ns["META"], ns["POSITIONS"], ns["tier"]
    companies = {
        k: {"size_tier": m["size"], "sal_tier": m["sal"], "stars": m["stars"],
            "gba": bool(m["gba"]), "size_txt": m["size_txt"], "core": m["core"],
            "city": m["city"], "tier": tier(k)}
        for k, m in META.items()
    }
    jobs = [build_job(c, p, META[c], tier)
            for c, poss in POSITIONS.items() if c in META
            for p in poss]
    jobs.sort(key=lambda j: (-j["priority"]["match_score"], j["priority"]["tier"],
                             -j["priority"]["size_tier"], -j["priority"]["sal_tier"], j["company"]))
    data = {
        "generated_at": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
        "schema_version": SCHEMA_VERSION,
        "stats": stats(jobs),
        "companies": companies,
        "jobs": jobs,
    }
    (BASE / "jobs.json").write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")

    # 内联版 index.bundle.html
    index_html = BASE / "index.html"
    if index_html.exists():
        bundle = index_html.read_text(encoding="utf-8")
        marker = "window.__JOBS_INLINE__ = null;"
        inline = "window.__JOBS_INLINE__ = %s;" % json.dumps(data, ensure_ascii=False)
        if marker in bundle:
            bundle = bundle.replace(marker, inline)
            (BASE / "index.bundle.html").write_text(bundle, encoding="utf-8")
        else:
            print("[WARN] index.html 缺少内联标记，跳过 index.bundle.html")

    print("[OK] %d 条岗位 -> %s" % (len(jobs), BASE / "jobs.json"))
    print("     公司数: %d | 来源: %s" % (len(META), data["stats"]["by_source"]))
    print("     地区Top6: %s" % ", ".join("%s(%d)" % kv for kv in list(data["stats"]["by_city"].items())[:6]))
    print("     标签Top8: %s" % ", ".join("%s(%d)" % kv for kv in list(data["stats"]["by_tag"].items())[:8]))
    print("     match>=80: %d | 60-79: %d | <60: %d" % (
        sum(1 for j in jobs if j["priority"]["match_score"] >= 80),
        sum(1 for j in jobs if 60 <= j["priority"]["match_score"] < 80),
        sum(1 for j in jobs if j["priority"]["match_score"] < 60)))


if __name__ == "__main__":
    main()
