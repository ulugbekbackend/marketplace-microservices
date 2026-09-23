"""Query string filters of the product lists."""

from django.db.models import Q, QuerySet
from django_filters import rest_framework as filters

from products.models import PRODUCT_STATUS_CHOICES, Product
from products.queries import category_with_descendants


class PublicProductFilter(filters.FilterSet):  # type: ignore[misc]  # untyped library
    category = filters.CharFilter(
        method="filter_category", help_text="Category slug; products of subcategories too."
    )
    seller = filters.CharFilter(field_name="seller__slug", help_text="Shop slug.")

    class Meta:
        model = Product
        fields = ("category", "seller")

    def filter_category(
        self, queryset: QuerySet[Product], name: str, value: str
    ) -> QuerySet[Product]:
        categories = category_with_descendants(value)
        if categories is None:
            return queryset.none()
        return queryset.filter(category__in=categories)


class SellerProductFilter(filters.FilterSet):  # type: ignore[misc]  # untyped library
    status = filters.ChoiceFilter(choices=PRODUCT_STATUS_CHOICES)
    q = filters.CharFilter(method="filter_q", help_text="Search in title, slug and SKU.")

    class Meta:
        model = Product
        fields = ("status", "q")

    def filter_q(self, queryset: QuerySet[Product], name: str, value: str) -> QuerySet[Product]:
        value = value.strip()
        if not value:
            return queryset
        matching_sku = Product.objects.filter(variants__sku__iexact=value).values("id")
        return queryset.filter(
            Q(title__icontains=value) | Q(slug__icontains=value) | Q(id__in=matching_sku)
        )
