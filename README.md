# 3D / 三维重建 / 点云 岗位检索（深大 GIS 版）

基于个人专业画像（**摄影测量 · LiDAR点云 · 三维重建 SfM/MVS/NeRF/3DGS · SLAM · GIS · 城市AI · C++/Python**）检索符合背景的岗位。
架构：**纯前端 + JSON 导入**，数据可离线刷新。

## 快速开始

### 方式 A：双击即用（推荐离线）
直接打开 **`index.bundle.html`**（数据已内联，零网络请求），无需装任何东西。

### 方式 B：完整服务（带「刷新数据源」按钮 + 公网访问）
```bash
pip install -r requirements.txt
python server.py
# 浏览器打开 http://localhost:8000/
# 顶栏出现「🔄 刷新数据源」按钮：点击后后台抓取官网/牛客，完成自动重载数据
```
服务绑定 `0.0.0.0:8000`，同一局域网可直接用 `http://<本机IP>:8000` 访问。

### 方式 C：纯静态（数据独立更新）
```bash
python -m http.server 8000
# 浏览器打开 http://localhost:8000/  （读取 jobs.json，无刷新按钮）
```

## 公网访问

### 快速（内网穿透，无需云账号，临时 URL）
```bash
# 安装后运行（cloudflared 官网下载对应系统版本）
cloudflared tunnel --url http://localhost:8000
# 输出形如 https://xxxx.trycloudflare.com 的公网地址，可发给任何人访问
```

### 持久（云部署，免费额度）
用 Flask 服务部署到 **Render / Railway**（支持免费 tier）：
1. 把 `jobfinder/` 推送为 Git 仓库；
2. Render：New → Web Service → 选仓库，Build `pip install -r requirements.txt`，Start `gunicorn server:app`；
   Railway：New Project → Deploy from GitHub，Start Command `gunicorn server:app`；
3. 平台会分配永久公网 URL（如 `https://xxx.onrender.com`），「刷新数据源」按钮同样可用。

> 提示：公网部署后，刷新按钮会在服务器上抓取数据并写入服务器的 `jobs.json`；如需本地同步，部署前先在本机 `python -m scripts.build_seed_jobs` 生成种子，抓取结果可再拉回本机。

## 检索功能
- **关键词**：全文搜索（岗位名/公司/要求/标签，空格分隔多词 AND）
- **城市 / 地区**：深圳、广州… + 大湾区/长三角/京津冀 聚合
- **工作经验**：应届 / 实习 / 1-3年 / 3-5年 / 5年+ / 博士后 / 不限 / **应届友好**（研一专属）
- **招聘类型**：校招 / 实习 / 社招 / 博士后 / 管培 / 不限
- **薪资区间**：滑块（K/月，未公开薪资自动放行）
- **方向/技能标签**：三维重建 / LiDAR点云 / NeRF/3DGS / SLAM / GIS / 3D生成…
- **排序**：匹配度 / 年薪 / 大湾区优先 / 应届友好
- 匹配度颜色：绿≥80 / 黄60-79 / 灰<60；支持打印（Ctrl+P）、移动端单列

## 刷新数据

首版数据来自报告里的 77 家公司 / 159 条岗位种子（`scripts/build_seed_jobs.py` 生成）。

从网上刷新（新增/更新岗位，覆盖官网 / 牛客 / 就业网等）：
```bash
pip install -r requirements.txt
python -m scripts.fetch_jobs --adapters official,nowcoder   # 具体 adapter 见下
```
抓取结果会**增量合并**进 `jobs.json`（同岗位按 id 去重，`first_seen` 保留、`last_seen` 刷新），再刷新页面即可看到。
可直接把 `jobs.json` 或 `index.bundle.html` 发给别人/部署到 GitHub Pages。

## 目录结构
```
jobfinder/
├── index.html              # 前端（fetch jobs.json）
├── index.bundle.html       # 数据内联版（双击即用）
├── jobs.json               # 岗位数据（脚本生成）
├── config/                 # 抓取目标公司 + 标签规则
└── scripts/
    ├── parsers.py          # 薪资/城市/类型/经验/标签 解析（前后端共用）
    ├── schema.py           # 数据模型 + 匹配度打分
    ├── build_seed_jobs.py  # 种子数据生成器
    ├── merge.py            # 去重合并
    ├── fetch_jobs.py       # 抓取入口
    └── adapters/           # 各数据源抓取适配器
```

## 抓取适配器
| 优先级 | adapter | 数据源 | 实现 |
|---|---|---|---|
| P0 | `official` | 公司官网招聘系统 | httpx+BS4 优先，JS 渲染站点用 Playwright |
| P1 | `nowcoder` | 牛客校招 | httpx+BS4 |
| P2 | `university` | 深大/武大就业网 + 实习僧 | httpx+BS4 |
| P3 | `boss` / `liepin` / `lagou` | 招聘平台（强反爬） | Playwright + 本地登录态 |

说明：BOSS/猎聘等平台有强反爬（验证码/封IP），官网岗自动抓、平台岗需本地登录态或手动补充；抓取失败的源只告警不阻塞，种子数据始终兜底。

## 开发/测试
```bash
python -m scripts.build_seed_jobs      # 重新生成种子数据
python -m pytest tests/                # 解析器单测（可选）
```
