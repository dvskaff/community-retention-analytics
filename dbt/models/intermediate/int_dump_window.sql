{{ config(materialized='ephemeral') }}
-- The period the dump covers, defined once. data_end = the latest activity in the dump.
select
    min(created_at)                                   as data_start,
    max(created_at)                                   as data_end,
    cast(date_trunc('month', max(created_at)) as date) as last_month
from {{ ref('int_contributions') }}
