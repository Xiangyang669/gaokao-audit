"""构造测试用 Case 的共享助手（不是 pytest 插件，是被 import 的普通模块）。

⚠️ 两个坑，都是实测踩出来的：
  1. **必须从 `admission_line` JOIN `enrollment_plan` 取组** ——
     两张表的 (学校, 专业组) 集合并不相同；只从前者取，选科检查会因为查不到要求而空转。
  2. **必须让考生位次真的够得着所选组**（`min_rank >= candidate_rank`）——
     否则"干净表"里每一行都该被报 tier_inconsistent，基线误报直接等于行数，
     评测里的 recall 就是假阳性撑出来的。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from gaokao_audit import config, queries  # noqa: E402
from gaokao_audit.models import AuditContext, PlanItem  # noqa: E402

Y = 2025
CAT = config.CATEGORIES[0]
SUBJECTS = ("物理", "化学", "生物")
CAND_RANK = 20000  # 一个"够得着不少组"的考生位次


def make_items(conn, n=12, year=Y, category=CAT, candidate_rank=CAND_RANK, reachable=True):
    """造一张**干净**的志愿表：每条都够得着、都是一致的。"""
    op = ">=" if reachable else "<"
    rows = conn.execute(
        f"""
        select a.university_name, a.major_group, a.min_score
        from admission_line a
        join (select distinct university_name, major_group
              from enrollment_plan where year = ?) e
          on a.university_name = e.university_name and a.major_group = e.major_group
        where a.year = ? and a.category = ?
          and a.min_score is not null and a.min_rank is not null
          and a.min_rank {op} ?
        limit ?
        """,
        (year, year, category, candidate_rank, n),
    ).fetchall()
    items = []
    for i, (school, group, score) in enumerate(rows, start=1):
        rank = queries.rank_of(conn, int(score), category, year)
        items.append(
            PlanItem(seq=i, university_name=school, major_group=group,
                     claimed_min_score=int(score), claimed_rank=rank,
                     subject_req=None, tier="稳")
        )
    return items


def make_ctx(year=Y, category=CAT, candidate_rank=CAND_RANK, subjects=SUBJECTS):
    return AuditContext(year=year, category=category,
                        candidate_rank=candidate_rank, candidate_subjects=subjects)
