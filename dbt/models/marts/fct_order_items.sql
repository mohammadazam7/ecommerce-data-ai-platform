-- One row per item in an order, with what the analyses slice by already joined in: who
-- bought it, when, which category it is and where the seller is.
select
    i.order_id,
    i.order_item_id,
    i.product_id,
    i.seller_id,
    o.customer_unique_id,
    o.order_status,
    o.purchased_at,
    i.price,
    i.freight,
    p.category_english,
    s.state as seller_state
from {{ ref('stg_order_items') }} as i
inner join {{ ref('fct_orders') }} as o using (order_id)
left join {{ ref('stg_products') }} as p using (product_id)
left join {{ ref('stg_sellers') }} as s using (seller_id)
