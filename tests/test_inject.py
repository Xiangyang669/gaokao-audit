"""Task 7 · 错误注入：往干净的表里塞**已知**的错误，好回头量"抓到了几个"."""
import random

import pytest

from conftest_helpers import make_ctx, make_items
from eval import inject

KINDS = ("year", "number", "tier", "subject")


@pytest.fixture
def case(conn):
    items = make_items(conn, n=20)
    assert len(items) >= 4, "样本太少，评测说明不了问题"
    return inject.Case(items=items, ctx=make_ctx())


@pytest.mark.parametrize("kind", KINDS)
def test_injection_changes_something_and_records_it(conn, case, kind):
    new_case, injected = inject.inject(case, conn, kind, random.Random(1))
    assert injected, f"{kind} 类没注入任何东西"
    assert all(i.kind == kind for i in injected)
    assert all(i.expected_finding_kind for i in injected)
    assert new_case != case, f"{kind} 类注入了但内容没变"


@pytest.mark.parametrize("kind", KINDS)
def test_injection_is_reproducible(conn, case, kind):
    a, ia = inject.inject(case, conn, kind, random.Random(7))
    b, ib = inject.inject(case, conn, kind, random.Random(7))
    assert (a, [i.seq for i in ia]) == (b, [i.seq for i in ib])


def test_untouched_items_are_left_alone(conn, case):
    new_case, injected = inject.inject(case, conn, "number", random.Random(3))
    touched = {i.seq for i in injected}
    for old, new in zip(case.items, new_case.items):
        if old.seq not in touched:
            assert old == new, f"没被注入的第 {old.seq} 条被改动了"


def test_n_limits_how_many_are_injected(conn, case):
    _, injected = inject.inject(case, conn, "number", random.Random(5), n=3)
    assert len(injected) == 3


def test_unknown_kind_raises(case):
    with pytest.raises(ValueError):
        inject.inject(case, None, "不存在的类", random.Random(1))
