"""
Serializers for Invoice Collections API endpoints.
"""

from rest_framework import serializers
from decimal import Decimal
from .models import Invoice, AgentAction, PaymentAttempt, CollectionRequest


class CollectionRequestSerializer(serializers.Serializer):
    """
    Serializer for incoming collection requests from Salesforce.
    """
    
    # Required fields
    invoice_id = serializers.CharField(max_length=100)
    sf_invoice_id = serializers.CharField(max_length=100)
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
        """
        Validate amount is positive and convert to cents.
        """
        if value <= 0:
            raise serializers.ValidationError("Amount must be positive")
        return value
    
    def validate_currency(self, value):
        """
        Validate currency code.
        """
        valid_currencies = ['USD', 'EUR', 'GBP', 'CAD', 'AUD']
        if value.upper() not in valid_currencies:
            raise serializers.ValidationError(f"Currency must be one of: {', '.join(valid_currencies)}")
        return value.upper()
    
    def validate_payment_method(self, value):
        """
        Validate payment method.
        """
        valid_methods = ['ACH', 'CARD', 'SEPA', 'BACS']
        if value.upper() not in valid_methods:
            raise serializers.ValidationError(f"Payment method must be one of: {', '.join(valid_methods)}")
        return value.upper()


class CollectionResponseSerializer(serializers.Serializer):
    """
    Serializer for collection request responses.
    """
    
    success = serializers.BooleanField()
    payment_id = serializers.UUIDField(required=False)
    status = serializers.CharField()
    transaction_id = serializers.CharField(required=False)
    message = serializers.CharField()
    estimated_completion = serializers.DateTimeField(required=False)
    error_code = serializers.CharField(required=False)
    error_message = serializers.CharField(required=False)


class InvoiceStatusSerializer(serializers.ModelSerializer):
    """
    Serializer for invoice status responses.
    """
    
    amount_dollars = serializers.ReadOnlyField()
    is_overdue = serializers.ReadOnlyField()
    
    class Meta:
        model = Invoice
        fields = [
            'invoice_id', 'sf_invoice_id', 'amount_cents', 'amount_dollars',
            'currency', 'customer_id', 'customer_name', 'status',
            'due_date', 'is_overdue', 'created_at', 'updated_at'
        ]


class AgentActionSerializer(serializers.ModelSerializer):
    """
    Serializer for agent actions.
    """
    
    invoice_id = serializers.CharField(source='invoice.invoice_id', read_only=True)
    
    class Meta:
        model = AgentAction
        fields = [
            'action_id', 'invoice_id', 'action_type', 'decision',
            'human_actor', 'system_actor', 'created_at', 'notes'
        ]


class PaymentAttemptSerializer(serializers.ModelSerializer):
    """
    Serializer for payment attempts.
    """
    
    invoice_id = serializers.CharField(source='invoice.invoice_id', read_only=True)
    duration_seconds = serializers.ReadOnlyField()
    
    class Meta:
        model = PaymentAttempt
        fields = [
            'attempt_id', 'invoice_id', 'attempt_number', 'status',
            'amount_cents', 'fees_charged_cents', 'stripe_payment_intent_id',
            'error_code', 'error_message', 'initiated_at', 'completed_at',
            'duration_seconds'
        ]


class SalesforceNotificationSerializer(serializers.Serializer):
    """
    Serializer for notifications sent to Salesforce.
    """
    
    invoice_id = serializers.CharField()
    sf_invoice_id = serializers.CharField()
    payment_status = serializers.CharField()
    transaction_id = serializers.CharField(required=False)
    amount_settled = serializers.DecimalField(max_digits=10, decimal_places=2, required=False)
    settlement_date = serializers.DateTimeField(required=False)
    fees_charged = serializers.DecimalField(max_digits=10, decimal_places=2, required=False)
    error_code = serializers.CharField(required=False)
    error_message = serializers.CharField(required=False)


class HealthCheckSerializer(serializers.Serializer):
    """
    Serializer for health check responses.
    """
    
    status = serializers.CharField()
    timestamp = serializers.DateTimeField()
    version = serializers.CharField()
    database = serializers.CharField()
    redis = serializers.CharField()
    stripe = serializers.CharField()
    google_cloud = serializers.CharField()
