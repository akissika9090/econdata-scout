"""一个数据源的总时限（2026-11-19）：官网核查开始时设定截止时间，模型调用、网页读取及它们的重试都按剩余时间缩短，
剩余时间不够就不再等待重试，抛出 Expired（官网核查把它记为 timed_out）。没有设定时限时一切照旧。"""
import contextvars
import time

_deadline = contextvars.ContextVar("deadline", default=None)
clock = time.monotonic


class Expired(TimeoutError):
    def __init__(self, message: str = "time limit reached", where: str | None = None):
        super().__init__(message)
        self.where = where or message


def start(seconds: float | None):
    """设定截止时间；返回 token，结束时传给 stop()。seconds=None 表示不设时限。"""
    return _deadline.set(None if seconds is None else clock() + seconds)


def stop(token) -> None:
    _deadline.reset(token)


def remaining() -> float | None:
    d = _deadline.get()
    return None if d is None else d - clock()


def cap(timeout: float) -> float:
    """把单次请求的超时缩短到剩余时间以内；已经到时就抛 Expired。"""
    r = remaining()
    if r is None:
        return timeout
    if r <= 0:
        raise Expired("time limit reached")
    return max(1.0, min(timeout, r))


def can_wait(seconds: float) -> bool:
    """等待 seconds 后是否还有时间再试一次。"""
    r = remaining()
    return r is None or r > seconds + 1
