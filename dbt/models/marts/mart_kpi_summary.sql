-- One row of headline numbers for the dashboard and README.
with w as (select * from {{ ref('int_dump_window') }}),

recent_newcomers as (
    -- Newcomers in the 12 months ending 31 days before the data ends, so each has 30 days of follow-up.
    select u.* from {{ ref('dim_users') }} as u, w
    where u.is_contributor
      and u.first_contribution_at > w.data_end - interval 396 day
      and u.first_contribution_at <= w.data_end - interval 31 day
),

c as (select * from {{ ref('fct_contributions') }}),

conc as (
    select
        min(cumulative_share_of_answers) filter (where share_of_answerers >= 0.01)  as top1pct_share,
        min(cumulative_share_of_answers) filter (where share_of_answerers >= 0.10)  as top10pct_share,
        count(*)                                                                     as answerers_12m
    from {{ ref('mart_answer_concentration') }}
),

q as (
    select
        count(*) filter (where created_at > w.data_end - interval 365 day)                         as questions_12m,
        count(*) filter (where created_at > w.data_end - interval 730 day
                           and created_at <= w.data_end - interval 365 day)                        as questions_prior_12m,
        avg(answered_within_7d::int) filter (where created_at > w.data_end - interval 372 day
                                               and created_at <= w.data_end - interval 7 day)      as share_answered_7d,
        median(hours_to_first_answer) filter (where created_at > w.data_end - interval 372 day
                                                and created_at <= w.data_end - interval 7 day)     as median_hours_to_answer
    from {{ ref('fct_questions') }}, w
)

select
    any_value(w.data_start)                                                                   as data_start,
    any_value(w.data_end)                                                                     as data_end,
    (select count(*) from {{ ref('dim_users') }})                                             as registered_users,
    (select count(*) from {{ ref('dim_users') }} where is_contributor)                        as contributors_all_time,
    (select count(*) from c)                                                                  as contributions_all_time,
    (select count(distinct user_id) from c, w where c.created_at > w.data_end - interval 365 day)
                                                                                              as active_contributors_12m,
    (select count(*) from recent_newcomers)                                                   as newcomers_12m,
    (select avg(came_back::int) from recent_newcomers)                                        as newcomer_came_back_rate,
    any_value(q.questions_12m)                                                                as questions_12m,
    any_value(q.questions_prior_12m)                                                          as questions_prior_12m,
    any_value(q.share_answered_7d)                                                            as share_answered_7d,
    any_value(q.median_hours_to_answer)                                                       as median_hours_to_answer,
    any_value(conc.top1pct_share)                                                             as top1pct_answer_share,
    any_value(conc.top10pct_share)                                                            as top10pct_answer_share,
    any_value(conc.answerers_12m)                                                             as answerers_12m
from w, q, conc
