"""
Invoice Collections Models

This module contains the core models for managing invoice collections,
agent actions, and audit trails.
"""

import uuid
from django.db import models
from django.core.validators import MinValueValidator
from django.utils import timezone


class Invoice(models.Model):
    """
    Core invoice model for tracking collection requests and status.
    """
    
    INVOICE_STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled'),
    ]
    
    # Primary identifiers
    invoice_id = models.CharField(max_length=100, unique=True, db_index=True)
    external_invoice_id = models.CharField(max_length=100, unique=True, db_index=True, null=True, blank=True)  # SF or ERP ID
    
    # Financial details
    amount_cents = models.PositiveIntegerField(
        validators=[MinValueValidator(1)],
        help_text="Amount in cents to avoid floating point issues"
    )
    currency = models.CharField(max_length=3, default='USD')
    
    # Customer information
    customer_id = models.CharField(max_length=100, db_index=True)
    customer_name = models.CharField(max_length=255)
    
    # Payment details
    mandate_id = models.CharField(max_length=100, db_index=True)
    payment_method = models.CharField(max_length=50, default='ACH')
    
    # Dates and status
    due_date = models.DateTimeField()
    status = models.CharField(
        max_length=20,
        choices=INVOICE_STATUS_CHOICES,
        default='pending',
        db_index=True
    )
    
    # Approval tracking
    approved_by = models.EmailField()
    idempotency_key = models.CharField(max_length=255, unique=True, db_index=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    # Metadata
    metadata = models.JSONField(default=dict, blank=True)
    
    class Meta:
        db_table = 'invoices'
        indexes = [
            models.Index(fields=['status', 'created_at']),
            models.Index(fields=['customer_id', 'status']),
            models.Index(fields=['due_date', 'status']),
        ]
        ordering = ['-created_at']
    
    def __str__(self):
        return f"Invoice {self.invoice_id} - {self.customer_name} - ${self.amount_cents/100:.2f}"
    
    @property
    def amount_dollars(self):
        """Convert amount from cents to dollars."""
        return self.amount_cents / 100
    
    def is_overdue(self):
        """Check if invoice is overdue."""
        return timezone.now() > self.due_date and self.status not in ['completed', 'cancelled']


class AgentAction(models.Model):
    """
    Audit trail for all agent actions and decisions.
    """
    
    ACTION_TYPE_CHOICES = [
        ('collection_initiated', 'Collection Initiated'),
        ('payment_processed', 'Payment Processed'),
        ('payment_failed', 'Payment Failed'),
        ('status_updated', 'Status Updated'),
        ('webhook_received', 'Webhook Received'),
        ('retry_attempted', 'Retry Attempted'),
        ('manual_intervention', 'Manual Intervention'),
    ]
    
    DECISION_CHOICES = [
        ('approve', 'Approve'),
        ('reject', 'Reject'),
        ('retry', 'Retry'),
        ('escalate', 'Escalate'),
        ('auto_process', 'Auto Process'),
    ]
    
    # Primary key
    action_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    # Related invoice
    invoice = models.ForeignKey(
        Invoice,
        on_delete=models.CASCADE,
        related_name='agent_actions',
        db_index=True
    )
    
    # Action details
    action_type = models.CharField(
        max_length=50,
        choices=ACTION_TYPE_CHOICES,
        db_index=True
    )
    decision = models.CharField(
        max_length=20,
        choices=DECISION_CHOICES,
        null=True,
        blank=True
    )
    
    # Payload and response data
    payload = models.JSONField(default=dict, blank=True)
    response_data = models.JSONField(default=dict, blank=True)
    
    # Actor information
    human_actor = models.EmailField(null=True, blank=True)
    system_actor = models.CharField(max_length=100, default='collections-agent')
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    
    # Additional metadata
    notes = models.TextField(blank=True)
    error_message = models.TextField(blank=True)
    
    class Meta:
        db_table = 'agent_actions'
        indexes = [
            models.Index(fields=['invoice', 'created_at']),
            models.Index(fields=['action_type', 'created_at']),
            models.Index(fields=['decision', 'created_at']),
        ]
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.action_type} - {self.invoice.invoice_id} - {self.created_at}"


class PaymentAttempt(models.Model):
    """
    Track individual payment attempts for retry logic and audit.
    """
    
    ATTEMPT_STATUS_CHOICES = [
        ('initiated', 'Initiated'),
        ('processing', 'Processing'),
        ('succeeded', 'Succeeded'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled'),
    ]
    
    # Primary key
    attempt_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    # Related invoice
    invoice = models.ForeignKey(
        Invoice,
        on_delete=models.CASCADE,
        related_name='payment_attempts',
        db_index=True
    )
    
    # Attempt details
    attempt_number = models.PositiveIntegerField(default=1)
    status = models.CharField(
        max_length=20,
        choices=ATTEMPT_STATUS_CHOICES,
        default='initiated',
        db_index=True
    )
    
    # Stripe details
    stripe_payment_intent_id = models.CharField(max_length=100, blank=True)
    stripe_charge_id = models.CharField(max_length=100, blank=True)
    
    # Amount and fees
    amount_cents = models.PositiveIntegerField()
    fees_charged_cents = models.PositiveIntegerField(default=0)
    
    # Error tracking
    error_code = models.CharField(max_length=100, blank=True)
    error_message = models.TextField(blank=True)
    
    # Timestamps
    initiated_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    
    # Raw response data
    raw_stripe_response = models.JSONField(default=dict, blank=True)
    
    class Meta:
        db_table = 'payment_attempts'
        indexes = [
            models.Index(fields=['invoice', 'attempt_number']),
            models.Index(fields=['status', 'initiated_at']),
            models.Index(fields=['stripe_payment_intent_id']),
        ]
        ordering = ['-initiated_at']
    
    def __str__(self):
        return f"Payment Attempt {self.attempt_number} - {self.invoice.invoice_id} - {self.status}"
    
    @property
    def duration_seconds(self):
        """Calculate duration of payment attempt."""
        if self.completed_at:
            return (self.completed_at - self.initiated_at).total_seconds()
        return None


class CollectionRequest(models.Model):
    """
    Track incoming collection requests for idempotency.
    Note: Salesforce integration is handled by your Salesforce team.
    """
    
    REQUEST_STATUS_CHOICES = [
        ('received', 'Received'),
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    ]
    
    # Primary key
    request_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    # Idempotency key from Salesforce
    idempotency_key = models.CharField(max_length=255, unique=True, db_index=True)
    
    # Request details
    status = models.CharField(
        max_length=20,
        choices=REQUEST_STATUS_CHOICES,
        default='received',
        db_index=True
    )
    
    # Related invoice (created after processing)
    invoice = models.OneToOneField(
        Invoice,
        on_delete=models.CASCADE,
        related_name='collection_request',
        null=True,
        blank=True
    )
    
    # Raw request data
    raw_request_data = models.JSONField()
    
    # Timestamps
    received_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)
    
    # Error tracking
    error_message = models.TextField(blank=True)
    
    class Meta:
        db_table = 'collection_requests'
        indexes = [
            models.Index(fields=['idempotency_key']),
            models.Index(fields=['status', 'received_at']),
        ]
        ordering = ['-received_at']
    
    def __str__(self):
        return f"Collection Request {self.idempotency_key} - {self.status}"