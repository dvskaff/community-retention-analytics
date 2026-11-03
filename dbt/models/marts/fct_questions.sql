-- Grain: one question, with how the community responded.
select
    q.*,
    cast(date_trunc('week', q.created_at) as date) as created_week,
    cast(date_trunc('month', q.created_at) as date) as created_month
from {{ ref('int_question_outcomes') }} as q
