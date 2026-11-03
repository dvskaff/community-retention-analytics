-- What happened to each question: how fast another user answered or commented, votes, closure.
with questions as (
    select * from {{ ref('stg_se__posts') }} where post_type = 'question'
),

first_answer as (
    select a.parent_question_id as post_id, min(a.created_at) as first_answer_at, count(*) as answers
    from {{ ref('stg_se__posts') }} as a
    join questions as q on q.post_id = a.parent_question_id
    where a.post_type = 'answer' and a.owner_user_id is distinct from q.owner_user_id
    group by 1
),

first_comment as (
    select c.post_id, min(c.created_at) as first_comment_at
    from {{ ref('stg_se__comments') }} as c
    join questions as q using (post_id)
    where c.user_id is distinct from q.owner_user_id
    group by 1
)

select
    q.post_id                                                                     as question_id,
    q.owner_user_id                                                               as asker_user_id,
    q.created_at,
    q.primary_tag,
    q.score,
    q.view_count,
    fa.first_answer_at,
    coalesce(fa.answers, 0)                                                       as answers_from_others,
    date_diff('second', q.created_at, fa.first_answer_at) / 3600.0                as hours_to_first_answer,
    coalesce(fa.first_answer_at <= q.created_at + interval {{ var('fast_answer_hours') }} hour, false)
                                                                                  as answered_fast,
    coalesce(fa.first_answer_at <= q.created_at + interval 7 day, false)          as answered_within_7d,
    coalesce(fc.first_comment_at <= q.created_at + interval {{ var('fast_answer_hours') }} hour, false)
                                                                                  as commented_fast,
    q.accepted_answer_id is not null                                              as has_accepted_answer,
    coalesce(q.closed_at <= q.created_at + interval 7 day, false)                 as closed_within_7d,
    coalesce(f.upvotes_early, 0)                                                  as upvotes_early,
    coalesce(f.downvotes_early, 0)                                                as downvotes_early
from questions as q
left join first_answer as fa using (post_id)
left join first_comment as fc using (post_id)
left join {{ ref('int_post_feedback') }} as f using (post_id)
