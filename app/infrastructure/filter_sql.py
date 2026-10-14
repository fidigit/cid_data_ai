"""Whitelisted predicate rendering; no raw user SQL is accepted."""
import re

from app.domain.query_filters import NUMERIC_OPERATORS


def text_literal(value):
    # CHR avoids quote/backslash escaping differences between ODPS project settings.
    parts = re.split(r"(['\\\x00-\x1f\x7f])", value)
    terms = [f"CHR({ord(part)})" if len(part) == 1 and (ord(part) < 32 or part in "'\\\x7f")
             else "'" + part + "'" for part in parts if part]
    if not terms:
        return "''"
    return terms[0] if len(terms) == 1 else "CONCAT(" + ", ".join(terms) + ")"


def safe_bigint(field):
    raw = f"TRIM(CAST({field} AS STRING))"
    digits = f"REGEXP_REPLACE({raw}, '^[+-]?0*', '')"
    bound = f"CASE WHEN SUBSTR({raw}, 1, 1) = '-' THEN '9223372036854775808' ELSE '9223372036854775807' END"
    return (f"CAST(CASE WHEN {raw} RLIKE '^[+-]?[0-9]+$' AND "
            f"(LENGTH({digits}) < 19 OR (LENGTH({digits}) = 19 AND {digits} <= ({bound}))) "
            f"THEN CASE WHEN {digits} = '' THEN '0' ELSE CONCAT("
            f"CASE WHEN SUBSTR({raw}, 1, 1) = '-' THEN '-' ELSE '' END, {digits}) END "
            "ELSE NULL END AS BIGINT)")


def render_condition(field, condition):
    op, target = condition.operator, condition.target
    if op in NUMERIC_OPERATORS:
        return f"{safe_bigint(field)} {NUMERIC_OPERATORS[op]} CAST('{target}' AS BIGINT)"
    literal = text_literal(target)
    value = f"CAST({field} AS STRING)"
    positive = op.removeprefix("not_")
    if not target:
        expression = f"{value} IS NOT NULL"
    elif positive == "contains":
        expression = f"INSTR({value}, {literal}) > 0"
    elif positive == "starts":
        expression = f"SUBSTR({value}, 1, LENGTH({literal})) = {literal}"
    else:
        expression = f"SUBSTR({value}, -LENGTH({literal})) = {literal}"
    return f"NOT ({expression})" if op.startswith("not_") else expression


def render_value_filters(selected):
    groups = ["(" + f" {group.logic.upper()} ".join(
        render_condition(group.field, condition) for condition in group.conditions
    ) + ")" for group in selected.value_filters]
    return "(" + f" {selected.value_logic.upper()} ".join(groups) + ")" if groups else ""
