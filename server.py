# -*- coding: utf-8 -*-
"""岗位检索 WebApp 服务端（Flask）：服务前端 + 提供「刷新数据源」接口。

本地：      python server.py            → http://localhost:8000
公网(快速)：cloudflared tunnel --url http://localhost:8000
公网(持久)：部署到 Render / Railway（见 README）
"""
import pathlib
import sys
import threading
import time

BASE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))

try:
    from flask import Flask, jsonify, send_from_directory
except ImportError:
    print("缺少 flask：pip install -r requirements.txt")
    raise

app = Flask(__name__, static_folder=str(BASE), static_url_path="")

# 刷新任务状态
STATE = {
    "running": False,
    "started": None,
    "finished": None,
    "last_count": 0,   # 本次新增
    "total": 0,        # 合并后总数
    "errors": [],      # 失败源列表
}

DEFAULT_ADAPTERS = "official,nowcoder"


@app.route("/")
def index():
    return send_from_directory(BASE, "index.html")


@app.route("/jobs.json")
def jobs():
    return send_from_directory(BASE, "jobs.json")


@app.route("/api/health")
def health():
    return jsonify(ok=True, total=_total())


@app.route("/api/refresh", methods=["POST"])
def refresh():
    if STATE["running"]:
        return jsonify(running=True, message="刷新已在进行中，请稍候")
    STATE.update(running=True, started=time.time(), finished=None,
                 last_count=0, total=_total(), errors=[])

    def worker():
        from scripts.fetch_jobs import run_refresh
        try:
            new, errors, data = run_refresh(adapters=DEFAULT_ADAPTERS)
            STATE["last_count"] = len(new)
            STATE["total"] = len(data.get("jobs", []))
            STATE["errors"] = errors[:20]
        except Exception as e:  # noqa: BLE001
            STATE["errors"] = ["整体失败: %s" % e]
        finally:
            STATE["running"] = False
            STATE["finished"] = time.strftime("%Y-%m-%d %H:%M:%S")

    threading.Thread(target=worker, daemon=True).start()
    return jsonify(running=True)


@app.route("/api/refresh/status")
def refresh_status():
    return jsonify(**STATE)


def _total():
    try:
        import json
        d = json.loads((BASE / "jobs.json").read_text(encoding="utf-8"))
        return len(d.get("jobs", []))
    except Exception:  # noqa: BLE001
        return 0


if __name__ == "__main__":
    print("启动 jobfinder 服务：http://localhost:8000  (Ctrl+C 停止)")
    # host=0.0.0.0 允许局域网/内网穿透访问；threaded 让刷新后台任务不阻塞
    app.run(host="0.0.0.0", port=8000, debug=False, threaded=True)
