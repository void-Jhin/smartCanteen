from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("canteen", "0002_student_student_pin"),
    ]

    operations = [
        migrations.CreateModel(
            name="LatestScan",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("key", models.CharField(default="rfid", max_length=40, unique=True)),
                ("uid", models.CharField(blank=True, default="", max_length=100)),
                ("timestamp", models.FloatField(default=0)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
        ),
    ]
