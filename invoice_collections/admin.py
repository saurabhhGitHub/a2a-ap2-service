"""
Admin configuration for Invoice Collections app.
"""

from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.utils.safestring import mark_safe
from .models import Invoice, AgentAction, PaymentAttempt, CollectionRequest


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = [
        'invoice_id', 'customer_name', 'amount_dollars', 'currency',
        'status', 'due_date', 'created_at'
    ]
    list_filter = ['status', 'currency', 'payment_method', 'created_at']
    search_fields = ['invoice_id', 'sf_invoice_id', 'customer_name', 'customer_id']
    readonly_fields = ['created_at', 'updated_at', 'amount_dollars']
    fieldsets = (
        ('Basic Information', {
            'fields': ('invoice_id', 'sf_invoice_id', 'customer_id', 'customer_name')
        }),
        ('Financial Details', {
            'fields': ('amount_cents', 'amount_dollars', 'currency')
        }),
        ('Payment Information', {
            'fields': ('mandate_id', 'payment_method', 'approved_by')
        }),
        ('Status & Dates', {
            'fields': ('status', 'due_date', 'idempotency_key')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
        ('Metadata', {
            'fields': ('metadata',),
            'classes': ('collapse',)
        }),
    )
    
    def amount_dollars(self, obj):
        return f"${obj.amount_dollars:.2f}"
    amount_dollars.short_description = 'Amount (USD)'


@admin.register(AgentAction)
class AgentActionAdmin(admin.ModelAdmin):
    list_display = [
        'action_id', 'invoice_link', 'action_type', 'decision',
        'human_actor', 'created_at'
    ]
    list_filter = ['action_type', 'decision', 'created_at']
    search_fields = ['invoice__invoice_id', 'human_actor', 'notes']
    readonly_fields = ['action_id', 'created_at']
    fieldsets = (
        ('Action Details', {
            'fields': ('action_id', 'invoice', 'action_type', 'decision')
        }),
        ('Actors', {
            'fields': ('human_actor', 'system_actor')
        }),
        ('Data', {
            'fields': ('payload', 'response_data'),
            'classes': ('collapse',)
        }),
        ('Additional Info', {
            'fields': ('notes', 'error_message', 'created_at'),
            'classes': ('collapse',)
        }),
    )
    
    def invoice_link(self, obj):
        url = reverse('admin:invoice_collections_invoice_change', args=[obj.invoice.id])
        return format_html('<a href="{}">{}</a>', url, obj.invoice.invoice_id)
    invoice_link.short_description = 'Invoice'


@admin.register(PaymentAttempt)
class PaymentAttemptAdmin(admin.ModelAdmin):
    list_display = [
        'attempt_id', 'invoice_link', 'attempt_number', 'status',
        'amount_cents', 'initiated_at', 'duration_display'
    ]
    list_filter = ['status', 'attempt_number', 'initiated_at']
    search_fields = ['invoice__invoice_id', 'stripe_payment_intent_id']
    readonly_fields = ['attempt_id', 'initiated_at', 'duration_display']
    fieldsets = (
        ('Attempt Details', {
            'fields': ('attempt_id', 'invoice', 'attempt_number', 'status')
        }),
        ('Stripe Information', {
            'fields': ('stripe_payment_intent_id', 'stripe_charge_id')
        }),
        ('Financial Details', {
            'fields': ('amount_cents', 'fees_charged_cents')
        }),
        ('Error Information', {
            'fields': ('error_code', 'error_message'),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('initiated_at', 'completed_at', 'duration_display')
        }),
        ('Raw Data', {
            'fields': ('raw_stripe_response',),
            'classes': ('collapse',)
        }),
    )
    
    def invoice_link(self, obj):
        url = reverse('admin:invoice_collections_invoice_change', args=[obj.invoice.id])
        return format_html('<a href="{}">{}</a>', url, obj.invoice.invoice_id)
    invoice_link.short_description = 'Invoice'
    
    def duration_display(self, obj):
        duration = obj.duration_seconds
        if duration:
            return f"{duration:.2f}s"
        return "N/A"
    duration_display.short_description = 'Duration'


@admin.register(CollectionRequest)
class CollectionRequestAdmin(admin.ModelAdmin):
    list_display = [
        'request_id', 'idempotency_key', 'status', 'invoice_link',
        'received_at', 'processed_at'
    ]
    list_filter = ['status', 'received_at']
    search_fields = ['idempotency_key', 'invoice__invoice_id']
    readonly_fields = ['request_id', 'received_at']
    fieldsets = (
        ('Request Details', {
            'fields': ('request_id', 'idempotency_key', 'status')
        }),
        ('Related Invoice', {
            'fields': ('invoice',)
        }),
        ('Timestamps', {
            'fields': ('received_at', 'processed_at')
        }),
        ('Error Information', {
            'fields': ('error_message',),
            'classes': ('collapse',)
        }),
        ('Raw Data', {
            'fields': ('raw_request_data',),
            'classes': ('collapse',)
        }),
    )
    
    def invoice_link(self, obj):
        if obj.invoice:
            url = reverse('admin:invoice_collections_invoice_change', args=[obj.invoice.id])
            return format_html('<a href="{}">{}</a>', url, obj.invoice.invoice_id)
        return "Not created yet"
    invoice_link.short_description = 'Invoice'