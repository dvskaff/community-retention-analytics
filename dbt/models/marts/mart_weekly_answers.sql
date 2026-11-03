-- North-star metric: questions per week that another user answered within 7 days (help actually delivered).
with w as (select * from {{ ref('int_dump_window') }})

select
    created_week                                                       as week_start,
    count(*)                                                           as questions,
    count(*) filter (where answered_within_7d)                         as answered_within_7d,
    avg(answered_within_7d::int)                                       as share_answered_within_7d,
    median(hours_to_first_answer)                                      as median_hours_to_first_answer,
    created_week + interval 14 day <= any_value(w.data_end)            as is_complete
from {{ ref('fct_questions') }}
cross join w
group by created_week
