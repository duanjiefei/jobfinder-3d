# -*- coding: utf-8 -*-
"""Job 数据模型：字段常量、地区/招聘类型/经验枚举、确定性 id、匹配度打分。

前端 index.html 依赖本文件派生字段的稳定命名（cities/regions/salary/hire_type/experience/tags/priority）。
"""
import hashlib
import re

SCHEMA_VERSION = "1.0"

# 地区聚合（城市 -> 区域）
GBA = {"深圳", "广州", "东莞", "佛山", "中山", "珠海", "惠州", "江门", "肇庆", "香港", "澳门"}
YRD = {"上海", "杭州", "苏州", "南京", "合肥", "宁波", "无锡", "常州", "嘉兴"}
JJJ = {"北京", "天津", "石家庄"}
OVERSEAS = {"美国", "英国", "德国", "法国", "加拿大", "荷兰", "新加坡", "日本", "瑞士", "印度", "波兰", "澳大利亚", "韩国", "马来西亚", "阿联酋"}

# 招聘类型（含"不限"）
HIRE_TYPES = ["校招", "实习", "社招", "博士后", "管培", "不限"]

# 经验档位
EXP_LEVELS = ["应届", "实习", "1-3年", "3-5年", "5年+", "博士后", "不限"]

# 方向标签（参与匹配度打分的"方向命中"）
DIRECTION_TAGS = ["摄影测量", "LiDAR点云", "三维重建", "NeRF/3DGS", "SLAM", "GIS", "城市AI", "3D生成", "图形学", "具身/机器人"]

# 技能标签（参与匹配度打分的"技能栈命中"）
SKILL_TAGS = ["C++", "Python", "PyTorch", "CUDA", "OpenCV", "Eigen", "Ceres", "GTSAM", "COLMAP"]

# 招聘类型 -> 匹配度分值
HIRE_SCORE = {"校招": 20, "实习": 18, "管培": 15, "博士后": 10, "不限": 8, "社招": 5}

# 城市行政区/通用后缀，剥掉后取城市主干
_CITY_SUFFIX = (
    "总部", "分公司", "创新中心", "研发中心", "办公", "office", "园区", "基地",
    "南山", "福田", "宝安", "龙岗", "罗湖", "盐田", "光明", "坪山", "龙华",
    "天河", "番禺", "黄埔", "越秀", "海珠", "白云", "荔湾", "增城", "南沙",
    "青浦", "浦东", "嘉定", "徐汇", "静安", "杨浦", "闵行", "张江",
    "海淀", "朝阳", "丰台", "石景山", "大兴", "昌平",
    "余杭", "西湖", "滨江", "萧山", "拱墅", "钱塘",
    "东湖高新", "高新", "天府", "光谷", "曲江", "长安", "余杭",
)
_CITY_SPLIT_RE = re.compile(r"[/、，,;；和及与＋+（）()]|(?:与|和)")

KNOWN_CITIES = GBA | YRD | JJJ | OVERSEAS | {
    "武汉", "成都", "西安", "长沙", "重庆", "郑州", "南京", "合肥", "济南", "青岛",
    "沈阳", "大连", "昆明", "厦门", "福州", "贵阳", "南宁", "兰州", "乌鲁木齐",
    "台北", "高雄", "台中",
}


def make_id(company, title, url):
    """确定性去重 id：company+title+规范化url 的 md5。"""
    url_clean = re.sub(r"[?&](utm_[^&]+|spm=[^&]+|ncid=[^&]+)", "", url or "")
    norm = "%s|%s|%s" % (company.strip().lower(), re.sub(r"\s+", "", title or ""), url_clean.strip())
    h = hashlib.md5(norm.encode("utf-8")).hexdigest()[:8]
    slug = re.sub(r"[^\w一-鿿]+", "-", "%s-%s" % (company, title))[:40].strip("-").lower()
    return "%s__%s" % (slug, h)


def compute_match_score(tags, hire_type, regions, stars):
    """针对深大 GIS「人工智能（城市）」研一画像打匹配分（0-100）。"""
    tags = set(tags or [])
    score = 0
    # 方向命中（40分）
    hit = sum(1 for t in DIRECTION_TAGS if t in tags)
    score += min(hit * 10, 40)
    # 技能栈命中（20分）
    sk = sum(1 for t in SKILL_TAGS if t in tags)
    score += min(sk * 5, 20)
    # 招聘类型（20分）
    score += HIRE_SCORE.get(hire_type, 8)
    # 地理（10分）
    regions = regions or []
    if "大湾区" in regions:
        score += 10
    elif "远程" in regions:
        score += 5
    elif any(r in regions for r in ("长三角", "京津冀", "国内")):
        score += 6
    else:
        score += 3  # 海外
    # 公司质量（10分）
    score += min(int(stars or 0) * 2, 10)
    return max(0, min(score, 100))
