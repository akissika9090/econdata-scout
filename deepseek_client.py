"""
DeepSeek 模型调用（只用于 V2 官网核查 Agent；论文提取仍用 Gemini，保证与 V1 可比）。

- 模型 deepseek-flash，关闭思考模式（更快、更省），JSON 输出（response_format = json_object）
- 429 / 5xx / 超时时等待后重试；402（余额不足）等其他错误直接报错
- 需要 DEEPSEEK_API_KEY
"""

import json
import os
import time

URL = "https://api.deepseek.com/chat/completions"
MODEL = "deepseek-flash"
RETRY_WAITS = [0, 5, 15, 30]


class ParseError(ValueError):
    """模型返回的不是可解析的 JSON。raw 保留原始响应，方便复现。"""
    def __init__(self, message: str, raw: str):
        super().__init__(message)
        self.raw = raw


def parse_first_json(text: str) -> dict:
    """只取第一个完整的 JSON 对象。模型偶尔在 JSON 后面多输出一段（2026-11-17 试点 CLDS 的 “Extra data” 错误）。"""
    text = (text or "").strip()
    start = text.find("{")
    if start < 0:
        raise ValueError("no JSON object in the model output")
    # strict=False：字符串里出现未转义的换行、制表符等控制字符时照常解析（2026-11-17 独立检验 nbs_aircon 的
    # “Invalid control character” 错误）。只放宽控制字符，不做全局替换，引文内容原样保留
    obj, _ = json.JSONDecoder(strict=False).raw_decode(text[start:])
    return obj


def generate_json(system: str, content: str, schema: dict | None = None, session=None, sleep=time.sleep,
                  full_schema: bool = False) -> tuple[dict, str]:
    """返回 (JSON 结果, 模型名)。schema 只用来在提示中列出字段（DeepSeek 的 JSON 模式不强制结构，调用方自己检查）。"""
    import requests
    key = os.environ.get("DEEPSEEK_API_KEY")
    if not key:
        raise SystemExit("没有找到 DEEPSEEK_API_KEY。")
    fields = ""
    if schema and full_schema:
        # 论文提取、检索这类嵌套结构：DeepSeek 的 JSON 模式不强制结构，把完整 schema 写进提示，由调用方的核对兜底
        fields = ("\nAnswer with ONE JSON object that follows this JSON Schema exactly (same field names, nesting and types; "
                  "use null where a value is unknown):\n" + json.dumps(schema, ensure_ascii=False))
    elif schema:
        fields = "\nJSON fields: " + ", ".join(schema.get("properties", {}))
    payload = {"model": MODEL, "temperature": 0, "response_format": {"type": "json_object"},
               "thinking": {"type": "disabled"},
               "messages": [{"role": "system", "content": system + fields},
                            {"role": "user", "content": content}]}
    import time_budget
    session = session or requests.Session()
    last, parse_failed = None, None
    for wait in RETRY_WAITS:
        if wait and not time_budget.can_wait(wait):   # 总时限内来不及再试：不等、不再发请求
            raise time_budget.Expired(f"time limit reached before retrying DeepSeek ({last})", "DeepSeek retry")
        if wait:
            print(f"  retrying in {wait}s (DeepSeek)...", flush=True)
            sleep(wait)
        try:
            r = session.post(URL, json=payload, timeout=time_budget.cap(120),
                             headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
        except time_budget.Expired:
            raise
        except Exception as e:   # 网络超时等
            last = f"{type(e).__name__}"
            continue
        if r.status_code == 200:
            text = r.json()["choices"][0]["message"]["content"]
            try:
                return parse_first_json(text), MODEL
            except ValueError as e:
                if parse_failed is not None:   # 第二次还解析不了：不再重试
                    raise ParseError(f"model output is not valid JSON twice: {e}", text)
                parse_failed = text
                print("  model output was not valid JSON; asking once more...", flush=True)
                continue
        last = f"HTTP {r.status_code}: {r.text[:200]}"
        if r.status_code not in (408, 429) and r.status_code < 500:
            break
    raise RuntimeError(f"DeepSeek call failed: {last}")
