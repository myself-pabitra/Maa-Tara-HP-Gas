from django.db.models.signals import post_save
from django.dispatch import receiver

from SubDealers.models import DailySellInvoiceItem, SubdealerDue

@receiver(post_save, sender=DailySellInvoiceItem)
def create_due_record(sender, instance, created, **kwargs):
    if created and instance.payment_status == "Pending":
        SubdealerDue.objects.create(
            subdealer=instance.subdealer,
            product=instance.product,
            invoice_item=instance,
            due_amount=instance.total_amount,
            remaining_amount=instance.total_amount,
        )
