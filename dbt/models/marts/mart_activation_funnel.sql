-- Funnel by signup year: sign up -> first contribution within 30 days -> come back within 30 days -> still active
-- six months later. Each step is a share of all signups that year.
with w as (select * from {{ ref('int_dump_window') }})

select
    year(u.signed_up_at)                                                                          as signup_year,
    count(*)                                                                                       as signups,
    count(*) filter (where u.activated)                                                            as activated,
    count(*) filter (where u.activated and u.came_back)                                            as came_back,
    count(*) filter (where u.activated and u.last_contribution_at >= u.first_contribution_at + interval 180 day)
                                                                                                   as active_after_6_months,
    -- Signups from the last ~7 months have not had time to reach every step.
    max(u.signed_up_at) + interval 210 day <= any_value(w.data_end)                                as is_complete
from {{ ref('dim_users') }} as u
cross join w
group by 1
