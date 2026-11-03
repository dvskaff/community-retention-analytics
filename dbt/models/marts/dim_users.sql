{{ config(contract={'enforced': true}) }}
-- One row per registered user: signup, first contribution, whether they activated and came back, first experience.
with w as (select * from {{ ref('int_dump_window') }})

select
    u.user_id,
    u.signed_up_at,
    cast(date_trunc('month', u.signed_up_at) as date)                                      as signup_month,
    f.first_at                                                                              as first_contribution_at,
    cast(date_trunc('month', f.first_at) as date)                                           as first_contribution_month,
    f.first_type                                                                            as first_contribution_type,
    cast(date_diff('second', u.signed_up_at, f.first_at) / 86400.0 as double)                              as days_signup_to_first,
    f.first_at is not null                                                                  as is_contributor,
    coalesce(f.first_at <= u.signed_up_at + interval {{ var('activation_window_days') }} day, false)
                                                                                            as activated,
    f.next_at                                                                               as next_visit_at,
    cast(date_diff('second', f.first_at, f.next_at) / 86400.0 as double)                                   as days_to_next_visit,
    coalesce(cast(f.next_at as date) <= cast(f.first_at as date) + {{ var('return_window_days') }}, false)
                                                                                            as came_back,
    -- Days the user could be observed after their first contribution (needed to judge "came back" fairly).
    cast(date_diff('second', f.first_at, w.data_end) / 86400.0 as double)                                  as follow_up_days,
    coalesce(f.contributions, 0)                                                            as contributions,
    coalesce(f.active_days, 0)                                                              as active_days,
    coalesce(f.active_months, 0)                                                            as active_months,
    f.last_at                                                                               as last_contribution_at,
    f.first_q_answered_fast,
    f.first_q_commented_fast,
    f.first_q_upvoted_early,
    f.first_q_downvoted_early,
    f.first_q_closed_7d,
    f.first_a_upvoted_early,
    f.first_a_accepted
from {{ ref('stg_se__users') }} as u
left join {{ ref('int_user_firsts') }} as f using (user_id)
cross join w
