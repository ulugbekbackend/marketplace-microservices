from django.urls import path

from orders import seller_views, views

urlpatterns = [
    path("", views.OrderListView.as_view(), name="order-list"),
    path("checkout/", views.CheckoutView.as_view(), name="order-checkout"),
    path("seller/", seller_views.SellerSubOrderListView.as_view(), name="seller-order-list"),
    path("seller/stats/", seller_views.SellerStatsView.as_view(), name="seller-order-stats"),
    path(
        "seller/<uuid:sub_order_id>/",
        seller_views.SellerSubOrderDetailView.as_view(),
        name="seller-order-detail",
    ),
    path(
        "seller/<uuid:sub_order_id>/status/",
        seller_views.SellerSubOrderStatusView.as_view(),
        name="seller-order-status",
    ),
    path("<uuid:order_id>/", views.OrderDetailView.as_view(), name="order-detail"),
    path("<uuid:order_id>/status/", views.OrderStatusView.as_view(), name="order-status"),
    path("<uuid:order_id>/cancel/", views.OrderCancelView.as_view(), name="order-cancel"),
    path("<uuid:order_id>/pay/mock/", views.MockPayView.as_view(), name="order-pay-mock"),
]
