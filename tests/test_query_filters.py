import pytest
from pydantic import ValidationError
from app.domain.query_filters import QueryFilters
from app.core.config import Settings
from app.domain.partitions import PartitionRange
from app.services.query_plan import build_query_plan, plan_fingerprint


def plan(filters=None, log_type="client"):
    settings=Settings(_env_file=None, data_source_table="events", data_partition_column="dt", data_user_id_column="uid", data_event_code_column="cid_parm")
    return build_query_plan(settings,"70081134" if log_type=="web" else "90036",PartitionRange("20260901","20260907"),log_type,filters)


def test_filters_generate_matching_columns_and_predicates():
    detail, aggregate=plan({"systems":["ios","android"],"versions":["1.2.0","1.3.0"],"value_fields":["value25","value3"]})
    assert "AND sys IN ('android', 'ios')" in detail
    assert "AND ver IN ('1.2.0', '1.3.0')" in detail
    assert "t3.value3," in detail and "t3.value25," in detail
    assert "t3.value1," not in detail
    assert "AND value1 = '1'" in detail
    assert detail.endswith("LIMIT 200000;")
    assert "LIMIT" not in aggregate
    assert "AND ver IN ('1.2.0', '1.3.0')" in aggregate


def test_defaults_empty_fields_and_web_isolation():
    detail,_=plan()
    assert "t3.value" not in detail
    assert "AND sys IN" not in detail and "AND ver IN" not in detail
    detail,_=plan({"value_fields":[]})
    assert "t3.value" not in detail
    assert "AND value1 = '1'" in detail
    assert plan({"systems":["ios"],"versions":["1.0"],"value_fields":["value25"]},"web") == plan(log_type="web")


@pytest.mark.parametrize("filters",[
    {"systems":["linux"]}, {"versions":["1.0' OR 1=1 --"]},
    {"versions":["a\\b"]}, {"value_fields":["value26"]},
    {"value_fields":["value1; DROP TABLE x"]}, {"unknown":[]},
])
def test_invalid_filters_rejected(filters):
    with pytest.raises(ValidationError): QueryFilters.model_validate(filters)


def test_canonical_filters_and_plan_fingerprint():
    a=plan({"versions":["2.0","1.0","1.0"],"value_fields":["value3","value1"]})
    b=plan({"versions":["1.0","2.0"],"value_fields":["value1","value3"]})
    assert a==b
    assert plan_fingerprint(a)!=plan_fingerprint(plan({"versions":["3.0"]}))
