select
    order_id,
    order_item_id,
    product_id,
    seller_id,
    shipping_limit_date as ship_by,
    price,
    freight_value as freight
from {{ source('bronze', 'order_items') }}
