import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine, text

from app.core.config import Settings
from app.database import migrate_log_type
from app.domain.event_codes import extract_event_codes, missing_event_codes
from app.domain.partitions import PartitionRange
from app.domain.query_filters import QueryFilters, ValueCondition
from app.infrastructure.filter_sql import render_condition, text_literal
from app.services.query_plan import build_query_plan, plan_fingerprint


def test_multi_events_and_whitespace():
    assert extract_event_codes('查询 170035\t170036\n90056 170035') == ['170035','170036','90056']
    assert extract_event_codes(' 90056 _ 0001 1700930_0001 ') == ['90056_0001','1700930_0001']
    assert extract_event_codes('70081134 70081133','web') == ['70081134','70081133']
    assert missing_event_codes(['90056','170035','170036'],['90056_0001','170035-0002']) == ['170036']
    assert missing_event_codes(['70081134'],['700811340'],'web') == ['70081134']
    assert missing_event_codes(['90056'],[]) == ['90056']


@pytest.mark.parametrize('target',['abc','1.5','1e3','',str(2**63),str(-2**63-1),"1 OR 1=1",'１２３'])
def test_invalid_numeric_targets(target):
    with pytest.raises(ValidationError): ValueCondition(operator='eq',target=target)


@pytest.mark.parametrize('target',[str(-2**63),str(2**63-1),'0',' +00100 '])
def test_bigint_targets(target):
    assert ValueCondition(operator='eq',target=target).target == str(int(target))


@pytest.mark.parametrize('operator',['eq','ne','gt','ge','lt','le'])
def test_numeric_source_cast_is_guarded(operator):
    sql=render_condition('value1',ValueCondition(operator=operator,target='100'))
    assert 'ELSE NULL END AS BIGINT)' in sql
    assert '9223372036854775808' in sql and "RLIKE '^[+-]?[0-9]+$'" in sql
    assert "CAST('100' AS BIGINT)" in sql


@pytest.mark.parametrize('operator',['starts','not_starts','ends','not_ends','contains','not_contains'])
def test_text_operators_literal_and_safe(operator):
    sql=render_condition('value2',ValueCondition(operator=operator,target="a'\\_%\n中文"))
    assert 'CHR(39)' in sql and 'CHR(92)' in sql and 'CHR(10)' in sql
    assert 'LIKE' not in sql and 'BIGINT' not in sql
    assert sql.startswith('NOT (') == operator.startswith('not_')
    assert text_literal('') == "''"


def test_group_validation():
    for value in ({'new_users':[]},{'new_users':[2]}, {'value_logic':'xor'},
                  {'value_fields':[], 'value_filters':[{'field':'value1','conditions':[{'operator':'eq','target':'1'}]}]},
                  {'value_filters':[{'field':'value26','conditions':[{'operator':'eq','target':'1'}]}]},
                  {'value_filters':[{'field':'value1','conditions':[]}]}):
        with pytest.raises(ValidationError): QueryFilters.model_validate(value)


def test_multi_plan_groups_and_new_users():
    settings=Settings(_env_file=None,data_source_table='events',data_partition_column='dt',data_user_id_column='uid',data_event_code_column='cid_parm')
    filters={'new_users':[1], 'value_fields':['value1','value2'], 'value_logic':'or','value_filters':[
        {'field':'value1','logic':'or','conditions':[{'operator':'eq','target':'100'},{'operator':'eq','target':'200'}]},
        {'field':'value2','logic':'or','conditions':[{'operator':'starts','target':'abc'},{'operator':'contains','target':'abc'}]}
    ]}
    args=(settings,['170035','170036','90056'],PartitionRange('20260901','20260907'))
    detail,agg=build_query_plan(*args,filters=filters)
    assert "AND is_new = 1" in detail and 't3.is_new' in detail
    assert "cid_parm LIKE '%170035%' OR cid_parm LIKE '%170036%' OR cid_parm LIKE '%90056%'" in detail
    assert "CAST('200' AS BIGINT)" in detail and "OR ((SUBSTR" in detail
    assert 'GROUP BY event_date, cid_parm' in agg and 'LIMIT' not in agg
    assert detail.endswith('LIMIT 200000;')
    assert plan_fingerprint((detail,agg)) == plan_fingerprint(build_query_plan(*args,filters=filters|{'value_logic':'and'}))
    assert QueryFilters.model_validate(filters|{'value_logic':'and'}).value_logic == 'or'
    default=build_query_plan(*args)[0]
    assert 'AND is_new' not in default
    web=build_query_plan(settings,['70081134','70081133'],args[2],'web',filters)
    assert "eventid IN ('70081134', '70081133')" in web[0] and 'is_new' not in web[0]


def test_v005_additive_migration_preserves_records():
    engine=create_engine('sqlite://')
    with engine.begin() as conn:
        conn.execute(text('CREATE TABLE query_job_contexts (job_id TEXT, filters_json TEXT, export_limit INTEGER, log_type TEXT)'))
        conn.execute(text("INSERT INTO query_job_contexts VALUES ('old','{}',100,'client')"))
        conn.execute(text('CREATE TABLE daily_aggregations (job_id TEXT,event_date TEXT,pv INTEGER,uv INTEGER)'))
        conn.execute(text("INSERT INTO daily_aggregations VALUES ('old','20260901',12,5)"))
        conn.execute(text('CREATE TABLE user_accounts (username TEXT,password_hash TEXT)'))
        conn.execute(text("INSERT INTO user_accounts VALUES ('existing','unchanged-hash')"))
    migrate_log_type(engine);migrate_log_type(engine)
    with engine.connect() as conn:
        assert conn.execute(text('SELECT * FROM user_accounts')).one()==('existing','unchanged-hash')
        assert conn.execute(text('SELECT pv,uv,event_code FROM daily_aggregations')).one()==(12,5,'')
        assert conn.execute(text('SELECT export_limit,event_codes_json FROM query_job_contexts')).one()==(100,'[]')
