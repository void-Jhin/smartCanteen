from django.urls import path
from . import views

urlpatterns = [
    path("login/", views.staff_login, name="login"),
    path("logout/", views.staff_logout, name="logout"),
    path("student/login/", views.student_login, name="student_login"),
    path("student/logout/", views.student_logout, name="student_logout"),
    path("student/profile/", views.student_profile, name="student_profile"),
    path("", views.home, name="home"),
    path("topup/scan/", views.topup_scan, name="topup_scan"),
    path("topup/amount/", views.topup_amount, name="topup_amount"),
    path("buy/", views.buy_select, name="buy_select"),
    path("buy/scan/", views.buy_scan, name="buy_scan"),
    path("products/", views.product_list, name="product_list"),
    path("products/<int:item_id>/edit/", views.product_edit, name="product_edit"),
    path("dashboard/", views.dashboard, name="dashboard"),

    path("api/scan/", views.receive_scan_api, name="receive_scan_api"),
    path("api/latest-scan/", views.latest_scan_api, name="latest_scan_api"),

    path("api/student/by-rfid/", views.student_by_rfid_api, name="student_by_rfid_api"),
    path("api/menu/", views.menu_list_api, name="menu_list_api"),
    path("api/buy/", views.buy_api, name="buy_api"),
    path("api/admin-topup/", views.admin_topup_api, name="admin_topup_api"),
]
