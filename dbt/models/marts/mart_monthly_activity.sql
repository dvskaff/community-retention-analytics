{#-
    Growth accounting per month. Every active contributor in a month is exactly one of:
      new (first contribution ever), retained (also active last month) or resurrected (back after a gap).
    Churned = active last month but not this month. Quick ratio = (new + resurrected) / churned:
    above 1 the active community is growing, below 1 it is shrinking.
-#}
with w as (select * from {{ ref('int_dump_window') }}),

user_months as (
    select distinct user_id, created_month as month from {{ ref('fct_contributions') }}
),

classified as (
    select
        user_id,
        month,
        lag(month) over (partition by user_id order by month)  as prev_month,
        lead(month) over (partition by user_id order by month) as next_month
    from user_months
),

active as (
    select
        month,
        count(*)                                                                         as active_contributors,
        count(*) filter (where prev_month is null)                                       as new_contributors,
        count(*) filter (where prev_month = month - interval 1 month)                    as retained,
        count(*) filter (where prev_month < month - interval 1 month)                    as resurrected
    from classified
    group by month
),

churn as (
    -- Users active in a month who are not active the following month churn in that following month.
    select cast(month + interval 1 month as date) as month, count(*) as churned
    from classified
    where next_month is null or next_month > month + interval 1 month
    group by 1
),

volume as (
    select
        created_month as month,
        count(*) filter (where contribution_type = 'question')   as questions,
        count(*) filter (where contribution_type = 'answer')     as answers,
        count(*) filter (where contribution_type = 'comment')    as comments
    from {{ ref('fct_contributions') }}
    group by 1
),

signups as (
    select signup_month as month, count(*) as signups from {{ ref('dim_users') }} group by 1
),

months as (
    select cast(unnest(generate_series(
        cast(date_trunc('month', w.data_start) as date), w.last_month, interval 1 month)) as date) as month
    from w
)

select
    m.month,
    coalesce(v.questions, 0)                                   as questions,
    coalesce(v.answers, 0)                                     as answers,
    coalesce(v.comments, 0)                                    as comments,
    coalesce(s.signups, 0)                                     as signups,
    coalesce(a.active_contributors, 0)                         as active_contributors,
    coalesce(a.new_contributors, 0)                            as new_contributors,
    coalesce(a.retained, 0)                                    as retained,
    coalesce(a.resurrected, 0)                                 as resurrected,
    coalesce(c.churned, 0)                                     as churned,
    (coalesce(a.new_contributors, 0) + coalesce(a.resurrected, 0)) / nullif(c.churned, 0) as quick_ratio,
    m.month < w.last_month                                     as is_complete_month
from months as m
cross join w
left join active as a using (month)
left join churn as c using (month)
left join volume as v using (month)
left join signups as s using (month)
