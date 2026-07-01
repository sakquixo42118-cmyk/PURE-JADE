"""Schema-aligned behavior response generator for PURE-JADE.

This is a revised third-part prototype that keeps the original
behavior_generator_api.py untouched.

Module boundary:
    dialogue / recent_dialogue_window + strategy_decision_card
    -> behavior_response_card

It intentionally does not read the first-part user_state_card. In v0.2.1
record mode, the script reads the target turn from conversation_record but
only extracts dialogue_log and strategy_decision_card for behavior generation.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path
from typing import Any


SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import pure_jade_api as api_client  # noqa: E402


DEFAULT_RECORD = Path("examples/conversation-record-v0.2.1.json")
DEFAULT_CASES = Path("examples/test-cases-v0.1.json")
DEFAULT_ENV_FILE = Path(".env")

ALLOWED_ESCONV_STRATEGIES = {
    "Question",
    "Restatement or Paraphrasing",
    "Reflection of feelings",
    "Self-disclosure",
    "Affirmation and Reassurance",
    "Providing Suggestions",
    "Information",
    "Others",
}
ALLOWED_REALIZED_STRATEGIES = ALLOWED_ESCONV_STRATEGIES | {"Safety Guidance"}
UNSAFE_SAFETY_FOLLOWUP_PATTERNS = (
    "具体怎么伤害",
    "怎么伤害自己",
    "伤害自己的方法",
    "具体计划",
    "计划伤害自己",
)
SAFETY_FALLBACK_RESPONSE = (
    "这件事需要先认真保护你的安全。请先远离可能伤到你的物品或冲突现场，"
    "尽量待在容易被看见、能联系到人的地方；如果有即时危险，请联系当地紧急服务、学校值班老师或可信任成年人。"
)
ALLOWED_TONE_STYLES = {
    "warm_and_calm",
    "validating",
    "exploratory",
    "practical",
    "safety_directive",
}
ALLOWED_FACIAL_EXPRESSIONS = {"neutral", "soft_smile", "concerned", None}
ALLOWED_ACTIONS = {"none", "pause", "offer_resource", None}
PRACTICAL_RESPONSE_CUES = (
    "先",
    "马上",
    "现在",
    "联系",
    "发消息",
    "打电话",
    "邮件",
    "老师",
    "任课",
    "教务",
    "辅导员",
    "补考",
    "缓考",
    "缺考",
    "流程",
    "教务系统",
    "证明",
    "记录",
    "截图",
    "查看",
    "确认",
    "下一步",
    "办法",
)
MINIMUM_INFORMATION_INTENTIONS = {"comfort", "affirm", "normalize", "advise", "inform"}
MINIMUM_INFORMATION_LENGTH = 160

REQUIRED_STRATEGY_FIELDS = {
    "conversation_id",
    "turn_id",
    "schema_version",
    "support_intention",
    "primary_strategy",
    "secondary_strategy",
    "response_timing",
    "response_intensity",
    "response_goal",
    "reason",
    "esconv_example_ids",
    "constraints",
    "prohibited_actions",
    "safety_override",
}
REQUIRED_STRATEGY_V02_FIELDS = REQUIRED_STRATEGY_FIELDS | {
    "state_basis_turn_id",
    "state_change_summary",
}

REQUIRED_BEHAVIOR_V01 = {
    "conversation_id",
    "turn_id",
    "schema_version",
    "text_response",
    "tone_style",
    "strategy_realization",
    "follow_up_question_count",
    "facial_expression",
    "action",
    "safety_message_used",
}
REQUIRED_BEHAVIOR_V02 = REQUIRED_BEHAVIOR_V01 | {
    "uses_previous_context",
    "context_used",
}

FIRST_PART_ONLY_FIELDS = {
    "user_state_card",
    "latest_user_state_card",
    "emotion",
    "emotion_intensity",
    "need",
    "support_stage",
    "risk_level",
    "evidence",
    "unknowns",
    "risk_memory",
}


class BehaviorCheck:
    def __init__(self, conversation_id: str, turn_id: int) -> None:
        self.conversation_id = conversation_id
        self.turn_id = turn_id
        self.errors: list[str] = []
        self.warnings: list[str] = []

    @property
    def status(self) -> str:
        return "pass" if not self.errors else "fail"

    def error(self, message: str) -> None:
        self.errors.append(message)

    def warn(self, message: str) -> None:
        self.warnings.append(message)

    def to_dict(self) -> dict[str, Any]:
        return {
            "conversation_id": self.conversation_id,
            "turn_id": self.turn_id,
            "status": self.status,
            "errors": self.errors,
            "warnings": self.warnings,
        }


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def compact_json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def count_questions(text: str) -> int:
    return text.count("?") + text.count("？")


def compact_text_length(text: str) -> int:
    return len(re.sub(r"\s+", "", text))


def minimum_information_issue(card: dict[str, Any], behavior_request: dict[str, Any]) -> str | None:
    strategy_card = behavior_request.get("strategy_decision_card")
    if not isinstance(strategy_card, dict):
        return None
    if strategy_card.get("safety_override") is True:
        return None
    if strategy_card.get("support_intention") not in MINIMUM_INFORMATION_INTENTIONS:
        return None
    response = card.get("text_response")
    if not isinstance(response, str) or not response.strip():
        return None
    length = compact_text_length(response)
    if length >= MINIMUM_INFORMATION_LENGTH:
        return None
    return (
        "minimum_information_warning: non-safety support response is too short "
        f"({length} compact characters; expected at least {MINIMUM_INFORMATION_LENGTH})"
    )


def minimum_information_retry_prompt(issue: str) -> str:
    return f"""你的 behavior_response_card 结构合法，但 text_response 过短，缺少情绪展开或轻度重构。

问题：
{issue}

请在不增加新事实、不诊断、不说教的前提下，将 text_response 扩展为 180-320 字。
必须包含：
1. 基于用户原话的具体情绪承接；
2. 对用户自责/无力/后悔/关系压力的轻度重构；
3. 一个低负担微行动或温和探索入口；
4. 一句降低自责或稳定预期的收束。

保持安全、克制、少推测，但不要压缩成模板化短句。展开只能来自 recent_dialogue_window/dialogue 中已有事实。

请重新输出完整、合法的 behavior_response_card JSON 对象，并同步更新 strategy_realization.text_span，确保每个 text_span 都真实出现在新的 text_response 中。不要输出 Markdown、解释文字或代码块。"""


def split_first_sentence(text: str) -> tuple[str, str]:
    for index, char in enumerate(text):
        if char in {"。", "！", "？", "!", "?"}:
            return text[: index + 1].strip(), text[index + 1 :].strip()
    return text.strip(), ""


def latest_user_message(behavior_request: dict[str, Any]) -> str:
    turn_id = behavior_request.get("turn_id")
    messages = behavior_request.get("recent_dialogue_window")
    if not isinstance(messages, list):
        return ""
    for item in reversed(messages):
        if (
            isinstance(item, dict)
            and item.get("speaker") == "user"
            and (turn_id is None or item.get("turn_id") == turn_id)
            and isinstance(item.get("content"), str)
        ):
            return item["content"].strip()
    for item in reversed(messages):
        if isinstance(item, dict) and item.get("speaker") == "user" and isinstance(item.get("content"), str):
            return item["content"].strip()
    return ""


def compact_acknowledgement(user_message: str, strategy_card: dict[str, Any]) -> str:
    support_intention = strategy_card.get("support_intention")
    if support_intention in {"advise", "inform"}:
        return "可以，我们先把它缩小到眼前能做的一步。"
    if any(keyword in user_message for keyword in ("朋友", "社交", "孤独", "封闭", "一个人", "圈子")):
        return "这种越来越退回到自己一个人的状态，确实很消耗人。"
    if any(keyword in user_message for keyword in ("考试", "成绩", "高数", "复习", "刷题", "学习")):
        return "一直用力却看不到变化，真的会把人拖得很累。"
    if any(keyword in user_message for keyword in ("妈妈", "爸爸", "父母", "家里", "吵架")):
        return "想说清楚却总变成争执，确实会让人很委屈。"
    if any(keyword in user_message for keyword in ("不想醒", "伤害自己", "自杀", "活着")):
        return "这件事需要先认真照顾你的安全。"
    return "这段状态确实不轻松。"


def simplify_followup_tail(tail: str, user_message: str) -> str:
    if "社交圈子逐渐缩小" in tail or ("社交" in user_message and "进入大学" in tail and "最近" in tail):
        return "这是进入大学后慢慢发生的，还是最近突然变明显的？"
    if "没有目标" in tail and "持续多久" in tail:
        return "这种没劲的状态大概持续多久了？"
    if "错题" in tail and "哪类" in tail:
        return "最卡住你的题型是哪一类？"
    return tail


def repeated_opening_score(sentence: str, user_message: str) -> int:
    score = 0
    if len(sentence) >= 45:
        score += 1
    if sentence.count("，") + sentence.count("、") >= 3:
        score += 1
    overlap_keywords = (
        "现实",
        "无趣",
        "朋友",
        "社交",
        "封闭",
        "进取心",
        "网上",
        "快感",
        "老东西",
        "成绩",
        "考试",
        "复习",
        "刷题",
        "妈妈",
        "爸爸",
        "吵架",
        "委屈",
        "孤独",
        "圈子",
    )
    keyword_hits = sum(1 for keyword in overlap_keywords if keyword in sentence and keyword in user_message)
    score += min(keyword_hits, 3)
    for chunk in re.split(r"[，。！？、；;,.!?\\s]+", user_message):
        chunk = chunk.strip()
        if len(chunk) >= 4 and chunk in sentence:
            score += 1
    if any(marker in sentence for marker in ("你说", "你提到", "听起来", "我听到", "好像", "这种", "真的很")):
        score += 1
    return score


def compress_repetitive_opening(text: str, behavior_request: dict[str, Any]) -> tuple[str, bool]:
    # v0.2.6 keeps natural API wording; local code no longer rewrites empathy openings into canned phrases.
    return text, False
    response = text.strip()
    if not response:
        return text, False
    first, rest = split_first_sentence(response)
    if not first or not rest:
        return text, False
    strategy_card = behavior_request.get("strategy_decision_card")
    strategy_card = strategy_card if isinstance(strategy_card, dict) else {}
    if strategy_card.get("safety_override") is True:
        return text, False

    user_message = latest_user_message(behavior_request)
    if not user_message:
        return text, False
    if repeated_opening_score(first, user_message) < 3:
        return text, False

    ack = compact_acknowledgement(user_message, strategy_card)
    remaining_first, remaining_rest = split_first_sentence(rest)
    # Drop a second generic empathy sentence after the long restatement.
    generic_empathy = any(
        phrase in remaining_first
        for phrase in ("真的很不好受", "真的会很难受", "确实很难", "确实很累", "很不容易", "压在心上")
    )
    tail = remaining_rest if generic_empathy and remaining_rest else rest
    tail = simplify_followup_tail(tail, user_message)
    compacted = (ack + tail).strip()
    return compacted, compacted != response


def limit_question_marks(text: str, max_questions: int = 1) -> tuple[str, bool]:
    question_count = 0
    changed = False
    chars: list[str] = []
    for char in text:
        if char in {"?", "？"}:
            question_count += 1
            if question_count > max_questions:
                chars.append("。")
                changed = True
            else:
                chars.append(char)
        else:
            chars.append(char)
    return "".join(chars), changed


def default_report_path(mode: str, source_kind: str, turn_id: int | None, case_id: str | None) -> Path:
    if mode == "api":
        root = Path("reports/final/api")
    else:
        root = Path("reports/final/local")

    if source_kind == "record":
        suffix = f"turn{turn_id or 1}"
    else:
        suffix = case_id or "case"
    return root / f"behavior_generator_schema_aligned_{mode}_{suffix}_report.json"


def find_turn_record(record: dict[str, Any], turn_id: int) -> dict[str, Any] | None:
    for item in as_list(record.get("turn_records")):
        if isinstance(item, dict) and item.get("turn_id") == turn_id:
            return item
    return None


def get_target_turn_id(record: dict[str, Any], requested_turn_id: int | None) -> int:
    if requested_turn_id is not None:
        return requested_turn_id
    current_turn_id = record.get("current_turn_id")
    return current_turn_id if isinstance(current_turn_id, int) else 1


def recent_dialogue_window(record: dict[str, Any], turn_id: int, max_turns: int) -> list[dict[str, Any]]:
    dialogue_log = [item for item in as_list(record.get("dialogue_log")) if isinstance(item, dict)]
    min_turn = max(1, turn_id - max_turns + 1)
    window = [
        {
            "turn_id": item.get("turn_id"),
            "speaker": item.get("speaker"),
            "content": item.get("content"),
        }
        for item in dialogue_log
        if (
            isinstance(item.get("turn_id"), int)
            and min_turn <= item.get("turn_id") <= turn_id
            and (
                item.get("turn_id") < turn_id
                or item.get("speaker") == "user"
            )
        )
    ]
    return [item for item in window if item.get("speaker") and item.get("content")]


def find_case(case_doc: dict[str, Any], case_id: str | None) -> dict[str, Any]:
    cases = [item for item in as_list(case_doc.get("cases")) if isinstance(item, dict)]
    if not cases:
        raise ValueError("cases document must contain a non-empty cases list")
    if case_id is None:
        return cases[0]
    for case in cases:
        if case.get("case_id") == case_id:
            return case
    raise ValueError(f"case_id was not found: {case_id}")


def strategy_card_version(strategy_card: dict[str, Any]) -> str:
    version = strategy_card.get("schema_version")
    if version == "0.2":
        return "0.2"
    return "0.1"


def build_input_from_record(
    record_path: Path,
    turn_id: int | None,
    max_recent_turns: int,
) -> tuple[dict[str, Any], dict[str, Any] | None, dict[str, Any]]:
    record = load_json(record_path)
    if not isinstance(record, dict):
        raise ValueError("conversation record must be a JSON object")

    target_turn_id = get_target_turn_id(record, turn_id)
    turn_record = find_turn_record(record, target_turn_id)
    if turn_record is None:
        raise ValueError(f"turn_records does not contain turn_id={target_turn_id}")

    strategy_card = turn_record.get("strategy_decision_card")
    if not isinstance(strategy_card, dict) or not strategy_card:
        raise ValueError("target turn must contain a non-empty strategy_decision_card")

    behavior_request = {
        "conversation_id": record.get("conversation_id"),
        "turn_id": target_turn_id,
        "request_schema_version": "0.2.1",
        "target_behavior_schema_version": strategy_card_version(strategy_card),
        "recent_dialogue_window": recent_dialogue_window(record, target_turn_id, max_recent_turns),
        "strategy_decision_card": strategy_card,
        "generation_policy": {
            "direct_upstream_only": True,
            "do_not_read_user_state_card": True,
            "max_follow_up_questions": 1,
        },
    }
    expected = turn_record.get("behavior_response_card")
    expected_behavior = expected if isinstance(expected, dict) else None
    source_meta = {
        "source_kind": "record",
        "record_path": str(record_path),
        "turn_id": target_turn_id,
        "ignored_first_part_card_present": isinstance(turn_record.get("user_state_card"), dict),
    }
    return behavior_request, expected_behavior, source_meta


def build_input_from_case(
    cases_path: Path,
    case_id: str | None,
) -> tuple[dict[str, Any], dict[str, Any] | None, dict[str, Any]]:
    case_doc = load_json(cases_path)
    if not isinstance(case_doc, dict):
        raise ValueError("cases file must be a JSON object")
    case = find_case(case_doc, case_id)

    strategy_card = case.get("expected_strategy_decision_card")
    if not isinstance(strategy_card, dict) or not strategy_card:
        raise ValueError("case must contain expected_strategy_decision_card")

    behavior_request = {
        "conversation_id": case.get("case_id"),
        "turn_id": strategy_card.get("turn_id", 1),
        "request_schema_version": "0.1",
        "target_behavior_schema_version": "0.1",
        "dialogue": case.get("dialogue"),
        "strategy_decision_card": strategy_card,
        "generation_policy": {
            "direct_upstream_only": True,
            "do_not_read_user_state_card": True,
            "max_follow_up_questions": 1,
        },
    }
    expected = case.get("expected_behavior_response_card")
    expected_behavior = expected if isinstance(expected, dict) else None
    source_meta = {
        "source_kind": "case",
        "cases_path": str(cases_path),
        "case_id": case.get("case_id"),
        "ignored_first_part_card_present": isinstance(case.get("expected_user_state_card"), dict),
    }
    return behavior_request, expected_behavior, source_meta


def behavior_system_prompt() -> str:
    return """你是 PURE-JADE 项目的第三部分：行为回应生成模块。

你的模块边界非常严格：
1. 你只根据原始/近期对话和第二部分输出的 strategy_decision_card 生成 behavior_response_card。
2. 你不读取、不要求、也不重新推断第一部分 user_state_card。
3. 你不重新选择策略，不覆盖第二部分的 support_intention、primary_strategy、secondary_strategy。
4. strategy_decision_card 中的 response_goal、constraints、prohibited_actions 是你的生成约束。
5. 输出必须是一个合法 JSON 对象，不要输出 Markdown、解释文字或代码块。

Schema v0.1 行为回应卡必须包含：
conversation_id, turn_id, schema_version, text_response, tone_style,
strategy_realization, follow_up_question_count, facial_expression, action,
safety_message_used。

Schema v0.2 行为回应卡在 v0.1 基础上必须额外包含：
uses_previous_context, context_used。

生成规则：
1. conversation_id、turn_id、schema_version 必须与目标行为卡版本和策略卡一致。
2. text_response 只写要发给用户的话，最长 520 字。普通低风险场景通常写 3-6 句、约 180-320 字；不要为了简短而只输出一句。
3. strategy_realization 必须至少落实 primary_strategy；如果 secondary_strategy 不为 null，也应落实 secondary_strategy。
4. 每个 strategy_realization.text_span 必须是 text_response 中真实出现的片段。
5. follow_up_question_count 只能是 0 或 1，并且回复中最多只出现一个问号。
6. tone_style 只能选择 warm_and_calm, validating, exploratory, practical, safety_directive。
7. facial_expression 只能是 neutral, soft_smile, concerned 或 null。
8. action 只能是 none, pause, offer_resource 或 null。
9. 如果 safety_override 为 true，必须使用安全优先回应：strategy_realization 使用 Safety Guidance，safety_message_used 为 true，tone_style 为 safety_directive，避免诊断、责备、承诺和危险方法细节；允许最多一个必要的安全确认问题，例如确认用户此刻是否安全、是否能远离冲突现场。
10. 如果目标版本是 v0.2，uses_previous_context 和 context_used 只能描述实际用到的历史对话信息，不要引用 user_state_card。

自然表达规则：
1. 不要用模板化开头。避免反复使用“我听到你说”“听起来”“我能感受到”“我理解你现在”“你提到”“确实很难受”“确实让人”“这确实”等句式。
2. Restatement or Paraphrasing 和 Reflection of feelings 不是逐字复读用户信息；用自然语言承接当前感受，可以是一句完整的话，不要机械压缩到没有温度。
3. 多轮对话中不要重复上一轮已经承接过的背景。优先回应当前轮的新信息、新请求或情绪变化。
4. 如果用户明确要建议、步骤、话术或行动方案，先给可执行内容，也要保留一句自然的情绪承接或收束，不要只剩任务指令。
5. 回复要像真实对话，不要像评分表说明。可以使用“这一步可以先缩小一点”“先不用急着证明自己”“今晚可以只做一件事”这类自然开头。
6. text_response 中最多保留一个核心问题；只有这个问题能推进帮助或确认安全时才问。
7. 如果 strategy_decision_card 的 response_timing 是 offer_next_step，或 primary/secondary_strategy 包含 Providing Suggestions / Information，text_response 必须包含具体、低负担、现实可执行的下一步；可以给 1-2 个小动作，但不能信息过载，也不能只做情绪认可或正常化。
8. 如果策略卡约束提到考试、补考、缓考、教务、老师或辅导员，回复要给出一个不承诺结果的现实联系/确认动作，而不是只说“这种情绪正常”。
9. 如果 support_intention 是 comfort / affirm / normalize，回复不能只停在肯定和正常化；在不违背策略卡的前提下，补一个很小的稳定动作、温和探索入口或自我评价缓冲。
10. 如果用户在问“为什么/问题在哪/我不理解”，不要给一串未经证实的原因推测。更好的写法是：先接住困惑和不甘，再给一个帮助具体化的入口，或建议去获得具体反馈。
11. 当策略卡要求情绪承接时，不要只输出情绪标签；需要把用户处境中的心理张力具体化。展开必须来自 recent_dialogue_window 或 dialogue 中已有事实。
12. 普通低风险、非安全场景推荐结构：
    - 用 1-2 句具体化用户处境中的情绪张力。
    - 用 1-2 句做轻度重构，帮助用户从自责、羞耻、嫉妒或无力感中稍微退一步。
    - 给 1 个低负担微行动或温和探索入口。
    - 用一句降低自责或稳定预期的话收束。
13. 对现实压力但低风险的场景，推荐结构是：两句接住情绪和意义 + 一到两句轻度重构 + 一个微行动或温和探索入口 + 一句降低自责或稳定预期的话。
14. 不要把“安全克制”理解为短句模板。只要内容来自用户已提供的信息，就应该允许自然展开。
15. 允许 evidence-grounded expansion：可以基于用户原话展开其处境中的心理负担、关系压力、自责机制和轻度重构；禁止添加未经证实的新事实、心理诊断、动机判断或责任归因。
16. “微行动”不是沉重建议，也不是直接解决人生问题；它可以是写一句最刺痛的比较、暂停自我审判、少看一次触发源、用一句话向老师/朋友请教、或把一个抽象问题落到具体场景。
"""


def behavior_user_prompt(behavior_request: dict[str, Any]) -> str:
    target_version = behavior_request.get("target_behavior_schema_version", "0.1")
    extra_fields = ""
    if target_version == "0.2":
        extra_fields = "\n- uses_previous_context\n- context_used"

    return f"""请根据以下 behavior_response_request 生成行为回应卡。

[behavior_response_request]
{compact_json(behavior_request)}

[输出字段]
- conversation_id
- turn_id
- schema_version
- text_response
- tone_style
- strategy_realization
- follow_up_question_count
- facial_expression
- action
- safety_message_used{extra_fields}

[重要边界]
不要使用第一部分用户状态卡字段。即使请求来源是 conversation_record，也只能使用 recent_dialogue_window/dialogue 和 strategy_decision_card。

[表达风格]
- 避免模板化开头，不要每轮都从“我听到你说/听起来/我能感受到”开始。
- 可以自然承接情绪，但不要机械重复用户原话。
- 如果本轮用户在要办法、话术或下一步，直接进入具体帮助。
- 除安全覆盖外，回复不要过短；通常保持 3-6 句，让它既有温度也有行动感。
- 不要把“克制”写成压缩短句；克制是不编造，不是不展开。
- 当策略卡要求情绪承接时，用 1-2 句基于用户已经说出的事实具体化心理张力，不要只给“很难受/很焦虑/很正常”的标签。
- 展开只能来自 recent_dialogue_window/dialogue 中已有事实；可以展开用户的自责、后悔、无力、关系压力或比较感，但不能添加新人物、新动机、新诊断或未经证实的责任归因。
- 对 comfort / affirm 轮，至少给出一个轻量推进：很小的稳定动作、温和问题、或把自我攻击暂时放下的具体说法；不要只说“你不差/这很正常”。
- 对 action 轮，先回应用户最强的“不理解、委屈、不甘或自我怀疑”，再给现实下一步；不要只给任务。
- 允许适度展开，但不要像长文分析；目标是 evidence-grounded expansion：比 v0.25 更有上下文连续性、情绪深度和具体小动作，同时保持安全、克制、少推测。
- 安全场景不要套固定模板；根据风险类型回应。现实冲突/暴力风险可以问一个安全确认问题，自伤风险不能追问方法、工具、地点或计划细节。
"""


def build_messages(behavior_request: dict[str, Any]) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": behavior_system_prompt()},
        {"role": "user", "content": behavior_user_prompt(behavior_request)},
    ]


def _string_items(value: Any) -> list[str]:
    if isinstance(value, list):
        return [item.strip() for item in value if isinstance(item, str) and item.strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _choose_text_span(value: Any, response: str) -> tuple[str, bool]:
    candidates = _string_items(value)
    if not candidates:
        return "", False
    variants: list[str] = []
    for item in candidates:
        variants.append(item)
        period_variant = item.replace("？", "。").replace("?", "。")
        if period_variant not in variants:
            variants.append(period_variant)

    exact_matches = [item for item in variants if item in response]
    if exact_matches:
        chosen = max(exact_matches, key=len)
        return chosen, chosen != value

    joined = "".join(variants)
    if joined and joined in response:
        return joined, True

    joined_with_space = " ".join(variants)
    if joined_with_space and joined_with_space in response:
        return joined_with_space, True

    if response:
        return response, True
    return candidates[0], not isinstance(value, str)


def normalize_behavior_card(card: Any, behavior_request: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """Normalize common API shape drift before strict schema validation."""
    if not isinstance(card, dict):
        return {}, ["api output was not an object"]

    normalized = json.loads(json.dumps(card, ensure_ascii=False))
    changes: list[str] = []
    strategy_card = behavior_request.get("strategy_decision_card")
    safety_override = isinstance(strategy_card, dict) and strategy_card.get("safety_override") is True
    response = normalized.get("text_response") if isinstance(normalized.get("text_response"), str) else ""
    if response:
        limited_response, question_limit_changed = limit_question_marks(response)
        if question_limit_changed:
            normalized["text_response"] = limited_response
            response = limited_response
            changes.append("converted extra question marks in text_response to periods")
    if safety_override and any(pattern in response for pattern in UNSAFE_SAFETY_FOLLOWUP_PATTERNS):
        normalized["text_response"] = SAFETY_FALLBACK_RESPONSE
        normalized["tone_style"] = "safety_directive"
        normalized["facial_expression"] = "concerned"
        normalized["action"] = "offer_resource"
        normalized["safety_message_used"] = True
        normalized["follow_up_question_count"] = 0
        normalized["strategy_realization"] = [{"strategy": "Safety Guidance", "text_span": SAFETY_FALLBACK_RESPONSE}]
        response = SAFETY_FALLBACK_RESPONSE
        changes.append("replaced unsafe safety follow-up with local safety fallback response")
    elif response:
        compacted_response, compacted = compress_repetitive_opening(response, behavior_request)
        if compacted:
            normalized["text_response"] = compacted_response
            response = compacted_response
            changes.append("compressed repetitive opening in text_response")

    context_used = normalized.get("context_used")
    if isinstance(context_used, str):
        normalized["context_used"] = [context_used] if context_used.strip() else []
        changes.append("wrapped string context_used as list")
    elif context_used is None and behavior_request.get("target_behavior_schema_version") == "0.2":
        normalized["context_used"] = []
        changes.append("filled missing context_used with empty list")
    elif isinstance(context_used, list):
        cleaned_context = [item.strip() for item in context_used if isinstance(item, str) and item.strip()]
        if cleaned_context != context_used:
            normalized["context_used"] = cleaned_context
            changes.append("removed invalid context_used items")

    if behavior_request.get("target_behavior_schema_version") == "0.2" and "uses_previous_context" not in normalized:
        normalized["uses_previous_context"] = bool(normalized.get("context_used"))
        changes.append("filled missing uses_previous_context")

    realization = normalized.get("strategy_realization")
    if isinstance(realization, dict):
        realization = [realization]
        normalized["strategy_realization"] = realization
        changes.append("wrapped strategy_realization object as list")
    elif not isinstance(realization, list):
        realization = []
        normalized["strategy_realization"] = realization
        changes.append("filled invalid strategy_realization with empty list")

    if safety_override and not realization:
        normalized["strategy_realization"] = [
            {
                "strategy": "Safety Guidance",
                "text_span": response,
            }
        ]
        changes.append("created Safety Guidance realization for safety_override")
        realization = normalized["strategy_realization"]

    for item in realization:
        if not isinstance(item, dict):
            continue
        if "strategy" not in item and isinstance(item.get("strategy_name"), str):
            item["strategy"] = item["strategy_name"]
            changes.append("mapped strategy_name to strategy")
        if safety_override and item.get("strategy") not in ALLOWED_REALIZED_STRATEGIES:
            item["strategy"] = "Safety Guidance"
            changes.append("filled safety_override realization strategy")

        chosen_span, changed = _choose_text_span(item.get("text_span"), response)
        if changed:
            item["text_span"] = chosen_span
            changes.append("normalized strategy_realization.text_span")
        elif "text_span" not in item and response:
            item["text_span"] = response
            changes.append("filled missing strategy_realization.text_span")

    if safety_override:
        literal_question_count = min(count_questions(response), 1)
        if normalized.get("follow_up_question_count") != literal_question_count:
            normalized["follow_up_question_count"] = literal_question_count
            changes.append("aligned safety follow_up_question_count with text_response")
    else:
        literal_question_count = count_questions(response)
        if normalized.get("follow_up_question_count") != literal_question_count:
            normalized["follow_up_question_count"] = literal_question_count
            changes.append("aligned follow_up_question_count with text_response")

    return normalized, changes


def validate_string_list(check: BehaviorCheck, field_name: str, values: Any, min_items: int, max_items: int) -> None:
    if not isinstance(values, list):
        check.error(f"{field_name} must be a list")
        return
    if len(values) < min_items or len(values) > max_items:
        check.error(f"{field_name} must contain {min_items}-{max_items} items")
    for value in values:
        if not isinstance(value, str) or not value.strip():
            check.error(f"{field_name} contains an empty or non-string value")


def validate_strategy_card(check: BehaviorCheck, strategy_card: dict[str, Any]) -> None:
    version = strategy_card.get("schema_version")
    if version not in {"0.1", "0.2"}:
        check.error(f"strategy_decision_card.schema_version must be '0.1' or '0.2': {version!r}")

    required = REQUIRED_STRATEGY_V02_FIELDS if version == "0.2" else REQUIRED_STRATEGY_FIELDS
    missing = sorted(required - set(strategy_card))
    if missing:
        check.error(f"strategy_decision_card missing required keys: {missing}")
        return

    if version == "0.2":
        if not isinstance(strategy_card.get("state_basis_turn_id"), int):
            check.error("strategy_decision_card.state_basis_turn_id must be an integer")
        state_change_summary = strategy_card.get("state_change_summary")
        if not isinstance(state_change_summary, str) or not state_change_summary.strip():
            check.error("strategy_decision_card.state_change_summary must be a non-empty string")

    for field_name in ("primary_strategy", "secondary_strategy"):
        value = strategy_card.get(field_name)
        if value is not None and value not in ALLOWED_ESCONV_STRATEGIES:
            check.error(f"invalid strategy_decision_card.{field_name}: {value!r}")

    safety_override = strategy_card.get("safety_override")
    if not isinstance(safety_override, bool):
        check.error("strategy_decision_card.safety_override must be boolean")
    elif safety_override:
        if strategy_card.get("support_intention") != "safety_support":
            check.error("safety_override strategy must use support_intention='safety_support'")
        if strategy_card.get("primary_strategy") is not None or strategy_card.get("secondary_strategy") is not None:
            check.error("safety_override strategy must set primary_strategy and secondary_strategy to null")
    elif strategy_card.get("primary_strategy") is None:
        check.error("non-safety strategy must include a primary_strategy")


def strategy_requires_practical_step(strategy_card: dict[str, Any]) -> bool:
    if strategy_card.get("response_timing") == "offer_next_step":
        return True
    if strategy_card.get("support_intention") in {"advise", "inform"}:
        return True
    strategies = {strategy_card.get("primary_strategy"), strategy_card.get("secondary_strategy")}
    return bool(strategies & {"Providing Suggestions", "Information"})


def response_has_practical_step(response: str) -> bool:
    return any(cue in response for cue in PRACTICAL_RESPONSE_CUES)


def validate_behavior_card(
    check: BehaviorCheck,
    card: dict[str, Any],
    behavior_request: dict[str, Any],
) -> None:
    strategy_card = behavior_request.get("strategy_decision_card")
    if not isinstance(strategy_card, dict):
        check.error("behavior_request.strategy_decision_card must be an object")
        return

    target_version = behavior_request.get("target_behavior_schema_version", "0.1")
    required = REQUIRED_BEHAVIOR_V02 if target_version == "0.2" else REQUIRED_BEHAVIOR_V01
    allowed_fields = required

    missing = sorted(required - set(card))
    if missing:
        check.error(f"behavior_response_card missing required keys: {missing}")
        return

    extra = sorted(set(card) - allowed_fields)
    if extra:
        check.error(f"behavior_response_card has fields outside schema: {extra}")

    forbidden = sorted(FIRST_PART_ONLY_FIELDS & set(card))
    if forbidden:
        check.error(f"behavior_response_card must not include first-part fields: {forbidden}")

    if card.get("conversation_id") != strategy_card.get("conversation_id"):
        check.error("conversation_id must equal strategy_decision_card.conversation_id")
    if card.get("turn_id") != strategy_card.get("turn_id"):
        check.error("turn_id must equal strategy_decision_card.turn_id")
    if card.get("schema_version") != target_version:
        check.error(f"schema_version must be {target_version}")

    response = card.get("text_response")
    if not isinstance(response, str) or not response.strip():
        check.error("text_response must be a non-empty string")
        response = ""
    elif len(response) > 520:
        check.error("text_response must be at most 520 characters")

    if card.get("tone_style") not in ALLOWED_TONE_STYLES:
        check.error(f"invalid tone_style: {card.get('tone_style')!r}")
    if card.get("facial_expression") not in ALLOWED_FACIAL_EXPRESSIONS:
        check.error(f"invalid facial_expression: {card.get('facial_expression')!r}")
    if card.get("action") not in ALLOWED_ACTIONS:
        check.error(f"invalid action: {card.get('action')!r}")
    if not isinstance(card.get("safety_message_used"), bool):
        check.error("safety_message_used must be boolean")

    follow_up_count = card.get("follow_up_question_count")
    if not isinstance(follow_up_count, int) or not (0 <= follow_up_count <= 1):
        check.error("follow_up_question_count must be 0 or 1")
    question_count = count_questions(response)
    if question_count > 1:
        check.error(f"text_response contains too many questions: {question_count}")
    if isinstance(follow_up_count, int) and follow_up_count != question_count:
        check.warn(
            "follow_up_question_count does not match literal question marks "
            f"({follow_up_count} declared, {question_count} found)"
        )

    realization = card.get("strategy_realization")
    if not isinstance(realization, list) or not (1 <= len(realization) <= 4):
        check.error("strategy_realization must contain 1-4 items")
        realized: set[str] = set()
    else:
        realized = set()
        for index, item in enumerate(realization):
            if not isinstance(item, dict):
                check.error(f"strategy_realization[{index}] must be an object")
                continue
            item_strategy = item.get("strategy")
            text_span = item.get("text_span")
            if item_strategy not in ALLOWED_REALIZED_STRATEGIES:
                check.error(f"strategy_realization[{index}].strategy is invalid: {item_strategy!r}")
            else:
                realized.add(item_strategy)
            if not isinstance(text_span, str) or not text_span.strip():
                check.error(f"strategy_realization[{index}].text_span must be non-empty")
            elif text_span not in response:
                check.error(f"strategy_realization[{index}].text_span is not in text_response")

    safety_override = strategy_card.get("safety_override") is True
    if safety_override:
        if not card.get("safety_message_used"):
            check.error("safety_override behavior must set safety_message_used=true")
        if card.get("tone_style") != "safety_directive":
            check.error("safety_override behavior must use tone_style='safety_directive'")
        if "Safety Guidance" not in realized:
            check.error("safety_override behavior must realize Safety Guidance")
        if card.get("follow_up_question_count") not in {0, 1}:
            check.error("safety_override behavior may ask at most one immediate safety-check question")
    else:
        for required_strategy in (strategy_card.get("primary_strategy"), strategy_card.get("secondary_strategy")):
            if required_strategy is not None and required_strategy not in realized:
                check.error(f"behavior does not realize strategy: {required_strategy}")

    if strategy_requires_practical_step(strategy_card) and not response_has_practical_step(response):
        check.warn(
            "semantic warning: strategy requires a concrete next step, but text_response may only validate emotion; "
            "include one low-burden practical action"
        )

    if target_version == "0.2":
        if not isinstance(card.get("uses_previous_context"), bool):
            check.error("uses_previous_context must be boolean")
        validate_string_list(check, "context_used", card.get("context_used"), 0, 6)
        if card.get("uses_previous_context") is False and card.get("context_used"):
            check.error("context_used must be empty when uses_previous_context=false")


def mock_behavior_card(expected_behavior: dict[str, Any] | None) -> dict[str, Any]:
    return json.loads(json.dumps(expected_behavior, ensure_ascii=False)) if expected_behavior else {}


def api_behavior_card(
    behavior_request: dict[str, Any],
    config: api_client.ApiConfig,
) -> tuple[dict[str, Any], dict[str, Any]]:
    messages = build_messages(behavior_request)
    attempts: list[dict[str, Any]] = []
    latest_card: dict[str, Any] = {}
    minimum_information_retry_used = False
    final_minimum_information_warning = False
    max_attempts = config.max_retries + 2

    for attempt_number in range(max_attempts):
        started = time.time()
        raw_output = ""
        try:
            raw_output, response_json = api_client.request_chat_completion(messages, config)
            parsed_card, parse_error = api_client.extract_json_object(raw_output)
        except Exception as error:  # noqa: BLE001 - keep CLI errors readable.
            attempts.append(
                {
                    "attempt": attempt_number + 1,
                    "status": "api_error",
                    "error": str(error),
                    "elapsed_seconds": round(time.time() - started, 3),
                }
            )
            break

        attempt_record: dict[str, Any] = {
            "attempt": attempt_number + 1,
            "status": "received",
            "raw_output": raw_output,
            "elapsed_seconds": round(time.time() - started, 3),
            "response_id": response_json.get("id") if isinstance(response_json, dict) else None,
        }

        if parse_error:
            attempt_record["status"] = "parse_error"
            attempt_record["errors"] = [parse_error]
            attempts.append(attempt_record)
            messages.extend(
                [
                    {"role": "assistant", "content": raw_output},
                    {"role": "user", "content": api_client.retry_user_prompt([parse_error], raw_output)},
                ]
            )
            continue

        latest_card, normalization_changes = normalize_behavior_card(parsed_card or {}, behavior_request)
        if normalization_changes:
            attempt_record["normalization_changes"] = normalization_changes
            attempt_record["normalized_output"] = latest_card
        strategy_card = behavior_request.get("strategy_decision_card") or {}
        check = BehaviorCheck(
            str(strategy_card.get("conversation_id", "unknown_conversation")),
            int(strategy_card.get("turn_id", 1)) if isinstance(strategy_card.get("turn_id"), int) else 1,
        )
        validate_behavior_card(check, latest_card, behavior_request)
        if not check.errors:
            min_info_issue = minimum_information_issue(latest_card, behavior_request)
            if min_info_issue and not minimum_information_retry_used and attempt_number < max_attempts - 1:
                attempt_record["status"] = "minimum_information_retry"
                attempt_record["minimum_information_warning"] = True
                attempt_record["warnings"] = check.warnings + [min_info_issue]
                attempts.append(attempt_record)
                minimum_information_retry_used = True
                messages.extend(
                    [
                        {"role": "assistant", "content": raw_output},
                        {"role": "user", "content": minimum_information_retry_prompt(min_info_issue)},
                    ]
                )
                continue

            attempt_record["status"] = "valid"
            if min_info_issue:
                check.warn(min_info_issue)
                attempt_record["minimum_information_warning"] = True
                final_minimum_information_warning = True
            if check.warnings:
                attempt_record["warnings"] = check.warnings
            attempts.append(attempt_record)
            return latest_card, {
                "status": "valid",
                "attempts": attempts,
                "model": config.model,
                "url": config.url,
                "json_mode": config.json_mode,
                "minimum_information_retry_used": minimum_information_retry_used,
                "minimum_information_warning": final_minimum_information_warning,
            }

        attempt_record["status"] = "validation_error"
        attempt_record["errors"] = check.errors
        attempts.append(attempt_record)
        messages.extend(
            [
                {"role": "assistant", "content": raw_output},
                {"role": "user", "content": api_client.retry_user_prompt(check.errors, raw_output)},
            ]
        )

    return latest_card, {
        "status": "failed",
        "attempts": attempts,
        "model": config.model,
        "url": config.url,
        "json_mode": config.json_mode,
        "minimum_information_retry_used": minimum_information_retry_used,
        "minimum_information_warning": final_minimum_information_warning,
    }


def run(args: argparse.Namespace) -> int:
    if args.source == "record":
        behavior_request, expected_behavior, source_meta = build_input_from_record(
            args.record,
            args.turn_id,
            args.max_recent_turns,
        )
        report_path = args.report or default_report_path(args.mode, "record", source_meta.get("turn_id"), None)
    else:
        behavior_request, expected_behavior, source_meta = build_input_from_case(args.cases, args.case_id)
        report_path = args.report or default_report_path(args.mode, "case", None, source_meta.get("case_id"))

    strategy_card = behavior_request.get("strategy_decision_card") or {}
    check = BehaviorCheck(
        str(strategy_card.get("conversation_id", "unknown_conversation")),
        int(strategy_card.get("turn_id", 1)) if isinstance(strategy_card.get("turn_id"), int) else 1,
    )
    validate_strategy_card(check, strategy_card if isinstance(strategy_card, dict) else {})

    api_meta: dict[str, Any] | None = None
    behavior_card: dict[str, Any] = {}

    if check.errors:
        pass
    elif args.mode == "dry-run":
        behavior_card = {}
    elif args.mode == "mock":
        behavior_card = mock_behavior_card(expected_behavior)
        validate_behavior_card(check, behavior_card, behavior_request)
    else:
        api_config, config_errors = api_client.load_api_config(args)
        if config_errors:
            for error in config_errors:
                check.error(error)
            api_meta = {"status": "failed", "errors": config_errors}
        elif api_config is not None:
            behavior_card, api_meta = api_behavior_card(behavior_request, api_config)
            if api_meta.get("status") != "valid":
                check.error("api mode did not produce a valid behavior response card")
            if behavior_card:
                validate_behavior_card(check, behavior_card, behavior_request)

    report = {
        "status": "dry_run" if args.mode == "dry-run" and check.status == "pass" else check.status,
        "module_scope": "research_content_3_behavior_response_schema_aligned",
        "mode": args.mode,
        "source": source_meta,
        "input_contract": {
            "uses_dialogue": True,
            "uses_strategy_decision_card": True,
            "uses_user_state_card": False,
            "ignored_first_part_card_present": source_meta.get("ignored_first_part_card_present"),
        },
        "messages": build_messages(behavior_request) if args.mode == "dry-run" else None,
        "input": {
            "behavior_response_request": behavior_request,
        },
        "output": {
            "behavior_response_card": behavior_card,
        },
        "api": api_meta,
        "expected_behavior_available": expected_behavior is not None,
        "validation": check.to_dict(),
    }
    write_json(report_path, report)

    print("scope=research_content_3_behavior_response_schema_aligned")
    print(f"mode={args.mode} source={args.source}")
    print(f"status={report['status']}")
    print("uses_user_state_card=False")
    for error in check.errors:
        print(f"  ERROR {error}")
    for warning in check.warnings:
        print(f"  WARN {warning}")
    print(f"report={report_path}")
    return 0 if report["status"] in {"pass", "dry_run"} else 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", choices=("record", "case"), default="record")
    parser.add_argument("--record", type=Path, default=DEFAULT_RECORD)
    parser.add_argument("--turn-id", type=int)
    parser.add_argument("--max-recent-turns", type=int, default=3)
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--case-id")
    parser.add_argument("--mode", choices=("dry-run", "mock", "api"), default="dry-run")
    parser.add_argument("--report", type=Path)
    parser.add_argument("--env-file", type=Path, default=DEFAULT_ENV_FILE)
    parser.add_argument("--api-url")
    parser.add_argument("--api-model")
    parser.add_argument("--api-temperature", type=float)
    parser.add_argument("--api-timeout", type=int)
    parser.add_argument("--api-max-retries", type=int)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.max_recent_turns < 1:
        raise ValueError("--max-recent-turns must be at least 1")
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())

