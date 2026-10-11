"""一次性把 data/raw/*.csv 灌进 SQLite。

只灌 config 里宣布的范围：广东 · 本科批 · SCORE_YEARS / ADMISSION_YEARS。
跑法： py scripts/build_db.py
"""
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from gaokao_audit import config, db  # noqa: E402
from gaokao_audit.normalize import normalize_group  # noqa: E402


def _benke(df: pd.DataFrame) -> pd.DataFrame:
    return df[df["batch"].astype(str) == config.BATCH]


def build(raw_dir: Path, out: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists():
        out.unlink()
    conn = db.connect(out)
    db.create_schema(conn)

    # ── 一分一段表 ──
    for y in config.SCORE_YEARS:
        df = pd.read_csv(raw_dir / f"{y}-score-range.csv")
        df = df[df["province"].astype(str) == config.PROVINCE]
        df = _benke(df) if df["batch"].notna().any() else df
        rows = [
            (config.PROVINCE, int(r.year), r.category, r.batch,
             _f(r.control_score), _f(r.score), _i(r.cumulative_count),
             _i(r.segment_count), r.rank_range)
            for r in df.itertuples()
        ]
        conn.executemany("insert into score_range values (?,?,?,?,?,?,?,?,?)", rows)

    # ── 投档线（由专业录取分聚合到专业组）──
    for y in config.ADMISSION_YEARS:
        df = pd.read_csv(raw_dir / f"{y}-major-admission.csv")
        df = df[df["province"].astype(str) == config.PROVINCE]
        df = _benke(df)
        df = df[df["major_group"].notna() & df["min_score"].notna()]
        g = (
            df.groupby(["category", "university_name", "major_group"], dropna=False)
              .agg(min_score=("min_score", "min"),
                   min_rank=("min_rank", "max"),
                   subject_req=("subject_req", _first_nonnull))
              .reset_index()
        )
        conn.executemany(
            "insert into admission_line values (?,?,?,?,?,?,?,?)",
            [(config.PROVINCE, int(y), r.category, r.university_name, normalize_group(r.major_group),
              _f(r.min_score), _i(r.min_rank), r.subject_req) for r in g.itertuples()],
        )

    # ── 招生计划 ──
    for y in config.SCORE_YEARS:
        p = raw_dir / f"{y}-enrollment-plan.csv"
        df = pd.read_csv(p)
        df = df[df["province"].astype(str) == config.PROVINCE]
        df = _benke(df)
        conn.executemany(
            "insert into enrollment_plan values (?,?,?,?,?,?,?,?,?,?)",
            [(config.PROVINCE, int(r.year), r.category, r.batch, r.university_name,
              normalize_group(r.major_group), r.major_code, r.major_name, r.subject_req, _i(r.plan_count))
             for r in df.itertuples()],
        )

    # ── 规则常量 ──
    conn.executemany("insert or replace into rules values (?,?)", [
        ("province", config.PROVINCE),
        ("batch", config.BATCH),
        ("categories", ",".join(config.CATEGORIES)),
    ])
    conn.commit()
    conn.close()


def _f(v):
    return None if pd.isna(v) else float(v)


def _i(v):
    return None if pd.isna(v) else int(v)


def _first_nonnull(s):
    s = s.dropna()
    return s.iloc[0] if len(s) else None


if __name__ == "__main__":
    build(config.RAW_DIR, config.DB_PATH)
    print(f"wrote {config.DB_PATH}")
