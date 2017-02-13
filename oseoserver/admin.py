from __future__ import absolute_import

from django.contrib import admin
from django.core.urlresolvers import reverse
from django.utils.html import format_html

from . import models
from . import server
from . import utilities


class SelectedPaymentOptionInline(admin.StackedInline):
    model = models.SelectedPaymentOption
    extra = 1


class SelectedSceneSelectionOptionInline(admin.StackedInline):
    model = models.SelectedSceneSelectionOption
    extra = 1


class SelectedOrderOptionInline(admin.StackedInline):
    model = models.SelectedOrderOption
    extra = 1


class ItemSpecificationInline(admin.StackedInline):
    model = models.ItemSpecification
    extra = 1


@admin.register(models.Order)
class OrderAdmin(admin.ModelAdmin):
    inlines = (
        SelectedOrderOptionInline,
        ItemSpecificationInline,
    )
    fieldsets = (
        (None, {
            "fields": (
                "order_type",
                "status",
                "status_notification",
                "status_changed_on",
                "completed_on",
                "user",
                "reference",
                "priority",
                "packaging",
                "extensions",
                #"selected_options",
            )
        }),
        ("Further info", {
            "classes": ("collapse",),
            "fields": (
                "remark",
                "additional_status_info",
                "mission_specific_status_info",
            )
        }),
    )
    list_display = (
        "id",
        "order_type",
        "status",
        "status_changed_on",
        "user",
    )
    list_filter = (
        "status",
        "user",
        "order_type",
    )
    readonly_fields = (
        "order_type",
        "status",
        "status_changed_on",
        "completed_on",
        "last_describe_result_access_request",
    )
    date_hierarchy = "created_on"


@admin.register(models.OrderPendingModeration)
class PendingOrderAdmin(admin.ModelAdmin):
    actions = ["approve_order", "reject_order"]
    list_display = ("id", "order_type", "user")

    def get_actions(self, request):
        actions = super(PendingOrderAdmin, self).get_actions(request)
        del actions["delete_selected"]
        if not request.user.is_staff:
            if "approve_order" in actions:
                del actions["approve_order"]
            if "reject_order" in actions:
                del actions["reject_order"]
        return actions

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def approve_order(self, request, queryset):
        for order in queryset:
            config = utilities.get_generic_order_config(order.order_type)
            server.handle_submit(
                order=order,
                approved=True,
                notify=config["notify_moderation"]
            )
    approve_order.short_description = "Approve selected orders"

    def reject_order(self, request, queryset):
        for order in queryset:
            config = utilities.get_generic_order_config(order.order_type)
            server.handle_submit(
                order=order,
                approved=False,
                notify=config["notify_moderation"]
            )
    reject_order.short_description = "Reject selected orders"


@admin.register(models.OrderItem)
class OrderItemAdmin(admin.ModelAdmin):
    fieldsets = (
        (None, {
            "fields": (
                "identifier",
                "collection",
                "batch",
                "order",
                "item_specification",
                "status",
                "available",
                "status_changed_on",
                "completed_on",
            )
        }),
        ("Further info", {
            "classes": ("collapse",),
            "fields": (
                "expires_on",
                "downloads",
                "last_downloaded_at",
                "url",
                "additional_status_info",
                "mission_specific_status_info",
            )
        }),
    )
    list_display = (
        "id",
        "available",
        "link_to_batch",
        "link_to_order",
        "identifier",
        "status",
        "status_changed_on",
    )
    list_filter = (
        "status",
    )
    search_fields = (
        "batch__order__id",
        "identifier",
    )
    date_hierarchy = "status_changed_on"
    readonly_fields = (
        "status_changed_on",
        "completed_on",
        "available",
        "batch",
        "item_specification",
    )

    def link_to_batch(self, obj):
        url = reverse("admin:oseoserver_batch_change", args=(obj.batch_id,))
        html = "<a href='{0}'>{1}</a>".format(url, obj.batch_id)
        return format_html(html)
    link_to_batch.short_description = "Batch"
    link_to_batch.allow_tags = True

    def link_to_order(self, obj):
        url = reverse("admin:oseoserver_order_change",
                      args=(obj.batch.order_id,))
        html = "<a href='{0}'>{1}</a>".format(url, obj.batch.order_id)
        return format_html(html)
    link_to_order.short_description = "Order"
    link_to_order.allow_tags = True


#@admin.register(models.Batch)
#class BatchAdmin(admin.ModelAdmin):
#    list_display = ("id", "order", "status", "price", "created_on",
#                    "completed_on", "updated_on",)


#@admin.register(models.SubscriptionBatch)
#class SubscriptionBatchAdmin(admin.ModelAdmin):
#    list_display = ("id", "timeslot", "collection", "status", "price",
#                    "created_on", "completed_on", "updated_on",)


admin.site.register(models.DeliveryInformation)
admin.site.register(models.OnlineAddress)
admin.site.register(models.InvoiceAddress)
