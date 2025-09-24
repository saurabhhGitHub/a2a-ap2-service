"""
Admin configuration for Payment Processing app.
"""

from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from .models import PaymentMethod, Payment, PaymentWebhook, PaymentRetry


@admin.register(PaymentMethod)
class PaymentMethodAdmin(admin.ModelAdmin):
    list_display = [
        'payment_method_id', 'customer_name', 'type', 'status',
        'last_four', 'brand', 'created_at'
    ]
    list_filter = ['type', 'status', 'mandate_status', 'created_at']
    search_fields = ['customer_name', 'customer_id', 'stripe_payment_method_id']
    readonly_fields = ['payment_method_id', 'created_at', 'updated_at']
    fieldsets = (
        ('Basic Information', {
            'fields': ('payment_method_id', 'customer_id', 'customer_name')
        }),
        ('Payment Method Details', {
            'fields': ('type', 'status', 'stripe_payment_method_id', 'mandate_id', 'mandate_status')
        }),
        ('Card Information', {
            'fields': ('last_four', 'brand', 'exp_month', 'exp_year'),
            'classes': ('collapse',)
        }),
        ('Bank Information', {
            'fields': ('bank_name', 'account_type'),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at', 'expires_at')
        }),
        ('Metadata', {
            'fields': ('metadata',),
            'classes': ('collapse',)
        }),
    )


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = [
        'payment_id', 'invoice_link', 'amount_dollars', 'currency',
        'status', 'method', 'created_at'
    ]
    list_filter = ['status', 'currency', 'method', 'created_at']
    search_fields = ['payment_id', 'invoice__invoice_id', 'stripe_payment_intent_id']
    readonly_fields = [
        'payment_id', 'created_at', 'updated_at', 'amount_dollars',
        'fees_dollars', 'net_amount_dollars'
    ]
    fieldsets = (
        ('Payment Details', {
            'fields': ('payment_id', 'invoice', 'payment_method', 'amount_cents', 'amount_dollars', 'currency', 'method')
        }),
        ('Stripe Information', {
            'fields': ('stripe_payment_intent_id', 'stripe_charge_id')
        }),
        ('Status & Processing', {
            'fields': ('status', 'processed_at', 'settled_at')
        }),
        ('Financial Details', {
            'fields': ('amount_received_cents', 'fees_charged_cents', 'fees_dollars', 'net_amount_cents', 'net_amount_dollars')
        }),
        ('Error Information', {
            'fields': ('failure_code', 'failure_message'),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at')
        }),
        ('Raw Data', {
            'fields': ('raw_stripe_response', 'metadata'),
            'classes': ('collapse',)
        }),
    )
    
    def invoice_link(self, obj):
        url = reverse('admin:invoice_collections_invoice_change', args=[obj.invoice.id])
        return format_html('<a href="{}">{}</a>', url, obj.invoice.invoice_id)
    invoice_link.short_description = 'Invoice'
    
    def amount_dollars(self, obj):
        return f"${obj.amount_dollars:.2f}"
    amount_dollars.short_description = 'Amount (USD)'
    
    def fees_dollars(self, obj):
        return f"${obj.fees_dollars:.2f}"
    fees_dollars.short_description = 'Fees (USD)'
    
    def net_amount_dollars(self, obj):
        return f"${obj.net_amount_dollars:.2f}"
    net_amount_dollars.short_description = 'Net Amount (USD)'


@admin.register(PaymentWebhook)
class PaymentWebhookAdmin(admin.ModelAdmin):
    list_display = [
        'webhook_id', 'stripe_event_id', 'webhook_type', 'payment_link',
        'processed', 'received_at'
    ]
    list_filter = ['webhook_type', 'processed', 'received_at']
    search_fields = ['stripe_event_id', 'payment__payment_id']
    readonly_fields = ['webhook_id', 'received_at']
    fieldsets = (
        ('Webhook Details', {
            'fields': ('webhook_id', 'stripe_event_id', 'webhook_type', 'payment')
        }),
        ('Processing Status', {
            'fields': ('processed', 'processing_error', 'processed_at')
        }),
        ('Timestamps', {
            'fields': ('received_at',)
        }),
        ('Raw Data', {
            'fields': ('raw_webhook_data',),
            'classes': ('collapse',)
        }),
    )
    
    def payment_link(self, obj):
        if obj.payment:
            url = reverse('admin:payment_processing_payment_change', args=[obj.payment.id])
            return format_html('<a href="{}">{}</a>', url, obj.payment.payment_id)
        return "N/A"
    payment_link.short_description = 'Payment'


@admin.register(PaymentRetry)
class PaymentRetryAdmin(admin.ModelAdmin):
    list_display = [
        'retry_id', 'payment_link', 'retry_number', 'status',
        'scheduled_at', 'attempted_at'
    ]
    list_filter = ['status', 'retry_number', 'scheduled_at']
    search_fields = ['payment__payment_id', 'retry_reason']
    readonly_fields = ['retry_id', 'scheduled_at']
    fieldsets = (
        ('Retry Details', {
            'fields': ('retry_id', 'payment', 'retry_number', 'status')
        }),
        ('Scheduling', {
            'fields': ('scheduled_at', 'attempted_at', 'completed_at')
        }),
        ('Retry Information', {
            'fields': ('retry_reason', 'error_message')
        }),
        ('Stripe Details', {
            'fields': ('new_stripe_payment_intent_id',)
        }),
    )
    
    def payment_link(self, obj):
        url = reverse('admin:payment_processing_payment_change', args=[obj.payment.id])
        return format_html('<a href="{}">{}</a>', url, obj.payment.payment_id)
    payment_link.short_description = 'Payment'