import re
from pydantic import BaseModel, Field, field_validator, ConfigDict


class QueryFilters(BaseModel):
    model_config = ConfigDict(extra="forbid")
    systems: list[str] = Field(default_factory=list, max_length=3)
    versions: list[str] = Field(default_factory=list, max_length=50)
    value_fields: list[str] = Field(default_factory=lambda: ["value1", "value2", "value3"], max_length=25)

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
