-- The fact table holds every question, answer and comment by a registered user, no more and no less.
with expected as (
    select
        (select count(*) from {{ ref('stg_se__posts') }}
          where post_type in ('question', 'answer') and owner_user_id is not null)
      + (select count(*) from {{ ref('stg_se__comments') }} where user_id is not null) as n
)
select expected.n as expected_rows, (select count(*) from {{ ref('fct_contributions') }}) as fact_rows
from expected
where expected.n != (select count(*) from {{ ref('fct_contributions') }})
