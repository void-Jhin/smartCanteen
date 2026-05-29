import json
from datetime import timedelta
from decimal import Decimal, InvalidOperation
from time import time
from django.conf import settings
from django.contrib import messages
from django.db import transaction as db_transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from collections import OrderedDict
from .forms import TopUpForm, AdminPasswordForm, BuySelectForm, StudentLoginForm, MenuItemForm
from .models import LatestScan, Student, MenuItem, Transaction
from django.db.models import Count, Sum


def require_staff_login(view_func):
    def wrapped(request, *args, **kwargs):
        if not request.session.get("staff_logged_in"):
            return redirect(f"{settings.LOGIN_URL}?next={request.path}")
        return view_func(request, *args, **kwargs)

    return wrapped


def require_student_login(view_func):
    def wrapped(request, *args, **kwargs):
        if not request.session.get("student_logged_in"):
            return redirect("student_login")
        return view_func(request, *args, **kwargs)

    return wrapped


def staff_login(request):
    if request.session.get("staff_logged_in"):
        return redirect("home")

    next_url = request.GET.get("next") or request.POST.get("next") or "home"

    if request.method == "POST":
        username = request.POST.get("username", "").strip().lower()
        password = request.POST.get("password", "").strip()
        account = settings.CANTEEN_LOGIN_ACCOUNTS.get(username)

        if account and password == account["password"]:
            request.session.flush()
            request.session["staff_logged_in"] = True
            request.session["staff_username"] = username
            request.session["staff_role"] = account["role"]
            messages.success(request, f"Welcome, {account['role']}.")
            return redirect(next_url)

        messages.error(request, "Invalid username or password.")

    return render(request, "login.html", {"next": next_url})


def student_login(request):
    if request.session.get("student_logged_in"):
        return redirect("student_profile")

    form = StudentLoginForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        student_id = form.cleaned_data["student_id"].strip()
        student_pin = form.cleaned_data["student_pin"].strip()

        student = Student.objects.filter(student_id=student_id, active=True).first()
        if student and student.student_pin == student_pin:
            request.session.flush()
            request.session["student_logged_in"] = True
            request.session["student_id"] = student.id
            messages.success(request, f"Welcome, {student.full_name}.")
            return redirect("student_profile")

        messages.error(request, "Invalid student ID or password.")

    return render(request, "student_login.html", {"form": form, "hide_session_bar": True})


def student_logout(request):
    request.session.flush()
    messages.success(request, "You have been logged out.")
    return redirect("student_login")


def staff_logout(request):
    request.session.flush()
    messages.success(request, "You have been logged out.")
    return redirect("login")


@require_student_login
def student_profile(request):
    student = get_object_or_404(Student, id=request.session.get("student_id"), active=True)
    transactions = student.transactions.select_related("menu_item").order_by("-created_at")
    total_topup = transactions.filter(transaction_type="TOPUP").aggregate(total=Sum("amount"))["total"] or Decimal("0.00")
    total_spent = transactions.filter(transaction_type="BUY").aggregate(total=Sum("amount"))["total"] or Decimal("0.00")

    return render(request, "student_profile.html", {
        "student": student,
        "transactions": transactions,
        "total_topup": total_topup,
        "total_spent": total_spent,
        "hide_session_bar": True,
    })


@require_staff_login
def home(request):
    students = Student.objects.filter(active=True).order_by("full_name")
    menu_items = MenuItem.objects.all().order_by("name")
    transactions = Transaction.objects.select_related("student", "menu_item").order_by("-created_at")
    today = timezone.localdate()
    today_transactions = transactions.filter(created_at__date=today)
    today_topups = today_transactions.filter(transaction_type="TOPUP")
    today_sales = today_transactions.filter(transaction_type="BUY")
    today_topup_total = today_topups.aggregate(total=Sum("amount"))["total"] or Decimal("0.00")
    today_sales_total = today_sales.aggregate(total=Sum("amount"))["total"] or Decimal("0.00")
    today_food_count = today_sales.count()
    recent_transactions = transactions[:5]
    popular_items = (
        Transaction.objects
        .filter(transaction_type="BUY", menu_item__isnull=False)
        .values("menu_item__name")
        .annotate(count=Count("id"), total=Sum("amount"))
        .order_by("-count", "-total")[:4]
    )

    return render(request, "home.html", {
        "students": students,
        "menu_items": menu_items,
        "today_topup_total": today_topup_total,
        "today_sales_total": today_sales_total,
        "today_transaction_count": today_transactions.count(),
        "today_food_count": today_food_count,
        "recent_transactions": recent_transactions,
        "popular_items": popular_items,
        "hide_session_bar": True,
    })


@require_staff_login
def product_list(request):
    items = MenuItem.objects.all().order_by("name")
    form = MenuItemForm()

    if request.method == "POST":
        action = request.POST.get("action", "add")

        if action == "add":
            form = MenuItemForm(request.POST)
            if form.is_valid():
                form.save()
                messages.success(request, "Product added successfully.")
                return redirect("product_list")
            messages.error(request, "Please fix the product details.")

        elif action == "toggle":
            item = get_object_or_404(MenuItem, id=request.POST.get("item_id"))
            item.available = not item.available
            item.save(update_fields=["available"])
            status = "available" if item.available else "unavailable"
            messages.success(request, f"{item.name} is now {status}.")
            return redirect("product_list")

        elif action == "delete":
            item = get_object_or_404(MenuItem, id=request.POST.get("item_id"))
            item.delete()
            messages.success(request, "Product deleted.")
            return redirect("product_list")

    return render(request, "product_list.html", {
        "items": items,
        "form": form,
        "hide_session_bar": True,
    })


@require_staff_login
def product_edit(request, item_id):
    item = get_object_or_404(MenuItem, id=item_id)
    form = MenuItemForm(request.POST or None, instance=item)

    if request.method == "POST":
        if form.is_valid():
            form.save()
            messages.success(request, "Product updated successfully.")
            return redirect("product_list")
        messages.error(request, "Please fix the product details.")

    return render(request, "product_edit.html", {
        "item": item,
        "form": form,
        "hide_session_bar": True,
    })

@csrf_exempt
def receive_scan_api(request):
    if request.method != "POST":
        return JsonResponse({"ok": False, "error": "POST required"}, status=405)

    try:
        data = json.loads(request.body.decode("utf-8"))
        uid = data.get("uid", "").strip()

        if not uid:
            return JsonResponse({"ok": False, "error": "UID is required"}, status=400)

        LatestScan.objects.update_or_create(
            key="rfid",
            defaults={
                "uid": uid,
                "timestamp": time(),
            },
        )

        return JsonResponse({"ok": True, "uid": uid})

    except json.JSONDecodeError:
        return JsonResponse({"ok": False, "error": "Invalid JSON"}, status=400)
    except Exception as e:
        return JsonResponse({"ok": False, "error": str(e)}, status=500)


def latest_scan_api(request):
    try:
        scan = LatestScan.objects.filter(key="rfid").first()
        uid = scan.uid if scan else ""

        if uid:
            LatestScan.objects.filter(key="rfid").update(uid="", timestamp=0)

        return JsonResponse({"uid": uid})

    except Exception:
        return JsonResponse({"uid": ""})


def clear_scan_file():
    try:
        LatestScan.objects.update_or_create(
            key="rfid",
            defaults={
                "uid": "",
                "timestamp": 0,
            },
        )
    except Exception:
        pass


@csrf_exempt
def student_by_rfid_api(request):
    if request.method != "POST":
        return JsonResponse({"ok": False, "error": "POST required"}, status=405)

    try:
        data = json.loads(request.body.decode("utf-8"))
        uid = data.get("uid", "").strip()

        if not uid:
            return JsonResponse({"ok": False, "error": "UID is required"}, status=400)

        try:
            student = Student.objects.get(rfid_uid=uid, active=True)
        except Student.DoesNotExist:
            return JsonResponse({"ok": False, "error": "RFID card not recognized"}, status=404)

        return JsonResponse({
            "ok": True,
            "student_id": student.student_id,
            "full_name": student.full_name,
            "balance": float(student.balance),
            "rfid_uid": student.rfid_uid,
        })

    except json.JSONDecodeError:
        return JsonResponse({"ok": False, "error": "Invalid JSON"}, status=400)
    except Exception as e:
        return JsonResponse({"ok": False, "error": str(e)}, status=500)


def menu_list_api(request):
    items = MenuItem.objects.filter(available=True).order_by("id")
    return JsonResponse({
        "ok": True,
        "items": [
            {
                "id": item.id,
                "name": item.name,
                "price": float(item.price),
            }
            for item in items
        ]
    })


@csrf_exempt
def buy_api(request):
    if request.method != "POST":
        return JsonResponse({"ok": False, "error": "POST required"}, status=405)

    try:
        data = json.loads(request.body.decode("utf-8"))
        uid = data.get("uid", "").strip()
        student_pin = data.get("student_pin", "").strip()
        menu_item_id = data.get("menu_item_id")

        if not uid or not student_pin or not menu_item_id:
            return JsonResponse({"ok": False, "error": "uid, student_pin, and menu_item_id are required"}, status=400)

        try:
            student = Student.objects.get(rfid_uid=uid, active=True)
        except Student.DoesNotExist:
            return JsonResponse({"ok": False, "error": "RFID card not recognized"}, status=404)

        if student.student_pin != student_pin:
            return JsonResponse({"ok": False, "error": "Invalid student PIN"}, status=403)

        try:
            menu_item = MenuItem.objects.get(id=menu_item_id, available=True)
        except MenuItem.DoesNotExist:
            return JsonResponse({"ok": False, "error": "Menu item not found"}, status=404)

        if student.balance < menu_item.price:
            return JsonResponse({
                "ok": False,
                "error": "Insufficient balance",
                "balance": float(student.balance),
                "price": float(menu_item.price),
            }, status=400)

        with db_transaction.atomic():
            student = Student.objects.select_for_update().get(pk=student.pk)
            if student.balance < menu_item.price:
                return JsonResponse({
                    "ok": False,
                    "error": "Insufficient balance",
                    "balance": float(student.balance),
                    "price": float(menu_item.price),
                }, status=400)

            balance_before = student.balance
            balance_after = balance_before - menu_item.price
            student.balance = balance_after
            student.save(update_fields=["balance"])

            Transaction.objects.create(
                student=student,
                transaction_type="BUY",
                amount=menu_item.price,
                menu_item=menu_item,
                balance_before=balance_before,
                balance_after=balance_after,
            )

        return JsonResponse({
            "ok": True,
            "message": "Purchase successful",
            "student_name": student.full_name,
            "item_name": menu_item.name,
            "amount": float(menu_item.price),
            "balance_after": float(balance_after),
        })

    except json.JSONDecodeError:
        return JsonResponse({"ok": False, "error": "Invalid JSON"}, status=400)
    except Exception as e:
        return JsonResponse({"ok": False, "error": str(e)}, status=500)


@csrf_exempt
def admin_topup_api(request):
    if request.method != "POST":
        return JsonResponse({"ok": False, "error": "POST required"}, status=405)

    try:
        data = json.loads(request.body.decode("utf-8"))
        uid = data.get("uid", "").strip()
        admin_pin = data.get("admin_pin", "").strip()
        amount_raw = str(data.get("amount", "")).strip()

        if not uid or not admin_pin or not amount_raw:
            return JsonResponse({"ok": False, "error": "uid, admin_pin, and amount are required"}, status=400)

        if admin_pin != settings.CANTEEN_ADMIN_PASSWORD:
            return JsonResponse({"ok": False, "error": "Invalid admin PIN"}, status=403)

        try:
            amount = Decimal(amount_raw)
        except (InvalidOperation, ValueError):
            return JsonResponse({"ok": False, "error": "Invalid amount"}, status=400)

        if amount <= 0:
            return JsonResponse({"ok": False, "error": "Amount must be greater than 0"}, status=400)

        try:
            student = Student.objects.get(rfid_uid=uid, active=True)
        except Student.DoesNotExist:
            return JsonResponse({"ok": False, "error": "RFID card not recognized"}, status=404)

        with db_transaction.atomic():
            student = Student.objects.select_for_update().get(pk=student.pk)
            balance_before = student.balance
            balance_after = balance_before + amount
            student.balance = balance_after
            student.save(update_fields=["balance"])

            Transaction.objects.create(
                student=student,
                transaction_type="TOPUP",
                amount=amount,
                balance_before=balance_before,
                balance_after=balance_after,
            )

        return JsonResponse({
            "ok": True,
            "message": "Top up successful",
            "student_name": student.full_name,
            "amount": float(amount),
            "balance_after": float(balance_after),
        })

    except json.JSONDecodeError:
        return JsonResponse({"ok": False, "error": "Invalid JSON"}, status=400)
    except Exception as e:
        return JsonResponse({"ok": False, "error": str(e)}, status=500)


@require_staff_login
def topup_scan(request):
    if request.method == "POST":
        rfid_uid = request.POST.get("rfid_uid", "").strip()

        try:
            student = Student.objects.get(rfid_uid=rfid_uid, active=True)
            request.session["topup_student_id"] = student.id
            clear_scan_file()
            return redirect("topup_amount")
        except Student.DoesNotExist:
            messages.error(request, "RFID card not recognized.")
            return redirect("topup_scan")

    clear_scan_file()
    return render(request, "topup_scan.html", {"hide_session_bar": True})


@require_staff_login
def topup_amount(request):
    student_id = request.session.get("topup_student_id")
    if not student_id:
        messages.warning(request, "Please scan a card first.")
        return redirect("topup_scan")

    student = get_object_or_404(Student, id=student_id)
    amount_form = TopUpForm(request.POST or None)
    password_form = AdminPasswordForm(request.POST or None)

    if request.method == "POST":
        if amount_form.is_valid() and password_form.is_valid():
            amount = amount_form.cleaned_data["amount"]
            admin_password = password_form.cleaned_data["admin_password"]

            if admin_password != settings.CANTEEN_ADMIN_PASSWORD:
                messages.error(request, "Invalid admin password.")
                return redirect("topup_amount")

            with db_transaction.atomic():
                student = Student.objects.select_for_update().get(pk=student.pk)
                balance_before = student.balance
                balance_after = balance_before + amount
                student.balance = balance_after
                student.save(update_fields=["balance"])

                Transaction.objects.create(
                    student=student,
                    transaction_type="TOPUP",
                    amount=amount,
                    balance_before=balance_before,
                    balance_after=balance_after,
                )

            request.session.pop("topup_student_id", None)
            messages.success(
                request,
                f"Top up successful. {student.full_name} added ₱{amount:.2f}. New balance: ₱{balance_after:.2f}",
            )
            return redirect("home")

    return render(request, "topup_amount.html", {
        "student": student,
        "amount_form": amount_form,
        "password_form": password_form,
        "hide_session_bar": True,
    })


@require_staff_login
def buy_select_legacy(request):
    available_items = MenuItem.objects.filter(available=True).order_by("name")
    student = None
    student_id = request.session.get("buy_student_id")

    if student_id:
        student = Student.objects.filter(id=student_id, active=True).first()
        if not student:
            request.session.pop("buy_student_id", None)

    if request.method == "POST":
        action = request.POST.get("action", "")

        if action == "verify_student":
            rfid_uid = request.POST.get("rfid_uid", "").strip()
            student_pin = request.POST.get("student_pin", "").strip()

            try:
                student = Student.objects.get(rfid_uid=rfid_uid, active=True)
            except Student.DoesNotExist:
                messages.error(request, "RFID card not recognized.")
                return redirect("buy_select")

            if student.student_pin != student_pin:
                messages.error(request, "Invalid student password.")
                return redirect("buy_select")

            request.session["buy_student_id"] = student.id
            clear_scan_file()
            messages.success(request, f"{student.full_name} profile loaded.")
            return redirect("buy_select")

        if action == "change_student":
            request.session.pop("buy_student_id", None)
            clear_scan_file()
            return redirect("buy_select")

        if action == "buy_item":
            if not student:
                messages.warning(request, "Please scan and verify a student first.")
                return redirect("buy_select")

            menu_item = get_object_or_404(MenuItem, id=request.POST.get("menu_item_id"), available=True)

            if student.balance < menu_item.price:
                messages.error(
                    request,
                    f"Insufficient balance. Current balance: ₱{student.balance:.2f}, Item cost: ₱{menu_item.price:.2f}",
                )
                return redirect("buy_select")

            with db_transaction.atomic():
                student = Student.objects.select_for_update().get(pk=student.pk)
                if student.balance < menu_item.price:
                    messages.error(
                        request,
                        f"Insufficient balance. Current balance: ₱{student.balance:.2f}, Item cost: ₱{menu_item.price:.2f}",
                    )
                    return redirect("buy_select")

                balance_before = student.balance
                balance_after = balance_before - menu_item.price
                student.balance = balance_after
                student.save(update_fields=["balance"])

                Transaction.objects.create(
                    student=student,
                    transaction_type="BUY",
                    amount=menu_item.price,
                    menu_item=menu_item,
                    balance_before=balance_before,
                    balance_after=balance_after,
                )

            messages.success(
                request,
                f"Purchase successful. {student.full_name} bought {menu_item.name}. Remaining balance: ₱{balance_after:.2f}",
            )
            return redirect("buy_select")

    if not student:
        clear_scan_file()

    return render(request, "buy_select.html", {
        "student": student,
        "available_items": available_items,
    })


@require_staff_login
def buy_select(request):
    available_items = MenuItem.objects.filter(available=True).order_by("name")
    student = None
    student_id = request.session.get("buy_student_id")
    cart = request.session.get("buy_cart", {})

    if student_id:
        student = Student.objects.filter(id=student_id, active=True).first()
        if not student:
            request.session.pop("buy_student_id", None)
            request.session.pop("buy_cart", None)
            cart = {}

    if request.method == "POST":
        action = request.POST.get("action", "")

        if action == "verify_student":
            rfid_uid = request.POST.get("rfid_uid", "").strip()
            student_pin = request.POST.get("student_pin", "").strip()

            try:
                student = Student.objects.get(rfid_uid=rfid_uid, active=True)
            except Student.DoesNotExist:
                messages.error(request, "RFID card not recognized.")
                return redirect("buy_select")

            if student.student_pin != student_pin:
                messages.error(request, "Invalid student password.")
                return redirect("buy_select")

            request.session["buy_student_id"] = student.id
            request.session["buy_cart"] = {}
            clear_scan_file()
            messages.success(request, f"{student.full_name} profile loaded.")
            return redirect("buy_select")

        if action == "change_student":
            request.session.pop("buy_student_id", None)
            request.session.pop("buy_cart", None)
            clear_scan_file()
            return redirect("buy_select")

        if action == "add_item":
            if not student:
                messages.warning(request, "Please scan and verify a student first.")
                return redirect("buy_select")

            menu_item = get_object_or_404(MenuItem, id=request.POST.get("menu_item_id"), available=True)
            item_id = str(menu_item.id)
            cart[item_id] = cart.get(item_id, 0) + 1
            request.session["buy_cart"] = cart
            request.session.modified = True
            messages.success(request, f"{menu_item.name} added to checkout summary.")
            return redirect("buy_select")

        if action == "remove_item":
            item_id = request.POST.get("menu_item_id", "")
            if item_id in cart:
                cart[item_id] -= 1
                if cart[item_id] <= 0:
                    cart.pop(item_id)
                request.session["buy_cart"] = cart
                request.session.modified = True
            return redirect("buy_select")

        if action == "clear_cart":
            request.session["buy_cart"] = {}
            request.session.modified = True
            return redirect("buy_select")

        if action == "confirm_purchase":
            if not student:
                messages.warning(request, "Please scan and verify a student first.")
                return redirect("buy_select")

            if not cart:
                messages.warning(request, "Please add at least one product first.")
                return redirect("buy_select")

            item_ids = [int(item_id) for item_id in cart.keys()]
            item_map = {
                str(item.id): item
                for item in MenuItem.objects.filter(id__in=item_ids, available=True)
            }
            total = Decimal("0.00")

            for item_id, quantity in cart.items():
                item = item_map.get(item_id)
                if item:
                    total += item.price * quantity

            if total <= 0:
                messages.error(request, "Selected products are no longer available.")
                request.session["buy_cart"] = {}
                request.session.modified = True
                return redirect("buy_select")

            if student.balance < total:
                messages.error(
                    request,
                    f"Insufficient balance. Current balance: ₱{student.balance:.2f}, Order total: ₱{total:.2f}",
                )
                return redirect("buy_select")

            with db_transaction.atomic():
                student = Student.objects.select_for_update().get(pk=student.pk)
                if student.balance < total:
                    messages.error(
                        request,
                        f"Insufficient balance. Current balance: ₱{student.balance:.2f}, Order total: ₱{total:.2f}",
                    )
                    return redirect("buy_select")

                balance_before = student.balance
                balance_after = balance_before - total
                student.balance = balance_after
                student.save(update_fields=["balance"])

                running_balance = balance_before
                for item_id, quantity in cart.items():
                    item = item_map.get(item_id)
                    if not item:
                        continue
                    amount = item.price * quantity
                    next_balance = running_balance - amount
                    Transaction.objects.create(
                        student=student,
                        transaction_type="BUY",
                        amount=amount,
                        menu_item=item,
                        balance_before=running_balance,
                        balance_after=next_balance,
                    )
                    running_balance = next_balance

            request.session["buy_cart"] = {}
            request.session.modified = True
            messages.success(
                request,
                f"Payment confirmed. {student.full_name} spent ₱{total:.2f}. Remaining balance: ₱{balance_after:.2f}",
            )
            return redirect("buy_select")

    if not student:
        clear_scan_file()

    cart_items = []
    cart_total = Decimal("0.00")
    if cart:
        item_ids = [int(item_id) for item_id in cart.keys()]
        item_map = {
            str(item.id): item
            for item in MenuItem.objects.filter(id__in=item_ids, available=True)
        }
        for item_id, quantity in cart.items():
            item = item_map.get(item_id)
            if not item:
                continue
            line_total = item.price * quantity
            cart_total += line_total
            cart_items.append({
                "item": item,
                "quantity": quantity,
                "line_total": line_total,
            })

    projected_balance = student.balance - cart_total if student else Decimal("0.00")

    return render(request, "buy_select.html", {
        "student": student,
        "available_items": available_items,
        "cart_items": cart_items,
        "cart_total": cart_total,
        "projected_balance": projected_balance,
        "hide_session_bar": True,
    })


@require_staff_login
def buy_scan(request):
    menu_item_id = request.session.get("buy_menu_item_id")
    if not menu_item_id:
        messages.warning(request, "Please choose a food item first.")
        return redirect("buy_select")

    menu_item = get_object_or_404(MenuItem, id=menu_item_id, available=True)
    password_form = AdminPasswordForm(request.POST or None)

    if request.method == "POST":
        rfid_uid = request.POST.get("rfid_uid", "").strip()

        if password_form.is_valid():
            admin_password = password_form.cleaned_data["admin_password"]

            if admin_password != settings.CANTEEN_ADMIN_PASSWORD:
                messages.error(request, "Invalid admin password.")
                return redirect("buy_scan")

            try:
                student = Student.objects.get(rfid_uid=rfid_uid, active=True)
            except Student.DoesNotExist:
                messages.error(request, "RFID card not recognized.")
                return redirect("buy_scan")

            if student.balance < menu_item.price:
                messages.error(
                    request,
                    f"Insufficient balance. Current balance: ₱{student.balance:.2f}, Item cost: ₱{menu_item.price:.2f}",
                )
                return redirect("buy_scan")

            with db_transaction.atomic():
                student = Student.objects.select_for_update().get(pk=student.pk)
                if student.balance < menu_item.price:
                    messages.error(
                        request,
                        f"Insufficient balance. Current balance: ₱{student.balance:.2f}, Item cost: ₱{menu_item.price:.2f}",
                    )
                    return redirect("buy_scan")

                balance_before = student.balance
                balance_after = balance_before - menu_item.price
                student.balance = balance_after
                student.save(update_fields=["balance"])

                Transaction.objects.create(
                    student=student,
                    transaction_type="BUY",
                    amount=menu_item.price,
                    menu_item=menu_item,
                    balance_before=balance_before,
                    balance_after=balance_after,
                )

            request.session.pop("buy_menu_item_id", None)
            clear_scan_file()
            messages.success(
                request,
                f"Purchase successful. {student.full_name} bought {menu_item.name} for ₱{menu_item.price:.2f}. Remaining balance: ₱{balance_after:.2f}",
            )
            return redirect("home")

    return render(request, "buy_scan.html", {
        "menu_item": menu_item,
        "password_form": password_form,
    })


@require_staff_login
def dashboard(request):
    students = Student.objects.all().order_by("full_name")
    menu_items = MenuItem.objects.all().order_by("name")
    transactions = Transaction.objects.select_related("student", "menu_item").order_by("-created_at")

    total_students = students.count()
    total_active_students = students.filter(active=True).count()
    total_menu_items = menu_items.count()

    total_topup = sum(
        (txn.amount for txn in transactions if txn.transaction_type == "TOPUP"),
        Decimal("0.00")
    )
    total_sales = sum(
        (txn.amount for txn in transactions if txn.transaction_type == "BUY"),
        Decimal("0.00")
    )

    today = timezone.localdate()
    last_7_days = [today - timedelta(days=i) for i in range(6, -1, -1)]

    weekly_map = OrderedDict()
    for day in last_7_days:
        weekly_map[day] = {
            "label": day.strftime("%b %d"),
            "topup": Decimal("0.00"),
            "sales": Decimal("0.00"),
        }

    weekly_transactions = Transaction.objects.filter(
        created_at__date__gte=last_7_days[0],
        created_at__date__lte=last_7_days[-1]
    )

    for txn in weekly_transactions:
        txn_day = timezone.localtime(txn.created_at).date()
        if txn_day in weekly_map:
            if txn.transaction_type == "TOPUP":
                weekly_map[txn_day]["topup"] += txn.amount
            elif txn.transaction_type == "BUY":
                weekly_map[txn_day]["sales"] += txn.amount

    weekly_labels = [item["label"] for item in weekly_map.values()]
    weekly_topup_values = [float(item["topup"]) for item in weekly_map.values()]
    weekly_sales_values = [float(item["sales"]) for item in weekly_map.values()]

    top_selling_items = (
        Transaction.objects
        .filter(transaction_type="BUY", menu_item__isnull=False)
        .values("menu_item__name")
        .annotate(
            count=Count("id"),
            total=Sum("amount")
        )
        .order_by("-count", "-total")[:5]
    )

    formatted_top_selling_items = [
        {
            "name": item["menu_item__name"],
            "count": item["count"],
            "total": item["total"] or Decimal("0.00"),
        }
        for item in top_selling_items
    ]

    return render(request, "dashboard.html", {
        "students": students,
        "menu_items": menu_items,
        "transactions": transactions,
        "total_students": total_students,
        "total_active_students": total_active_students,
        "total_menu_items": total_menu_items,
        "total_topup": total_topup,
        "total_sales": total_sales,
        "weekly_labels": weekly_labels,
        "weekly_topup_values": weekly_topup_values,
        "weekly_sales_values": weekly_sales_values,
        "top_selling_items": formatted_top_selling_items,
        "hide_session_bar": True,
    })
