-- Early feedback on every post: votes cast within the first week (votes are dated to the day).
select
    p.post_id,
    count(*) filter (where v.vote_type = 'upvote'
                       and v.voted_on <= cast(p.created_at as date) + {{ var('early_feedback_days') }}) as upvotes_early,
    count(*) filter (where v.vote_type = 'downvote'
                       and v.voted_on <= cast(p.created_at as date) + {{ var('early_feedback_days') }}) as downvotes_early,
    count(*) filter (where v.vote_type = 'upvote')                                                     as upvotes_total
from {{ ref('stg_se__posts') }} as p
left join {{ ref('stg_se__votes') }} as v using (post_id)
where p.post_type in ('question', 'answer')
group by p.post_id
