"""跨表/跨来源的标识符归一化。

⚠️ 只归一化"同一个东西的两种写法"，**不要**合并本该区分的值。
   实测依据：本数据集里专业组号全是纯三位数字（唯一非数字的 `（L艺术类）` 属艺体，
   已按批次过滤掉），去掉括号与空格不会把该区分的组合并。见 docs/data-schema.md。
"""

_STRIP = "（）()【】[] 　\t"


def normalize_group(value) -> str | None:
    """专业组号归一化。

    实测：同一个专业组在两张表里写法不同 ——
      `major-admission` 写 `（206）`（全角括号），`enrollment-plan` 写 `206`（纯数字）。
    写库时归一化还不够：**读的时候也得归一化**，否则 Plan 2 从截图解析出来的组号
    （必然带括号/空格）会查不到任何东西，而且不报错。
    """
    if value is None:
        return None
    s = str(value).strip()
    for ch in _STRIP:
        s = s.replace(ch, "")
    return s or None
