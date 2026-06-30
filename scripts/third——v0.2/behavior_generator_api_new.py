from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

# ==================== 1. 复用你项目里的 .env 读取逻辑 ====================
DEFAULT_ENV_FILE = Path(".env")

def load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key and key not in os.environ:
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
                value = value[1:-1]
            os.environ[key] = value

def get_api_config():
    load_env_file(DEFAULT_ENV_FILE)
    url = os.environ.get("PURE_JADE_API_URL", "https://api.openai.com/v1/chat/completions")
    api_key = os.environ.get("PURE_JADE_API_KEY", "")
    model = os.environ.get("PURE_JADE_API_MODEL", "gpt-4")
    if not api_key or not model:
        raise ValueError("请在 .env 文件中配置 PURE_JADE_API_KEY 和 PURE_JADE_API_MODEL")
    return {
        "url": url.rstrip("/") + "/chat/completions" if not url.endswith("/chat/completions") else url,
        "api_key": api_key,
        "model": model,
        "temperature": 0.7,
        "timeout": 60,
        "max_retries": 1,
    }

def build_behavior_system_prompt() -> str:
    return """你是 PURE-JADE 项目的**行为响应生成模块**（第三部分）。

    【核心职责】
    - 你只负责“怎么说”（把策略卡翻译成自然语言回复）
    - 你绝对不负责“用什么策略”（策略卡里写什么你就用什么）
    - 你绝对不负责“判断用户状态”（不要猜测用户情绪、需求、风险）

    【输入来源】
    - 你只能使用：原始对话历史 + 第二部分传来的策略决策卡
    - 你不应知道、也不应使用第一部分的用户状态卡

【铁律】
1. 你只负责“怎么写”，不负责“用什么策略”。策略卡里写什么策略，你就必须用什么策略。
2. 回复文本必须基于「用户原话」和「历史上下文」，绝对禁止编造用户没提过的事实。
3. 输出必须是一个合法的 JSON 对象，不要加 Markdown、不要加解释文字。
4. strategy_realization 必须把策略卡里的策略，和你回复文本中的具体句子（text_span）一一对应。
5. 如果使用了之前轮次的信息，必须在 context_used 里明确写出来（v0.2.1 强制要求）。
6. 注意安全：如果策略卡里有 prohibited_actions，你的回复绝对不能触碰这些禁令。
7.不要编造用户状态。

【输出 JSON 字段】（严格按照这个结构）：
{
  "text_response": "发给用户的完整回复文本",
  "tone_style": "warm_and_calm | exploratory | validating | directive",
  "strategy_realization": [
    {"strategy": "策略名", "text_span": "对应回复中的原句"}
  ],
  "follow_up_question_count": 数字,
  "uses_previous_context": true/false,
  "context_used": ["具体引用了哪轮历史"],
  "safety_message_used": false
}
"""

def build_behavior_user_prompt(dialogue_history: list[dict], strategy_card: dict) -> str:
    intention = strategy_card.get("support_intention", "comfort")
    primary = strategy_card.get("primary_strategy", "Reflection of feelings")
    secondary = strategy_card.get("secondary_strategy")
    goal = strategy_card.get("response_goal", "无具体目标")
    constraints = strategy_card.get("constraints", [])
    prohibited = strategy_card.get("prohibited_actions", [])
    return f"""请根据以下数据，生成行为响应卡。

【近期对话历史】
{json.dumps(dialogue_history, ensure_ascii=False, indent=2)}

【策略决策卡指令】
- 支持意图：{intention}
- 主策略：{primary}
- 副策略：{secondary if secondary else '无'}
- 回复目标：{goal}
- 约束条件：{', '.join(constraints) if constraints else '无'}
- 禁止行为：{', '.join(prohibited) if prohibited else '无'}

【生成要求】
1. 回复文本要自然、有温度、口语化。
2. 必须至少体现「主策略」。
3. 如果使用了历史对话中的信息，必须在 context_used 里写明。
4. 最多提出 1 个问题。
5. 输出纯 JSON，不要任何额外文字。
"""

def call_behavior_api(dialogue_history: list[dict], strategy_card: dict) -> dict[str, Any]:

    if strategy_card.get("safety_override") is True:
       return {
            "conversation_id": strategy_card["conversation_id"],
            "turn_id": strategy_card["turn_id"],
            "schema_version": "0.1",
            "text_response": "听起来你现在的情况可能很紧急，我建议你先联系身边信任的人或拨打当地心理援助热线，先确保自己的安全。",
            "tone_style": "safety_directive",
            "strategy_realization": [
                {"strategy": "Safety Guidance", "text_span": "建议你先联系身边信任的人或拨打当地心理援助热线"}],
            "follow_up_question_count": 0,
            "facial_expression": None,
            "action": None,
            "safety_message_used": True
        }
    config = get_api_config()
    messages = [
        {"role": "system", "content": build_behavior_system_prompt()},
        {"role": "user", "content": build_behavior_user_prompt(dialogue_history, strategy_card)},
    ]
    payload = {
        "model": config["model"],
        "messages": messages,
        "temperature": config["temperature"],
        "response_format": {"type": "json_object"},
    }
    request = urllib.request.Request(
        config["url"],
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {config['api_key']}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=config["timeout"]) as response:
            body = response.read().decode("utf-8")
            result = json.loads(body)
            content = result["choices"][0]["message"]["content"]
            behavior_card = json.loads(content)
            if "tone_style" not in behavior_card:
                behavior_card["tone_style"] = "warm_and_calm"
            if "follow_up_question_count" not in behavior_card:
                behavior_card["follow_up_question_count"] = behavior_card.get("text_response", "").count("？")
            if "uses_previous_context" not in behavior_card:
                behavior_card["uses_previous_context"] = bool(behavior_card.get("context_used"))
            if "safety_message_used" not in behavior_card:
                behavior_card["safety_message_used"] = False
            if "strategy_realization" not in behavior_card:
                behavior_card["strategy_realization"] = [
                    {"strategy": strategy_card.get("primary_strategy"), "text_span": behavior_card.get("text_response", "")[:20]}
                ]
            behavior_card["conversation_id"] = strategy_card.get("conversation_id", "unknown")
            behavior_card["turn_id"] = strategy_card.get("turn_id", 1)
            behavior_card["schema_version"] = "0.1"
            behavior_card["facial_expression"] = None
            behavior_card["action"] = None
            return behavior_card
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"API HTTP {e.code}: {error_body}") from e
    except Exception as e:
        raise RuntimeError(f"API 调用失败: {e}") from e

if __name__ == "__main__":
    mock_strategy = {
        "conversation_id": "case_learning_frustration_001",
        "turn_id": 1,
        "support_intention": "comfort",
        "primary_strategy": "Reflection of feelings",
        "secondary_strategy": "Affirmation and Reassurance",
        "response_goal": "先承接用户努力后看不到结果的无力感，并肯定其持续投入的价值",
        "constraints": ["先共情，不急于给学习建议", "最多提出一个开放问题"],
        "prohibited_actions": ["不要说教", "不要承诺成绩一定会提升"]
    }
    mock_state = {
        "emotion": ["疲惫", "沮丧", "自我怀疑"],
        "emotion_intensity": 2,
        "need": ["被理解", "被肯定"]
    }
    mock_history = [
        {"turn_id": 1, "speaker": "user", "content": "我最近真的很累，明明每天都在复习，但成绩还是没有起色。"},
    ]
    print("🚀 正在调用 API 生成行为响应卡...")
    try:
        result = call_behavior_api(dialogue_history=mock_history, strategy_card=mock_strategy)
        print("\n✅ 生成成功！行为响应卡如下：")
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except Exception as e:
        print(f"\n❌ 出错了：{e}")
        print("请检查你的 .env 文件是否配置了 PURE_JADE_API_KEY 和 PURE_JADE_API_MODEL")