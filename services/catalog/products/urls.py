from django.urls import path

from products import views

urlpatterns = [
    path("categories/", views.CategoryTreeView.as_view(), name="category-tree"),
    path("products/", views.PublicProductListView.as_view(), name="product-list"),
    path("products/<slug:slug>/", views.PublicProductDetailView.as_view(), name="product-detail"),
    path("shops/<slug:slug>/", views.ShopDetailView.as_view(), name="shop-detail"),
    path("attributes/", views.AttributeListView.as_view(), name="attribute-list"),
    path(
        "seller/products/",
        views.SellerProductListCreateView.as_view(),
        name="seller-product-list",
    ),
    path(
        "seller/products/<uuid:product_id>/",
        views.SellerProductDetailView.as_view(),
        name="seller-product-detail",
    ),
    path(
        "seller/products/<uuid:product_id>/variants/",
        views.SellerVariantCreateView.as_view(),
        name="seller-variant-create",
    ),
    path(
        "seller/products/<uuid:product_id>/images/",
        views.ProductImageCreateView.as_view(),
        name="seller-image-create",
    ),
    path(
        "seller/variants/<uuid:variant_id>/",
        views.SellerVariantUpdateView.as_view(),
        name="seller-variant-update",
    ),
    path(
        "seller/variants/<uuid:variant_id>/stock/",
        views.SellerVariantStockView.as_view(),
        name="seller-variant-stock",
    ),
    path("seller/uploads/presign/", views.PresignUploadView.as_view(), name="seller-presign"),
]
