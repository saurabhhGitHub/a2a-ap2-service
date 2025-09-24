"""
A2A Broker Models

Models for tracking A2A conversations, sub-agent interactions, and authorization.
"""

import uuid
from django.db import models
from django.utils import timezone


class A2AAgent(models.Model):
    """
    Track registered A2A agents in the system.
    """
    
    AGENT_TYPES = [
        ('collections_agent', 'Collections Agent'),
        ('payment_agent', 'Payment Agent'),
        ('customer_support_agent', 'Customer Support Agent'),
        ('fraud_detection_agent', 'Fraud Detection Agent'),
        ('reconciliation_agent', 'Reconciliation Agent'),
    ]
    
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('inactive', 'Inactive'),
        ('maintenance', 'Maintenance'),
        ('error', 'Error'),
    ]
    
    agent_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    # Agent details
    agent_name = models.CharField(max_length=100, unique=True)
    agent_type = models.CharField(max_length=30, choices=AGENT_TYPES)
    description = models.TextField(blank=True)
    
    # A2A configuration
    a2a_endpoint = models.URLField()
    public_key = models.TextField()  # For signature verification
    capabilities = models.JSONField(default=list)  # List of capabilities
    
    # Status and health
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    last_heartbeat = models.DateTimeField(null=True, blank=True)
    consecutive_failures = models.PositiveIntegerField(default=0)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'a2a_agents'
        indexes = [
            models.Index(fields=['agent_type', 'status']),
            models.Index(fields=['status', 'last_heartbeat']),
        ]
        ordering = ['agent_name']
    
    def __str__(self):
        return f"{self.agent_name} ({self.agent_type}) - {self.status}"


class A2AConversation(models.Model):
    """
    Track A2A conversations between agents.
    """
    
    CONVERSATION_TYPES = [
        ('payment_initiation', 'Payment Initiation'),
        ('customer_verification', 'Customer Verification'),
        ('fraud_check', 'Fraud Check'),
        ('reconciliation', 'Reconciliation'),
        ('mandate_verification', 'Mandate Verification'),
    ]
    
    STATUS_CHOICES = [
        ('initiated', 'Initiated'),
        ('active', 'Active'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('timeout', 'Timeout'),
    ]
    
    conversation_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    # Participants
    initiator_agent = models.ForeignKey(
        A2AAgent, 
        on_delete=models.CASCADE, 
        related_name='initiated_conversations'
    )
    target_agent = models.ForeignKey(
        A2AAgent, 
        on_delete=models.CASCADE, 
        related_name='received_conversations'
    )
    
    # Conversation details
    conversation_type = models.CharField(max_length=30, choices=CONVERSATION_TYPES)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='initiated')
    
    # Context
    context_data = models.JSONField(default=dict)  # Invoice ID, customer info, etc.
    authorization_token = models.CharField(max_length=255, blank=True)
    
    # Results
    result_data = models.JSONField(default=dict, blank=True)
    error_message = models.TextField(blank=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField()
    
    class Meta:
        db_table = 'a2a_conversations'
        indexes = [
            models.Index(fields=['initiator_agent', 'status']),
            models.Index(fields=['target_agent', 'status']),
            models.Index(fields=['conversation_type', 'status']),
            models.Index(fields=['status', 'expires_at']),
        ]
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.conversation_type} - {self.initiator_agent} -> {self.target_agent} - {self.status}"
    
    def is_expired(self):
        """Check if conversation has expired."""
        return timezone.now() > self.expires_at


class A2AMessage(models.Model):
    """
    Track individual messages within A2A conversations.
    """
    
    MESSAGE_TYPES = [
        ('request', 'Request'),
        ('response', 'Response'),
        ('notification', 'Notification'),
        ('error', 'Error'),
    ]
    
    message_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    # Related conversation
    conversation = models.ForeignKey(
        A2AConversation, 
        on_delete=models.CASCADE, 
        related_name='messages'
    )
    
    # Message details
    message_type = models.CharField(max_length=20, choices=MESSAGE_TYPES)
    sender_agent = models.ForeignKey(A2AAgent, on_delete=models.CASCADE)
    
    # Content
    payload = models.JSONField()
    signature = models.CharField(max_length=512)  # Message signature for verification
    
    # Processing
    processed = models.BooleanField(default=False)
    processing_error = models.TextField(blank=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        db_table = 'a2a_messages'
        indexes = [
            models.Index(fields=['conversation', 'created_at']),
            models.Index(fields=['sender_agent', 'created_at']),
            models.Index(fields=['message_type', 'created_at']),
        ]
        ordering = ['created_at']
    
    def __str__(self):
        return f"{self.message_type} - {self.sender_agent} - {self.created_at}"


class A2AAuthorization(models.Model):
    """
    Track A2A authorization grants between agents.
    """
    
    PERMISSION_TYPES = [
        ('payment_initiate', 'Payment Initiation'),
        ('customer_data_access', 'Customer Data Access'),
        ('mandate_verification', 'Mandate Verification'),
        ('fraud_check', 'Fraud Check'),
        ('reconciliation', 'Reconciliation'),
    ]
    
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('revoked', 'Revoked'),
        ('expired', 'Expired'),
    ]
    
    authorization_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    # Participants
    grantor_agent = models.ForeignKey(
        A2AAgent, 
        on_delete=models.CASCADE, 
        related_name='granted_authorizations'
    )
    grantee_agent = models.ForeignKey(
        A2AAgent, 
        on_delete=models.CASCADE, 
        related_name='received_authorizations'
    )
    
    # Authorization details
    permission_type = models.CharField(max_length=30, choices=PERMISSION_TYPES)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    
    # Scope and limits
    scope_data = models.JSONField(default=dict)  # Specific permissions, limits, etc.
    max_amount_cents = models.PositiveIntegerField(null=True, blank=True)
    max_frequency_per_hour = models.PositiveIntegerField(null=True, blank=True)
    
    # Expiration
    expires_at = models.DateTimeField()
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        db_table = 'a2a_authorizations'
        indexes = [
            models.Index(fields=['grantor_agent', 'status']),
            models.Index(fields=['grantee_agent', 'status']),
            models.Index(fields=['permission_type', 'status']),
            models.Index(fields=['status', 'expires_at']),
        ]
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.permission_type} - {self.grantor_agent} -> {self.grantee_agent} - {self.status}"
    
    def is_expired(self):
        """Check if authorization has expired."""
        return timezone.now() > self.expires_at
    
    def is_valid(self):
        """Check if authorization is valid."""
        return (
            self.status == 'active' and 
            not self.is_expired()
        )
