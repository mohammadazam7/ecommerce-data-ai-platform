select
    seller_id,
    seller_zip_code_prefix as zip_prefix,
    seller_city as city,
    seller_state as state
from {{ source('bronze', 'sellers') }}
