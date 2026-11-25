-- One row per order. Olist issues a new customer_id for every order, so the person who
-- placed it is customer_unique_id, joined in here once so no mart has to remember that.
select
    o.order_id,
    o.customer_id,
    c.customer_unique_id,
    o.order_status,
    o.order_purchase_timestamp as purchased_at,
    o.order_approved_at as approved_at,
    o.order_delivered_carrier_date as handed_to_carrier_at,
    o.order_delivered_customer_date as delivered_at,
    o.order_estimated_delivery_date as estimated_delivery_at
from {{ source('bronze', 'orders') }} as o
inner join {{ source('bronze', 'customers') }} as c using (customer_id)
