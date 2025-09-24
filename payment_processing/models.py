"""
Payment Processing Models

This module contains models for managing payment processing,
Stripe integration, and payment method management.
"""

import uuid
from django.db import models
from django.core.validators import MinValueValidator
from django.utils import timezone


class PaymentMethod(models.Model):
    """
    Store payment methods (mandates) for customers.
    """
    
    PAYMENT_METHOD_TYPES = [
        ('card', 'Credit/Debit Card'),
        ('ach', 'ACH Bank Transfer'),
        ('sepa', 'SEPA Direct Debit'),
        ('bacs', 'BACS Direct Debit'),
    ]
    
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('inactive', 'Inactive'),
        ('expired', 'Expired'),
        ('failed', 'Failed'),
    ]
    
    # Primary key
    payment_method_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    # Stripe payment method ID
    stripe_payment_method_id = models.CharField(max_length=100, unique=True, db_index=True)
    
    # Customer information
    customer_id = models.CharField(max_length=100, db_index=True)
    customer_name = models.CharField(max_length=255)
    
    # Payment method details
    type = models.CharField(max_length=20, choices=PAYMENT_METHOD_TYPES)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    
    # Card details (for cards)
    last_four = models.CharField(max_length=4, blank=True)
    brand = models.CharField(max_length=20, blank=True)  # visa, mastercard, etc.
    exp_month = models.PositiveIntegerField(null=True, blank=True)
    exp_year = models.PositiveIntegerField(null=True, blank=True)
    
    # Bank details (for ACH)
    bank_name = models.CharField(max_length=100, blank=True)
    account_type = models.CharField(max_length=20, blank=True)  # checking, savings
    
    # Mandate information
    mandate_id = models.CharField(max_length=100, unique=True, db_index=True)
    mandate_status = models.CharField(max_length=20, default='active')
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    
    # Metadata
    metadata = models.JSONField(default=dict, blank=True)
    
    class Meta:
        db_table = 'payment_methods'
        indexes = [
            models.Index(fields=['customer_id', 'status']),
            models.Index(fields=['type', 'status']),
            models.Index(fields=['mandate_id']),
        ]
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.customer_name} - {self.type} - {self.last_four or '****'}"
    
    def is_expired(self):
        """Check if payment method is expired."""
        if self.expires_at:
            return timezone.now() > self.expires_at
        return False
    
    def is_valid(self):
        """Check if payment method is valid for payments."""
        return (
            self.status == 'active' and
            self.mandate_status == 'active' and
            not self.is_expired()
        )


class Payment(models.Model):
    """
    Track individual payments processed through Stripe.
    """
    
    PAYMENT_STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('succeeded', 'Succeeded'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled'),
        ('requires_action', 'Requires Action'),
    ]
    
    PAYMENT_METHOD_CHOICES = [
        ('card', 'Credit/Debit Card'),
        ('ach', 'ACH Bank Transfer'),
        ('sepa', 'SEPA Direct Debit'),
        ('bacs', 'BACS Direct Debit'),
    ]
    
    # Primary key
    payment_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    # Related invoice
    invoice = models.ForeignKey(
        'invoice_collections.Invoice',
        on_delete=models.CASCADE,
        related_name='payments',
        db_index=True
    )
    
    # Payment method used
    payment_method = models.ForeignKey(
        PaymentMethod,
        on_delete=models.PROTECT,
        related_name='payments',
        db_index=True
    )
    
    # Payment details
    amount_cents = models.PositiveIntegerField(
        validators=[MinValueValidator(1)]
    )
    currency = models.CharField(max_length=3, default='USD')
    method = models.CharField(max_length=20, choices=PAYMENT_METHOD_CHOICES)
    
    # Stripe details
    stripe_payment_intent_id = models.CharField(max_length=100, unique=True, db_index=True)
    stripe_charge_id = models.CharField(max_length=100, blank=True)
    
    # Status and processing
    status = models.CharField(
        max_length=20,
        choices=PAYMENT_STATUS_CHOICES,
        default='pending',
        db_index=True
    )
    
    # Financial details
    amount_received_cents = models.PositiveIntegerField(default=0)
    fees_charged_cents = models.PositiveIntegerField(default=0)
    net_amount_cents = models.PositiveIntegerField(default=0)
    
    # Error tracking
    failure_code = models.CharField(max_length=100, blank=True)
    failure_message = models.TextField(blank=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    processed_at = models.DateTimeField(null=True, blank=True)
    settled_at = models.DateTimeField(null=True, blank=True)
    
    # Raw Stripe response
    raw_stripe_response = models.JSONField(default=dict, blank=True)
    
    # Additional metadata
    metadata = models.JSONField(default=dict, blank=True)
    
    class Meta:
        db_table = 'payments'
        indexes = [
            models.Index(fields=['invoice', 'created_at']),
            models.Index(fields=['status', 'created_at']),
            models.Index(fields=['stripe_payment_intent_id']),
            models.Index(fields=['payment_method', 'created_at']),
        ]
        ordering = ['-created_at']
    
    def __str__(self):
        return f"Payment {self.payment_id} - {self.invoice.invoice_id} - {self.status}"
    
    @property
    def amount_dollars(self):
        """Convert amount from cents to dollars."""
        return self.amount_cents / 100
    
    @property
    def fees_dollars(self):
        """Convert fees from cents to dollars."""
        return self.fees_charged_cents / 100
    
    @property
    def net_amount_dollars(self):
        """Convert net amount from cents to dollars."""
        return self.net_amount_cents / 100
    
    def is_successful(self):
        """Check if payment was successful."""
        return self.status == 'succeeded'
    
    def is_failed(self):
        """Check if payment failed."""
        return self.status == 'failed'
    
    def is_pending(self):
        """Check if payment is still pending."""
        return self.status in ['pending', 'processing', 'requires_action']


class PaymentWebhook(models.Model):
    """
    Track Stripe webhook events for audit and debugging.
    """
    
    WEBHOOK_TYPES = [
        ('payment_intent.succeeded', 'Payment Intent Succeeded'),
        ('payment_intent.payment_failed', 'Payment Intent Failed'),
        ('payment_intent.canceled', 'Payment Intent Canceled'),
        ('payment_intent.requires_action', 'Payment Intent Requires Action'),
        ('charge.succeeded', 'Charge Succeeded'),
        ('charge.failed', 'Charge Failed'),
        ('payment_method.attached', 'Payment Method Attached'),
        ('payment_method.detached', 'Payment Method Detached'),
    ]
    
    # Primary key
    webhook_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    # Stripe webhook details
    stripe_event_id = models.CharField(max_length=100, unique=True, db_index=True)
    webhook_type = models.CharField(max_length=50, choices=WEBHOOK_TYPES, db_index=True)
    
    # Related payment (if applicable)
    payment = models.ForeignKey(
        Payment,
        on_delete=models.CASCADE,
        related_name='webhooks',
        null=True,
        blank=True,
        db_index=True
    )
    
    # Processing status
    processed = models.BooleanField(default=False)
    processing_error = models.TextField(blank=True)
    
    # Raw webhook data
    raw_webhook_data = models.JSONField()
    
    # Timestamps
    received_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        db_table = 'payment_processing_webhooks'
        indexes = [
            models.Index(fields=['stripe_event_id']),
            models.Index(fields=['webhook_type', 'received_at']),
            models.Index(fields=['processed', 'received_at']),
        ]
        ordering = ['-received_at']
    
    def __str__(self):
        return f"Webhook {self.stripe_event_id} - {self.webhook_type}"


class PaymentRetry(models.Model):
    """
    Track payment retry attempts for failed payments.
    """
    
    RETRY_STATUS_CHOICES = [
        ('scheduled', 'Scheduled'),
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled'),
    ]
    
    # Primary key
    retry_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    # Related payment
    payment = models.ForeignKey(
        Payment,
        on_delete=models.CASCADE,
        related_name='retries',
        db_index=True
    )
    
    # Retry details
    retry_number = models.PositiveIntegerField()
    status = models.CharField(
        max_length=20,
        choices=RETRY_STATUS_CHOICES,
        default='scheduled',
        db_index=True
    )
    
    # Scheduling
    scheduled_at = models.DateTimeField()
    attempted_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    
    # Retry reason and result
    retry_reason = models.CharField(max_length=100)
    error_message = models.TextField(blank=True)
    
    # New payment intent (if created)
    new_stripe_payment_intent_id = models.CharField(max_length=100, blank=True)
    
    class Meta:
        db_table = 'payment_retries'
        indexes = [
            models.Index(fields=['payment', 'retry_number']),
            models.Index(fields=['status', 'scheduled_at']),
        ]
        ordering = ['-scheduled_at']
    
    def __str__(self):
        return f"Retry {self.retry_number} - {self.payment.payment_id} - {self.status}"