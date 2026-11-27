-- One row per seller: what they sold, how often their orders arrived late, and how
-- their orders were reviewed.
--
-- A review belongs to an order, not to a seller. For an order with several sellers
-- there is no telling whose item the score is about, so the review average uses only
-- orders where this seller was the only one.
with seller_orders as (
    select distinct seller_id, order_id
    from {{ ref('fct_order_items') }}
),

sales as (
    select
        seller_id,
        count(distinct order_id) as orders,
        count(*) as items,
        sum(price) as revenue,
        min(purchased_at) as first_sale_at,
        max(purchased_at) as last_sale_at
    from {{ ref('fct_order_items') }}
    where order_status not in ('canceled', 'unavailable')
    group by seller_id
),

delivery as (
    select
        so.seller_id,
        count(o.delivered_late) as delivered_orders,
        avg(cast(o.delivered_late as integer)) as late_share
    from seller_orders as so
    inner join {{ ref('fct_orders') }} as o using (order_id)
    group by so.seller_id
),

reviews as (
    select
        so.seller_id,
        count(*) as reviewed_orders,
        avg(r.score) as review_score
    from seller_orders as so
    inner join {{ ref('fct_orders') }} as o using (order_id)
    inner join {{ ref('fct_order_reviews') }} as r using (order_id)
    where o.sellers = 1
    group by so.seller_id
)

select
    s.seller_id,
    s.city,
    s.state,
    coalesce(sales.orders, 0) as orders,
    coalesce(sales.items, 0) as items,
    coalesce(sales.revenue, 0) as revenue,
    sales.first_sale_at,
    sales.last_sale_at,
    coalesce(d.delivered_orders, 0) as delivered_orders,
    d.late_share,
    coalesce(r.reviewed_orders, 0) as reviewed_orders,
    r.review_score
from {{ ref('stg_sellers') }} as s
left join sales using (seller_id)
left join delivery as d using (seller_id)
left join reviews as r using (seller_id)
