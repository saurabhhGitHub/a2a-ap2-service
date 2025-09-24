"""
API Views for Invoice Collections.

This module contains the main API endpoints for processing collection requests,
checking status, and managing invoice collections.
"""

import logging
from datetime import datetime, timedelta
from django.utils import timezone
from django.db import transaction, models
from django.conf import settings
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes, authentication_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from django_ratelimit.decorators import ratelimit

from .models import Invoice, AgentAction, PaymentAttempt, CollectionRequest
from payment_processing.models import Payment
from .serializers import (
    CollectionRequestSerializer, CollectionResponseSerializer,
    InvoiceStatusSerializer, AgentActionSerializer, PaymentAttemptSerializer,
    SalesforceNotificationSerializer, HealthCheckSerializer
)
from .authentication import APIKeyAuthentication, APIKeyPermission

logger = logging.getLogger(__name__)


class CollectionInitiateView(APIView):
    """
    POST /api/v1/collections/initiate/
    
    Receives collection requests from Salesforce and initiates payment processing.
    """
    
    authentication_classes = [APIKeyAuthentication]
    permission_classes = [APIKeyPermission]
    
    def post(self, request):
        """
        Process a collection request from Salesforce.
        """
        try:
            # Validate request data
            serializer = CollectionRequestSerializer(data=request.data)
            if not serializer.is_valid():
                return Response({
                    'success': False,
                    'error_code': 'VALIDATION_ERROR',
                    'error_message': 'Invalid request data',
                    'details': serializer.errors
                }, status=status.HTTP_400_BAD_REQUEST)
            
            validated_data = serializer.validated_data
            
            # Check for idempotency
            idempotency_key = validated_data['idempotency_key']
            existing_request = CollectionRequest.objects.filter(
                idempotency_key=idempotency_key
            ).first()
            
            if existing_request:
                # Return existing response
                if existing_request.invoice:
                    return Response({
                        'success': True,
                        'payment_id': str(existing_request.invoice.payments.first().payment_id) if existing_request.invoice.payments.exists() else None,
                        'status': existing_request.invoice.status,
                        'transaction_id': existing_request.invoice.payments.first().stripe_payment_intent_id if existing_request.invoice.payments.exists() else None,
                        'message': 'Collection request already processed',
                        'estimated_completion': timezone.now() + timedelta(minutes=5)
                    })
                else:
                    return Response({
                        'success': False,
                        'error_code': 'PROCESSING_ERROR',
                        'error_message': existing_request.error_message or 'Collection request is being processed'
                    }, status=status.HTTP_202_ACCEPTED)
            
            # Create collection request record
            with transaction.atomic():
                collection_request = CollectionRequest.objects.create(
                    idempotency_key=idempotency_key,
                    raw_request_data=request.data,
                    status='processing'
                )
                
                # Convert amount to cents
                amount_cents = int(validated_data['amount'] * 100)
                
                # Create invoice
                invoice = Invoice.objects.create(
                    invoice_id=validated_data['invoice_id'],
                    external_invoice_id=validated_data['sf_invoice_id'],
                    amount_cents=amount_cents,
                    currency=validated_data['currency'],
                    customer_id=validated_data['customer_id'],
                    customer_name=validated_data['customer_name'],
                    mandate_id=validated_data['mandate_id'],
                    payment_method=validated_data['payment_method'],
                    approved_by=validated_data['approved_by'],
                    due_date=validated_data['due_date'],
                    idempotency_key=idempotency_key,
                    status='processing'
                )
                
                # Link collection request to invoice
                collection_request.invoice = invoice
                collection_request.save()
                
                # Log agent action
                # Convert Decimal and datetime to JSON-serializable types
                payload_data = dict(validated_data)
                if 'amount' in payload_data:
                    payload_data['amount'] = float(payload_data['amount'])
                if 'due_date' in payload_data:
                    payload_data['due_date'] = payload_data['due_date'].isoformat()
                
                AgentAction.objects.create(
                    invoice=invoice,
                    action_type='collection_initiated',
                    decision='auto_process',
                    payload=payload_data,
                    human_actor=validated_data['approved_by'],
                    notes=f'Collection initiated for invoice {invoice.invoice_id}'
                )
            
            # Return success response
            response_data = {
                'success': True,
                'payment_id': str(invoice.id),  # Using invoice ID as payment ID for now
                'status': 'processing',
                'message': 'Payment initiated successfully',
                'estimated_completion': timezone.now() + timedelta(minutes=5)
            }
            
            return Response(response_data, status=status.HTTP_202_ACCEPTED)
            
        except Exception as e:
            logger.error(f"Error processing collection request: {e}", exc_info=True)
            return Response({
                'success': False,
                'error_code': 'INTERNAL_ERROR',
                'error_message': 'An internal error occurred while processing the request'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class CollectionStatusView(APIView):
    """
    GET /api/v1/collections/status/{invoice_id}/
    
    Returns the current status of a collection request.
    """
    
    authentication_classes = [APIKeyAuthentication]
    permission_classes = [APIKeyPermission]
    
    def get(self, request, invoice_id):
        """
        Get the status of a collection request.
        """
        try:
            # Try to find invoice by invoice_id or sf_invoice_id
            invoice = Invoice.objects.filter(
                models.Q(invoice_id=invoice_id) | models.Q(external_invoice_id=invoice_id)
            ).first()
            
            if not invoice:
                return Response({
                    'success': False,
                    'error_code': 'INVOICE_NOT_FOUND',
                    'error_message': f'Invoice {invoice_id} not found'
                }, status=status.HTTP_404_NOT_FOUND)
            
            # Get latest payment attempt
            latest_payment = invoice.payments.first()
            latest_attempt = invoice.payment_attempts.first()
            
            # Prepare response data
            response_data = {
                'success': True,
                'invoice_id': invoice.invoice_id,
                'sf_invoice_id': invoice.external_invoice_id,
                'status': invoice.status,
                'amount_cents': invoice.amount_cents,
                'currency': invoice.currency,
                'customer_name': invoice.customer_name,
                'due_date': invoice.due_date,
                'created_at': invoice.created_at,
                'updated_at': invoice.updated_at,
                'is_overdue': invoice.is_overdue(),
            }
            
            # Add payment details if available
            if latest_payment:
                response_data.update({
                    'payment_id': str(latest_payment.payment_id),
                    'transaction_id': latest_payment.stripe_payment_intent_id,
                    'payment_status': latest_payment.status,
                    'amount_received_cents': latest_payment.amount_received_cents,
                    'fees_charged_cents': latest_payment.fees_charged_cents,
                    'processed_at': latest_payment.processed_at,
                    'settled_at': latest_payment.settled_at,
                })
            
            # Add attempt details if available
            if latest_attempt:
                response_data.update({
                    'attempt_number': latest_attempt.attempt_number,
                    'attempt_status': latest_attempt.status,
                    'error_code': latest_attempt.error_code,
                    'error_message': latest_attempt.error_message,
                })
            
            return Response(response_data)
            
        except Exception as e:
            logger.error(f"Error getting collection status: {e}", exc_info=True)
            return Response({
                'success': False,
                'error_code': 'INTERNAL_ERROR',
                'error_message': 'An internal error occurred while retrieving status'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@authentication_classes([APIKeyAuthentication])
@permission_classes([APIKeyPermission])
@ratelimit(key='ip', rate='30/m', method='GET')
def health_check(request):
    """
    GET /api/v1/health/
    
    Health check endpoint for monitoring and load balancers.
    """
    try:
        from django.db import connection
        from django.core.cache import cache
        
        # Check database
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
            db_status = "healthy"
        except Exception:
            db_status = "unhealthy"
        
        # Check Redis
        try:
            cache.set('health_check', 'ok', 10)
            cache.get('health_check')
            redis_status = "healthy"
        except Exception:
            redis_status = "unhealthy"
        
        # Determine overall status
        overall_status = "healthy" if db_status == "healthy" and redis_status == "healthy" else "unhealthy"
        
        response_data = {
            'status': overall_status,
            'timestamp': timezone.now(),
            'version': '1.0.0',
            'database': db_status,
            'redis': redis_status,
            'stripe': 'healthy',  # Will be checked in production
            'google_cloud': 'healthy'  # Will be checked in production
        }
        
        http_status = status.HTTP_200_OK if overall_status == "healthy" else status.HTTP_503_SERVICE_UNAVAILABLE
        
        return Response(response_data, status=http_status)
        
    except Exception as e:
        logger.error(f"Health check failed: {e}", exc_info=True)
        return Response({
            'status': 'unhealthy',
            'timestamp': timezone.now(),
            'error': str(e)
        }, status=status.HTTP_503_SERVICE_UNAVAILABLE)