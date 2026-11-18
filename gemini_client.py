"""
调用 Gemini 并取回 JSON 的唯一入口：step2（论文提取）和 search_papers（检索词、相关度）共用。

只做一件事：把请求发出去，处理免费层常见的暂时性错误，返回 (JSON 结果, 实际使用的模型)。
提示词、输出格式（schema）、发什么内容，都由调用方决定，这里不管。

免费层高峰时常返回 503（模型繁忙）或 429（超过频率限制），所以：
    每个模型最多试 3 次，间隔 0 / 15 / 45 秒；还不行就换备用模型。
    404（模型名不存在）直接换下一个模型；其他错误（如 key 无效）直接报出来。
"""

import json
import os
import time

GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.8-flash")
# 主模型繁忙时依次尝试的备用模型（更轻量，通常更容易排上）
GEMINI_FALLBACK_MODELS = ["gemini-3.1-flash-lite"]
RETRY_WAITS = [0, 15, 45]          # 每个模型的第 1、2、3 次尝试之前等待的秒数
RETRY_CODES = (429, 500, 503)      # 暂时性错误：等一会儿再试


def generate_json(system: str, content: str, schema: dict, temperature: float = 0,
                  client=None, sleep=time.sleep) -> tuple[dict, str]:
    """返回 (JSON 结果, 实际使用的模型名)。
    client 和 sleep 只在测试时替换（用假的客户端、不真的等待），平时不用传。
    环境变量 LLM_PROVIDER=deepseek 时改用 DeepSeek（2026-11-17：Gemini 免费层太慢）。返回的模型名会写进结果，换了模型可以追溯。"""
    if os.environ.get("LLM_PROVIDER", "gemini").lower() == "deepseek" and client is None:
        import deepseek_client
        return deepseek_client.generate_json(system, content, schema=schema, full_schema=True)
    from google import genai
    from google.genai import errors, types
    client = client or genai.Client()   # 自动读取环境变量 GEMINI_API_KEY
    config = types.GenerateContentConfig(
        system_instruction=system,
        response_mime_type="application/json",
        response_json_schema=schema,
        temperature=temperature,   # 默认 0：尽量让同样的输入每次结果一致，方便测试
    )
    models = [GEMINI_MODEL] + [m for m in GEMINI_FALLBACK_MODELS if m != GEMINI_MODEL]
    last_error = None
    for model in models:
        for attempt, wait in enumerate(RETRY_WAITS, start=1):
            if wait:
                print(f"  retrying in {wait}s ({model}, attempt {attempt})...")
                sleep(wait)
            try:
                response = client.models.generate_content(model=model, contents=content, config=config)
            except errors.APIError as e:
                last_error = e
                code = getattr(e, "code", None)
                if code in RETRY_CODES:
                    print(f"  Gemini temporarily unavailable ({code})")
                    continue
                if code == 404:
                    print(f"  model {model} not found, switching to the next model")
                    break
                raise
            try:
                return json.loads(response.text), model
            except (json.JSONDecodeError, TypeError):
                raise RuntimeError(f"Gemini returned invalid JSON: {str(response.text)[:300]}")
        print(f"  {model} failed repeatedly, trying the next model")
    raise SystemExit(f"All Gemini models are unavailable right now; please try again in a few minutes. "
                     f"Last error: {last_error}")
