from django import forms
from .models import MenuItem


class StudentLoginForm(forms.Form):
    student_id = forms.CharField(
        label="Student ID",
        widget=forms.TextInput(attrs={
            "class": "input login-icon-user",
            "placeholder": "Enter your student ID",
            "autocomplete": "username",
        })
    )
    student_pin = forms.CharField(
        label="Password",
        widget=forms.PasswordInput(attrs={
            "class": "input login-icon-lock",
            "placeholder": "Enter your password",
            "autocomplete": "current-password",
        })
    )


class TopUpForm(forms.Form):
    amount = forms.DecimalField(
        max_digits=10,
        decimal_places=2,
        min_value=1,
        label="Top Up Amount",
        widget=forms.NumberInput(attrs={
            "class": "input",
            "placeholder": "Enter amount (ex. 50.00)",
            "step": "0.01",
        })
    )


class AdminPasswordForm(forms.Form):
    admin_password = forms.CharField(
        label="Admin Verification PIN",
        widget=forms.PasswordInput(attrs={
            "class": "input",
            "placeholder": "Enter admin verification PIN",
        })
    )


class BuySelectForm(forms.Form):
    menu_item = forms.ModelChoiceField(
        queryset=MenuItem.objects.filter(available=True),
        empty_label=None,
        label="Available Menu Items",
        widget=forms.Select(attrs={
            "class": "input custom-select",
        })
    )


class MenuItemForm(forms.ModelForm):
    class Meta:
        model = MenuItem
        fields = ["name", "price", "available"]
        widgets = {
            "name": forms.TextInput(attrs={
                "class": "input",
                "placeholder": "Food or product name",
            }),
            "price": forms.NumberInput(attrs={
                "class": "input",
                "placeholder": "Enter price",
                "step": "0.01",
                "min": "0.01",
            }),
            "available": forms.CheckboxInput(attrs={
                "class": "checkbox-input",
            }),
        }

    def clean_price(self):
        price = self.cleaned_data["price"]
        if price <= 0:
            raise forms.ValidationError("Price must be greater than 0.")
        return price
