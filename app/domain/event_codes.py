from __future__ import annotations

import re


# 支持 140961、1700930、90056_0001、1700930_0001，并避免从更长 token 中误截取。
EVENT_CODE_PATTERN = re.compile(
    r"(?<![A-Za-z0-9_-])(?P<code>\d{5,7}(?:[_-]\d{4})?)(?![A-Za-z0-9_-])"
)


class EventCodeExtractionError(ValueError):
    pass


def normalize_question(question: str) -> str:
    """移除用户输入中的全部 Unicode 空白字符。"""
    return re.sub(r"\s+", "", question)


WEB_EVENT_CODE_PATTERN = re.compile(r"(?<![A-Za-z0-9_-])(?P<code>\d{8})(?![A-Za-z0-9_-])")


def find_event_codes(question: str, log_type: str = "client") -> list[str]:
    """按首次出现顺序返回去重的 CID 候选。"""
    normalized = normalize_question(question)
    pattern = WEB_EVENT_CODE_PATTERN if log_type == "web" else EVENT_CODE_PATTERN
    matches = list(pattern.finditer(normalized))
    if not matches and normalized != question:
        matches = list(pattern.finditer(question))
    return list(dict.fromkeys(match.group("code") for match in matches))


def extract_unique_event_code(question: str, log_type: str = "client") -> str:
    codes = find_event_codes(question, log_type)
    if not codes:
        if log_type == "web":
            raise EventCodeExtractionError("未识别到 WEB 事件编码，请输入8位数字，例如70081134。")
        raise EventCodeExtractionError("未识别到 CID，请输入类似 90056_0001 或 140961 的事件编码。")
    if len(codes) > 1:
        joined = "、".join(codes)
        raise EventCodeExtractionError(f"识别到多个 CID（{joined}），请一次只查询一个事件编码。")
    return codes[0]


def is_valid_event_code(value: str, log_type: str = "client") -> bool:
    pattern = WEB_EVENT_CODE_PATTERN if log_type == "web" else EVENT_CODE_PATTERN
    return pattern.fullmatch(value) is not None
