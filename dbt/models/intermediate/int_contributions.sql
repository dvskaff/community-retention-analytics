-- Every contribution by a registered user: questions, answers and comments, one row each.
select 'q' || post_id as contribution_key, owner_user_id as user_id, 'question' as contribution_type,
       post_id, post_id as question_id, created_at
from {{ ref('stg_se__posts') }}
where post_type = 'question' and owner_user_id is not null

union all

select 'a' || post_id, owner_user_id, 'answer', post_id, parent_question_id, created_at
from {{ ref('stg_se__posts') }}
where post_type = 'answer' and owner_user_id is not null

union all

select 'c' || c.comment_id, c.user_id, 'comment', c.post_id,
       case when p.post_type = 'answer' then p.parent_question_id else p.post_id end, c.created_at
from {{ ref('stg_se__comments') }} as c
left join {{ ref('stg_se__posts') }} as p using (post_id)
where c.user_id is not null
