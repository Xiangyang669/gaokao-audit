"""只读查询层。**查不到一律返回 None / 空列表** —— 不抛异常、不返回 0。

返回 0 或抛异常都会让上层的降级逻辑误判：前者看起来像"查到了且值为 0"，
后者会让一路检查崩掉。缺数据是一个**正常状态**，用它自己的形状表达。

⚠️ 两条必须遵守的读时约定（都是实测栽过的）：
  ① **科类必须参与查询** —— 同一所学校、同一个专业组号，物理类和历史类的分数线
     是**两回事**。漏掉 category 会串表，而且不报错，只让结论翻盘。
  ② **专业组号必须归一化后再查** —— 上游的写法带全角括号/空格（见 normalize.py）。
"""
import sqlite3

from gaokao_audit import config
from gaokao_audit.models import AdmissionLine, EnrollmentPlan, Rules
from gaokao_audit.normalize import normalize_group


def rank_of(conn: sqlite3.Connection, score: int, category: str, year: int) -> int | None:
    """分数 → 全省位次。位次取该分数段的**累计人数（段末位）**。"""
    if category not in config.CATEGORIES:
        return None
    row = conn.execute(
        "select cumulative_count from score_range "
        "where score <= ? and category = ? and year = ? "
        "order by score desc limit 1",
        (float(score), category, int(year)),
    ).fetchone()
    return int(row[0]) if row and row[0] is not None else None


def segment_size(conn: sqlite3.Connection, score: int, category: str, year: int) -> int | None:
    """该分数段里有几个人 —— 也就是「同分的人最多能差多少名」。

    为什么需要它：投档表里的「最低位次」是**投档最低排位**（最后一个被录取者的名次），
    而 `rank_of()` 给的是**段末位**。同一个分数有多少人，这两个值就能差多少。
    所以位次比对的容差必须**按段内人数**给，不能写死一个小常数。
    """
    row = conn.execute(
        "select segment_count from score_range "
        "where score <= ? and category = ? and year = ? order by score desc limit 1",
        (float(score), category, int(year)),
    ).fetchone()
    return int(row[0]) if row and row[0] is not None else None


def admission_line_of(
    conn: sqlite3.Connection, university_name: str, major_group: str, year: int, category: str
) -> AdmissionLine | None:
    row = conn.execute(
        "select university_name, major_group, category, year, min_score, min_rank, subject_req "
        "from admission_line "
        "where university_name = ? and major_group = ? and year = ? and category = ?",
        (university_name, normalize_group(major_group), int(year), category),
    ).fetchone()
    if row is None:
        return None
    return AdmissionLine(
        university_name=row[0], major_group=row[1], category=row[2], year=row[3],
        min_score=row[4], min_rank=row[5], subject_req=row[6],
    )


def enrollment_plan_of(
    conn: sqlite3.Connection, university_name: str, major_group: str, year: int, category: str
) -> list[EnrollmentPlan]:
    rows = conn.execute(
        "select university_name, major_group, major_code, major_name, subject_req, plan_count, year "
        "from enrollment_plan "
        "where university_name = ? and major_group = ? and year = ? and category = ?",
        (university_name, normalize_group(major_group), int(year), category),
    ).fetchall()
    return [
        EnrollmentPlan(
            university_name=r[0], major_group=r[1], major_code=r[2], major_name=r[3],
            subject_req=r[4], plan_count=r[5], year=r[6],
        )
        for r in rows
    ]


def rules_of(conn: sqlite3.Connection) -> Rules:
    kv = {r[0]: r[1] for r in conn.execute("select key, value from rules")}
    return Rules(
        province=kv.get("province", config.PROVINCE),
        batch=kv.get("batch", config.BATCH),
        categories=tuple((kv.get("categories") or "").split(",")),
    )
