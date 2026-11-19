select
    order_id,
    payment_sequential,
    payment_type,
    payment_installments as installments,
    payment_value as amount
from {{ source('bronze', 'order_payments') }}
