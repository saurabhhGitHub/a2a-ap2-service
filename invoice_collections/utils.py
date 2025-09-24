"""
Utility functions for the Collections Agent.

This module contains helper functions for Google Cloud integration,
Stripe operations, and other common utilities.
"""

import logging
import json
from typing import Dict, Any, Optional
from django.conf import settings
from google.cloud import secretmanager, pubsub_v1, logging as cloud_logging

logger = logging.getLogger(__name__)


def get_google_cloud_secrets(secret_name: str) -> str:
    """
    Retrieve a secret from Google Cloud Secret Manager.
    
    Args:
        secret_name: Name of the secret to retrieve
        
    Returns:
        Secret value as string
        
    Raises:
        Exception: If secret cannot be retrieved
    """
    try:
        client = secretmanager.SecretManagerServiceClient()
        project_id = settings.GOOGLE_CLOUD_PROJECT
        name = f"projects/{project_id}/secrets/{secret_name}/versions/latest"
        
        response = client.access_secret_version(request={"name": name})
        return response.payload.data.decode("UTF-8")
        
    except Exception as e:
        logger.error(f"Failed to retrieve secret {secret_name}: {e}")
        raise


def publish_to_pubsub(topic: str, message: Dict[str, Any]) -> None:
    """
    Publish a message to Google Cloud Pub/Sub.
    
    Args:
        topic: Pub/Sub topic name
        message: Message data to publish
    """
    try:
        publisher = pubsub_v1.PublisherClient()
        project_id = settings.GOOGLE_CLOUD_PROJECT
        topic_path = publisher.topic_path(project_id, topic)
        
        message_data = json.dumps(message).encode("utf-8")
        future = publisher.publish(topic_path, message_data)
        
        logger.info(f"Published message to {topic}: {future.result()}")
        
    except Exception as e:
        logger.error(f"Failed to publish to Pub/Sub topic {topic}: {e}")
        raise


def log_to_cloud_logging(severity: str, message: str, **kwargs) -> None:
    """
    Log a message to Google Cloud Logging.
    
    Args:
        severity: Log severity level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        message: Log message
        **kwargs: Additional log data
    """
    try:
        client = cloud_logging.Client()
        logger_instance = client.logger("collections-agent")
        
        # Map severity string to Cloud Logging severity
        severity_map = {
            'DEBUG': cloud_logging.DEBUG,
            'INFO': cloud_logging.INFO,
            'WARNING': cloud_logging.WARNING,
            'ERROR': cloud_logging.ERROR,
            'CRITICAL': cloud_logging.CRITICAL,
        }
        
        log_severity = severity_map.get(severity.upper(), cloud_logging.INFO)
        
        logger_instance.log_struct(
            {
                'message': message,
                'severity': severity,
                **kwargs
            },
            severity=log_severity
        )
        
    except Exception as e:
        # Fallback to standard logging if Cloud Logging fails
        logger.error(f"Failed to log to Cloud Logging: {e}")
        logger.info(f"Fallback log: {message}")


def validate_mandate_id(mandate_id: str) -> bool:
    """
    Validate that a mandate ID exists and is active in Stripe.
    
    Args:
        mandate_id: Stripe payment method ID to validate
        
    Returns:
        True if mandate is valid, False otherwise
    """
    try:
        import stripe
        
        # Get Stripe secret key from Google Cloud Secret Manager
        stripe.api_key = get_google_cloud_secrets('stripe-secret-key')
        
        # Retrieve the payment method
        payment_method = stripe.PaymentMethod.retrieve(mandate_id)
        
        # Check if payment method is attached to a customer
        if not payment_method.customer:
            logger.warning(f"Payment method {mandate_id} is not attached to a customer")
            return False
        
        # Check if payment method is active
        if payment_method.metadata.get('status') == 'inactive':
            logger.warning(f"Payment method {mandate_id} is inactive")
            return False
        
        return True
        
    except stripe.error.InvalidRequestError:
        logger.warning(f"Invalid payment method ID: {mandate_id}")
        return False
    except Exception as e:
        logger.error(f"Error validating mandate {mandate_id}: {e}")
        return False


def format_currency(amount_cents: int, currency: str = 'USD') -> str:
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
        return f"${amount_dollars:.2f}"
    elif currency == 'EUR':
        return f"€{amount_dollars:.2f}"
    elif currency == 'GBP':
        return f"£{amount_dollars:.2f}"
    else:
        return f"{amount_dollars:.2f} {currency}"


def calculate_stripe_fees(amount_cents: int, payment_method: str) -> int:
    """
    Calculate estimated Stripe fees for a payment.
    
    Args:
        amount_cents: Payment amount in cents
        payment_method: Payment method type (ACH, CARD, etc.)
        
    Returns:
        Estimated fees in cents
    """
    # Stripe fee structure (simplified)
    if payment_method.upper() == 'ACH':
        # ACH: 0.8% + $0.30
        fee_percentage = 0.008
        fixed_fee = 30  # $0.30 in cents
    elif payment_method.upper() == 'CARD':
        # Card: 2.9% + $0.30
        fee_percentage = 0.029
        fixed_fee = 30  # $0.30 in cents
    else:
        # Default to card fees
        fee_percentage = 0.029
        fixed_fee = 30
    
    percentage_fee = int(amount_cents * fee_percentage)
    total_fee = percentage_fee + fixed_fee
    
    return total_fee


def generate_idempotency_key(invoice_id: str, timestamp: str, attempt: int = 1) -> str:
    """
    Generate a unique idempotency key for payment processing.
    
    Args:
        invoice_id: Invoice identifier
        timestamp: Timestamp string
        attempt: Attempt number (for retries)
        
    Returns:
        Unique idempotency key
    """
    return f"payment_{invoice_id}_{timestamp}_{attempt}"


def sanitize_log_data(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Sanitize sensitive data for logging.
    
    Args:
        data: Dictionary containing potentially sensitive data
        
    Returns:
        Sanitized dictionary
    """
    sensitive_keys = [
        'api_key', 'secret', 'password', 'token', 'authorization',
        'stripe_secret_key', 'webhook_secret', 'private_key'
    ]
    
    sanitized = {}
    for key, value in data.items():
        if any(sensitive in key.lower() for sensitive in sensitive_keys):
            if isinstance(value, str) and len(value) > 8:
                sanitized[key] = value[:8] + '...'
            else:
                sanitized[key] = '***'
        else:
            sanitized[key] = value
    
    return sanitized


def retry_with_backoff(func, max_retries: int = 3, base_delay: float = 1.0):
    """
    Retry a function with exponential backoff.
    
    Args:
        func: Function to retry
        max_retries: Maximum number of retry attempts
        base_delay: Base delay in seconds
        
    Returns:
        Function result
        
    Raises:
        Exception: If all retries fail
    """
    import time
    import random
    
    for attempt in range(max_retries + 1):
        try:
            return func()
        except Exception as e:
            if attempt == max_retries:
                raise e
            
            # Calculate delay with jitter
            delay = base_delay * (2 ** attempt) + random.uniform(0, 1)
            logger.warning(f"Attempt {attempt + 1} failed, retrying in {delay:.2f}s: {e}")
            time.sleep(delay)
