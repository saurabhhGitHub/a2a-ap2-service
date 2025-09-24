"""
Webhook Handlers Models

This module contains models for managing webhook events,
notifications, and external system integrations.
"""

import uuid
from django.db import models
from django.utils import timezone


class WebhookEvent(models.Model):
    """
    Generic webhook event tracking for audit and debugging.
    """
    
    EVENT_SOURCES = [
        ('stripe', 'Stripe'),
        ('salesforce', 'Salesforce'),
        ('internal', 'Internal System'),
    ]
    
    EVENT_TYPES = [
        ('payment_completed', 'Payment Completed'),
        ('payment_failed', 'Payment Failed'),
        ('invoice_updated', 'Invoice Updated'),
        ('collection_request', 'Collection Request'),
        ('status_update', 'Status Update'),
        ('error_notification', 'Error Notification'),
    ]
    
    STATUS_CHOICES = [
        ('received', 'Received'),
        ('processing', 'Processing'),
        ('processed', 'Processed'),
        ('failed', 'Failed'),
        ('ignored', 'Ignored'),
    ]
    
    # Primary key
    event_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    # Event identification
    source = models.CharField(max_length=20, choices=EVENT_SOURCES, db_index=True)
    event_type = models.CharField(max_length=50, choices=EVENT_TYPES, db_index=True)
    external_id = models.CharField(max_length=100, blank=True, db_index=True)
    
    # Processing status
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='received',
        db_index=True
    )
    
    # Event data
    payload = models.JSONField()
    headers = models.JSONField(default=dict, blank=True)
    
    # Processing details
    processing_error = models.TextField(blank=True)
    retry_count = models.PositiveIntegerField(default=0)
    max_retries = models.PositiveIntegerField(default=3)
    
    # Timestamps
    received_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)
    next_retry_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        db_table = 'webhook_events'
        indexes = [
            models.Index(fields=['source', 'event_type', 'received_at']),
            models.Index(fields=['status', 'next_retry_at']),
            models.Index(fields=['external_id']),
        ]
        ordering = ['-received_at']
    
    def __str__(self):
        return f"{self.source} - {self.event_type} - {self.status}"
    
    def should_retry(self):
        """Check if event should be retried."""
        return (
            self.status == 'failed' and
            self.retry_count < self.max_retries and
            (not self.next_retry_at or timezone.now() >= self.next_retry_at)
        )


class SalesforceNotification(models.Model):
    """
    Track notifications sent to Salesforce for invoice status updates.
    """
    
    NOTIFICATION_TYPES = [
        ('payment_completed', 'Payment Completed'),
        ('payment_failed', 'Payment Failed'),
        ('collection_initiated', 'Collection Initiated'),
        ('status_update', 'Status Update'),
        ('error_occurred', 'Error Occurred'),
    ]
    
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('sent', 'Sent'),
        ('delivered', 'Delivered'),
        ('failed', 'Failed'),
        ('acknowledged', 'Acknowledged'),
    ]
    
    # Primary key
    notification_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    # Related invoice
    invoice = models.ForeignKey(
        'invoice_collections.Invoice',
        on_delete=models.CASCADE,
        related_name='salesforce_notifications',
        db_index=True
    )
    
    # Notification details
    notification_type = models.CharField(
        max_length=50,
        choices=NOTIFICATION_TYPES,
        db_index=True
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending',
        db_index=True
    )
    
    # Salesforce details
    sf_webhook_url = models.URLField()
    sf_webhook_secret = models.CharField(max_length=255, blank=True)
    
    # Notification payload
    payload = models.JSONField()
    
    # Delivery tracking
    delivery_attempts = models.PositiveIntegerField(default=0)
    max_delivery_attempts = models.PositiveIntegerField(default=3)
    last_delivery_error = models.TextField(blank=True)
    
    # Response tracking
    response_status_code = models.PositiveIntegerField(null=True, blank=True)
    response_body = models.TextField(blank=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    acknowledged_at = models.DateTimeField(null=True, blank=True)
    next_retry_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        db_table = 'salesforce_notifications'
        indexes = [
            models.Index(fields=['invoice', 'created_at']),
            models.Index(fields=['status', 'next_retry_at']),
            models.Index(fields=['notification_type', 'created_at']),
        ]
        ordering = ['-created_at']
    
    def __str__(self):
        return f"SF Notification - {self.invoice.invoice_id} - {self.notification_type}"
    
    def should_retry(self):
        """Check if notification should be retried."""
        return (
            self.status in ['pending', 'failed'] and
            self.delivery_attempts < self.max_delivery_attempts and
            (not self.next_retry_at or timezone.now() >= self.next_retry_at)
        )


class ExternalSystemIntegration(models.Model):
    """
    Track integrations with external systems (Salesforce, etc.).
    """
    
    SYSTEM_TYPES = [
        ('salesforce', 'Salesforce'),
        ('stripe', 'Stripe'),
        ('slack', 'Slack'),
        ('email', 'Email'),
    ]
    
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('inactive', 'Inactive'),
        ('error', 'Error'),
        ('maintenance', 'Maintenance'),
    ]
    
    # Primary key
    integration_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    # Integration details
    system_type = models.CharField(max_length=20, choices=SYSTEM_TYPES, db_index=True)
    system_name = models.CharField(max_length=100)
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='active',
        db_index=True
    )
    
    # Configuration
    base_url = models.URLField()
    api_key = models.CharField(max_length=255, blank=True)
    webhook_secret = models.CharField(max_length=255, blank=True)
    
    # Health monitoring
    last_health_check = models.DateTimeField(null=True, blank=True)
    health_check_status = models.CharField(max_length=20, blank=True)
    consecutive_failures = models.PositiveIntegerField(default=0)
    
    # Rate limiting
    requests_per_minute = models.PositiveIntegerField(default=60)
    requests_per_hour = models.PositiveIntegerField(default=1000)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    # Configuration metadata
    config = models.JSONField(default=dict, blank=True)
    
    class Meta:
        db_table = 'external_system_integrations'
        indexes = [
            models.Index(fields=['system_type', 'status']),
            models.Index(fields=['status', 'last_health_check']),
        ]
        ordering = ['system_type', 'system_name']
    
    def __str__(self):
        return f"{self.system_name} ({self.system_type}) - {self.status}"
    
    def is_healthy(self):
        """Check if integration is healthy."""
        return (
            self.status == 'active' and
            self.health_check_status == 'healthy' and
            self.consecutive_failures < 5
        )


class AuditLog(models.Model):
    """
    Comprehensive audit log for all system activities.
    """
    
    ACTION_TYPES = [
        ('api_request', 'API Request'),
        ('payment_processed', 'Payment Processed'),
        ('webhook_received', 'Webhook Received'),
        ('notification_sent', 'Notification Sent'),
        ('status_changed', 'Status Changed'),
        ('error_occurred', 'Error Occurred'),
        ('user_action', 'User Action'),
        ('system_action', 'System Action'),
    ]
    
    # Primary key
    log_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    # Action details
    action_type = models.CharField(max_length=50, choices=ACTION_TYPES, db_index=True)
    action_description = models.CharField(max_length=255)
    
    # Related objects (generic foreign key would be better, but keeping simple)
    invoice_id = models.CharField(max_length=100, blank=True, db_index=True)
    payment_id = models.CharField(max_length=100, blank=True, db_index=True)
    
    # Actor information
    actor_type = models.CharField(max_length=20, default='system')  # user, system, api
    actor_id = models.CharField(max_length=100, blank=True)
    actor_email = models.EmailField(blank=True)
    
    # Request context
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    request_id = models.CharField(max_length=100, blank=True, db_index=True)
    
    # Action data
    old_values = models.JSONField(default=dict, blank=True)
    new_values = models.JSONField(default=dict, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    
    # Timestamp
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    
    class Meta:
        db_table = 'audit_logs'
        indexes = [
            models.Index(fields=['action_type', 'created_at']),
            models.Index(fields=['invoice_id', 'created_at']),
            models.Index(fields=['payment_id', 'created_at']),
            models.Index(fields=['actor_type', 'created_at']),
        ]
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.action_type} - {self.action_description} - {self.created_at}"