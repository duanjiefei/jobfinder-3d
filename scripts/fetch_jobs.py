# -*- coding: utf-8 -*-
"""抓取入口：调度各 adapter，增量合并进 jobs.json，并重新生成 index.bundle.html。

命令行用法（在 jobfinder/ 目录下）：
    python -m scripts.fetch_jobs --adapters official,nowcoder
    python -m scripts.fetch_jobs --adapters official --no-seed     # 不带种子兜底

也可被 server.py 导入，作为「刷新数据源」按钮的后台任务：run_refresh(...)。
"""
import argparse
import asyncio
import json
import pathlib
import sys

BASE = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))

from scripts.merge import merge_jobs, rebuild  # noqa: E402


def load_existing():
    p = BASE / "jobs.json"
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return {"generated_at": None, "schema_version": None, "stats": {}, "companies": {}, "jobs": []}


def load_config():
    """读取 config/companies.yaml，并注入公司元数据（供官方 adapter 复用星级/优先级）。"""
    try:
        import yaml
        cfg = yaml.safe_load((BASE / "config" / "companies.yaml").read_text(encoding="utf-8"))
    except FileNotFoundError:
        cfg = {}
    try:
        from scripts.build_seed_jobs import load_reorg_data
        meta = load_reorg_data()["META"]
        cfg.setdefault("meta", {k: {"stars": m["stars"], "size": m["size"], "sal": m["sal"],
                                    "tier": (0 if m["gba"] else 1)} for k, m in meta.items()})
    except Exception as e:  # noqa: BLE001
        print("[WARN] 未加载公司元数据:", e)
    return cfg


def write_data(data):
    """写 jobs.json + 同步生成 index.bundle.html。"""
    (BASE / "jobs.json").write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    index_html = BASE / "index.html"
    if index_html.exists():
        bundle = index_html.read_text(encoding="utf-8")
        inline = "window.__JOBS_INLINE__ = %s;" % json.dumps(data, ensure_ascii=False)
        if "window.__JOBS_INLINE__ = null;" in bundle:
            bundle = bundle.replace("window.__JOBS_INLINE__ = null;", inline)
            (BASE / "index.bundle.html").write_text(bundle, encoding="utf-8")


def run_refresh(adapters="official,nowcoder", keep_seed=True, write=True):
    """跑指定的 adapter 并合并进 jobs.json。返回 (new_jobs, errors, data)。"""
    from scripts.adapters import ADAPTERS

    cfg = load_config()
    errors = []

    async def run_all():
        new = []
        for name in [n.strip() for n in adapters.split(",") if n.strip()]:
            cls = ADAPTERS.get(name)
            if not cls:
                errors.append("未知 adapter: %s" % name)
                continue
            try:
                adapter = cls(cfg)
                new += await adapter.run()
                errors.extend(adapter.errors)
            except Exception as e:  # noqa: BLE001
                errors.append("%s: %s" % (name, e))
        return new

    new = asyncio.run(run_all())
    data = load_existing()
    if write:
        merged = merge_jobs(data.get("jobs", []), new, keep_seed=keep_seed)
        data = rebuild(data, merged)
        write_data(data)
    return new, errors, data


def main():
    ap = argparse.ArgumentParser(description="从网上刷新岗位数据 -> jobs.json")
    ap.add_argument("--adapters", default="tencent,official,nowcoder",
                    help="逗号分隔的 adapter 名：tencent,official,nowcoder,university,boss,liepin,lagou")
    ap.add_argument("--seed", dest="seed", action="store_true", default=True, help="保留 seed 兜底岗（默认）")
    ap.add_argument("--no-seed", dest="seed", action="store_false")
    ap.add_argument("--dry", action="store_true", help="只跑适配器不写文件（验证管线）")
    args = ap.parse_args()

    new, errors, data = run_refresh(adapters=args.adapters, keep_seed=args.seed, write=not args.dry)
    for e in errors:
        print("[ERROR] %s" % e)
    if args.dry:
        print("[DRY] 抓取 %d 条，未写文件。示例:" % len(new))
        for j in new[:3]:
            print("  -", j.get("company"), j.get("title"))
        return
    print("[OK] 本次新增 %d 条，合并后共 %d 条 -> %s" % (len(new), len(data.get("jobs", [])), BASE / "jobs.json"))


if __name__ == "__main__":
    main()
