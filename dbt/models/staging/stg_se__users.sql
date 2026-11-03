-- Registered users. The "Community" system account (Id -1) is not a person and is dropped.
select
    try_cast(Id as integer)                       as user_id,
    try_cast(CreationDate as timestamp)           as signed_up_at,
    try_cast(Reputation as integer)               as reputation,
    try_cast(LastAccessDate as timestamp)         as last_access_at,
    try_cast(AccountId as bigint)                 as account_id
from {{ source('stackexchange', 'users') }}
where try_cast(Id as integer) > 0
