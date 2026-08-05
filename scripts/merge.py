# -*- coding: utf-8 -*-
"""岗位增量合并与去重：同 id 覆盖式合并，first_seen 保留、last_seen 刷新。"""
import datetime


def today():
    return datetime.date.today().isoformat()


def merge_jobs(existing, new, keep_seed=True):
    """existing/new 均为 job dict 列表。keep_seed=True 时保留 source='seed' 的兜底岗。"""
    by_id = {}
    for j in existing or []:
        by_id[j["id"]] = j
    for j in new or []:
        if not j or not j.get("id"):
            continue
        if not keep_seed and j.get("source") == "seed":
            continue
        old = by_id.get(j["id"])
        if old:
            j["first_seen"] = old.get("first_seen", j.get("first_seen") or today())
        j["last_seen"] = today()
        by_id[j["id"]] = j
    return list(by_id.values())


def rebuild(data, jobs):
    """合并后重建顶层 JSON（stats/companies 保留原有）。"""
    from .schema import SCHEMA_VERSION
    data = dict(data or {})
    data["generated_at"] = datetime.datetime.now().astimezone().isoformat(timespec="seconds")
    data["schema_version"] = SCHEMA_VERSION
    data["stats"] = {
        "total": len(jobs),
        "by_source": _count(jobs, lambda j: [j.get("source", "?")]),
        "by_city": _count(jobs, lambda j: j.get("cities", [])),
        "by_tag": _count(jobs, lambda j: j.get("tags", [])),
    }
    data["jobs"] = jobs
    return data


def _count(jobs, key):
    from collections import Counter
    c = Counter()
    for j in jobs:
        for k in key(j):
            c[k] += 1
    return dict(sorted(c.items(), key=lambda x: -x[1]))
