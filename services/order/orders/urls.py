from django.urls import path

from orders import views

urlpatterns = [
    path("", views.OrderListView.as_view(), name="order-list"),
    path("checkout/", views.CheckoutView.as_view(), name="order-checkout"),
    path("<uuid:order_id>/", views.OrderDetailView.as_view(), name="order-detail"),
    path("<uuid:order_id>/status/", views.OrderStatusView.as_view(), name="order-status"),
    path("<uuid:order_id>/cancel/", views.OrderCancelView.as_view(), name="order-cancel"),
    path("<uuid:order_id>/pay/mock/", views.MockPayView.as_view(), name="order-pay-mock"),
]
