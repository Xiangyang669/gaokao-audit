"""全局常量与路径。范围：广东省 · 本科批。

⚠️ 所有取值都以**真实数据**为准（见 docs/data-schema.md），不是按直觉写的：
   - 批次叫 `本科批`（不是"本科普通批"）
   - 科类叫 `物理类` / `历史类`（不是"物理"/"历史"）
   - 累计人数列叫 `cumulative_count`；专业组列叫 `major_group`
"""
from pathlib import Path

PROVINCE = "广东"
DOWNLOAD_YEARS = (2021, 2025)     # 实际下载了哪几年

# 一分一段表可用年份：2021 的 category/batch 全空，不可用
SCORE_YEARS = (2022, 2023, 2024, 2025)

# 🔴 本科批录取数据可用年份 —— 2023 整张缺失、2024 只有专科批（数据集自身的洞）
# Ruling（2026-10-11，用户选 A）：接受缩窄，投档线相关检查只在这两年上做。
ADMISSION_YEARS = (2022, 2025)

BATCH = "本科批"
CATEGORIES = ("物理类", "历史类")

# 真实列名（改动前先看 docs/data-schema.md）
COL_CUMULATIVE = "cumulative_count"
COL_MAJOR_GROUP = "major_group"
COL_CATEGORY = "category"
COL_MIN_SCORE = "min_score"
COL_MIN_RANK = "min_rank"
COL_SUBJECT_REQ = "subject_req"
COL_PLAN_COUNT = "plan_count"

ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = ROOT / "data" / "raw"
DB_PATH = ROOT / "data" / "gaokao.db"
RANK_TOLERANCE = 5  # 位次比对容差（名）
LINE_TOLERANCE = 1  # 投档线比对容差（分）
