-- One row per product with what it sold. Items of canceled and unavailable orders are
-- not counted as sales. A product that never sold is kept with zeros.
with sales as (
    select
        product_id,
        count(*) as items_sold,
        count(distinct order_id) as orders,
        sum(price) as revenue,
        min(purchased_at) as first_sold_at,
        max(purchased_at) as last_sold_at
    from {{ ref('fct_order_items') }}
    where order_status not in ('canceled', 'unavailable')
    group by product_id
)

select
    p.product_id,
    p.category,
    p.category_english,
    p.weight_g,
    p.volume_cm3,
    p.photos,
    coalesce(s.items_sold, 0) as items_sold,
    coalesce(s.orders, 0) as orders,
    coalesce(s.revenue, 0) as revenue,
    s.first_sold_at,
    s.last_sold_at
from {{ ref('stg_products') }} as p
left join sales as s using (product_id)
