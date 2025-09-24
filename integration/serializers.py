"""
Integration Serializers

Serializers for external system integration APIs.
"""

from rest_framework import serializers
from invoice_collections.models import Invoice, AgentAction


class SalesforceWebhookSerializer(serializers.Serializer):
    """Serializer for Salesforce webhook requests."""
    
    invoice_id = serializers.CharField(max_length=100)
    sf_invoice_id = serializers.CharField(max_length=100, required=False)
    amount = serializers.DecimalField(max_digits=10, decimal_places=2)
    currency = serializers.CharField(max_length=3, default='USD')
    customer_id = serializers.CharField(max_length=100)
    customer_name = serializers.CharField(max_length=255)
    mandate_id = serializers.CharField(max_length=100)
    payment_method = serializers.CharField(max_length=50, default='ACH')
    approved_by = serializers.EmailField()
    due_date = serializers.DateTimeField()
    idempotency_key = serializers.CharField(max_length=255)
    
    def validate_amount(self, value):
        """Validate amount is positive."""
        if value <= 0:
            raise serializers.ValidationError("Amount must be positive")
        return value


class SlackApprovalSerializer(serializers.Serializer):
    """Serializer for Slack approval requests."""
    
    invoice_id = serializers.CharField(max_length=100)
    decision = serializers.ChoiceField(choices=['approve', 'reject'])
    user_id = serializers.CharField(max_length=100)
    user_name = serializers.CharField(max_length=255)
    reason = serializers.CharField(max_length=500, required=False, allow_blank=True)
    timestamp = serializers.DateTimeField(required=False)


class StatusResponseSerializer(serializers.ModelSerializer):
    """Serializer for status response."""
    
    recent_actions = serializers.SerializerMethodField()
    
    class Meta:
        model = Invoice
        fields = [
            'invoice_id', 'external_invoice_id', 'status', 'amount_cents',
            'currency', 'customer_name', 'due_date', 'created_at', 'updated_at',
            'recent_actions'
        ]
    
    def get_recent_actions(self, obj):
        """Get recent agent actions."""
        actions = obj.agent_actions.all()[:5]
        return [
            {
                'action_type': action.action_type,
                'decision': action.decision,
                'human_actor': action.human_actor,
                'created_at': action.created_at.isoformat(),
                'notes': action.notes
            }
            for action in actions
        ]


class OverdueInvoiceSerializer(serializers.ModelSerializer):
    """Serializer for overdue invoice list."""
    
    days_overdue = serializers.SerializerMethodField()
    
    class Meta:
        model = Invoice
        fields = [
            'invoice_id', 'external_invoice_id', 'customer_id', 'customer_name',
            'amount_cents', 'currency', 'due_date', 'status', 'days_overdue',
            'mandate_id', 'payment_method'
        ]
    
    def get_days_overdue(self, obj):
        """Calculate days overdue."""
        from django.utils import timezone
        if obj.due_date < timezone.now():
            return (timezone.now() - obj.due_date).days
        return 0


class WebhookStatusUpdateSerializer(serializers.Serializer):
    """Serializer for webhook status updates."""
    
    invoice_id = serializers.CharField(max_length=100)
    status = serializers.ChoiceField(choices=[
        'pending', 'processing', 'completed', 'failed', 'cancelled'
    ])
    source_system = serializers.CharField(max_length=100)
    external_transaction_id = serializers.CharField(max_length=100, required=False, allow_blank=True)
    notes = serializers.CharField(max_length=500, required=False, allow_blank=True)
    metadata = serializers.JSONField(required=False, default=dict)
