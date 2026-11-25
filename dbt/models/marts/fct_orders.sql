-- One row per order with its basket, what was paid, and how delivery went against the
-- date promised at checkout. Orders with no items (canceled or unavailable before
-- picking) are kept with zero totals, so counts match the orders table.
with items as (
    select
        order_id,
        count(*) as items,
        count(distinct seller_id) as sellers,
        sum(price) as item_value,
        sum(freight) as freight_value
    from {{ ref('stg_order_items') }}
    group by order_id
),

payments as (
    select
        order_id,
        sum(amount) as paid,
        max(installments) as installments,
        arg_max(payment_type, amount) as main_payment_type
    from {{ ref('stg_order_payments') }}
    group by order_id
)

select
    o.order_id,
    o.customer_unique_id,
    o.order_status,
    o.purchased_at,
    cast(o.purchased_at as date) as purchase_date,
    coalesce(i.items, 0) as items,
    coalesce(i.sellers, 0) as sellers,
    coalesce(i.item_value, 0) as item_value,
    coalesce(i.freight_value, 0) as freight_value,
    coalesce(i.item_value, 0) + coalesce(i.freight_value, 0) as order_value,
    p.paid,
    p.installments,
    p.main_payment_type,
    o.delivered_at,
    o.estimated_delivery_at,
    date_diff('hour', o.purchased_at, o.delivered_at) / 24.0 as days_to_deliver,
    case
        when o.delivered_at is null then null
        else cast(o.delivered_at as date) > cast(o.estimated_delivery_at as date)
    end as delivered_late
from {{ ref('stg_orders') }} as o
left join items as i using (order_id)
left join payments as p using (order_id)
