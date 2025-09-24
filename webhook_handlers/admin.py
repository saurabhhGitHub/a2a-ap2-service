"""
Admin configuration for Webhook Handlers app.
"""

from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from .models import WebhookEvent, SalesforceNotification, ExternalSystemIntegration, AuditLog


@admin.register(WebhookEvent)
class WebhookEventAdmin(admin.ModelAdmin):
    list_display = [
        'event_id', 'source', 'event_type', 'status',
        'retry_count', 'received_at'
    ]
    list_filter = ['source', 'event_type', 'status', 'received_at']
    search_fields = ['external_id', 'processing_error']
    readonly_fields = ['event_id', 'received_at']
    fieldsets = (
        ('Event Details', {
            'fields': ('event_id', 'source', 'event_type', 'external_id', 'status')
        }),
        ('Processing', {
            'fields': ('processing_error', 'retry_count', 'max_retries', 'next_retry_at')
        }),
        ('Timestamps', {
            'fields': ('received_at', 'processed_at')
        }),
        ('Data', {
            'fields': ('payload', 'headers'),
            'classes': ('collapse',)
        }),
    )


@admin.register(SalesforceNotification)
class SalesforceNotificationAdmin(admin.ModelAdmin):
    list_display = [
        'notification_id', 'invoice_link', 'notification_type', 'status',
        'delivery_attempts', 'created_at'
    ]
    list_filter = ['notification_type', 'status', 'created_at']
    search_fields = ['invoice__invoice_id', 'last_delivery_error']
    readonly_fields = ['notification_id', 'created_at']
    fieldsets = (
        ('Notification Details', {
            'fields': ('notification_id', 'invoice', 'notification_type', 'status')
        }),
        ('Salesforce Configuration', {
            'fields': ('sf_webhook_url', 'sf_webhook_secret')
        }),
        ('Delivery Tracking', {
            'fields': ('delivery_attempts', 'max_delivery_attempts', 'last_delivery_error', 'next_retry_at')
        }),
        ('Response Information', {
            'fields': ('response_status_code', 'response_body'),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'sent_at', 'delivered_at', 'acknowledged_at')
        }),
        ('Payload', {
            'fields': ('payload',),
            'classes': ('collapse',)
        }),
    )
    
    def invoice_link(self, obj):
        url = reverse('admin:invoice_collections_invoice_change', args=[obj.invoice.id])
        return format_html('<a href="{}">{}</a>', url, obj.invoice.invoice_id)
    invoice_link.short_description = 'Invoice'


@admin.register(ExternalSystemIntegration)
class ExternalSystemIntegrationAdmin(admin.ModelAdmin):
    list_display = [
        'integration_id', 'system_name', 'system_type', 'status',
        'last_health_check', 'consecutive_failures'
    ]
    list_filter = ['system_type', 'status', 'last_health_check']
    search_fields = ['system_name', 'base_url']
    readonly_fields = ['integration_id', 'created_at', 'updated_at']
    fieldsets = (
        ('Integration Details', {
            'fields': ('integration_id', 'system_type', 'system_name', 'status')
        }),
        ('Configuration', {
            'fields': ('base_url', 'api_key', 'webhook_secret')
        }),
        ('Health Monitoring', {
            'fields': ('last_health_check', 'health_check_status', 'consecutive_failures')
        }),
        ('Rate Limiting', {
            'fields': ('requests_per_minute', 'requests_per_hour')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at')
        }),
        ('Configuration Data', {
            'fields': ('config',),
            'classes': ('collapse',)
        }),
    )


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = [
        'log_id', 'action_type', 'action_description', 'actor_type',
        'invoice_id', 'created_at'
    ]
    list_filter = ['action_type', 'actor_type', 'created_at']
    search_fields = ['action_description', 'invoice_id', 'payment_id', 'actor_email']
    readonly_fields = ['log_id', 'created_at']
    fieldsets = (
        ('Action Details', {
            'fields': ('log_id', 'action_type', 'action_description')
        }),
        ('Related Objects', {
            'fields': ('invoice_id', 'payment_id')
        }),
        ('Actor Information', {
            'fields': ('actor_type', 'actor_id', 'actor_email')
        }),
        ('Request Context', {
            'fields': ('ip_address', 'user_agent', 'request_id'),
            'classes': ('collapse',)
        }),
        ('Change Data', {
            'fields': ('old_values', 'new_values', 'metadata'),
            'classes': ('collapse',)
        }),
        ('Timestamp', {
            'fields': ('created_at',)
        }),
    )