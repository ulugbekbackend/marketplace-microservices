from django.urls import path

from accounts import views

urlpatterns = [
    path("otp/send/", views.OtpSendView.as_view(), name="otp-send"),
    path("otp/verify/", views.OtpVerifyView.as_view(), name="otp-verify"),
    path("token/refresh/", views.TokenRefreshView.as_view(), name="token-refresh"),
    path("logout/", views.LogoutView.as_view(), name="logout"),
    path("me/", views.MeView.as_view(), name="me"),
    path("seller/apply/", views.SellerApplyView.as_view(), name="seller-apply"),
    path("seller/application/", views.SellerApplicationView.as_view(), name="seller-application"),
    path("verify/", views.VerifyView.as_view(), name="verify"),
    path(".well-known/jwks.json", views.JwksView.as_view(), name="jwks"),
    path(
        "admin/seller-applications/",
        views.AdminApplicationListView.as_view(),
        name="admin-seller-applications",
    ),
    path(
        "admin/seller-applications/<uuid:application_id>/approve/",
        views.AdminApproveView.as_view(),
        name="admin-seller-application-approve",
    ),
    path(
        "admin/seller-applications/<uuid:application_id>/reject/",
        views.AdminRejectView.as_view(),
        name="admin-seller-application-reject",
    ),
]
