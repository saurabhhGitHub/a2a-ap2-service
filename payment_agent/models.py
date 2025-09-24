"""
Payment Agent (AP2) Models

Models for AP2-compliant payment orchestration and settlement tracking.
"""

import uuid
from django.db import models
from django.utils import timezone


class PaymentProcessor(models.Model):
    """
    Track payment processors integrated with the AP2 Payment Agent.
    """
    
    PROCESSOR_TYPES = [
        ('stripe', 'Stripe'),
        ('adyen', 'Adyen'),
        ('plaid', 'Plaid'),
        ('banking_api', 'Banking API'),
    ]
    
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('inactive', 'Inactive'),
        ('maintenance', 'Maintenance'),
        ('error', 'Error'),
    ]
    
    processor_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    # Processor details
    processor_name = models.CharField(max_length=100, unique=True)
    processor_type = models.CharField(max_length=20, choices=PROCESSOR_TYPES)
    description = models.TextField(blank=True)
    
    # Configuration
    api_endpoint = models.URLField()
    webhook_endpoint = models.URLField(blank=True)
    api_key = models.CharField(max_length=255)  # Encrypted in production
    secret_key = models.CharField(max_length=255, blank=True)  # Encrypted in production
    
    # Supported payment methods
    supported_methods = models.JSONField(default=list)  # ['ach', 'card', 'sepa', 'bacs']
    supported_currencies = models.JSONField(default=list)  # ['USD', 'EUR', 'GBP']
    
    # Status and health
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    last_health_check = models.DateTimeField(null=True, blank=True)
    consecutive_failures = models.PositiveIntegerField(default=0)
    
    # Rate limiting
    requests_per_minute = models.PositiveIntegerField(default=60)
    requests_per_hour = models.PositiveIntegerField(default=1000)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'payment_processors'
        indexes = [
            models.Index(fields=['processor_type', 'status']),
            models.Index(fields=['status', 'last_health_check']),
        ]
        ordering = ['processor_name']
    
    def __str__(self):
        return f"{self.processor_name} ({self.processor_type}) - {self.status}"


class AP2PaymentRequest(models.Model):
    """
    Track AP2 payment requests from Collections Agent.
    """
    
    PAYMENT_METHODS = [
        ('ach', 'ACH Bank Transfer'),
        ('card', 'Credit/Debit Card'),
        ('sepa', 'SEPA Direct Debit'),
        ('bacs', 'BACS Direct Debit'),
        ('wire', 'Wire Transfer'),
    ]
    
    STATUS_CHOICES = [
        ('received', 'Received'),
        ('processing', 'Processing'),
        ('authorized', 'Authorized'),
        ('settled', 'Settled'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled'),
    ]
    
    request_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    # Related entities
    invoice = models.ForeignKey('invoice_collections.Invoice', on_delete=models.CASCADE)
    processor = models.ForeignKey(PaymentProcessor, on_delete=models.CASCADE)
    
    # AP2 request details
    ap2_request_id = models.CharField(max_length=100, unique=True, db_index=True)
    mandate_id = models.CharField(max_length=100, db_index=True)
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHODS)
    
    # Payment details
    amount_cents = models.PositiveIntegerField()
    currency = models.CharField(max_length=3, default='USD')
    description = models.TextField(blank=True)
    
    # AP2 metadata
    ap2_version = models.CharField(max_length=10, default='1.0')
    idempotency_key = models.CharField(max_length=100, unique=True, db_index=True)
    context_data = models.JSONField(default=dict)
    
    # Status and processing
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='received')
    external_transaction_id = models.CharField(max_length=100, blank=True)
    
    # Results
    settlement_amount_cents = models.PositiveIntegerField(default=0)
    fees_charged_cents = models.PositiveIntegerField(default=0)
    net_amount_cents = models.PositiveIntegerField(default=0)
    
    # Error tracking
    error_code = models.CharField(max_length=100, blank=True)
    error_message = models.TextField(blank=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)
    settled_at = models.DateTimeField(null=True, blank=True)
    
    # Raw responses
    raw_request = models.JSONField(default=dict)
    raw_response = models.JSONField(default=dict, blank=True)
    
    class Meta:
        db_table = 'ap2_payment_requests'
        indexes = [
            models.Index(fields=['invoice', 'created_at']),
            models.Index(fields=['processor', 'status']),
            models.Index(fields=['status', 'created_at']),
            models.Index(fields=['ap2_request_id']),
            models.Index(fields=['mandate_id']),
        ]
        ordering = ['-created_at']
    
    def __str__(self):
        return f"AP2 Request {self.ap2_request_id} - {self.invoice.invoice_id} - {self.status}"
    
    @property
    def amount_dollars(self):
        """Convert amount from cents to dollars."""
        return self.amount_cents / 100
    
    @property
    def settlement_amount_dollars(self):
        """Convert settlement amount from cents to dollars."""
        return self.settlement_amount_cents / 100


class PaymentSettlement(models.Model):
    """
    Track payment settlements and reconciliation.
    """
    
    SETTLEMENT_TYPES = [
        ('immediate', 'Immediate'),
        ('next_day', 'Next Day'),
        ('standard', 'Standard (2-3 days)'),
        ('extended', 'Extended (5-7 days)'),
    ]
    
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('settled', 'Settled'),
        ('failed', 'Failed'),
        ('reversed', 'Reversed'),
    ]
    
    settlement_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    # Related payment request
    payment_request = models.ForeignKey(
        AP2PaymentRequest, 
        on_delete=models.CASCADE, 
        related_name='settlements'
    )
    
    # Settlement details
    settlement_type = models.CharField(max_length=20, choices=SETTLEMENT_TYPES)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    
    # Financial details
    gross_amount_cents = models.PositiveIntegerField()
    fees_cents = models.PositiveIntegerField()
    net_amount_cents = models.PositiveIntegerField()
    
    # External references
    external_settlement_id = models.CharField(max_length=100, blank=True)
    bank_reference = models.CharField(max_length=100, blank=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)
    settled_at = models.DateTimeField(null=True, blank=True)
    expected_settlement_date = models.DateTimeField()
    
    # Reconciliation
    reconciled = models.BooleanField(default=False)
    reconciled_at = models.DateTimeField(null=True, blank=True)
    reconciliation_reference = models.CharField(max_length=100, blank=True)
    
    class Meta:
        db_table = 'payment_settlements'
        indexes = [
            models.Index(fields=['payment_request', 'created_at']),
            models.Index(fields=['status', 'expected_settlement_date']),
            models.Index(fields=['reconciled', 'settled_at']),
        ]
        ordering = ['-created_at']
    
    def __str__(self):
        return f"Settlement {self.settlement_id} - {self.payment_request.ap2_request_id} - {self.status}"


class PaymentWebhook(models.Model):
    """
    Track webhooks from payment processors.
    """
    
    WEBHOOK_TYPES = [
        ('payment.succeeded', 'Payment Succeeded'),
        ('payment.failed', 'Payment Failed'),
        ('payment.cancelled', 'Payment Cancelled'),
        ('settlement.completed', 'Settlement Completed'),
        ('mandate.updated', 'Mandate Updated'),
        ('mandate.revoked', 'Mandate Revoked'),
    ]
    
    webhook_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    # Related entities
    processor = models.ForeignKey(PaymentProcessor, on_delete=models.CASCADE)
    payment_request = models.ForeignKey(
        AP2PaymentRequest, 
        on_delete=models.CASCADE, 
        null=True, 
        blank=True
    )
    
    # Webhook details
    webhook_type = models.CharField(max_length=30, choices=WEBHOOK_TYPES)
    external_event_id = models.CharField(max_length=100, unique=True, db_index=True)
    
    # Processing status
    processed = models.BooleanField(default=False)
    processing_error = models.TextField(blank=True)
    
    # Raw webhook data
    raw_payload = models.JSONField()
    headers = models.JSONField(default=dict)
    
    # Timestamps
    received_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        db_table = 'payment_webhooks'
        indexes = [
            models.Index(fields=['processor', 'received_at']),
            models.Index(fields=['webhook_type', 'received_at']),
            models.Index(fields=['processed', 'received_at']),
            models.Index(fields=['external_event_id']),
        ]
        ordering = ['-received_at']
    
    def __str__(self):
        return f"Webhook {self.external_event_id} - {self.webhook_type} - {self.processor}"
