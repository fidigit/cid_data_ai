from __future__ import annotations

import re


# 支持数字 CID、英文/数字/下划线 CID 及可选后缀；完整编码不超过数据库的 32 字符列。
# 历史的纯数字下划线后缀继续兼容，新输入统一使用短横线区分后缀。
EVENT_CODE_PATTERN = re.compile(
    r"(?<![A-Za-z0-9_-])(?P<code>\d{5,7}_\d{4}|[A-Za-z0-9_]{5,27}-\d{4}|[A-Za-z0-9_]{5,32})(?![A-Za-z0-9_-])"
)


class EventCodeExtractionError(ValueError):
    pass


def normalize_question(question: str) -> str:
    """保留事件间分隔符，只清理重复空白及编码连接符两侧空白。"""
    compact = re.sub(r"\s+", " ", question).strip()
    compact = re.sub(r"(?<=\d)\s*_\s*(?=\d{4}(?!\d))", "_", compact)
    return re.sub(r"(?<=[A-Za-z0-9_])\s*-\s*(?=\d{4}(?!\d))", "-", compact)


WEB_EVENT_CODE_PATTERN = re.compile(r"(?<![A-Za-z0-9_-])(?P<code>\d{8})(?![A-Za-z0-9_-])")


def find_event_codes(question: str, log_type: str = "client") -> list[str]:
    """按首次出现顺序返回去重的 CID 候选。"""
    normalized = normalize_question(question)
    pattern = WEB_EVENT_CODE_PATTERN if log_type == "web" else EVENT_CODE_PATTERN
    matches = list(pattern.finditer(normalized))
    if not matches and normalized != question:
        matches = list(pattern.finditer(question))
    return list(dict.fromkeys(match.group("code") for match in matches if is_valid_event_code(match.group("code"), log_type)))


def extract_unique_event_code(question: str, log_type: str = "client") -> str:
    codes = find_event_codes(question, log_type)
    if not codes:
        if log_type == "web":
            raise EventCodeExtractionError("未识别到 WEB 事件编码，请输入8位数字，例如70081134。")
        raise EventCodeExtractionError("未识别到 CID，请输入类似 90056、90056-0001 或 UID_WITHOUT_TOKEN 的事件编码。")
    if len(codes) > 1:
        joined = "、".join(codes)
        raise EventCodeExtractionError(f"识别到多个 CID（{joined}），请一次只查询一个事件编码。")
    return codes[0]


def is_valid_event_code(value: str, log_type: str = "client") -> bool:
    pattern = WEB_EVENT_CODE_PATTERN if log_type == "web" else EVENT_CODE_PATTERN
    if pattern.fullmatch(value) is None:
        return False
    if log_type == "web":
        return True
    if len(value) > 32:
        return False
    if re.fullmatch(r"\d+_\d{1,4}", value) and not re.fullmatch(r"\d{5,7}_\d{4}", value):
        return False
    base = value.rsplit("-", 1)[0] if re.search(r"-\d{4}$", value) else value
    if re.fullmatch(r"\d+", base) and not 5 <= len(base) <= 7:
        return False
    return True


def extract_event_codes(question: str, log_type: str = "client") -> list[str]:
    codes = find_event_codes(question, log_type)
    if not codes:
        extract_unique_event_code(question, log_type)  # existing localized error
    if len(codes) > 50:
        raise EventCodeExtractionError("单次最多查询50个事件编码。")
    return codes


def missing_event_codes(requested, returned, log_type="client"):
    def canonical(code):
        return code.replace("_", "-") if re.fullmatch(r"\d{5,7}_\d{4}", code) else code

    actual = {canonical(str(code)) for code in returned if code}
    def matched(code, item):
        if log_type == "web":
            return code == item
        if re.search(r"-\d{4}$", code) or re.fullmatch(r"\d{5,7}_\d{4}", code):
            return canonical(code) == item
        return code in item

    return [code for code in requested if not any(matched(code, item) for item in actual)]
