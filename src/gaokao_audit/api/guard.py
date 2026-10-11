"""成本护栏：IP 限流 + 全局封顶。

🔴 **这里唯一重要的一件事：先扣后调。**

如果反过来（先调模型、成功了再记账），那么"让调用失败"就成了一条免费通道 ——
刷的人只需要构造必然失败的请求，就能无限占用算力而不进账。所以：

    检查配额 → **扣掉** → 调模型 → （失败也认了）

代价是：调用失败时配额也被消耗了。这是**故意的** —— 那次尝试确实可能已经产生费用，
而且"失败就免费"是不可接受的激励。

⚠️ 进程内内存实现 + 一把锁。单机演示够用；多实例部署要换成共享存储
（这一点在 README 的已知边界里写明）。
"""
import threading
from dataclasses import dataclass, field


@dataclass(frozen=True)
class GuardVerdict:
    allowed: bool
    reason: str | None = None     # "ip_quota" / "global_cap"
    remaining: int = 0


@dataclass
class Guard:
    per_ip_daily: int = 3
    global_cap_yuan: float = 10.0
    cost_per_request: float = 0.02     # 一次请求的估算成本（spec §8.4 算过 ≈¥0.02）

    _used: dict = field(default_factory=dict, init=False)
    _spent: float = field(default=0.0, init=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False)

    def check_and_consume(self, ip: str | None) -> GuardVerdict:
        key = ip or "unknown"
        with self._lock:
            if self._spent + self.cost_per_request > self.global_cap_yuan:
                return GuardVerdict(False, "global_cap", 0)
            used = self._used.get(key, 0)
            if used >= self.per_ip_daily:
                return GuardVerdict(False, "ip_quota", 0)
            # 🔴 先扣 —— 扣完才允许往下走
            self._used[key] = used + 1
            self._spent += self.cost_per_request
            return GuardVerdict(True, None, self.per_ip_daily - used - 1)

    @property
    def spent_yuan(self) -> float:
        return round(self._spent, 4)
