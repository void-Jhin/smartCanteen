from django.contrib import admin
from .models import Student, MenuItem, Transaction, LatestScan


@admin.register(Student)
class StudentAdmin(admin.ModelAdmin):
    list_display = ("student_id", "full_name", "rfid_uid", "student_pin", "balance", "active")
    search_fields = ("student_id", "full_name", "rfid_uid", "student_pin")


@admin.register(MenuItem)
class MenuItemAdmin(admin.ModelAdmin):
    list_display = ("name", "price", "available")
    search_fields = ("name",)


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = ("student", "transaction_type", "amount", "menu_item", "balance_before", "balance_after", "created_at")
    list_filter = ("transaction_type", "created_at")
    search_fields = ("student__full_name", "student__student_id", "menu_item__name")


@admin.register(LatestScan)
class LatestScanAdmin(admin.ModelAdmin):
    list_display = ("key", "uid", "timestamp", "updated_at")
