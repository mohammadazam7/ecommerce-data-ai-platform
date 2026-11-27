-- One row per review of an order. Neither id is unique alone in the source: one review
-- can cover several orders, and an order can be reviewed more than once.
select
    review_id,
    order_id,
    review_score as score,
    coalesce(trim(review_comment_message), '') <> '' as has_comment,
    review_creation_date as created_at,
    review_answer_timestamp as answered_at
from {{ source('bronze', 'order_reviews') }}
