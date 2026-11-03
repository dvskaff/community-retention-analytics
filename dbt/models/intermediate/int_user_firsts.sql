-- Each contributor's first contribution, their next one, and what their first experience looked like.
with ordered as (
    select *, row_number() over (partition by user_id order by created_at, contribution_key) as n
    from {{ ref('int_contributions') }}
),

firsts as (
    select user_id, contribution_type as first_type, post_id as first_post_id, created_at as first_at
    from ordered where n = 1
),

next_after_first_day as (
    -- The next contribution on a later calendar day (several posts in one sitting count as one visit).
    select o.user_id, min(o.created_at) as next_at
    from ordered as o
    join firsts as f using (user_id)
    where cast(o.created_at as date) > cast(f.first_at as date)
    group by o.user_id
),

totals as (
    select user_id, count(*) as contributions, count(distinct cast(created_at as date)) as active_days,
           count(distinct date_trunc('month', created_at)) as active_months, max(created_at) as last_at
    from ordered group by user_id
)

select
    f.user_id,
    f.first_type,
    f.first_post_id,
    f.first_at,
    n.next_at,
    t.contributions,
    t.active_days,
    t.active_months,
    t.last_at,
    -- First-experience signals, only defined for the matching kind of first contribution.
    case when f.first_type = 'question' then q.answered_fast end                     as first_q_answered_fast,
    case when f.first_type = 'question' then q.commented_fast end                    as first_q_commented_fast,
    case when f.first_type = 'question' then q.upvotes_early > 0 end                 as first_q_upvoted_early,
    case when f.first_type = 'question' then q.downvotes_early > 0 end               as first_q_downvoted_early,
    case when f.first_type = 'question' then q.closed_within_7d end                  as first_q_closed_7d,
    case when f.first_type = 'answer' then pf.upvotes_early > 0 end                  as first_a_upvoted_early,
    case when f.first_type = 'answer' then pa.accepted_answer_id is not null end     as first_a_accepted
from firsts as f
join totals as t using (user_id)
left join next_after_first_day as n using (user_id)
left join {{ ref('int_question_outcomes') }} as q on f.first_type = 'question' and q.question_id = f.first_post_id
left join {{ ref('int_post_feedback') }} as pf on f.first_type = 'answer' and pf.post_id = f.first_post_id
left join {{ ref('stg_se__posts') }} as pa on f.first_type = 'answer' and pa.accepted_answer_id = f.first_post_id
