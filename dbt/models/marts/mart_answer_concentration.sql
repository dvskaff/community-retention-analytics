-- How concentrated is answering? Answerers in the last 12 months ranked by answers, with cumulative shares.
with w as (select * from {{ ref('int_dump_window') }}),

answerers as (
    select user_id, count(*) as answers
    from {{ ref('fct_contributions') }}, w
    where contribution_type = 'answer' and created_at > w.data_end - interval 365 day
    group by user_id
)

select
    user_id,
    answers,
    row_number() over (order by answers desc, user_id)                                  as answerer_rank,
    row_number() over (order by answers desc, user_id) / count(*) over ()               as share_of_answerers,
    sum(answers) over (order by answers desc, user_id rows unbounded preceding)
        / sum(answers) over ()                                                          as cumulative_share_of_answers
from answerers
