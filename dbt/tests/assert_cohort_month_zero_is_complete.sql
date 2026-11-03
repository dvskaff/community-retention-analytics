-- By definition every new contributor is active in their first month: month-0 retention must be 100%.
select cohort_month, retention_rate
from {{ ref('mart_cohort_retention') }}
where months_since_first = 0 and retention_rate != 1
