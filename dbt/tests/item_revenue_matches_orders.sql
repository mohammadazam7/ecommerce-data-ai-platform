-- The item fact and the order fact are built separately from the same items; if their
-- totals drift apart, one of the joins is dropping or repeating rows.
with by_items as (
    select sum(price) + sum(freight) as total from {{ ref('fct_order_items') }}
),

by_orders as (
    select sum(order_value) as total from {{ ref('fct_orders') }}
)

select by_items.total as from_items, by_orders.total as from_orders
from by_items, by_orders
where abs(by_items.total - by_orders.total) > 0.01
