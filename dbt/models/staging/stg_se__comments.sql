select
    try_cast(Id as integer)                                          as comment_id,
    try_cast(PostId as integer)                                      as post_id,
    case when try_cast(UserId as integer) > 0 then try_cast(UserId as integer) end as user_id,
    try_cast(CreationDate as timestamp)                              as created_at,
    try_cast(Score as integer)                                       as score
from {{ source('stackexchange', 'comments') }}
where try_cast(CreationDate as timestamp) is not null
