SELECT uid, time, act_type, eventid, dt
FROM yy_websdkprotocol_original
WHERE dt BETWEEN '$start_partition' AND '$end_partition'
  AND eventid IN ('$event_code');
