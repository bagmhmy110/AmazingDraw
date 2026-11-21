#!/usr/bin/env python3
"""人种 / 年龄选项：四个 prompt skill 共用。

人种按「地域 → 具体族裔 → 可见特征」组织，避免只贴一个「亚洲人」标签。
年龄只列成年区间（18 岁以上），这是所有 skill 的共同底线。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

# ── 人种 ──────────────────────────────────────────────────────────────
# 每条给出：value（写入提示词的落地描述）/ label（下拉显示）/ group（分组）
ETHNICITY: List[Dict[str, str]] = [
    # 东亚
    {"group": "东亚", "value": "中国汉族女性", "label": "中国 · 汉族"},
    {"group": "东亚", "value": "中国北方女性，骨架偏大、脸型偏方", "label": "中国 · 北方"},
    {"group": "东亚", "value": "中国江南女性，骨架纤细、脸型偏鹅蛋", "label": "中国 · 江南"},
    {"group": "东亚", "value": "中国西南少数民族女性，肤色偏暖、眼窝略深", "label": "中国 · 西南少数民族"},
    {"group": "东亚", "value": "日本女性，内双细长眼、鼻梁柔和", "label": "日本"},
    {"group": "东亚", "value": "韩国女性，单眼皮、颧骨平缓、下颌线清晰", "label": "韩国"},
    {"group": "东亚", "value": "蒙古女性，颧骨高、面部轮廓宽阔", "label": "蒙古"},
    # 东南亚
    {"group": "东南亚", "value": "泰国女性，肤色偏小麦、五官立体", "label": "泰国"},
    {"group": "东南亚", "value": "越南女性，骨架纤细、五官清秀", "label": "越南"},
    {"group": "东南亚", "value": "菲律宾女性，肤色偏暖棕、眼睛大而圆", "label": "菲律宾"},
    {"group": "东南亚", "value": "印尼女性，肤色偏深、鼻翼略宽", "label": "印尼"},
    {"group": "东南亚", "value": "马来西亚女性，肤色偏蜜色、五官柔和", "label": "马来西亚"},
    # 南亚
    {"group": "南亚", "value": "印度北部女性，肤色偏浅棕、眼窝深、鼻梁高", "label": "印度 · 北部"},
    {"group": "南亚", "value": "印度南部女性，肤色偏深棕、发质浓密", "label": "印度 · 南部"},
    {"group": "南亚", "value": "巴基斯坦女性，五官立体、眉骨明显", "label": "巴基斯坦"},
    {"group": "南亚", "value": "斯里兰卡女性，肤色偏暖棕、眼型圆润", "label": "斯里兰卡"},
    # 中亚 / 西亚
    {"group": "中亚·西亚", "value": "哈萨克女性，颧骨高、眼窝深、肤色偏白", "label": "哈萨克"},
    {"group": "中亚·西亚", "value": "维吾尔女性，眼窝深、睫毛长、肤色白皙", "label": "维吾尔"},
    {"group": "中亚·西亚", "value": "土耳其女性，五官立体、眉形浓", "label": "土耳其"},
    {"group": "中亚·西亚", "value": "伊朗女性，鼻梁高挺、眼窝深、发色深", "label": "伊朗"},
    # 亚裔 diaspora
    {"group": "亚裔侨居", "value": "华裔美国女性，混血感、轮廓柔和", "label": "华裔 · 美国"},
    {"group": "亚裔侨居", "value": "日裔巴西女性，肤色偏暖、眼型细长", "label": "日裔 · 巴西"},
    {"group": "亚裔侨居", "value": "韩裔加拿大女性，五官清冷、骨架偏细", "label": "韩裔 · 加拿大"},
    # 其他（保留扩展）
    {"group": "其他", "value": "混血亚欧女性，五官兼具东方的柔和与西方的立体", "label": "亚欧混血"},
]

# ── 年龄 ──────────────────────────────────────────────────────────────
# 只列成年区间。所有 skill 的底线：不出现未成年。
AGE: List[Dict[str, str]] = [
    {"value": "", "label": "不限（由风格决定）"},
    {"value": "18岁成年女性", "label": "18 岁"},
    {"value": "19岁成年女性", "label": "19 岁"},
    {"value": "20岁成年女性", "label": "20 岁"},
    {"value": "21岁成年女性", "label": "21 岁"},
    {"value": "22岁成年女性", "label": "22 岁"},
    {"value": "23岁成年女性", "label": "23 岁"},
    {"value": "24岁成年女性", "label": "24 岁"},
    {"value": "25岁成年女性", "label": "25 岁"},
    {"value": "26岁成年女性", "label": "26 岁"},
    {"value": "27岁成年女性", "label": "27 岁"},
    {"value": "28岁成年女性", "label": "28 岁"},
    {"value": "29岁成年女性", "label": "29 岁"},
    {"value": "30岁成熟女性", "label": "30 岁"},
    {"value": "32岁成熟女性", "label": "32 岁"},
    {"value": "35岁成熟女性", "label": "35 岁"},
    {"value": "38岁成熟女性", "label": "38 岁"},
    {"value": "40岁成熟女性", "label": "40 岁"},
    {"value": "45岁成熟女性", "label": "45 岁"},
]

# 年龄速选档（比逐岁更好用）
AGE_BANDS: List[Dict[str, str]] = [
    {"value": "", "label": "不限"},
    {"value": "18-22岁年轻成年女性", "label": "18-22 年轻"},
    {"value": "23-27岁成年女性", "label": "23-27 青年"},
    {"value": "28-32岁成熟女性", "label": "28-32 成熟"},
    {"value": "33-40岁成熟女性", "label": "33-40 熟龄"},
    {"value": "40岁以上成熟女性", "label": "40+"},
]

# 身材 / 气质（配合人种使用，让下拉更有用）
BODY: List[Dict[str, str]] = [
    {"value": "", "label": "不限"},
    {"value": "身形纤细，肩窄腰细", "label": "纤细"},
    {"value": "身形匀称，比例协调", "label": "匀称"},
    {"value": "身形高挑，一双修长的长腿", "label": "高挑长腿"},
    {"value": "身形丰腴，曲线明显", "label": "丰腴"},
    {"value": "身形紧实，肌肉线条清晰", "label": "紧实运动"},
    {"value": "骨架偏小，娇小玲珑", "label": "娇小"},
]

# 气质 / 表情基调
VIBE: List[Dict[str, str]] = [
    {"value": "", "label": "不限"},
    {"value": "神情清冷疏离", "label": "清冷疏离"},
    {"value": "眼神妩媚直视镜头", "label": "妩媚直视"},
    {"value": "笑意温柔，眼神柔和", "label": "温柔"},
    {"value": "神情慵懒松弛", "label": "慵懒"},
    {"value": "眼神凌厉，气场压人", "label": "凌厉"},
    {"value": "神情羞怯，视线回避", "label": "羞怯"},
    {"value": "神情高傲，居高临下", "label": "高傲"},
]


def ethnicity_options() -> Dict[str, Any]:
    """按 group 分好的人种选项，供前端做 optgroup。"""
    groups: Dict[str, List[Dict[str, str]]] = {}
    for item in ETHNICITY:
        groups.setdefault(item["group"], []).append(
            {"value": item["value"], "label": item["label"]}
        )
    return groups


def pick_ethnicity(value: str) -> str:
    """把下拉值规范成可写入提示词的描述。"""
    v = (value or "").strip()
    if not v:
        return ""
    for item in ETHNICITY:
        if v in (item["value"], item["label"]):
            return item["value"]
    return v


def pick_age(value: str) -> str:
    v = (value or "").strip()
    if not v:
        return ""
    for item in AGE + AGE_BANDS:
        if v in (item["value"], item["label"]):
            return item["value"]
    return v


def common_meta() -> Dict[str, Any]:
    """四个 skill 的 meta 都带上这段。"""
    return {
        "ethnicity_groups": ethnicity_options(),
        "ages": AGE,
        "age_bands": AGE_BANDS,
        "bodies": BODY,
        "vibes": VIBE,
        "note": "人种与年龄对所有 skill 通用；年龄只列成年区间",
    }
