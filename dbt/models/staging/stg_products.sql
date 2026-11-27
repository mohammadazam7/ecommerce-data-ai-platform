-- One row per product. Category names are Portuguese in the source; the translation
-- table covers all but two of them, and those keep their Portuguese name instead of
-- becoming null. About 2% of products have no category at all and stay null.
select
    p.product_id,
    p.product_category_name as category,
    coalesce(t.product_category_name_english, p.product_category_name) as category_english,
    p.product_weight_g as weight_g,
    p.product_length_cm * p.product_height_cm * p.product_width_cm as volume_cm3,
    p.product_photos_qty as photos
from {{ source('bronze', 'products') }} as p
left join {{ source('bronze', 'category_translation') }} as t using (product_category_name)
