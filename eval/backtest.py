"""④ 回测：**唯一能证明"推荐有用"的东西**。

## 怎么回测

```
① 造 n 个"考生视角"（用**检验年**的一分一段表定位 —— 那是考生自己当天就知道的信息）
        │
② 给每个考生生成方案 —— 只能用**参照年**（2022）的数据        🔴 不许看检验年
        │
③ 用**检验年**（2025）的**真实投档线**检验：推荐的条目里他能上几个？浪费了多少分？
```

## 🔴 绝不许偷看未来

生成时若读了检验年的数据，回测数字全绿也**毫无意义** —— 那不是回测，是作弊。
所以本模块把两件事**在代码上分开**：

- **生成**：`screen.candidates(..., year=fit_year)`（2022）
- **检验**：`_admitted(..., year=test_year)`（2025）

`tests/test_backtest.py::test_generation_path_never_reads_the_test_year` 盯着这条界线。

## 跑法

    py eval/backtest.py
"""
import argparse
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from gaokao_audit import config, db, queries  # noqa: E402
from gaokao_audit.recommend import compose, screen  # noqa: E402
from gaokao_audit.recommend.models import Candidate  # noqa: E402

FIT_YEAR = 2022     # 参照年（生成方案时的"历史依据"）
TEST_YEAR = 2025    # 检验年（真实结果）
N_PER_CANDIDATE = 8


@dataclass
class BacktestReport:
    admit_rate: float
    waste_p50: float | None
    waste_p90: float | None
    screened_out: int
    details: list[dict] = field(default_factory=list)


def run(
    conn,
    *,
    fit_year: int = FIT_YEAR,
    test_year: int = TEST_YEAR,
    n_candidates: int = 40,
    make_candidate: int = 40,
    chat=None,
    n_per_candidate: int = N_PER_CANDIDATE,
) -> BacktestReport:
    cands = _make_candidates(conn, test_year, n_candidates)
    details: list[dict] = []
    screened_out = 0

    for cand in cands:
        # 🔴 生成阶段：**只碰 fit_year**
        groups = screen.candidates(conn, cand, year=fit_year)
        if not groups:
            screened_out += 1
            continue
        recs = compose.recommend(cand, groups, n=n_per_candidate, chat=chat)
        for r in recs:
            # 🔴 检验阶段：**只碰 test_year**
            line = queries.admission_line_of(
                conn, r.university_name, r.major_group, test_year, cand.category
            )
            if line is None or line.min_rank is None:
                continue    # 该组在检验年不存在/无位次 → 无法判定，不计入
            details.append({
                "rank": cand.rank,
                "school": r.university_name,
                "group": r.major_group,
                "tier": r.tier,
                "admitted": _admitted(conn, r, cand, year=test_year),
                "waste": line.min_rank - cand.rank,
            })

    judged = [d for d in details if d["admitted"] is not None]
    admitted = [d for d in judged if d["admitted"]]
    wastes = sorted(d["waste"] for d in admitted)

    return BacktestReport(
        admit_rate=(len(admitted) / len(judged)) if judged else 0.0,
        waste_p50=_pct(wastes, 0.50),
        waste_p90=_pct(wastes, 0.90),
        screened_out=screened_out,
        details=details,
    )


def _admitted(conn, rec, cand: Candidate, *, year: int) -> bool | None:
    """考生能不能上这一条：**位次数值越大越靠后**，所以他排在最低位次之前就能上。"""
    line = queries.admission_line_of(conn, rec.university_name, rec.major_group, year, cand.category)
    if line is None or line.min_rank is None:
        return None
    return cand.rank <= line.min_rank


def _make_candidates(conn, test_year: int, n: int) -> list[Candidate]:
    """造 n 个"考生视角"，按位次从高到低铺开。

    ⚠️ 用**检验年**的一分一段表定位 —— 这是允许的：那是考生填报当天自己就知道的信息，
    不是"未来信息"。真正的未来信息是**录取结果**，那个只在检验阶段用。
    """
    category = config.CATEGORIES[0]
    rows = conn.execute(
        "select score from score_range where year = ? and category = ? "
        "and score is not null order by score desc",
        (int(test_year), category),
    ).fetchall()
    if not rows:
        return []
    scores = [int(r[0]) for r in rows]
    step = max(1, len(scores) // max(n, 1))
    out: list[Candidate] = []
    for i in range(0, len(scores), step):
        score = scores[i]
        rank = queries.rank_of(conn, score, category, test_year)
        if rank:
            out.append(Candidate(score=score, category=category, rank=rank,
                                 subjects=("物理", "化学", "生物")))
        if len(out) >= n:
            break
    return out


def _pct(sorted_values: list[int], q: float) -> float | None:
    if not sorted_values:
        return None
    idx = min(len(sorted_values) - 1, int(len(sorted_values) * q))
    return float(sorted_values[idx])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--candidates", type=int, default=40)
    ap.add_argument("--fit-year", type=int, default=FIT_YEAR)
    ap.add_argument("--test-year", type=int, default=TEST_YEAR)
    args = ap.parse_args()

    conn = db.connect(config.DB_PATH)
    rep = run(conn, fit_year=args.fit_year, test_year=args.test_year,
              n_candidates=args.candidates)

    print("=" * 66)
    print(f"回测：参照年 {args.fit_year} → 检验年 {args.test_year}，{args.candidates} 个考生视角")
    print("-" * 66)
    print(f"可判定的推荐条目       : {len([d for d in rep.details if d['admitted'] is not None])}")
    print(f"录取率（能上的占比）    : {rep.admit_rate:.3f}")
    print(f"浪费分位中位数 P50      : {rep.waste_p50}")
    print(f"浪费分位 P90            : {rep.waste_p90}")
    print(f"筛不出候选的考生数      : {rep.screened_out}")
    print("=" * 66)


if __name__ == "__main__":
    main()
