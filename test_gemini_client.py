"""
测试 gemini_client 的重试和换模型逻辑。不联网：用一个假的客户端按预定顺序返回结果或报错，也不真的等待。

运行：
    python test_gemini_client.py
"""

from google.genai import errors

import gemini_client as gc

failures = 0


def check(name, ok):
    global failures
    print(f"{'✓' if ok else '✗'}  {name}")
    if not ok:
        failures += 1


class FakeResponse:
    def __init__(self, text):
        self.text = text


class FakeClient:
    """按顺序取出预定的结果：字符串 = 返回这段文字；整数 = 抛出该状态码的 APIError。记录每次调用的模型。"""
    def __init__(self, script):
        self.script = list(script)
        self.calls = []
        self.models = self

    def generate_content(self, model, contents, config):
        self.calls.append(model)
        item = self.script.pop(0)
        if isinstance(item, int):
            raise errors.APIError(item, {"error": {"code": item, "message": "test", "status": "TEST"}})
        return FakeResponse(item)


def run(script):
    client, waits = FakeClient(script), []
    try:
        result = gc.generate_json("system", "content", {"type": "object"}, client=client, sleep=waits.append)
    except BaseException as e:   # SystemExit 不是 Exception 的子类
        result = e
    return result, client.calls, waits


MAIN, BACKUP = gc.GEMINI_MODEL, gc.GEMINI_FALLBACK_MODELS[0]

r, calls, waits = run(['{"a": 1}'])
check("第一次就成功：返回结果和实际使用的模型", r == ({"a": 1}, MAIN) and calls == [MAIN] and waits == [])

r, calls, waits = run([503, 429, '{"a": 2}'])
check("503、429 是暂时性错误：同一模型等待后重试", r == ({"a": 2}, MAIN) and calls == [MAIN] * 3)
check("等待间隔是 15 秒、45 秒", waits == [15, 45])

r, calls, waits = run([503, 503, 500, '{"a": 3}'])
check("主模型 3 次都失败 → 换备用模型，并报告用的是备用模型", r == ({"a": 3}, BACKUP) and calls == [MAIN] * 3 + [BACKUP])

r, calls, waits = run([404, '{"a": 4}'])
check("404（模型名不存在）不重试，直接换备用模型", r == ({"a": 4}, BACKUP) and calls == [MAIN, BACKUP])

r, calls, waits = run([503] * 6)
check("所有模型都失败 → 退出并说明原因（不返回空结果）", isinstance(r, SystemExit) and len(calls) == 6)

r, calls, waits = run([400])
check("其他错误（如 key 无效、请求格式错误）直接报出，不重试", isinstance(r, errors.APIError) and calls == [MAIN])

r, calls, waits = run(["这不是 JSON"])
check("返回的不是 JSON → 报错，而不是返回空结果", isinstance(r, RuntimeError))

print("\n全部通过" if failures == 0 else f"\n{failures} 项失败")
raise SystemExit(1 if failures else 0)
