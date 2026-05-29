from django.db import models
from django.utils import timezone


class Student(models.Model):
    student_id = models.CharField(max_length=30, unique=True)
    full_name = models.CharField(max_length=120)
    rfid_uid = models.CharField(max_length=100, unique=True)
    student_pin = models.CharField(max_length=20, blank=True, default="")
    balance = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return f"{self.full_name} ({self.student_id})"


class MenuItem(models.Model):
    name = models.CharField(max_length=120)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    available = models.BooleanField(default=True)
    created_at = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return f"{self.name} - {self.price}"


class Transaction(models.Model):
    TRANSACTION_TYPES = (
        ("TOPUP", "Top Up"),
        ("BUY", "Buy"),
    )

    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="transactions")
    transaction_type = models.CharField(max_length=10, choices=TRANSACTION_TYPES)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    menu_item = models.ForeignKey(
        MenuItem,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="transactions"
    )
    balance_before = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    balance_after = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    created_at = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return f"{self.student.full_name} - {self.transaction_type} - {self.amount}"


class LatestScan(models.Model):
    key = models.CharField(max_length=40, unique=True, default="rfid")
    uid = models.CharField(max_length=100, blank=True, default="")
    timestamp = models.FloatField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.uid or "No scan"
