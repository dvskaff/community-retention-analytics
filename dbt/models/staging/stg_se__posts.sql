-- Questions and answers (other post types such as tag wikis are labeled 'other'). Owner is NULL for deleted users.
with posts as (
    select
        try_cast(Id as integer)                                      as post_id,
        case PostTypeId when '1' then 'question' when '2' then 'answer' else 'other' end as post_type,
        try_cast(ParentId as integer)                                as parent_question_id,
        try_cast(AcceptedAnswerId as integer)                        as accepted_answer_id,
        case when try_cast(OwnerUserId as integer) > 0 then try_cast(OwnerUserId as integer) end as owner_user_id,
        try_cast(CreationDate as timestamp)                          as created_at,
        try_cast(Score as integer)                                   as score,
        try_cast(ViewCount as integer)                               as view_count,
        try_cast(AnswerCount as integer)                             as answer_count,
        try_cast(CommentCount as integer)                            as comment_count,
        try_cast(ClosedDate as timestamp)                            as closed_at,
        -- Tags are published as "|a|b|" (newer dumps) or "<a><b>" (older dumps); normalize to a list.
        list_filter(string_split(regexp_replace(coalesce(Tags, ''), '[<>|]+', '|', 'g'), '|'), lambda x: x != '') as tags
    from {{ source('stackexchange', 'posts') }}
)

select *, tags[1] as primary_tag
from posts
where created_at is not null
