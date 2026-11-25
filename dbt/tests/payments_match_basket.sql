-- Payments should equal items plus freight. Olist has a known few hundred orders where
-- they differ (vouchers, instalment interest), so this fails only if more than 1% of
-- orders with items disagree by over a cent, which would point to a join fan-out.
with checked as (
    select abs(paid - order_value) > 0.01 as differs
    from {{ ref('fct_orders') }}
    where items > 0 and paid is not null
)
select count(*) filter (where differs) as differing, count(*) as orders
from checked
having count(*) filter (where differs) > 0.01 * count(*)
