"""
Synchronous Tasks for Invoice Collections.

This module contains synchronous functions for processing collections,
handling webhooks, and managing notifications.
"""

import logging
import stripe
from datetime import datetime, timedelta
from django.utils import timezone
from django.db import transaction

from .models import Invoice, PaymentAttempt, AgentAction
from payment_processing.models import Payment
from webhook_handlers.models import SalesforceNotification
from .utils import (
    get_google_cloud_secrets, publish_to_pubsub, log_to_cloud_logging,
    validate_mandate_id, calculate_stripe_fees, retry_with_backoff
)

logger = logging.getLogger(__name__)


def process_payment(invoice_id: str):
    """
    Process a payment for an invoice using Stripe.
    
    Args:
        invoice_id: ID of the invoice to process payment for
    """
    try:
        # Get invoice
        invoice = Invoice.objects.get(id=invoice_id)
        
        # Log task start
        log_to_cloud_logging(
            'INFO',
            f'Starting payment processing for invoice {invoice.invoice_id}',
            invoice_id=invoice.invoice_id,
            amount_cents=invoice.amount_cents,
            mandate_id=invoice.mandate_id
        )
        
        # Validate mandate
        if not validate_mandate_id(invoice.mandate_id):
            raise Exception(f"Invalid or inactive mandate: {invoice.mandate_id}")
        
        # Create payment attempt
        attempt = PaymentAttempt.objects.create(
            invoice=invoice,
            attempt_number=1,
            status='initiated',
            amount_cents=invoice.amount_cents
        )
        
        # Configure Stripe
        stripe.api_key = get_google_cloud_secrets('stripe-secret-key')
        
        # Create payment intent
        payment_intent_data = {
            'amount': invoice.amount_cents,
            'currency': invoice.currency.lower(),
            'payment_method': invoice.mandate_id,
            'confirm': True,
            'return_url': 'https://your-app.com/return',  # Required for some payment methods
            'metadata': {
                'invoice_id': invoice.invoice_id,
                'sf_invoice_id': invoice.sf_invoice_id,
                'customer_id': invoice.customer_id,
                'attempt_id': str(attempt.attempt_id)
            }
        }
        
        # Process payment with retry logic
        def create_payment_intent():
            return stripe.PaymentIntent.create(**payment_intent_data)
        
        payment_intent = retry_with_backoff(create_payment_intent, max_retries=3)
        
        # Update payment attempt
        attempt.stripe_payment_intent_id = payment_intent.id
        attempt.status = 'processing'
        attempt.raw_stripe_response = payment_intent.to_dict()
        attempt.save()
        
        # Create payment record
        payment = Payment.objects.create(
            invoice=invoice,
            amount_cents=invoice.amount_cents,
            currency=invoice.currency,
            method=invoice.payment_method.lower(),
            stripe_payment_intent_id=payment_intent.id,
            status='processing',
            raw_stripe_response=payment_intent.to_dict()
        )
        
        # Update invoice status
        invoice.status = 'processing'
        invoice.save()
        
        # Log agent action
        AgentAction.objects.create(
            invoice=invoice,
            action_type='payment_processed',
            decision='auto_process',
            payload={
                'payment_intent_id': payment_intent.id,
                'amount_cents': invoice.amount_cents,
                'mandate_id': invoice.mandate_id
            },
            notes=f'Payment intent created: {payment_intent.id}'
        )
        
        # Publish to Pub/Sub
        try:
            publish_to_pubsub(
                topic='payment-agent-responses',
                message={
                    'invoice_id': invoice.invoice_id,
                    'action': 'payment_initiated',
                    'payment_intent_id': payment_intent.id,
                    'status': 'processing',
                    'timestamp': timezone.now().isoformat()
                }
            )
        except Exception as e:
            logger.warning(f"Failed to publish to Pub/Sub: {e}")
        
        log_to_cloud_logging(
            'INFO',
            f'Payment processing initiated for invoice {invoice.invoice_id}',
            invoice_id=invoice.invoice_id,
            payment_intent_id=payment_intent.id,
            status=payment_intent.status
        )
        
        return {
            'success': True,
            'payment_intent_id': payment_intent.id,
            'status': payment_intent.status
        }
        
    except Exception as e:
        logger.error(f"Payment processing failed for invoice {invoice_id}: {e}", exc_info=True)
        
        # Update invoice status to failed
        try:
            invoice = Invoice.objects.get(id=invoice_id)
            invoice.status = 'failed'
            invoice.save()
            
            # Log failed action
            AgentAction.objects.create(
                invoice=invoice,
                action_type='payment_failed',
                decision='auto_process',
                error_message=str(e),
                notes=f'Payment processing failed: {e}'
            )
        except Exception:
            pass
        
        raise e


def handle_stripe_webhook(webhook_data: dict):
    """
    Handle Stripe webhook events.
    
    Args:
        webhook_data: Webhook event data from Stripe
    """
    try:
        event_type = webhook_data.get('type')
        payment_intent_id = webhook_data.get('data', {}).get('object', {}).get('id')
        
        if not payment_intent_id:
            logger.warning("No payment intent ID in webhook data")
            return
        
        # Find payment by Stripe payment intent ID
        try:
            payment = Payment.objects.get(stripe_payment_intent_id=payment_intent_id)
            invoice = payment.invoice
        except Payment.DoesNotExist:
            logger.warning(f"Payment not found for payment intent {payment_intent_id}")
            return
        
        # Handle different event types
        if event_type == 'payment_intent.succeeded':
            _handle_payment_succeeded(payment, webhook_data)
        elif event_type == 'payment_intent.payment_failed':
            _handle_payment_failed(payment, webhook_data)
        elif event_type == 'payment_intent.canceled':
            _handle_payment_canceled(payment, webhook_data)
        else:
            logger.info(f"Unhandled webhook event type: {event_type}")
        
        # Publish to Pub/Sub
        try:
            publish_to_pubsub(
                topic='payment-agent-responses',
                message={
                    'invoice_id': invoice.invoice_id,
                    'action': 'webhook_processed',
                    'event_type': event_type,
                    'payment_intent_id': payment_intent_id,
                    'timestamp': timezone.now().isoformat()
                }
            )
        except Exception as e:
            logger.warning(f"Failed to publish webhook to Pub/Sub: {e}")
        
    except Exception as e:
        logger.error(f"Webhook processing failed: {e}", exc_info=True)
        raise e


def _handle_payment_succeeded(payment: Payment, webhook_data: dict):
    """Handle successful payment webhook."""
    with transaction.atomic():
        # Update payment
        payment.status = 'succeeded'
        payment.processed_at = timezone.now()
        payment.raw_stripe_response = webhook_data
        
        # Calculate fees
        amount_cents = payment.amount_cents
        fees_cents = calculate_stripe_fees(amount_cents, payment.method)
        payment.fees_charged_cents = fees_cents
        payment.net_amount_cents = amount_cents - fees_cents
        payment.amount_received_cents = amount_cents
        
        payment.save()
        
        # Update invoice
        invoice = payment.invoice
        invoice.status = 'completed'
        invoice.save()
        
        # Update payment attempt
        attempt = invoice.payment_attempts.first()
        if attempt:
            attempt.status = 'succeeded'
            attempt.completed_at = timezone.now()
            attempt.save()
        
        # Log agent action
        AgentAction.objects.create(
            invoice=invoice,
            action_type='payment_processed',
            decision='auto_process',
            payload=webhook_data,
            notes=f'Payment succeeded: {payment.stripe_payment_intent_id}'
        )
        
        # Send Salesforce notification
        notify_salesforce(invoice.id, 'payment_completed')
        
        log_to_cloud_logging(
            'INFO',
            f'Payment succeeded for invoice {invoice.invoice_id}',
            invoice_id=invoice.invoice_id,
            payment_intent_id=payment.stripe_payment_intent_id,
            amount_cents=payment.amount_cents,
            fees_cents=payment.fees_charged_cents
        )


def _handle_payment_failed(payment: Payment, webhook_data: dict):
    """Handle failed payment webhook."""
    with transaction.atomic():
        # Update payment
        payment.status = 'failed'
        payment.processed_at = timezone.now()
        payment.raw_stripe_response = webhook_data
        
        # Extract error information
        error_data = webhook_data.get('data', {}).get('object', {}).get('last_payment_error', {})
        payment.failure_code = error_data.get('code', '')
        payment.failure_message = error_data.get('message', '')
        
        payment.save()
        
        # Update invoice
        invoice = payment.invoice
        invoice.status = 'failed'
        invoice.save()
        
        # Update payment attempt
        attempt = invoice.payment_attempts.first()
        if attempt:
            attempt.status = 'failed'
            attempt.completed_at = timezone.now()
            attempt.error_code = payment.failure_code
            attempt.error_message = payment.failure_message
            attempt.save()
        
        # Log agent action
        AgentAction.objects.create(
            invoice=invoice,
            action_type='payment_failed',
            decision='auto_process',
            payload=webhook_data,
            error_message=payment.failure_message,
            notes=f'Payment failed: {payment.failure_code} - {payment.failure_message}'
        )
        
        # Send Salesforce notification
        notify_salesforce(invoice.id, 'payment_failed')
        
        log_to_cloud_logging(
            'WARNING',
            f'Payment failed for invoice {invoice.invoice_id}',
            invoice_id=invoice.invoice_id,
            payment_intent_id=payment.stripe_payment_intent_id,
            error_code=payment.failure_code,
            error_message=payment.failure_message
        )


def _handle_payment_canceled(payment: Payment, webhook_data: dict):
    """Handle canceled payment webhook."""
    with transaction.atomic():
        # Update payment
        payment.status = 'cancelled'
        payment.processed_at = timezone.now()
        payment.raw_stripe_response = webhook_data
        payment.save()
        
        # Update invoice
        invoice = payment.invoice
        invoice.status = 'cancelled'
        invoice.save()
        
        # Update payment attempt
        attempt = invoice.payment_attempts.first()
        if attempt:
            attempt.status = 'cancelled'
            attempt.completed_at = timezone.now()
            attempt.save()
        
        # Log agent action
        AgentAction.objects.create(
            invoice=invoice,
            action_type='payment_failed',
            decision='auto_process',
            payload=webhook_data,
            notes=f'Payment canceled: {payment.stripe_payment_intent_id}'
        )
        
        # Send Salesforce notification
        notify_salesforce(invoice.id, 'payment_failed')
        
        log_to_cloud_logging(
            'INFO',
            f'Payment canceled for invoice {invoice.invoice_id}',
            invoice_id=invoice.invoice_id,
            payment_intent_id=payment.stripe_payment_intent_id
        )


def notify_salesforce(invoice_id: str, notification_type: str):
    """
    Send notification to Salesforce about payment status.
    
    Args:
        invoice_id: ID of the invoice
        notification_type: Type of notification (payment_completed, payment_failed, etc.)
    """
    try:
        invoice = Invoice.objects.get(id=invoice_id)
        payment = invoice.payments.first()
        
        # Prepare notification data
        notification_data = {
            'invoice_id': invoice.invoice_id,
            'sf_invoice_id': invoice.sf_invoice_id,
            'payment_status': notification_type,
        }
        
        if payment:
            notification_data.update({
                'transaction_id': payment.stripe_payment_intent_id,
                'amount_settled': payment.amount_received_cents / 100,
                'fees_charged': payment.fees_charged_cents / 100,
                'settlement_date': payment.processed_at.isoformat() if payment.processed_at else None,
            })
            
            if payment.status == 'failed':
                notification_data.update({
                    'error_code': payment.failure_code,
                    'error_message': payment.failure_message,
                })
        
        # Create notification record
        notification = SalesforceNotification.objects.create(
            invoice=invoice,
            notification_type=notification_type,
            payload=notification_data,
            sf_webhook_url='https://your-salesforce-instance.com/webhook/collections',  # Configure this
            status='pending'
        )
        
        # Send notification (implement actual HTTP request to Salesforce)
        # For now, just mark as sent
        notification.status = 'sent'
        notification.sent_at = timezone.now()
        notification.save()
        
        log_to_cloud_logging(
            'INFO',
            f'Notification sent to Salesforce for invoice {invoice.invoice_id}',
            invoice_id=invoice.invoice_id,
            notification_type=notification_type,
            notification_id=str(notification.notification_id)
        )
        
        return {
            'success': True,
            'notification_id': str(notification.notification_id),
            'status': notification.status
        }
        
    except Exception as e:
        logger.error(f"Salesforce notification failed for invoice {invoice_id}: {e}", exc_info=True)
        raise e


def cleanup_old_data():
    """
    Clean up old data to maintain database performance.
    """
    try:
        # Delete old webhook events (older than 30 days)
        from webhook_handlers.models import WebhookEvent
        cutoff_date = timezone.now() - timedelta(days=30)
        
        old_events = WebhookEvent.objects.filter(
            received_at__lt=cutoff_date,
            status='processed'
        )
        deleted_count = old_events.count()
        old_events.delete()
        
        # Delete old audit logs (older than 90 days)
        from webhook_handlers.models import AuditLog
        audit_cutoff = timezone.now() - timedelta(days=90)
        
        old_audit_logs = AuditLog.objects.filter(created_at__lt=audit_cutoff)
        audit_deleted_count = old_audit_logs.count()
        old_audit_logs.delete()
        
        log_to_cloud_logging(
            'INFO',
            'Data cleanup completed',
            webhook_events_deleted=deleted_count,
            audit_logs_deleted=audit_deleted_count
        )
        
        return {
            'success': True,
            'webhook_events_deleted': deleted_count,
            'audit_logs_deleted': audit_deleted_count
        }
        
    except Exception as e:
        logger.error(f"Data cleanup failed: {e}", exc_info=True)
        raise e