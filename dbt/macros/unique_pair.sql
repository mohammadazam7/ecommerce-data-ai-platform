{% test unique_combination(model, columns) %}
-- Rows whose combination of `columns` appears more than once.
select {{ columns | join(', ') }}, count(*) as n
from {{ model }}
group by {{ columns | join(', ') }}
having count(*) > 1
{% endtest %}
