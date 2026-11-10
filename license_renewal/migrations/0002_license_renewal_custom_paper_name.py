from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("license_renewal", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="licenserenewal",
            name="custom_paper_name",
            field=models.CharField(blank=True, max_length=100, null=True),
        ),
    ]
