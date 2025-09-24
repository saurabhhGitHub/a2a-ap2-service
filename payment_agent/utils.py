"""
Payment Agent (AP2) Utilities

Helper functions for AP2 payment processing, processor integration, and settlement.
"""

import hmac
import hashlib
import json
import time
import uuid
from typing import Dict, Any, Optional
from django.conf import settings
from django.utils import timezone

from .models import PaymentProcessor, AP2PaymentRequest


def verify_ap2_signature(request) -> bool:
    """
    Verify AP2 request signature for security.
    
    Args:
        request: Django request object
        
    Returns:
        True if signature is valid, False otherwise
    """
    try:
        # Get signature and timestamp from headers
        signature = request.META.get('HTTP_X_AP2_SIGNATURE', '')
        timestamp = request.META.get('HTTP_X_AP2_TIMESTAMP', '')
        agent_id = request.META.get('HTTP_X_AP2_AGENT_ID', '')
        
        if not signature or not timestamp or not agent_id:
            return False
        
        # Check timestamp (prevent replay attacks)
        if abs(time.time() - int(timestamp)) > 60 * 5:  # 5 minutes
            return False
        
        # Create signature
        sig_basestring = f"{timestamp}:{request.body.decode('utf-8')}"
        expected_signature = hmac.new(
            settings.SECRET_KEY.encode('utf-8'),
            sig_basestring.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        
        # Compare signatures
        return hmac.compare_digest(signature, expected_signature)
        
    except Exception:
        return False


def create_payment_request_id() -> str:
    """
    Create a unique AP2 payment request ID.
    
    Returns:
        Unique payment request ID
    """
    timestamp = int(time.time())
    random_part = str(uuid.uuid4())[:8]
    return f"ap2_req_{timestamp}_{random_part}"


def process_stripe_payment(ap2_request: AP2PaymentRequest, request_data: dict) -> Dict[str, Any]:
    """
    Process payment through Stripe.
    
    Args:
        ap2_request: AP2 payment request
        request_data: Request data
        
    Returns:
        Processing result
    """
    try:
        import stripe
        
        # Configure Stripe
        stripe.api_key = ap2_request.processor.api_key
        
        # Create payment intent
        payment_intent_data = {
            'amount': ap2_request.amount_cents,
            'currency': ap2_request.currency.lower(),
            'payment_method': ap2_request.mandate_id,
            'confirm': True,
            'metadata': {
                'ap2_request_id': ap2_request.ap2_request_id,
                'invoice_id': ap2_request.invoice.invoice_id,
                'customer_id': ap2_request.invoice.customer_id
            }
        }
        
        # Add description if provided
        if ap2_request.description:
            payment_intent_data['description'] = ap2_request.description
        
        # Create payment intent
        payment_intent = stripe.PaymentIntent.create(**payment_intent_data)
        
        # Calculate estimated settlement
        estimated_settlement = timezone.now() + timezone.timedelta(days=2)  # Standard ACH
        
        return {
            'status': payment_intent.status,
            'transaction_id': payment_intent.id,
            'estimated_settlement': estimated_settlement.isoformat(),
            'stripe_response': payment_intent.to_dict()
        }
        
    except stripe.error.CardError as e:
        return {
            'status': 'failed',
            'error': str(e),
            'error_code': 'card_declined'
        }
    except stripe.error.RateLimitError as e:
        return {
            'status': 'failed',
            'error': str(e),
            'error_code': 'rate_limit'
        }
    except stripe.error.InvalidRequestError as e:
        return {
            'status': 'failed',
            'error': str(e),
            'error_code': 'invalid_request'
        }
    except stripe.error.AuthenticationError as e:
        return {
            'status': 'failed',
            'error': str(e),
            'error_code': 'authentication_error'
        }
    except stripe.error.APIConnectionError as e:
        return {
            'status': 'failed',
            'error': str(e),
            'error_code': 'api_connection_error'
        }
    except stripe.error.StripeError as e:
        return {
            'status': 'failed',
            'error': str(e),
            'error_code': 'stripe_error'
        }
    except Exception as e:
        return {
            'status': 'failed',
            'error': str(e),
            'error_code': 'unknown_error'
        }


def process_adyen_payment(ap2_request: AP2PaymentRequest, request_data: dict) -> Dict[str, Any]:
    """
    Process payment through Adyen.
    
    Args:
        ap2_request: AP2 payment request
        request_data: Request data
        
    Returns:
        Processing result
    """
    try:
        from adyen import Adyen
        
        # Configure Adyen
        adyen = Adyen()
        adyen.payment.client.api_key = ap2_request.processor.api_key
        adyen.payment.client.merchant_account = ap2_request.processor.config.get('merchant_account', '')
        
        # Create payment request
        payment_data = {
            'amount': {
                'value': ap2_request.amount_cents,
                'currency': ap2_request.currency.upper()
            },
            'paymentMethod': {
                'type': 'scheme',  # Card payment
                'storedPaymentMethodId': ap2_request.mandate_id
            },
            'reference': ap2_request.ap2_request_id,
            'merchantAccount': adyen.payment.client.merchant_account,
            'metadata': {
                'ap2_request_id': ap2_request.ap2_request_id,
                'invoice_id': ap2_request.invoice.invoice_id,
                'customer_id': ap2_request.invoice.customer_id
            }
        }
        
        # Add description if provided
        if ap2_request.description:
            payment_data['description'] = ap2_request.description
        
        # Process payment
        result = adyen.payment.payments(payment_data)
        
        # Calculate estimated settlement
        estimated_settlement = timezone.now() + timezone.timedelta(days=1)  # Adyen is typically faster
        
        return {
            'status': result.message.get('resultCode', 'unknown'),
            'transaction_id': result.message.get('pspReference', ''),
            'estimated_settlement': estimated_settlement.isoformat(),
            'adyen_response': result.message
        }
        
    except Exception as e:
        return {
            'status': 'failed',
            'error': str(e),
            'error_code': 'adyen_error'
        }


def process_plaid_payment(ap2_request: AP2PaymentRequest, request_data: dict) -> Dict[str, Any]:
    """
    Process payment through Plaid ACH.
    
    Args:
        ap2_request: AP2 payment request
        request_data: Request data
        
    Returns:
        Processing result
    """
    try:
        import plaid
        
        # Configure Plaid
        client = plaid.Client(
            client_id=ap2_request.processor.config.get('client_id', ''),
            secret=ap2_request.processor.secret_key,
            environment=ap2_request.processor.config.get('environment', 'sandbox')
        )
        
        # Create ACH payment
        payment_data = {
            'amount': {
                'value': ap2_request.amount_cents / 100,  # Plaid expects dollars
                'currency': ap2_request.currency.upper()
            },
            'payment_method': {
                'type': 'ach',
                'ach': {
                    'account_id': ap2_request.mandate_id,
                    'routing_number': ap2_request.context_data.get('routing_number', ''),
                    'account_number': ap2_request.context_data.get('account_number', '')
                }
            },
            'reference': ap2_request.ap2_request_id,
            'metadata': {
                'ap2_request_id': ap2_request.ap2_request_id,
                'invoice_id': ap2_request.invoice.invoice_id,
                'customer_id': ap2_request.invoice.customer_id
            }
        }
        
        # Add description if provided
        if ap2_request.description:
            payment_data['description'] = ap2_request.description
        
        # Process payment
        result = client.payment_initiation.payment_create(payment_data)
        
        # Calculate estimated settlement (ACH is typically 1-3 business days)
        estimated_settlement = timezone.now() + timezone.timedelta(days=3)
        
        return {
            'status': 'processing',
            'transaction_id': result['payment_id'],
            'estimated_settlement': estimated_settlement.isoformat(),
            'plaid_response': result
        }
        
    except Exception as e:
        return {
            'status': 'failed',
            'error': str(e),
            'error_code': 'plaid_error'
        }


def calculate_payment_fees(amount_cents: int, payment_method: str, processor_type: str) -> int:
    """
    Calculate estimated payment fees.
    
    Args:
        amount_cents: Payment amount in cents
        payment_method: Payment method
        processor_type: Processor type
        
    Returns:
        Estimated fees in cents
    """
    try:
        # Fee structures (simplified)
        if processor_type == 'stripe':
            if payment_method.lower() == 'ach':
                # ACH: 0.8% + $0.30
                fee_percentage = 0.008
                fixed_fee = 30
            else:  # Card
                # Card: 2.9% + $0.30
                fee_percentage = 0.029
                fixed_fee = 30
        elif processor_type == 'adyen':
            if payment_method.lower() == 'ach':
                # ACH: 0.5% + $0.25
                fee_percentage = 0.005
                fixed_fee = 25
            else:  # Card
                # Card: 2.5% + $0.25
                fee_percentage = 0.025
                fixed_fee = 25
        elif processor_type == 'plaid':
            # ACH: 0.3% + $0.20
            fee_percentage = 0.003
            fixed_fee = 20
        else:
            # Default to Stripe card fees
            fee_percentage = 0.029
            fixed_fee = 30
        
        percentage_fee = int(amount_cents * fee_percentage)
        total_fee = percentage_fee + fixed_fee
        
        return total_fee
        
    except Exception:
        return 0


def format_currency_amount(amount_cents: int, currency: str = 'USD') -> str:
    """
    Format amount in cents to currency string.
    
    Args:
        amount_cents: Amount in cents
        currency: Currency code
        
    Returns:
        Formatted currency string
    """
    amount_dollars = amount_cents / 100
    
    if currency == 'USD':
        return f"${amount_dollars:,.2f}"
    elif currency == 'EUR':
        return f"€{amount_dollars:,.2f}"
    elif currency == 'GBP':
        return f"£{amount_dollars:,.2f}"
    else:
        return f"{amount_dollars:,.2f} {currency}"


def validate_payment_request(request_data: dict) -> Dict[str, Any]:
    """
    Validate AP2 payment request data.
    
    Args:
        request_data: Request data dictionary
        
    Returns:
        Validation result
    """
    errors = []
    
    # Required fields
    required_fields = [
        'invoice_id', 'mandate_id', 'amount_cents', 'currency', 
        'payment_method', 'idempotency_key'
    ]
    
    for field in required_fields:
        if field not in request_data:
            errors.append(f"Missing required field: {field}")
    
    # Validate amount
    if 'amount_cents' in request_data:
        try:
            amount = int(request_data['amount_cents'])
            if amount <= 0:
                errors.append("Amount must be greater than 0")
            elif amount > 100000000:  # $1M limit
                errors.append("Amount exceeds maximum limit")
        except (ValueError, TypeError):
            errors.append("Invalid amount format")
    
    # Validate currency
    if 'currency' in request_data:
        supported_currencies = ['USD', 'EUR', 'GBP', 'CAD', 'AUD']
        if request_data['currency'].upper() not in supported_currencies:
            errors.append(f"Unsupported currency: {request_data['currency']}")
    
    # Validate payment method
    if 'payment_method' in request_data:
        supported_methods = ['ach', 'card', 'sepa', 'bacs', 'wire']
        if request_data['payment_method'].lower() not in supported_methods:
            errors.append(f"Unsupported payment method: {request_data['payment_method']}")
    
    return {
        'valid': len(errors) == 0,
        'errors': errors
    }


def create_settlement_record(ap2_request: AP2PaymentRequest, settlement_data: dict) -> Dict[str, Any]:
    """
    Create a settlement record for a payment request.
    
    Args:
        ap2_request: AP2 payment request
        settlement_data: Settlement data
        
    Returns:
        Settlement record data
    """
    try:
        from .models import PaymentSettlement
        
        # Calculate fees
        fees_cents = calculate_payment_fees(
            ap2_request.amount_cents,
            ap2_request.payment_method,
            ap2_request.processor.processor_type
        )
        
        # Create settlement
        settlement = PaymentSettlement.objects.create(
            payment_request=ap2_request,
            settlement_type=settlement_data.get('settlement_type', 'standard'),
            status='pending',
            gross_amount_cents=ap2_request.amount_cents,
            fees_cents=fees_cents,
            net_amount_cents=ap2_request.amount_cents - fees_cents,
            external_settlement_id=settlement_data.get('external_settlement_id', ''),
            expected_settlement_date=timezone.now() + timezone.timedelta(days=2)
        )
        
        return {
            'settlement_id': str(settlement.settlement_id),
            'status': settlement.status,
            'gross_amount_cents': settlement.gross_amount_cents,
            'fees_cents': settlement.fees_cents,
            'net_amount_cents': settlement.net_amount_cents,
            'expected_settlement_date': settlement.expected_settlement_date.isoformat()
        }
        
    except Exception as e:
        return {
            'error': str(e),
            'error_code': 'settlement_creation_failed'
        }


def send_webhook_notification(webhook_url: str, payload: dict) -> bool:
    """
    Send webhook notification to external system.
    
    Args:
        webhook_url: Webhook URL
        payload: Payload data
        
    Returns:
        True if successful, False otherwise
    """
    try:
        import requests
        
        response = requests.post(
            webhook_url,
            json=payload,
            headers={'Content-Type': 'application/json'},
            timeout=10
        )
        
        return response.status_code == 200
        
    except Exception as e:
        print(f"Error sending webhook notification: {e}")
        return False


def retry_payment_processing(ap2_request: AP2PaymentRequest, max_retries: int = 3) -> Dict[str, Any]:
    """
    Retry payment processing with exponential backoff.
    
    Args:
        ap2_request: AP2 payment request
        max_retries: Maximum number of retries
        
    Returns:
        Retry result
    """
    import time
    
    for attempt in range(max_retries):
        try:
            # Wait before retry (exponential backoff)
            if attempt > 0:
                wait_time = 2 ** attempt
                time.sleep(wait_time)
            
            # Retry payment processing
            if ap2_request.processor.processor_type == 'stripe':
                result = process_stripe_payment(ap2_request, {})
            elif ap2_request.processor.processor_type == 'adyen':
                result = process_adyen_payment(ap2_request, {})
            elif ap2_request.processor.processor_type == 'plaid':
                result = process_plaid_payment(ap2_request, {})
            else:
                return {'status': 'failed', 'error': 'Unknown processor type'}
            
            # If successful, return result
            if result.get('status') in ['succeeded', 'processing', 'authorized']:
                return result
            
        except Exception as e:
            if attempt == max_retries - 1:
                return {'status': 'failed', 'error': str(e)}
    
    return {'status': 'failed', 'error': 'Max retries exceeded'}
