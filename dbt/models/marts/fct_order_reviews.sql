-- One row per reviewed order. When an order was reviewed more than once, the most
-- recently answered review stands for it and `reviews` says how many there were, so a
-- join to orders never fans out. Delivery against the promise is carried along because
-- the question this table exists for is how lateness changes the score.
with ranked as (
    select
        *,
        count(*) over (partition by order_id) as reviews,
        row_number() over (
            partition by order_id
            order by answered_at desc, created_at desc, review_id desc
        ) as recency
    from {{ ref('stg_order_reviews') }}
)

select
    r.order_id,
    r.review_id,
    o.customer_unique_id,
    r.score,
    r.has_comment,
    r.created_at,
    r.answered_at,
    r.reviews,
    o.delivered_late,
    date_diff(
        'day', cast(o.estimated_delivery_at as date), cast(o.delivered_at as date)
    ) as days_after_promise
from ranked as r
inner join {{ ref('fct_orders') }} as o using (order_id)
where r.recency = 1
