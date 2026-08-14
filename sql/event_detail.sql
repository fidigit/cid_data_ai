SELECT
    time,
    detail_time2,
    t3.hdid,
    sys,
    ver,
    value1,
    value2,
    t3.uid,
    t3.uid AS user_id,
    t3.cid_parm,
    NVL(t4.cid_parm_name, '补充') AS cid_parm_name,
    t3.dt,
    t3.dt AS event_date
FROM (
    SELECT
        time,
        CONCAT(
            SUBSTR(FROM_UNIXTIME(time), 1, 13), '-',
            SUBSTR(FROM_UNIXTIME(time), -5, 2), '-',
            SUBSTR(FROM_UNIXTIME(time), -2, 2)
        ) AS detail_time2,
        hdid,
        $user_id_column AS uid,
        sys,
        ver,
        value1,
        value2,
        IF(
            $event_code_column = '160036-0003' AND value1 = '1',
            '冷启动不统计',
            $event_code_column
        ) AS cid_parm,
        $partition_column AS dt
    FROM $source_table
    WHERE $partition_column >= '$start_partition'
      AND $partition_column <= '$end_partition'
      AND product_id IN (27090, 27130)
      AND UPPER(ver) NOT LIKE '%SNAPSHOT%'
      AND INSTR(
          REPLACE($event_code_column, '-', '_'),
          REPLACE('$event_code', '-', '_')
      ) > 0
) t3
LEFT OUTER JOIN biugolite_dim_cid_parm AS t4
  ON t3.cid_parm = t4.cid_parm
WHERE t3.uid NOT IN (
    SELECT DISTINCT uid
    FROM biugolite_dws_user_tag_v2
    WHERE dt = '$end_partition'
      AND SUBSTR(phone, 1, 7) = '0086111'
)
  AND t3.uid NOT IN (
      SELECT DISTINCT uid
      FROM biugolite_dwd_invalid_user_view
  )
  AND SUBSTR(FROM_UNIXTIME(time), 1, 10) = CONCAT(
      SUBSTR(t3.dt, 1, 4), '-',
      SUBSTR(t3.dt, 5, 2), '-',
      SUBSTR(t3.dt, 7, 2)
  );
