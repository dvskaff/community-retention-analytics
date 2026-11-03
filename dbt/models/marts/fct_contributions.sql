{{ config(contract={'enforced': true}) }}
-- Grain: one contribution (question, answer or comment) by a registered user.
select
    c.contribution_key,
    c.user_id,
    c.contribution_type,
    c.post_id,
    c.question_id,
    c.created_at,
    cast(c.created_at as date)                               as created_date,
    cast(date_trunc('month', c.created_at) as date)          as created_month
from {{ ref('int_contributions') }} as c
