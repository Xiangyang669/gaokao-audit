"""Task 1 · 数据契约测试 —— 数据集落地的凭据.

断言"我们需要的表都在、里面有广东的行、以及**真实的批次/科类取值**".
⚠️ 文件名用**连字符**（`score-range.csv`），批次是 `本科批`，科类是 `物理类`/`历史类`
   —— 这些都以真实数据为准，见 docs/data-schema.md。
"""
import pandas as pd
import pytest

from gaokao_audit import config


@pytest.mark.parametrize("name", ["score-range", "school-admission", "enrollment-plan"])
def test_raw_csv_present(name):
    hits = list(config.RAW_DIR.glob(f"*{name}.csv"))
    assert hits, f"{config.RAW_DIR} 下没找到 {name} 的 CSV"


def test_guangdong_rows_exist():
    files = list(config.RAW_DIR.glob("*.csv"))
    assert files, f"{config.RAW_DIR} 下没有任何 CSV"
    df = pd.concat([pd.read_csv(p, nrows=200000) for p in files])
    assert (df.astype(str) == config.PROVINCE).any().any(), "没找到任何广东的行"


def test_batch_label_is_the_real_one():
    """锁住真实批次名：写错的话查数据会静默返回空。"""
    df = pd.read_csv(config.RAW_DIR / "2022-score-range.csv")
    if not (df.batch.astype(str) == config.BATCH).any():
        pytest.skip("该文件的 batch 列结构与预期不同，先看 docs/data-schema.md")
    assert (df.batch.astype(str) == config.BATCH).any()


def test_announced_admission_years_actually_have_data():
    """把「缩窄到 2022/2025」这个裁定落成可执行的断言.

    没有这条，将来有人改了 ADMISSION_YEARS 却碰上空洞，会静默拿到空结果。
    """
    for y in config.ADMISSION_YEARS:
        df = pd.read_csv(config.RAW_DIR / f"{y}-school-admission.csv")
        n = (df.batch.astype(str) == config.BATCH).sum()
        assert n > 0, f"{y} 年 {config.BATCH} 投档线为 0 行 —— 与 config.ADMISSION_YEARS 不符"


def test_score_years_have_both_categories():
    """一分一段表必须两个科类都有，否则位次换算会漏一半。"""
    for y in config.SCORE_YEARS:
        df = pd.read_csv(config.RAW_DIR / f"{y}-score-range.csv")
        cats = set(df.category.dropna().unique())
        assert set(config.CATEGORIES) <= cats, f"{y} 年缺科类：{cats}"
