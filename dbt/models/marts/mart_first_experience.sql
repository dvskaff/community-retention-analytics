{#-
    The "aha moment" table: for recent newcomers (with a full 30 days of follow-up), the share who came back,
    split by what happened on their first contribution. One row per signal x yes/no.
-#}
with w as (select * from {{ ref('int_dump_window') }}),

newcomers as (
    select u.*
    from {{ ref('dim_users') }} as u, w
    where u.is_contributor
      and u.first_contribution_at >= w.data_end - interval {{ var('experience_window_years') }} year
      and u.follow_up_days >= {{ var('return_window_days') }} + 1
),

signals as (
    unpivot (
        select user_id, came_back, first_contribution_type,
               first_q_answered_fast, first_q_commented_fast, first_q_upvoted_early, first_q_downvoted_early,
               first_q_closed_7d, first_a_upvoted_early, first_a_accepted
        from newcomers
    )
    on first_q_answered_fast, first_q_commented_fast, first_q_upvoted_early, first_q_downvoted_early,
       first_q_closed_7d, first_a_upvoted_early, first_a_accepted
    into name signal value has_signal
)

select
    signal,
    case when signal like 'first_q_%' then 'question' else 'answer' end   as first_contribution_type,
    has_signal,
    count(*)                                                              as newcomers,
    count(*) filter (where came_back)                                     as came_back,
    avg(came_back::int)                                                   as came_back_rate
from signals
group by all

union all

select 'all_newcomers', first_contribution_type, true, count(*), count(*) filter (where came_back),
       avg(came_back::int)
from newcomers
group by first_contribution_type
