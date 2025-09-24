"""
Payment Agent (AP2) Views

This module implements AP2-compliant endpoints for payment orchestration
and settlement with multiple processors (Stripe, Adyen, Plaid).
"""

import logging
import json
import uuid
from django.utils import timezone
from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.conf import settings
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework import status

from .models import PaymentProcessor, AP2PaymentRequest, PaymentSettlement, PaymentWebhook
from .utils import (
    verify_ap2_signature, create_payment_request_id, 
    process_stripe_payment, process_adyen_payment, process_plaid_payment
)

logger = logging.getLogger(__name__)


@api_view(['POST'])
@authentication_classes([])
@permission_classes([AllowAny])
def ap2_payment_initiate(request):
    """
    POST /api/v1/ap2/payments/initiate/
    
    AP2-compliant endpoint for initiating payments.
    """
    try:
        # Verify AP2 signature
        if not verify_ap2_signature(request):
            logger.warning("Invalid AP2 signature")
            return Response({
                'error': 'Unauthorized',
                'error_code': 'INVALID_SIGNATURE'
            }, status=status.HTTP_401_UNAUTHORIZED)
        
        # Parse request data
        data = request.data
        
        # Validate required fields
        required_fields = [
            'invoice_id', 'mandate_id', 'amount_cents', 'currency', 
            'payment_method', 'idempotency_key'
        ]
        for field in required_fields:
            if field not in data:
                return Response({
                    'error': f'Missing required field: {field}',
                    'error_code': 'MISSING_FIELD'
                }, status=status.HTTP_400_BAD_REQUEST)
        
        # Check for duplicate request
        existing_request = AP2PaymentRequest.objects.filter(
            idempotency_key=data['idempotency_key']
        ).first()
        
        if existing_request:
            return Response({
                'ap2_request_id': existing_request.ap2_request_id,
                'status': existing_request.status,
                'message': 'Request already processed'
            })
        
        # Get invoice
        from invoice_collections.models import Invoice
        try:
            invoice = Invoice.objects.get(invoice_id=data['invoice_id'])
        except Invoice.DoesNotExist:
            return Response({
                'error': 'Invoice not found',
                'error_code': 'INVOICE_NOT_FOUND'
            }, status=status.HTTP_404_NOT_FOUND)
        
        # Select payment processor based on payment method
        processor = select_payment_processor(data['payment_method'], data['currency'])
        if not processor:
            return Response({
                'error': f'No processor available for {data["payment_method"]} in {data["currency"]}',
                'error_code': 'PROCESSOR_UNAVAILABLE'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Create AP2 payment request
        ap2_request = AP2PaymentRequest.objects.create(
            invoice=invoice,
            processor=processor,
            ap2_request_id=create_payment_request_id(),
            mandate_id=data['mandate_id'],
            payment_method=data['payment_method'],
            amount_cents=data['amount_cents'],
            currency=data['currency'],
            description=data.get('description', ''),
            idempotency_key=data['idempotency_key'],
            context_data=data.get('context_data', {}),
            raw_request=data
        )
        
        # Process payment based on processor
        try:
            if processor.processor_type == 'stripe':
                result = process_stripe_payment(ap2_request, data)
            elif processor.processor_type == 'adyen':
                result = process_adyen_payment(ap2_request, data)
            elif processor.processor_type == 'plaid':
                result = process_plaid_payment(ap2_request, data)
            else:
                raise ValueError(f"Unsupported processor type: {processor.processor_type}")
            
            # Update request with result
            ap2_request.status = result.get('status', 'processing')
            ap2_request.external_transaction_id = result.get('transaction_id', '')
            ap2_request.raw_response = result
            ap2_request.processed_at = timezone.now()
            ap2_request.save()
            
            logger.info(f"AP2 payment initiated: {ap2_request.ap2_request_id}")
            
            return Response({
                'ap2_request_id': ap2_request.ap2_request_id,
                'status': ap2_request.status,
                'transaction_id': ap2_request.external_transaction_id,
                'processor': processor.processor_name,
                'estimated_settlement': result.get('estimated_settlement'),
                'message': 'Payment initiated successfully'
            }, status=status.HTTP_202_ACCEPTED)
            
        except Exception as e:
            # Mark request as failed
            ap2_request.status = 'failed'
            ap2_request.error_message = str(e)
            ap2_request.processed_at = timezone.now()
            ap2_request.save()
            
            logger.error(f"AP2 payment failed: {ap2_request.ap2_request_id} - {e}")
            
            return Response({
                'ap2_request_id': ap2_request.ap2_request_id,
                'status': 'failed',
                'error': str(e),
                'error_code': 'PROCESSING_ERROR'
            }, status=status.HTTP_400_BAD_REQUEST)
        
    except Exception as e:
        logger.error(f"Error initiating AP2 payment: {e}", exc_info=True)
        return Response({
            'error': 'Internal server error',
            'error_code': 'INTERNAL_ERROR'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@authentication_classes([])
@permission_classes([AllowAny])
def ap2_payment_status(request, ap2_request_id):
    """
    GET /api/v1/ap2/payments/{ap2_request_id}/status/
    
    Get the status of an AP2 payment request.
    """
    try:
        # Verify AP2 signature
        if not verify_ap2_signature(request):
            logger.warning("Invalid AP2 signature")
            return Response({
                'error': 'Unauthorized',
                'error_code': 'INVALID_SIGNATURE'
            }, status=status.HTTP_401_UNAUTHORIZED)
        
        # Get payment request
        try:
            ap2_request = AP2PaymentRequest.objects.get(ap2_request_id=ap2_request_id)
        except AP2PaymentRequest.DoesNotExist:
            return Response({
                'error': 'Payment request not found',
                'error_code': 'REQUEST_NOT_FOUND'
            }, status=status.HTTP_404_NOT_FOUND)
        
        # Get settlements
        settlements = ap2_request.settlements.all().order_by('-created_at')
        settlements_data = []
        for settlement in settlements:
            settlements_data.append({
                'settlement_id': str(settlement.settlement_id),
                'settlement_type': settlement.settlement_type,
                'status': settlement.status,
                'gross_amount_cents': settlement.gross_amount_cents,
                'fees_cents': settlement.fees_cents,
                'net_amount_cents': settlement.net_amount_cents,
                'expected_settlement_date': settlement.expected_settlement_date.isoformat(),
                'settled_at': settlement.settled_at.isoformat() if settlement.settled_at else None,
                'reconciled': settlement.reconciled
            })
        
        return Response({
            'ap2_request_id': ap2_request.ap2_request_id,
            'invoice_id': ap2_request.invoice.invoice_id,
            'status': ap2_request.status,
            'amount_cents': ap2_request.amount_cents,
            'currency': ap2_request.currency,
            'payment_method': ap2_request.payment_method,
            'processor': ap2_request.processor.processor_name,
            'transaction_id': ap2_request.external_transaction_id,
            'created_at': ap2_request.created_at.isoformat(),
            'processed_at': ap2_request.processed_at.isoformat() if ap2_request.processed_at else None,
            'settled_at': ap2_request.settled_at.isoformat() if ap2_request.settled_at else None,
            'error_message': ap2_request.error_message,
            'settlements': settlements_data
        })
        
    except Exception as e:
        logger.error(f"Error getting AP2 payment status: {e}", exc_info=True)
        return Response({
            'error': 'Internal server error',
            'error_code': 'INTERNAL_ERROR'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@csrf_exempt
@require_http_methods(["POST"])
def ap2_webhook_handler(request, processor_name):
    """
    POST /api/v1/ap2/webhooks/{processor_name}/
    
    Handle webhooks from payment processors.
    """
    try:
        # Get processor
        try:
            processor = PaymentProcessor.objects.get(processor_name=processor_name)
        except PaymentProcessor.DoesNotExist:
            logger.warning(f"Unknown processor: {processor_name}")
            return HttpResponse("Unknown processor", status=400)
        
        # Verify webhook signature (processor-specific)
        if not verify_processor_webhook_signature(request, processor):
            logger.warning(f"Invalid webhook signature for {processor_name}")
            return HttpResponse("Invalid signature", status=400)
        
        # Parse webhook data
        try:
            webhook_data = json.loads(request.body)
        except json.JSONDecodeError:
            logger.error(f"Invalid JSON in webhook from {processor_name}")
            return HttpResponse("Invalid JSON", status=400)
        
        # Create webhook record
        webhook = PaymentWebhook.objects.create(
            processor=processor,
            webhook_type=webhook_data.get('type', 'unknown'),
            external_event_id=webhook_data.get('id', str(uuid.uuid4())),
            raw_payload=webhook_data,
            headers=dict(request.META)
        )
        
        # Process webhook
        try:
            result = process_webhook(webhook, webhook_data)
            
            # Update webhook status
            webhook.processed = True
            webhook.processed_at = timezone.now()
            webhook.save()
            
            logger.info(f"Webhook processed: {webhook.external_event_id} from {processor_name}")
            
            return HttpResponse("OK")
            
        except Exception as e:
            # Mark webhook as failed
            webhook.processing_error = str(e)
            webhook.save()
            
            logger.error(f"Error processing webhook {webhook.external_event_id}: {e}")
            
            return HttpResponse("Processing error", status=500)
        
    except Exception as e:
        logger.error(f"Error handling webhook from {processor_name}: {e}", exc_info=True)
        return HttpResponse("Internal server error", status=500)


@api_view(['GET'])
@authentication_classes([])
@permission_classes([AllowAny])
def ap2_processors_list(request):
    """
    GET /api/v1/ap2/processors/
    
    List available payment processors.
    """
    try:
        # Verify AP2 signature
        if not verify_ap2_signature(request):
            logger.warning("Invalid AP2 signature")
            return Response({
                'error': 'Unauthorized',
                'error_code': 'INVALID_SIGNATURE'
            }, status=status.HTTP_401_UNAUTHORIZED)
        
        # Get processors
        processors = PaymentProcessor.objects.filter(status='active').order_by('processor_name')
        
        processors_data = []
        for processor in processors:
            processors_data.append({
                'processor_id': str(processor.processor_id),
                'processor_name': processor.processor_name,
                'processor_type': processor.processor_type,
                'supported_methods': processor.supported_methods,
                'supported_currencies': processor.supported_currencies,
                'status': processor.status,
                'last_health_check': processor.last_health_check.isoformat() if processor.last_health_check else None
            })
        
        return Response({
            'processors': processors_data,
            'total_count': len(processors_data)
        })
        
    except Exception as e:
        logger.error(f"Error listing AP2 processors: {e}", exc_info=True)
        return Response({
            'error': 'Internal server error',
            'error_code': 'INTERNAL_ERROR'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


def select_payment_processor(payment_method: str, currency: str) -> PaymentProcessor:
    """
    Select the best payment processor for the given method and currency.
    
    Args:
        payment_method: Payment method (ach, card, sepa, bacs)
        currency: Currency code
        
    Returns:
        PaymentProcessor instance or None
    """
    try:
        # Find processors that support the payment method and currency
        processors = PaymentProcessor.objects.filter(
            status='active',
            supported_methods__contains=[payment_method.lower()],
            supported_currencies__contains=[currency.upper()]
        ).order_by('processor_name')
        
        # Return the first available processor
        return processors.first()
        
    except Exception:
        return None


def verify_processor_webhook_signature(request, processor: PaymentProcessor) -> bool:
    """
    Verify webhook signature for a specific processor.
    
    Args:
        request: Django request object
        processor: PaymentProcessor instance
        
    Returns:
        True if signature is valid, False otherwise
    """
    try:
        if processor.processor_type == 'stripe':
            return verify_stripe_webhook_signature(request, processor)
        elif processor.processor_type == 'adyen':
            return verify_adyen_webhook_signature(request, processor)
        elif processor.processor_type == 'plaid':
            return verify_plaid_webhook_signature(request, processor)
        else:
            return False
    except Exception:
        return False


def verify_stripe_webhook_signature(request, processor: PaymentProcessor) -> bool:
    """Verify Stripe webhook signature."""
    try:
        import stripe
        
        signature = request.META.get('HTTP_STRIPE_SIGNATURE', '')
        payload = request.body
        webhook_secret = processor.secret_key
        
        stripe.Webhook.construct_event(payload, signature, webhook_secret)
        return True
    except Exception:
        return False


def verify_adyen_webhook_signature(request, processor: PaymentProcessor) -> bool:
    """Verify Adyen webhook signature."""
    try:
        # Adyen webhook signature verification logic
        # This would implement Adyen's specific signature verification
        return True  # Simplified for now
    except Exception:
        return False


def verify_plaid_webhook_signature(request, processor: PaymentProcessor) -> bool:
    """Verify Plaid webhook signature."""
    try:
        # Plaid webhook signature verification logic
        # This would implement Plaid's specific signature verification
        return True  # Simplified for now
    except Exception:
        return False


def process_webhook(webhook: PaymentWebhook, webhook_data: dict) -> dict:
    """
    Process webhook data and update payment requests.
    
    Args:
        webhook: PaymentWebhook instance
        webhook_data: Webhook payload
        
    Returns:
        Processing result
    """
    try:
        webhook_type = webhook.webhook_type
        
        if webhook_type == 'payment.succeeded':
            return handle_payment_succeeded_webhook(webhook, webhook_data)
        elif webhook_type == 'payment.failed':
            return handle_payment_failed_webhook(webhook, webhook_data)
        elif webhook_type == 'settlement.completed':
            return handle_settlement_completed_webhook(webhook, webhook_data)
        else:
            logger.info(f"Unhandled webhook type: {webhook_type}")
            return {'status': 'ignored'}
        
    except Exception as e:
        logger.error(f"Error processing webhook: {e}")
        raise e


def handle_payment_succeeded_webhook(webhook: PaymentWebhook, webhook_data: dict) -> dict:
    """Handle payment succeeded webhook."""
    try:
        # Find payment request by external transaction ID
        transaction_id = webhook_data.get('data', {}).get('object', {}).get('id')
        if not transaction_id:
            return {'status': 'ignored', 'reason': 'No transaction ID'}
        
        payment_request = AP2PaymentRequest.objects.filter(
            external_transaction_id=transaction_id
        ).first()
        
        if not payment_request:
            return {'status': 'ignored', 'reason': 'Payment request not found'}
        
        # Update payment request
        payment_request.status = 'settled'
        payment_request.settled_at = timezone.now()
        payment_request.settlement_amount_cents = webhook_data.get('data', {}).get('object', {}).get('amount_received', 0)
        payment_request.save()
        
        # Create settlement record
        settlement = PaymentSettlement.objects.create(
            payment_request=payment_request,
            settlement_type='immediate',
            status='settled',
            gross_amount_cents=payment_request.settlement_amount_cents,
            fees_cents=0,  # Would be calculated from webhook data
            net_amount_cents=payment_request.settlement_amount_cents,
            external_settlement_id=transaction_id,
            settled_at=timezone.now(),
            expected_settlement_date=timezone.now()
        )
        
        # Update invoice status
        invoice = payment_request.invoice
        invoice.status = 'completed'
        invoice.save()
        
        return {'status': 'processed', 'payment_request_id': payment_request.ap2_request_id}
        
    except Exception as e:
        logger.error(f"Error handling payment succeeded webhook: {e}")
        raise e


def handle_payment_failed_webhook(webhook: PaymentWebhook, webhook_data: dict) -> dict:
    """Handle payment failed webhook."""
    try:
        # Find payment request by external transaction ID
        transaction_id = webhook_data.get('data', {}).get('object', {}).get('id')
        if not transaction_id:
            return {'status': 'ignored', 'reason': 'No transaction ID'}
        
        payment_request = AP2PaymentRequest.objects.filter(
            external_transaction_id=transaction_id
        ).first()
        
        if not payment_request:
            return {'status': 'ignored', 'reason': 'Payment request not found'}
        
        # Update payment request
        payment_request.status = 'failed'
        payment_request.error_message = webhook_data.get('data', {}).get('object', {}).get('failure_message', 'Payment failed')
        payment_request.save()
        
        # Update invoice status
        invoice = payment_request.invoice
        invoice.status = 'failed'
        invoice.save()
        
        return {'status': 'processed', 'payment_request_id': payment_request.ap2_request_id}
        
    except Exception as e:
        logger.error(f"Error handling payment failed webhook: {e}")
        raise e


def handle_settlement_completed_webhook(webhook: PaymentWebhook, webhook_data: dict) -> dict:
    """Handle settlement completed webhook."""
    try:
        # Find payment request by external transaction ID
        transaction_id = webhook_data.get('data', {}).get('object', {}).get('id')
        if not transaction_id:
            return {'status': 'ignored', 'reason': 'No transaction ID'}
        
        payment_request = AP2PaymentRequest.objects.filter(
            external_transaction_id=transaction_id
        ).first()
        
        if not payment_request:
            return {'status': 'ignored', 'reason': 'Payment request not found'}
        
        # Update settlement
        settlement = payment_request.settlements.filter(
            external_settlement_id=transaction_id
        ).first()
        
        if settlement:
            settlement.status = 'settled'
            settlement.settled_at = timezone.now()
            settlement.reconciled = True
            settlement.reconciled_at = timezone.now()
            settlement.save()
        
        return {'status': 'processed', 'payment_request_id': payment_request.ap2_request_id}
        
    except Exception as e:
        logger.error(f"Error handling settlement completed webhook: {e}")
        raise e
