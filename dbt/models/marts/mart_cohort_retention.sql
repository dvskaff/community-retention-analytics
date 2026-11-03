-- Share of each monthly cohort of new contributors who contribute again N months after their first month.
-- Every cohort x month cell exists (zero when nobody from the cohort was active), so gaps are never ambiguous.
with w as (select * from {{ ref('int_dump_window') }}),

cohorts as (
    select user_id, first_contribution_month as cohort_month
    from {{ ref('dim_users') }} where is_contributor
),

sizes as (select cohort_month, count(*) as cohort_size from cohorts group by 1),

grid as (
    select s.cohort_month, s.cohort_size, k.months_since_first
    from sizes as s
    cross join (select unnest(range(0, 25)) as months_since_first) as k
),

activity as (
    select c.cohort_month, date_diff('month', c.cohort_month, f.created_month) as months_since_first,
           count(distinct f.user_id) as active_users
    from {{ ref('fct_contributions') }} as f
    join cohorts as c using (user_id)
    group by 1, 2
)

select
    g.cohort_month,
    g.months_since_first,
    g.cohort_size,
    coalesce(a.active_users, 0)                                         as active_users,
    coalesce(a.active_users, 0) / g.cohort_size                         as retention_rate,
    -- Only months that are fully in the past count; the current partial month would understate retention.
    g.cohort_month + to_months(g.months_since_first) < w.last_month     as is_complete
from grid as g
cross join w
left join activity as a using (cohort_month, months_since_first)
where g.cohort_month + to_months(g.months_since_first) <= w.last_month
