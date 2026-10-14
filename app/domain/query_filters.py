import re
from typing import Literal
from pydantic import BaseModel, Field, field_validator, model_validator, ConfigDict


NUMERIC_OPERATORS = {"eq": "=", "ne": "<>", "gt": ">", "ge": ">=", "lt": "<", "le": "<="}


class ValueCondition(BaseModel):
    model_config = ConfigDict(extra="forbid")
    operator: Literal["eq", "ne", "gt", "ge", "lt", "le", "starts", "not_starts", "ends", "not_ends", "contains", "not_contains"]
    target: str = Field(max_length=1000)

    @model_validator(mode="after")
    def validate_target(self):
        if self.operator in NUMERIC_OPERATORS:
            value = self.target.strip()
            if not re.fullmatch(r"[+-]?[0-9]+", value) or not -(2**63) <= int(value) < 2**63:
                raise ValueError("数值筛选目标必须为 BIGINT 整数（-9223372036854775808 至 9223372036854775807）")
            self.target = str(int(value))
        return self


class ValueFilterGroup(BaseModel):
    model_config = ConfigDict(extra="forbid")
    field: str = Field(pattern=r"^value([1-9]|1[0-9]|2[0-5])$")
    logic: Literal["and", "or"] = "and"
    conditions: list[ValueCondition] = Field(min_length=1, max_length=20)


class QueryFilters(BaseModel):
    model_config = ConfigDict(extra="forbid")
    systems: list[str] = Field(default_factory=list, max_length=3)
    versions: list[str] = Field(default_factory=list, max_length=50)
    value_fields: list[str] = Field(default_factory=lambda: ["value1", "value2", "value3"], max_length=25)
    new_users: list[Literal[0, 1]] = Field(default_factory=lambda: [0, 1], min_length=1, max_length=2)
    value_logic: Literal["and", "or"] = "and"
    value_filters: list[ValueFilterGroup] = Field(default_factory=list, max_length=25)

    @model_validator(mode="after")
    def valid_groups(self):
        fields = [group.field for group in self.value_filters]
        if len(set(fields)) != len(fields) or any(name not in self.value_fields for name in fields):
            raise ValueError("每个已选返回字段只能设置一个条件组，未选字段不能筛选")
        self.new_users = sorted(set(self.new_users))
        self.value_filters.sort(key=lambda group: int(group.field[5:]))
        return self

    @field_validator("systems")
    @classmethod
    def valid_systems(cls, values):
        if any(value not in ("ios", "android", "harmony") for value in values):
            raise ValueError("sys 只支持 ios、android、harmony")
        return sorted(set(values))

    @field_validator("versions")
    @classmethod
    def valid_versions(cls, values):
        values = [value.strip() for value in values if value.strip()]
        if any(not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._+\-]{0,63}", value) for value in values):
            raise ValueError("版本仅支持字母、数字、点、下划线、加号和短横线，最长64字符")
        return sorted(set(values))

    @field_validator("value_fields")
    @classmethod
    def valid_fields(cls, values):
        allowed = {f"value{i}" for i in range(1, 26)}
        if any(value not in allowed for value in values):
            raise ValueError("返回字段只支持 value1 至 value25")
        return sorted(set(values), key=lambda value: int(value[5:]))


def effective_filters(filters=None, log_type="client"):
    if log_type == "web":
        return QueryFilters(value_fields=[])
    return QueryFilters.model_validate(filters or {})


def export_limit(settings):
    return max(1, min(200_000, settings.max_export_rows))
