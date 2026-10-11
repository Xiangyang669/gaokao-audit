"""Task 2 · CSV → SQLite 的契约测试。`conn` fixture 在 conftest.py。"""
from gaokao_audit import config


def test_tables_exist(conn):
    names = {r[0] for r in conn.execute("select name from sqlite_master where type='table'")}
    assert {"score_range", "admission_line", "enrollment_plan", "rules"} <= names


def test_only_guangdong_loaded(conn):
    """Review Focus 3 的前置：库里不该混进别的省份。"""
    provinces = {r[0] for r in conn.execute("select distinct province from score_range")}
    assert provinces == {config.PROVINCE}


def test_score_years_match_config(conn):
    ys = {r[0] for r in conn.execute("select distinct year from score_range")}
    assert ys == set(config.SCORE_YEARS)


def test_admission_years_match_config(conn):
    """投档线表的年份必须恰好是裁定过的那几年，多一年少一年都要报出来。"""
    ys = {r[0] for r in conn.execute("select distinct year from admission_line")}
    assert ys == set(config.ADMISSION_YEARS)


def test_admission_line_is_group_level(conn):
    """admission_line 是**专业组**粒度：每年每组的专业数必须 ≥1 且组号非空。"""
    rows = conn.execute(
        "select year, major_group, count(*) from admission_line group by year, major_group"
    ).fetchall()
    assert rows, "admission_line 是空的"
    assert all(r[1] is not None and str(r[1]).strip() != "" for r in rows), "有专业组号为空的行"


def test_nonempty(conn):
    for t in ("score_range", "admission_line", "enrollment_plan"):
        assert conn.execute(f"select count(*) from {t}").fetchone()[0] > 0, f"{t} 是空的"
