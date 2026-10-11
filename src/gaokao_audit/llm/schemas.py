"""4 处 LLM 调用的**输出**结构。

放在一处，是为了让"模型该还什么"这件事只有一个定义 —— 提示词、解析、测试都从这里取。
"""
from dataclasses import dataclass
from enum import Enum


@dataclass(frozen=True)
class ParsedItem:
    """从截图里读出来的**一条**志愿。

    注意 `claimed_min_score` / `claimed_rank` 允许为空：某一格没读出来时，
    **保留这一行**（专业组还在，能查），只是那格为空 —— 整行丢掉会让
    "我明明填了 30 条它只读到 27 条"这件事无从察觉。
    """

    seq: int
    university_name: str
    major_group: str
    claimed_min_score: int | None
    claimed_rank: int | None
    tier: str | None


@dataclass(frozen=True)
class ParsedPlan:
    items: list[ParsedItem]
    raw_item_count: int          # 模型**声称**读到几行 —— 供人工核对（Review Focus 3）
    degraded: str | None = None  # 非空 = 这一路没成，**不是**"读到了 0 条"


class Intent(str, Enum):
    """用户这句提问属于哪一类 —— 它决定"这次必须查哪几项".

    兜底是 `full_check`：分类不出来时**审得宽一点**，而不是不审。
    """

    stability = "stability"          # 这表稳不稳 / 会不会滑档
    reachability = "reachability"    # 我能不能上某个学校/专业组
    full_check = "full_check"        # 全表体检（兜底）


INTENT_VALUES = tuple(i.value for i in Intent)
