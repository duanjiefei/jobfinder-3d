# -*- coding: utf-8 -*-
"""派生字段解析器：城市 / 薪资 / 招聘类型 / 经验 / 方向标签。

种子生成器 build_seed_jobs 与抓取 adapter 共用同一套规则，保证字段口径一致。
"""
import re

from .schema import (
    GBA, YRD, JJJ, OVERSEAS, KNOWN_CITIES,
    HIRE_TYPES, EXP_LEVELS, DIRECTION_TAGS,
    _CITY_SUFFIX,
)

# ---------------------------------------------------------------------------
# 城市
# ---------------------------------------------------------------------------
def _region_of(city):
    if city in GBA:
        return "大湾区"
    if city in YRD:
        return "长三角"
    if city in JJJ:
        return "京津冀"
    if city in OVERSEAS:
        return "海外"
    return "国内"


def parse_cities(raw):
    """把 city_raw 拆成 (标准城市列表, 地区聚合列表)。"""
    if not raw:
        return [], []
    s = raw.replace("，", "/").replace("、", "/").replace("；", "/")
    # 去掉括号里的备注（如 "全国（深圳有创新中心）" → 保留括号外）
    s = re.sub(r"（[^（）]*）", "", s).replace("(", " ").replace(")", " ")
    parts = [p.strip() for p in re.split(r"[/|,;，；和及]", s) if p.strip()]
    cities, remote = [], False
    for p in parts:
        if any(k in p for k in ("远程", "remote", "线上", "可议")):
            remote = True
            continue
        if p in ("全国", "多地", "不限城市"):
            continue
        # 去掉行政区/通用后缀，取主干城市名
        for suf in _CITY_SUFFIX:
            if p.endswith(suf):
                p = p[: -len(suf)]
                break
        p = p.strip("（）()·． ")
        if p in KNOWN_CITIES and p not in cities:
            cities.append(p)
        elif not p:
            continue
        # 未识别但含"海外/国外"的标记
        elif "海外" in p or "国外" in p:
            for c in OVERSEAS:
                if c in p:
                    cities.append(c)
                    break
    regions = sorted({_region_of(c) for c in cities})
    if remote:
        regions.append("远程")
    return cities, regions


# ---------------------------------------------------------------------------
# 薪资
# ---------------------------------------------------------------------------
_RE_K_RANGE = re.compile(r"(\d+\.?\d*)\s*[-~～至]\s*(\d+\.?\d*)\s*K", re.I)
_RE_K_SINGLE = re.compile(r"(\d+\.?\d*)\s*K\+?", re.I)
_RE_WAN_RANGE = re.compile(r"(\d+\.?\d*)\s*[-~～至]\s*(\d+\.?\d*)\s*万")
_RE_WAN_SINGLE = re.compile(r"(\d+\.?\d*)\s*万")
_RE_DAY = re.compile(r"(\d+\.?\d*)\s*[-~～至]\s*(\d+\.?\d*)\s*元\s*[/／]\s*(?:日|天)", re.I)
_RE_HOUR = re.compile(r"\$\s*(\d+\.?\d*)\s*[-~～至]\s*(\d+\.?\d*)\s*/\s*(?:时|hour)", re.I)
_RE_MONTHS = re.compile(r"(?:[×xX*·])\s*(\d{1,2})\s*薪?")
_RE_FOREIGN_RANGE = re.compile(r"(?:\$|€|CA\$|£)\s*(\d+\.?\d*)\s*[-~～至]\s*(\d+\.?\d*)\s*K", re.I)


def parse_salary(raw):
    """把 salary_raw 解析成 {min_k,max_k,months,annual_k_min,annual_k_max,currency,unit,confidence}。"""
    if not raw:
        return _empty_salary()
    r = raw
    # 置信度：含"未公开/未核实/面议/宣传"→参考或未知；含"参考"→low；纯数值→high
    has_num = bool(re.search(r"\d", r))
    low = "参考" in r or "宣传" in r or "待核" in r or "第三方" in r
    unknown = ("未公开" in r or "未核实" in r or "面议" in r or "未标注" in r) and not has_num

    months_m = _RE_MONTHS.search(r)
    months = int(months_m.group(1)) if months_m else None

    # 日薪
    m = _RE_DAY.search(r)
    if m:
        lo, hi = float(m.group(1)), float(m.group(2))
        return _salary(lo / 1000 * 22, hi / 1000 * 22, months or 12, "CNY", "K/月", low or unknown,
                       raw, "元/日")
    # 时薪（美元）
    m = _RE_HOUR.search(r)
    if m:
        lo, hi = float(m.group(1)), float(m.group(2))
        return _salary(lo * 22 * 8 * 7.2 / 1000, hi * 22 * 8 * 7.2 / 1000, 12, "USD", "K/月", low or unknown,
                       raw, "$/时")
    # 外币年薪 K
    m = _RE_FOREIGN_RANGE.search(r)
    if m:
        lo, hi = float(m.group(1)), float(m.group(2))
        cur = "USD" if "$" in m.group(0) else ("EUR" if "€" in m.group(0) else "CAD")
        return _salary(lo / 12, hi / 12, 12, cur, "K/月", low or unknown, raw, "年薪")
    # K/月
    m = _RE_K_RANGE.search(r)
    if m:
        lo, hi = float(m.group(1)), float(m.group(2))
        return _salary(lo, hi, months or 12, "CNY", "K/月", "high" if not low and not unknown else ("low" if low else "unknown"), raw)
    m = _RE_K_SINGLE.search(r)
    if m:
        lo = float(m.group(1))
        return _salary(lo, lo, months or 12, "CNY", "K/月", "high" if not low and not unknown else ("low" if low else "unknown"), raw)
    # 万/月 or 万/年
    m = _RE_WAN_RANGE.search(r)
    if m:
        lo, hi = float(m.group(1)), float(m.group(2))
        is_year = "年" in r and "月" not in r
        if is_year:
            return _salary(lo * 10 / 12, hi * 10 / 12, 12, "CNY", "万/年", "high" if not low else "low", raw)
        return _salary(lo * 10, hi * 10, months or 12, "CNY", "万/月", "high" if not low else "low", raw)
    m = _RE_WAN_SINGLE.search(r)
    if m:
        lo = float(m.group(1))
        is_year = "年" in r and "月" not in r
        if is_year:
            return _salary(lo * 10 / 12, lo * 10 / 12, 12, "CNY", "万/年", "high" if not low else "low", raw)
        return _salary(lo * 10, lo * 10, months or 12, "CNY", "万/月", "high" if not low else "low", raw)

    return _empty_salary(raw)


def _salary(min_k, max_k, months, currency, unit, confidence, raw, display_unit=None):
    months = months or 12
    return {
        "min_k": round(min_k, 1), "max_k": round(max_k, 1),
        "months": months,
        "annual_k_min": round(min_k * months, 1), "annual_k_max": round(max_k * months, 1),
        "currency": currency, "unit": unit, "display_unit": display_unit or unit,
        "confidence": confidence, "raw": raw,
    }


def _empty_salary(raw=""):
    return {"min_k": None, "max_k": None, "months": None,
            "annual_k_min": None, "annual_k_max": None,
            "currency": None, "unit": None, "display_unit": None,
            "confidence": "unknown", "raw": raw}


# ---------------------------------------------------------------------------
# 招聘类型 / 经验
# ---------------------------------------------------------------------------
def parse_hire_type(title, req):
    t = "%s %s" % (title, req)
    if re.search(r"博士后|postdoc", t, re.I):
        return "博士后"
    # 实习：明确实习信号且不带"校招/秋招/春招/campus/提前批"（避免"2027届校招…实习生"误判）
    if re.search(r"实习|intern|暑期|日常实习", t, re.I) and not re.search(r"校招|秋招|春招|campus|提前批", t, re.I):
        return "实习"
    if re.search(r"校招|202\d届|秋招|春招|campus|提前批|应届", t, re.I):
        return "校招"
    if re.search(r"管培|远见计划|星核人才", t):
        return "管培"
    if re.search(r"社招|高级|专家|资深|senior|正式", t, re.I):
        return "社招"
    return "不限"


def parse_experience(title, req):
    t = "%s %s" % (title, req)
    if "博士后" in t:  # 仅"博士后"字样才是博士后岗；"博士优先/硕士及以上"不算
        return {"level": "博士后", "education": "博士", "is_fresh_friendly": False}
    if re.search(r"实习|intern|暑期", t, re.I):
        return {"level": "实习", "education": "不限", "is_fresh_friendly": True}
    if re.search(r"校招|202\d届|应届|campus|提前批|毕业", t, re.I):
        return {"level": "应届", "education": "不限", "is_fresh_friendly": True}
    m = re.search(r"(\d+)\s*[-~～至]\s*(\d+)\s*年", t)
    if m:
        lo, hi = int(m.group(1)), int(m.group(2))
        if hi >= 5:
            return {"level": "5年+", "education": "不限", "is_fresh_friendly": False}
        if lo >= 3:
            return {"level": "3-5年", "education": "不限", "is_fresh_friendly": False}
        if hi >= 1:
            return {"level": "1-3年", "education": "不限", "is_fresh_friendly": True}
    m = re.search(r"(\d+)\s*年\+?\s*(以上)?", t)
    if m:
        n = int(m.group(1))
        if n >= 5:
            return {"level": "5年+", "education": "不限", "is_fresh_friendly": False}
        if n >= 3:
            return {"level": "3-5年", "education": "不限", "is_fresh_friendly": False}
        return {"level": "1-3年", "education": "不限", "is_fresh_friendly": True}
    edu = "不限"
    if re.search(r"博士", t):
        edu = "博士"
    elif re.search(r"硕士|研究生", t):
        edu = "硕士"
    elif re.search(r"本科", t):
        edu = "本科"
    return {"level": "不限", "education": edu, "is_fresh_friendly": True}


# ---------------------------------------------------------------------------
# 方向 + 技能标签
# ---------------------------------------------------------------------------
def _w(tok):
    """ASCII-only 词边界：中文也是 Unicode 单词字符，\b 在"SLAM算法"间不成立，故只对 [A-Za-z0-9_] 做边界。"""
    return r"(?<![A-Za-z0-9_])" + tok + r"(?![A-Za-z0-9_])"


TAG_RULES = {
    "摄影测量": r"摄影测量|%s|空三|倾斜摄影|航测|测绘|bundle adjustment|摄影测量与遥感" % _w(r"SfM"),
    "LiDAR点云": r"%s|激光雷达|点云|%s|三维激光|%s|%s|点云配准" % (_w(r"LiDAR"), _w(r"PCL"), _w(r"ICP"), _w(r"NDT")),
    "三维重建": r"三维重建|3D重建|%s|稠密重建|实景三维|网格重建|%s|重建算法" % (_w(r"MVS"), _w(r"mesh")),
    "NeRF/3DGS": r"%s|%s|Gaussian Splatting|%s|%s|Neural Radiance|神经渲染|可微渲染" % (_w(r"NeRF"), _w(r"3DGS"), _w(r"4DGS"), _w(r"VGGT")),
    "SLAM": r"%s|%s|%s|视觉里程计|LIO-SAM|ORB-SLAM|VINS|Cartographer|LOAM|多传感器融合|重定位" % (_w(r"SLAM"), _w(r"VIO"), _w(r"LIO")),
    "GIS": r"%s|WebGIS|Cesium|three\.js|WebGL|数字地球|数字孪生|PostGIS|GeoTools|地理信息" % _w(r"GIS"),
    "城市AI": r"城市|urban|低空|遥感|智能体|%s|%s|World Model|世界模型|智慧城市" % (_w(r"VLM"), _w(r"VLA")),
    "3D生成": r"3D生成|AIGC|生成式|diffusion|文生3D|图生3D|3D VAE|3D DiT|Mesh Generation",
    "图形学": r"图形学|计算几何|%s|OpenMesh|B样条|有限元|渲染|%s|%s|%s|光线追踪" % (_w(r"CGAL"), _w(r"Vulkan"), _w(r"OpenGL"), _w(r"GPGPU")),
    "具身/机器人": r"具身|embod|机器人|Robot|机械臂|人形|Sim2Real|无人驾驶|智驾|自动驾驶",
}
SKILL_RULES = {
    "C++": _w(r"C\+\+"),
    "Python": _w(r"Python"),
    "PyTorch": r"%s|torch" % _w(r"PyTorch"),
    "CUDA": _w(r"CUDA"),
    "OpenCV": _w(r"OpenCV"),
    "Eigen": _w(r"Eigen"),
    "Ceres": _w(r"Ceres"),
    "GTSAM": _w(r"GTSAM"),
    "COLMAP": r"%s|OpenMVS|OpenMVG|%s" % (_w(r"COLMAP"), _w(r"MVE")),
}


def parse_tags(title, req, core=""):
    """返回 (tags列表, 主方向标签)。tags 含方向+技能，匹配 title+req+core。"""
    text = "%s %s %s" % (title or "", req or "", core or "")
    tags = []
    for name, pat in TAG_RULES.items():
        if re.search(pat, text, re.I) and name not in tags:
            tags.append(name)
    for name, pat in SKILL_RULES.items():
        if re.search(pat, text, re.I) and name not in tags:
            tags.append(name)
    primary = next((t for t in DIRECTION_TAGS if t in tags), (tags[0] if tags else ""))
    return tags, primary


# 供模块内部使用的导入（避免 flake）
HIRE_TYPES = HIRE_TYPES
EXP_LEVELS = EXP_LEVELS
