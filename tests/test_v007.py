import pytest
from zipfile import ZipFile
from pydantic import ValidationError

from app.domain.event_codes import missing_event_codes
from app.domain.partitions import PartitionRange
from app.domain.query_filters import QueryFilters
from app.infrastructure.filter_sql import render_value_filters
from app.infrastructure.sql_renderer import EventQueryRenderer
from app.services.report_builder import build_xlsx


def render(codes, filters=None):
    return EventQueryRenderer(__import__('pathlib').Path('sql/event_detail.sql')).render_detail(
        source_table='events', partition_column='dt', event_code_column='cid_parm',
        user_id_column='uid', event_code=codes,
        partitions=PartitionRange('20261015', '20261021'), filters=filters,
    )


def test_version_greater_uses_lexicographic_segments():
    sql = render('160036', {'version_mode': 'greater', 'versions': ['16.3.1']})
    assert "SAFE_CAST(SPLIT_PART(ver, '.', 1) AS BIGINT)" in sql
    assert "COALESCE(SAFE_CAST(SPLIT_PART(ver, '.', 1) AS BIGINT), 0) > 16" in sql
    assert "= 16 AND COALESCE(SAFE_CAST(SPLIT_PART(ver, '.', 2) AS BIGINT), 0) > 3" in sql
    assert "= 3 AND COALESCE(SAFE_CAST(SPLIT_PART(ver, '.', 3) AS BIGINT), 0) > 1" in sql
    assert "ver RLIKE '^[0-9]+([.][0-9]+){0,3}$'" in sql


def test_version_greater_equal_includes_equal_and_higher_major():
    sql = render('160036', {'version_mode': 'greater_equal', 'versions': ['16.3.1']})
    assert "COALESCE(SAFE_CAST(SPLIT_PART(ver, '.', 1) AS BIGINT), 0) > 16" in sql
    assert "= 16 AND COALESCE(SAFE_CAST(SPLIT_PART(ver, '.', 2) AS BIGINT), 0) = 3 AND COALESCE(SAFE_CAST(SPLIT_PART(ver, '.', 3) AS BIGINT), 0) = 1" in sql
    assert QueryFilters.model_validate({}).version_mode == 'greater_equal'


def test_version_exclude_and_enum():
    assert "ver NOT IN ('16.3.1', '17.1.0')" in render('160036', {'version_mode':'exclude','versions':['16.3.1','17.1.0']})
    assert "ver IN ('16.3.1', '17.1.0')" in render('160036', {'version_mode':'enum','versions':['16.3.1','17.1.0']})
    assert "AND ver IN" not in render('160036', {'version_mode':'greater','versions':[]})


@pytest.mark.parametrize('value', ['16.3.1 17.0', '16.beta', '9223372036854775808.0'])
def test_invalid_greater_versions(value):
    with pytest.raises(ValidationError):
        QueryFilters.model_validate({'version_mode':'greater','versions':[value]})


def test_mixed_value_connectors_are_parenthesized_in_display_order():
    filters=QueryFilters.model_validate({'value_fields':['value1'],'value_filters':[{'field':'value1','connectors':['or','and'],
        'conditions':[{'operator':'eq','target':'1'},{'operator':'eq','target':'2'},{'operator':'eq','target':'3'}]}]})
    sql=render_value_filters(filters)
    assert "CAST('1' AS BIGINT)" in sql and " OR " in sql and " AND " in sql
    assert sql.index("CAST('1' AS BIGINT)") < sql.index("CAST('2' AS BIGINT)") < sql.index("CAST('3' AS BIGINT)")
    with pytest.raises(ValidationError):
        QueryFilters.model_validate({'value_fields':['value1'],'value_filters':[{'field':'value1','connectors':['or','and'],
            'conditions':[{'operator':'eq','target':'1'},{'operator':'eq','target':'2'}]}]})


def test_partial_and_exact_multi_events():
    sql=render(['160036','90059_0003'])
    assert "cid_parm LIKE '%160036%' OR cid_parm = '90059-0003'" in sql
    assert missing_event_codes(['160036','90059_0003'], ['160036-0001','90059-0002']) == ['90059_0003']
    assert missing_event_codes(['160036','90059_0003'], ['160036-0001','90059-0003']) == []


def test_two_partial_events_are_or_combined_in_full_aggregation():
    from app.infrastructure.sql_renderer import EventQueryRenderer
    sql=render(['170035','170061'])
    assert "AND (cid_parm LIKE '%170035%' OR cid_parm LIKE '%170061%')" in sql
    aggregate=EventQueryRenderer.render_daily_aggregation(sql)
    assert "cid_parm LIKE '%170061%'" in aggregate
    assert 'GROUP BY event_date, cid_parm' in aggregate
    assert missing_event_codes(['170035','170061'],['170035-0001','170061-0002']) == []


def test_multi_event_query_plan_limits_only_detail():
    from types import SimpleNamespace
    from app.services.query_plan import build_query_plan
    settings=SimpleNamespace(data_source_table='events',data_partition_column='dt',
                             data_event_code_column='cid_parm',data_user_id_column='uid',max_export_rows=200000)
    detail,aggregate=build_query_plan(settings,['170035','170061'],PartitionRange('20261021','20261022'))
    assert "cid_parm LIKE '%170035%' OR cid_parm LIKE '%170061%'" in detail
    assert "cid_parm LIKE '%170035%' OR cid_parm LIKE '%170061%'" in aggregate
    assert 'LIMIT 200000' in detail and 'LIMIT 200000' not in aggregate


def test_alphabetic_cid_is_literal_and_preserves_internal_underscores():
    sql=render(['UID_WITHOUT_TOKEN','UID_WITHOUT_TOKEN-0001'])
    assert "INSTR(cid_parm, 'UID_WITHOUT_TOKEN') > 0" in sql
    assert "cid_parm = 'UID_WITHOUT_TOKEN-0001'" in sql
    assert "LIKE '%UID_WITHOUT_TOKEN%'" not in sql
    assert missing_event_codes(['UID_WITHOUT_TOKEN','UID_WITHOUT_TOKEN-0001'],
                               ['UID_WITHOUT_TOKEN-0002']) == ['UID_WITHOUT_TOKEN-0001']
    assert missing_event_codes(['UID_WITHOUT_TOKEN-0001'],['UID_WITHOUT_TOKEN-0001']) == []


def test_harmonyos_product_and_system_filters():
    sql=render('UID_WITHOUT_TOKEN',{'systems':['harmonyos']})
    assert 'product_id IN (27090, 27130, 65462)' in sql
    assert "AND sys IN ('harmonyos')" in sql
    assert "AND sys IN ('harmony')" not in sql
    assert QueryFilters.model_validate({'systems':['harmony']}).systems == ['harmonyos']


def test_xlsx_records_version_mode_and_each_value_connector(tmp_path):
    output=tmp_path/'v007.xlsx'
    build_xlsx(destination=output,event_code='160036',partition_start='20261022',partition_end='20261022',
        aggregation=[{'event_date':'20261022','event_code':'160036-0001','pv':1,'uv':1}],
        detail_columns=('uid',),detail_rows=[('u1',)],max_rows=10,
        filters={'versions':['16.3.1'],'version_mode':'greater','value_fields':['value1'],'value_logic':'and','value_filters':[{'field':'value1',
            'connectors':['or','and'],'conditions':[{'operator':'eq','target':'1'},
            {'operator':'eq','target':'2'},{'operator':'eq','target':'3'}]}]})
    with ZipFile(output) as archive:
        xml=archive.read('xl/worksheets/sheet1.xml').decode('utf-8')
    assert 'ver：大于 16.3.1' in xml and '自定义筛选组之间：OR' in xml and '<t>OR</t>' in xml and '<t>AND</t>' in xml
