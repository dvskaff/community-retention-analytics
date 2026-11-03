{% docs __overview__ %}
# Community retention analytics

dbt project behind [the community retention dashboard](https://dvskaff.github.io/community-retention-analytics/):
product analytics on **Cross Validated** (stats.stackexchange.com), Stack Exchange's statistics Q&A community, from
the public Stack Exchange data dump.

| Layer | What it holds |
|---|---|
| `raw` (source) | Users, Posts, Comments and Votes from the dump, as published (text) |
| `staging` | Typed, cleaned tables; the Community system account and free text removed |
| `intermediate` | Every contribution, each question's outcome, each user's first contribution and next visit |
| `marts` | `dim_users`, `fct_contributions`, `fct_questions` and the metric tables used by the dashboard |

**Definitions**

* **Contribution**: a question, answer or comment by a registered user.
* **Activated**: first contribution within 30 days of signing up.
* **Came back**: another contribution on a later calendar day, within 30 days of the first contribution.
* **Growth accounting**: each month's active contributors are new, retained (active last month) or resurrected
  (back after a gap); churned = active last month, not this month.
* **North-star metric**: questions answered by another user within 7 days.

Upvotes and downvotes are anonymous in the public dump and dated to the day, so "early" feedback means votes cast
within 7 days of a post.
{% enddocs %}
