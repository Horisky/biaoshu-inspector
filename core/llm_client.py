"""
LLM 客户端 —— OpenAI 兼容接口，默认 DeepSeek（支持中转站 base_url）。
（移植自主平台 backend，改为依赖本地 core.config。）
"""
import json
import re
from openai import AsyncOpenAI
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from loguru import logger
from core.config import get_settings

settings = get_settings()


def _coerce_json(content: str) -> dict:
    """容错解析 LLM 返回的 JSON：
    - 兼容 ```json ... ``` 代码块包裹、前后多余文字；
    - 截取最外层 {...}；
    - 处理输出被截断（缺尾）的情况：从尾部逐步回退到上一个 '}' 再尝试。
    """
    if not content:
        raise json.JSONDecodeError("空响应", "", 0)
    s = content.strip()
    m = re.search(r"```(?:json)?\s*(.*?)\s*```", s, re.S)
    if m:
        s = m.group(1).strip()
    i = s.find("{")
    if i > 0:
        s = s[i:]
    # 先直接尝试
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        pass
    # 截断兜底：从最后一个 '}' 往前逐个尝试闭合
    for j in range(len(s) - 1, -1, -1):
        if s[j] == "}":
            try:
                return json.loads(s[: j + 1])
            except json.JSONDecodeError:
                continue
    raise json.JSONDecodeError("无法解析为 JSON", s[:200], 0)


class LLMClient:
    def __init__(self):
        self._client = AsyncOpenAI(
            api_key=settings.deepseek_api_key,
            base_url=settings.deepseek_base_url,
        )
        self.model = settings.deepseek_model

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type(Exception),
    )
    async def extract_json(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.1,
    ) -> dict:
        """结构化抽取：使用 JSON mode，返回 dict。"""
        resp = await self._client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            response_format={"type": "json_object"},
            temperature=temperature,
            max_tokens=16000,
        )
        content = resp.choices[0].message.content
        try:
            return _coerce_json(content)
        except json.JSONDecodeError as e:
            logger.error(f"LLM JSON 解析失败: {e}\n原始输出(尾部): ...{(content or '')[-500:]}")
            raise


_llm_client: LLMClient | None = None


def get_llm_client() -> LLMClient:
    global _llm_client
    if _llm_client is None:
        _llm_client = LLMClient()
    return _llm_client
