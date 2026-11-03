-- Every active contributor must be exactly one of new, retained or resurrected,
-- and this month's actives = last month's actives - churned + new + resurrected.
with m as (
    select *, lag(active_contributors) over (order by month) as prev_active
    from {{ ref('mart_monthly_activity') }}
)
select month, active_contributors, new_contributors, retained, resurrected, churned, prev_active
from m
where active_contributors != new_contributors + retained + resurrected
   or (prev_active is not null and active_contributors != prev_active - churned + new_contributors + resurrected)
