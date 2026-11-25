-- One row per person (customer_unique_id). Location is taken from their most recent
-- order, since a person can order to different addresses.
with orders as (
    select
        o.customer_unique_id,
        o.order_id,
        o.purchased_at,
        o.order_value,
        c.city,
        c.state,
        c.zip_prefix
    from {{ ref('fct_orders') }} as o
    inner join {{ ref('stg_orders') }} as s using (order_id)
    inner join {{ ref('stg_customers') }} as c on c.customer_id = s.customer_id
)

select
    customer_unique_id,
    min(purchased_at) as first_order_at,
    max(purchased_at) as last_order_at,
    count(*) as orders,
    sum(order_value) as lifetime_order_value,
    arg_max(state, purchased_at) as state,
    arg_max(city, purchased_at) as city,
    arg_max(zip_prefix, purchased_at) as zip_prefix
from orders
group by customer_unique_id
