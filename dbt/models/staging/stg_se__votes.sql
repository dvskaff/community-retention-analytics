-- Votes are anonymous in the public dump (no voter for up/down votes) and dated to the day.
select
    try_cast(Id as bigint)                                           as vote_id,
    try_cast(PostId as integer)                                      as post_id,
    try_cast(VoteTypeId as integer)                                  as vote_type_id,
    case try_cast(VoteTypeId as integer)
        when 1 then 'accepted' when 2 then 'upvote' when 3 then 'downvote' when 5 then 'favorite'
        when 6 then 'close' when 7 then 'reopen' when 8 then 'bounty_start' when 9 then 'bounty_close'
        else 'other'
    end                                                              as vote_type,
    cast(try_cast(CreationDate as timestamp) as date)                as voted_on
from {{ source('stackexchange', 'votes') }}
