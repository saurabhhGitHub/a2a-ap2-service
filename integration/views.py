"""
Integration Views for External Systems

This module provides API endpoints for Salesforce Agentforce and Slack teams
to integrate with the Collections Agent Backend.
"""

import logging
import json
from datetime import datetime, timedelta
from django.utils import timezone
from django.db import transaction
from django.conf import settings
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes, authentication_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from django_ratelimit.decorators import ratelimit

from invoice_collections.models import Invoice, AgentAction, CollectionRequest
from invoice_collections.authentication import APIKeyAuthentication, APIKeyPermission
from invoice_collections.serializers import CollectionRequestSerializer
from .a2a_ap2_integration import process_collection_with_a2a_ap2, get_a2a_conversation_status
from .a2a_ap2_integration import process_collection_with_a2a_ap2, get_a2a_conversation_status

logger = logging.getLogger(__name__)


class SalesforceWebhookView(APIView):
    """
    POST /api/v1/integration/salesforce/webhook/
    
    Webhook endpoint for Salesforce Agentforce to send collection requests.
    """
    
    authentication_classes = [APIKeyAuthentication]
    permission_classes = [APIKeyPermission]
    
    def post(self, request):
        """
        Process collection request from Salesforce Agentforce.
        """
        try:
            # Log incoming request
            logger.info(f"Salesforce webhook received: {request.data}")
            
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
                        'invoice_id': existing_request.invoice.invoice_id,
                        'status': existing_request.invoice.status,
                        'message': 'Collection request already processed',
                        'estimated_completion': timezone.now() + timedelta(minutes=5)
                    })
                else:
                    return Response({
                        'success': False,
                        'error_code': 'PROCESSING_ERROR',
                        'error_message': existing_request.error_message or 'Collection request is being processed'
                    }, status=status.HTTP_202_ACCEPTED)
            
            # Create collection request and invoice
            with transaction.atomic():
                # Create new collection request for each payment attempt
                collection_request = CollectionRequest.objects.create(
                    idempotency_key=idempotency_key,
                    raw_request_data=request.data,
                    status='processing'
                )
                
                # Convert amount to cents
                amount_cents = int(validated_data['amount'] * 100)
                
                # Get or create invoice (allow duplicates for multiple payments)
                invoice, created = Invoice.objects.get_or_create(
                    invoice_id=validated_data['invoice_id'],
                    defaults={
                        'external_invoice_id': validated_data.get('sf_invoice_id', validated_data['invoice_id']),
                        'amount_cents': amount_cents,
                        'currency': validated_data['currency'],
                        'customer_id': validated_data['customer_id'],
                        'customer_name': validated_data['customer_name'],
                        'mandate_id': validated_data['mandate_id'],
                        'payment_method': validated_data['payment_method'],
                        'approved_by': validated_data['approved_by'],
                        'due_date': validated_data['due_date'],
                        'idempotency_key': idempotency_key,
                        'status': 'processing'
                    }
                )
                
                if not created:
                    # Invoice already exists, update it for new payment
                    invoice.external_invoice_id = validated_data.get('sf_invoice_id', validated_data['invoice_id'])
                    invoice.amount_cents = amount_cents
                    invoice.currency = validated_data['currency']
                    invoice.customer_id = validated_data['customer_id']
                    invoice.customer_name = validated_data['customer_name']
                    invoice.mandate_id = validated_data['mandate_id']
                    invoice.payment_method = validated_data['payment_method']
                    invoice.approved_by = validated_data['approved_by']
                    invoice.due_date = validated_data['due_date']
                    invoice.idempotency_key = idempotency_key
                    invoice.status = 'processing'
                    invoice.save()
                
                # Link collection request to invoice only if it's a new invoice
                # For existing invoices, we don't link to avoid OneToOne constraint violation
                if created:
                    collection_request.invoice = invoice
                    collection_request.save()
                
                # Log agent action
                # Convert Decimal and datetime to JSON-serializable types
                payload_data = dict(validated_data)
                if 'amount' in payload_data:
                    payload_data['amount'] = float(payload_data['amount'])
                if 'due_date' in payload_data:
                    payload_data['due_date'] = payload_data['due_date'].isoformat()
                
                # Log agent action with appropriate message
                action_type = 'collection_initiated' if created else 'collection_reinitiated'
                notes = f'Collection initiated from Salesforce for invoice {invoice.invoice_id}' if created else f'Collection reinitiated from Salesforce for invoice {invoice.invoice_id} (multiple payments allowed)'
                
                AgentAction.objects.create(
                    invoice=invoice,
                    action_type=action_type,
                    decision='auto_process',
                    payload=payload_data,
                    human_actor=validated_data['approved_by'],
                    notes=notes
                )
            
            # Note: This webhook is only called when pre_approved__c = true
            # When pre_approved__c = false, SF team sends email instead
            logger.info(f"Processing payment for invoice {invoice.invoice_id} (pre_approved__c = true)")
            
            # Process collection using A2A and AP2 protocols
            a2a_ap2_result = process_collection_with_a2a_ap2(validated_data)
            
            if a2a_ap2_result['success']:
                # Update invoice status based on A2A/AP2 result
                invoice.status = 'completed' if a2a_ap2_result['status'] == 'settled' else 'processing'
                invoice.save()
                
                # Log A2A/AP2 success
                AgentAction.objects.create(
                    invoice=invoice,
                    action_type='payment_processed',
                    decision='auto_process',
                    payload=a2a_ap2_result,
                    notes=f'Payment processed via A2A conversation {a2a_ap2_result["conversation_id"]} and AP2 request {a2a_ap2_result["ap2_request_id"]}'
                )
                
                response_data = {
                     'success': True,
                     'invoice_id': invoice.invoice_id,
                     'status': a2a_ap2_result['status'],
                     'message': a2a_ap2_result['message'],
                     'conversation_id': a2a_ap2_result['conversation_id'],
                     'ap2_request_id': a2a_ap2_result['ap2_request_id'],
                     'transaction_id': a2a_ap2_result['transaction_id'],
                     'estimated_completion': timezone.now() + timedelta(minutes=1)
                 }
                
                return Response(response_data, status=status.HTTP_200_OK)
            else:
                # A2A/AP2 processing failed
                invoice.status = 'failed'
                invoice.save()
                
                # Log A2A/AP2 failure
                AgentAction.objects.create(
                    invoice=invoice,
                    action_type='payment_failed',
                    decision='auto_process',
                    payload=a2a_ap2_result,
                    notes=f'A2A/AP2 processing failed: {a2a_ap2_result["error"]}'
                )
                
                return Response({
                    'success': False,
                    'error_code': 'A2A_AP2_ERROR',
                    'error_message': a2a_ap2_result['error'],
                    'invoice_id': invoice.invoice_id
                }, status=status.HTTP_400_BAD_REQUEST)
            
        except Exception as e:
            logger.error(f"Error processing Salesforce webhook: {e}", exc_info=True)
            return Response({
                'success': False,
                'error_code': 'INTERNAL_ERROR',
                'error_message': 'An internal error occurred while processing the request'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class A2AConversationStatusView(APIView):
    """
    GET /api/v1/integration/a2a/conversation/{conversation_id}/
    
    Get A2A conversation status for demo display.
    """
    
    authentication_classes = [APIKeyAuthentication]
    permission_classes = [APIKeyPermission]
    
    def get(self, request, conversation_id):
        """
        Get A2A conversation status and messages.
        """
        try:
            conversation_status = get_a2a_conversation_status(conversation_id)
            
            if 'error' in conversation_status:
                return Response({
                    'success': False,
                    'error_code': 'CONVERSATION_NOT_FOUND',
                    'error_message': conversation_status['error']
                }, status=status.HTTP_404_NOT_FOUND)
            
            return Response({
                'success': True,
                'conversation': conversation_status
            })
            
        except Exception as e:
            logger.error(f"Error getting A2A conversation status: {e}", exc_info=True)
            return Response({
                'success': False,
                'error_code': 'INTERNAL_ERROR',
                'error_message': 'An internal error occurred while getting conversation status'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class SlackApprovalView(APIView):
    """
    POST /api/v1/integration/slack/approval/
    
    Endpoint for Slack to send approval decisions.
    """
    
    authentication_classes = [APIKeyAuthentication]
    permission_classes = [APIKeyPermission]
    
    def post(self, request):
        """
        Process approval decision from Slack.
        """
        try:
            data = request.data
            
            # Validate required fields
            required_fields = ['invoice_id', 'decision', 'user_id', 'user_name']
            for field in required_fields:
                if field not in data:
                    return Response({
                        'success': False,
                        'error_code': 'MISSING_FIELD',
                        'error_message': f'Missing required field: {field}'
                    }, status=status.HTTP_400_BAD_REQUEST)
            
            # Get invoice
            try:
                invoice = Invoice.objects.get(invoice_id=data['invoice_id'])
            except Invoice.DoesNotExist:
                return Response({
                    'success': False,
                    'error_code': 'INVOICE_NOT_FOUND',
                    'error_message': f'Invoice {data["invoice_id"]} not found'
                }, status=status.HTTP_404_NOT_FOUND)
            
            # Process approval decision
            decision = data['decision'].lower()
            if decision == 'approve':
                # Update invoice status to approved
                invoice.status = 'processing'
                invoice.save()
                
                # Log agent action
                AgentAction.objects.create(
                    invoice=invoice,
                    action_type='status_updated',
                    decision='approve',
                    payload=data,
                    human_actor=data['user_name'],
                    notes=f'Payment approved by {data["user_name"]} via Slack'
                )
                
                # TODO: Trigger payment processing
                # This would call the payment processing logic
                
                response_data = {
                    'success': True,
                    'invoice_id': invoice.invoice_id,
                    'status': 'approved',
                    'message': f'Payment approved by {data["user_name"]}',
                    'next_action': 'Payment processing initiated'
                }
                
            elif decision == 'reject':
                # Update invoice status to cancelled
                invoice.status = 'cancelled'
                invoice.save()
                
                # Log agent action
                AgentAction.objects.create(
                    invoice=invoice,
                    action_type='status_updated',
                    decision='reject',
                    payload=data,
                    human_actor=data['user_name'],
                    notes=f'Payment rejected by {data["user_name"]} via Slack'
                )
                
                response_data = {
                    'success': True,
                    'invoice_id': invoice.invoice_id,
                    'status': 'rejected',
                    'message': f'Payment rejected by {data["user_name"]}',
                    'next_action': 'Collection cancelled'
                }
                
            else:
                return Response({
                    'success': False,
                    'error_code': 'INVALID_DECISION',
                    'error_message': 'Decision must be "approve" or "reject"'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            return Response(response_data)
            
        except Exception as e:
            logger.error(f"Error processing Slack approval: {e}", exc_info=True)
            return Response({
                'success': False,
                'error_code': 'INTERNAL_ERROR',
                'error_message': 'An internal error occurred while processing the approval'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class StatusNotificationView(APIView):
    """
    GET /api/v1/integration/status/{invoice_id}/
    
    Get current status of an invoice for external systems.
    """
    
    authentication_classes = [APIKeyAuthentication]
    permission_classes = [APIKeyPermission]
    
    def get(self, request, invoice_id):
        """
        Get invoice status for external systems.
        """
        try:
            # Try to find invoice by invoice_id or external_invoice_id
            from django.db import models
            invoice = Invoice.objects.filter(
                models.Q(invoice_id=invoice_id) | models.Q(external_invoice_id=invoice_id)
            ).first()
            
            if not invoice:
                return Response({
                    'success': False,
                    'error_code': 'INVOICE_NOT_FOUND',
                    'error_message': f'Invoice {invoice_id} not found'
                }, status=status.HTTP_404_NOT_FOUND)
            
            # Get latest agent actions
            latest_actions = invoice.agent_actions.all()[:5]
            actions_data = []
            for action in latest_actions:
                actions_data.append({
                    'action_type': action.action_type,
                    'decision': action.decision,
                    'human_actor': action.human_actor,
                    'created_at': action.created_at.isoformat(),
                    'notes': action.notes
                })
            
            # Prepare response data
            response_data = {
                'success': True,
                'invoice_id': invoice.invoice_id,
                'external_invoice_id': invoice.external_invoice_id,
                'status': invoice.status,
                'amount_cents': invoice.amount_cents,
                'currency': invoice.currency,
                'customer_name': invoice.customer_name,
                'due_date': invoice.due_date.isoformat(),
                'created_at': invoice.created_at.isoformat(),
                'updated_at': invoice.updated_at.isoformat(),
                'is_overdue': invoice.is_overdue(),
                'recent_actions': actions_data
            }
            
            return Response(response_data)
            
        except Exception as e:
            logger.error(f"Error getting invoice status: {e}", exc_info=True)
            return Response({
                'success': False,
                'error_code': 'INTERNAL_ERROR',
                'error_message': 'An internal error occurred while retrieving status'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class OverdueInvoicesView(APIView):
    """
    GET /api/v1/integration/overdue-invoices/
    
    Get list of overdue invoices for Salesforce to monitor.
    """
    
    authentication_classes = [APIKeyAuthentication]
    permission_classes = [APIKeyPermission]
    
    def get(self, request):
        """
        Get list of overdue invoices.
        """
        try:
            # Get query parameters
            limit = int(request.GET.get('limit', 50))
            offset = int(request.GET.get('offset', 0))
            customer_id = request.GET.get('customer_id')
            
            # Build query
            from django.db import models
            query = models.Q(status__in=['pending', 'processing']) & models.Q(due_date__lt=timezone.now())
            
            if customer_id:
                query &= models.Q(customer_id=customer_id)
            
            # Get overdue invoices
            overdue_invoices = Invoice.objects.filter(query).order_by('-due_date')[offset:offset+limit]
            
            invoices_data = []
            for invoice in overdue_invoices:
                days_overdue = (timezone.now() - invoice.due_date).days
                invoices_data.append({
                    'invoice_id': invoice.invoice_id,
                    'external_invoice_id': invoice.external_invoice_id,
                    'customer_id': invoice.customer_id,
                    'customer_name': invoice.customer_name,
                    'amount_cents': invoice.amount_cents,
                    'currency': invoice.currency,
                    'due_date': invoice.due_date.isoformat(),
                    'status': invoice.status,
                    'days_overdue': days_overdue,
                    'mandate_id': invoice.mandate_id,
                    'payment_method': invoice.payment_method
                })
            
            return Response({
                'success': True,
                'invoices': invoices_data,
                'total_count': len(invoices_data),
                'limit': limit,
                'offset': offset
            })
            
        except Exception as e:
            logger.error(f"Error getting overdue invoices: {e}", exc_info=True)
            return Response({
                'success': False,
                'error_code': 'INTERNAL_ERROR',
                'error_message': 'An internal error occurred while retrieving overdue invoices'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@authentication_classes([APIKeyAuthentication])
@permission_classes([APIKeyPermission])
@ratelimit(key='ip', rate='100/m', method='POST')
def webhook_status_update(request):
    """
    POST /api/v1/integration/webhook/status-update/
    
    Generic webhook endpoint for status updates from external systems.
    """
    try:
        data = request.data
        
        # Validate required fields
        required_fields = ['invoice_id', 'status', 'source_system']
        for field in required_fields:
            if field not in data:
                return Response({
                    'success': False,
                    'error_code': 'MISSING_FIELD',
                    'error_message': f'Missing required field: {field}'
                }, status=status.HTTP_400_BAD_REQUEST)
        
        # Get invoice
        try:
            invoice = Invoice.objects.get(invoice_id=data['invoice_id'])
        except Invoice.DoesNotExist:
            return Response({
                'success': False,
                'error_code': 'INVOICE_NOT_FOUND',
                'error_message': f'Invoice {data["invoice_id"]} not found'
            }, status=status.HTTP_404_NOT_FOUND)
        
        # Update invoice status
        old_status = invoice.status
        invoice.status = data['status']
        invoice.save()
        
        # Log agent action
        AgentAction.objects.create(
            invoice=invoice,
            action_type='status_updated',
            decision='auto_process',
            payload=data,
            system_actor=data['source_system'],
            notes=f'Status updated from {data["source_system"]}: {old_status} -> {data["status"]}'
        )
        
        # If status indicates payment should be processed, trigger A2A/AP2
        if data['status'] in ['processing', 'approved', 'proceed_with_payment']:
            logger.info(f"Status update triggered A2A/AP2 processing for invoice {invoice.invoice_id}")
            
            # Prepare data for A2A/AP2 processing
            validated_data = {
                'invoice_id': invoice.invoice_id,
                'amount': invoice.amount_cents / 100,
                'currency': invoice.currency,
                'payment_method': invoice.payment_method,
                'customer_name': invoice.customer_name,
                'customer_id': getattr(invoice, 'customer_id', f'CUST-{invoice.invoice_id}'),
                'mandate_id': getattr(invoice, 'mandate_id', f'MANDATE-{invoice.invoice_id}'),
                'approved_by': data.get('approved_by', 'salesforce@company.com')
            }
            
            # Process collection using A2A and AP2 protocols
            from .a2a_ap2_integration import process_collection_with_a2a_ap2
            a2a_ap2_result = process_collection_with_a2a_ap2(validated_data)
            
            if a2a_ap2_result['success']:
                # Update invoice status based on A2A/AP2 result
                invoice.status = 'completed' if a2a_ap2_result['status'] == 'settled' else 'processing'
                invoice.save()
                
                # Log A2A/AP2 success
                AgentAction.objects.create(
                    invoice=invoice,
                    action_type='payment_processed_via_status_update',
                    decision='auto_process',
                    payload=a2a_ap2_result,
                    system_actor=data['source_system'],
                    notes=f'Payment processed via A2A conversation {a2a_ap2_result["conversation_id"]} and AP2 request {a2a_ap2_result["ap2_request_id"]}'
                )
                
                return Response({
                    'success': True,
                    'invoice_id': invoice.invoice_id,
                    'old_status': old_status,
                    'new_status': a2a_ap2_result['status'],
                    'updated_at': invoice.updated_at.isoformat(),
                    'a2a_ap2_processing': True,
                    'conversation_id': a2a_ap2_result['conversation_id'],
                    'ap2_request_id': a2a_ap2_result['ap2_request_id'],
                    'transaction_id': a2a_ap2_result['transaction_id'],
                    'message': a2a_ap2_result['message']
                })
            else:
                # A2A/AP2 processing failed
                invoice.status = 'failed'
                invoice.save()
                
                AgentAction.objects.create(
                    invoice=invoice,
                    action_type='payment_processing_failed_via_status_update',
                    decision='auto_process',
                    payload=a2a_ap2_result,
                    system_actor=data['source_system'],
                    notes=f'Payment processing failed for invoice {invoice.invoice_id}: {a2a_ap2_result.get("message", "Unknown error")}'
                )
                
                return Response({
                    'success': False,
                    'invoice_id': invoice.invoice_id,
                    'old_status': old_status,
                    'new_status': 'failed',
                    'updated_at': invoice.updated_at.isoformat(),
                    'a2a_ap2_processing': True,
                    'error': a2a_ap2_result.get('message', 'Payment processing failed'),
                    'conversation_id': a2a_ap2_result.get('conversation_id'),
                    'ap2_request_id': a2a_ap2_result.get('ap2_request_id'),
                    'transaction_id': a2a_ap2_result.get('transaction_id')
                })
        
        return Response({
            'success': True,
            'invoice_id': invoice.invoice_id,
            'old_status': old_status,
            'new_status': data['status'],
            'updated_at': invoice.updated_at.isoformat(),
            'a2a_ap2_processing': False
        })
        
    except Exception as e:
        logger.error(f"Error processing webhook status update: {e}", exc_info=True)
        return Response({
            'success': False,
            'error_code': 'INTERNAL_ERROR',
            'error_message': 'An internal error occurred while processing the status update'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class DemoPaymentDisplayHTMLView(APIView):
    """
    GET /api/v1/integration/stripe/payment-agent-sdk/{invoice_id}/
    
    Display payment details as HTML page for demo.
    Note: No authentication required for demo purposes.
    """
    
    authentication_classes = []
    permission_classes = []
    
    def get(self, request, invoice_id):
        """
        Display payment details as HTML page.
        """
        try:
            from invoice_collections.models import Invoice
            from django.shortcuts import render
            
            # Get invoice
            try:
                invoice = Invoice.objects.get(invoice_id=invoice_id)
            except Invoice.DoesNotExist:
                return Response({
                    'success': False,
                    'error_code': 'INVOICE_NOT_FOUND',
                    'error_message': f'Invoice {invoice_id} not found'
                }, status=status.HTTP_404_NOT_FOUND)
            
            # Create demo payment display data
            payment_display = {
                'invoice_id': invoice.invoice_id,
                'customer_name': invoice.customer_name,
                'amount': f"${invoice.amount_cents / 100:.2f}",
                'currency': invoice.currency,
                'payment_method': invoice.payment_method,
                'status': invoice.status,
                'due_date': invoice.due_date.isoformat() if invoice.due_date else None,
                'created_at': invoice.created_at.isoformat(),
                'demo_mode': True,
                'payment_details': {
                    'card_number': '**** **** **** 4242',
                    'card_type': 'Visa',
                    'expiry': '12/25',
                    'cvv': '***'
                },
                'processing_status': 'Processing payment...',
                'estimated_completion': '2-3 seconds',
                'demo_transaction_id': f"demo_txn_{invoice.invoice_id}"
            }
            
            # Render HTML template with data
            return render(request, 'demo_payment_display.html', {
                'payment_display': payment_display,
                'invoice_id': invoice_id
            })
            
        except Exception as e:
            logger.error(f"Error displaying payment HTML: {e}", exc_info=True)
            return Response({
                'success': False,
                'error_code': 'INTERNAL_ERROR',
                'error_message': 'An internal error occurred while displaying payment details'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class PreMandateApprovalView(APIView):
    """
    GET /api/v1/integration/pre-mandate-approval/{invoice_id}/
    
    Display pre-mandate approval page when judge clicks "No"
    """
    
    authentication_classes = []
    permission_classes = []
    
    
    def get(self, request, invoice_id):
        """
        Display pre-mandate approval page.
        """
        try:
            from invoice_collections.models import Invoice
            from django.shortcuts import render
            
            # Get invoice
            try:
                invoice = Invoice.objects.get(invoice_id=invoice_id)
            except Invoice.DoesNotExist:
                return Response({
                    'success': False,
                    'error_code': 'INVOICE_NOT_FOUND',
                    'error_message': f'Invoice {invoice_id} not found'
                }, status=status.HTTP_404_NOT_FOUND) 
            
            # Create pre-mandate approval data  
            approval_data = {
                'invoice_id': invoice.invoice_id,
                'customer_name': invoice.customer_name,
                'amount': f"${invoice.amount_cents / 100:.2f}",
                'currency': invoice.currency,
                'due_date': invoice.due_date.isoformat() if invoice.due_date else None,
                'created_at': invoice.created_at.isoformat(),
                'status': invoice.status
            }
            
            # Render HTML template with data
            from django.conf import settings
            return render(request, 'pre_mandate_approval.html', {
                'approval_data': approval_data,
                'invoice_id': invoice_id,
                'base_url': getattr(settings, 'BASE_URL', 'https://collection-agent-7fb01e4a92ee.herokuapp.com')
            })
            
        except Exception as e:
            logger.error(f"Error displaying pre-mandate approval: {e}", exc_info=True)
            return Response({
                'success': False,
                'error_code': 'INTERNAL_ERROR',
                'error_message': 'An internal error occurred while displaying approval page'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class PreMandateDecisionView(APIView):
    """
    POST /api/v1/integration/pre-mandate-decision/
    
    Handle pre-mandate approval/rejection decision
    """
    
    authentication_classes = [APIKeyAuthentication]
    permission_classes = [APIKeyPermission]
    
    def post(self, request):
        """
        Process pre-mandate approval/rejection decision.
        """
        try:
            data = request.data
            
            # Validate required fields
            required_fields = ['invoice_id', 'decision']
            for field in required_fields:
                if field not in data:
                    return Response({
                        'success': False,
                        'error_code': 'MISSING_FIELD',
                        'error_message': f'Missing required field: {field}'
                    }, status=status.HTTP_400_BAD_REQUEST)
            
            invoice_id = data['invoice_id']
            decision = data['decision']  # 'approve' or 'reject'
            
            # Get invoice
            try:
                from invoice_collections.models import Invoice
                invoice = Invoice.objects.get(invoice_id=invoice_id)
            except Invoice.DoesNotExist:
                return Response({
                    'success': False,
                    'error_code': 'INVOICE_NOT_FOUND',
                    'error_message': f'Invoice {invoice_id} not found'
                }, status=status.HTTP_404_NOT_FOUND)
            
            # Update Salesforce with pre-mandate decision
            from .salesforce_service import salesforce_service
            
            if decision == 'approve':
                # Update pre_approved field to true in Salesforce
                success = salesforce_service.update_pre_mandate_status(
                    invoice_id=invoice_id,
                    pre_mandate=True
                )
                
                if success:
                    # Update local invoice status
                    invoice.status = 'pre_mandate_approved'
                    invoice.save()
                    
                    # Log agent action
                    from invoice_collections.models import AgentAction
                    AgentAction.objects.create(
                        invoice=invoice,
                        action_type='pre_mandate_approved',
                        decision='approve',
                        payload=data,
                        human_actor=data.get('approved_by', 'unknown'),
                        notes=f'Pre-mandate approved for invoice {invoice_id}. SF team will now call status update API.'
                    )
                    
                    return Response({
                        'success': True,
                        'invoice_id': invoice_id,
                        'status': 'pre_mandate_approved',
                        'message': 'Pre-mandate approved successfully. Salesforce updated. SF team should now call status update API.',
                        'pre_approved': True,
                        'next_step': 'sf_team_calls_status_update_api'
                    })
                else:
                    return Response({
                        'success': False,
                        'error_code': 'SALESFORCE_UPDATE_FAILED',
                        'error_message': 'Failed to update Salesforce pre-mandate status'
                    }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
                    
            elif decision == 'reject':
                # Update pre_mandate field to false in Salesforce
                success = salesforce_service.update_pre_mandate_status(
                    invoice_id=invoice_id,
                    pre_mandate=False
                )
                
                if success:
                    # Update local invoice status
                    invoice.status = 'pre_mandate_rejected'
                    invoice.save()
                    
                    # Log agent action
                    from invoice_collections.models import AgentAction
                    AgentAction.objects.create(
                        invoice=invoice,
                        action_type='pre_mandate_rejected',
                        decision='reject',
                        payload=data,
                        human_actor=data.get('approved_by', 'unknown'),
                        notes=f'Pre-mandate rejected for invoice {invoice_id}'
                    )
                    
                    return Response({
                        'success': True,
                        'invoice_id': invoice_id,
                        'status': 'pre_mandate_rejected',
                        'message': 'Pre-mandate rejected. Salesforce updated.',
                        'pre_mandate': False
                    })
                else:
                    return Response({
                        'success': False,
                        'error_code': 'SALESFORCE_UPDATE_FAILED',
                        'error_message': 'Failed to update Salesforce pre-mandate status'
                    }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            else:
                return Response({
                    'success': False,
                    'error_code': 'INVALID_DECISION',
                    'error_message': 'Decision must be "approve" or "reject"'
                }, status=status.HTTP_400_BAD_REQUEST)
                
        except Exception as e:
            logger.error(f"Error processing pre-mandate decision: {e}", exc_info=True)
            return Response({
                'success': False,
                'error_code': 'INTERNAL_ERROR',
                'error_message': 'An internal error occurred while processing the decision'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class ProceedWithPaymentView(APIView):
    """
    POST /api/v1/integration/proceed-with-payment/
    
    Proceed with payment processing after pre-mandate approval
    """
    
    authentication_classes = [APIKeyAuthentication]
    permission_classes = [APIKeyPermission]
    
    def post(self, request):
        """
        Process payment after pre-mandate approval.
        """
        try:
            data = request.data
            
            # Validate required fields
            required_fields = ['invoice_id']
            for field in required_fields:
                if field not in data:
                    return Response({
                        'success': False,
                        'error_code': 'MISSING_FIELD',
                        'error_message': f'Missing required field: {field}'
                    }, status=status.HTTP_400_BAD_REQUEST)
            
            invoice_id = data['invoice_id']
            
            # Get invoice
            try:
                from invoice_collections.models import Invoice
                invoice = Invoice.objects.get(invoice_id=invoice_id)
            except Invoice.DoesNotExist:
                return Response({
                    'success': False,
                    'error_code': 'INVOICE_NOT_FOUND',
                    'error_message': f'Invoice {invoice_id} not found'
                }, status=status.HTTP_404_NOT_FOUND)
            
            # Check if pre-mandate is approved
            from .salesforce_service import salesforce_service
            pre_mandate_status = salesforce_service.get_pre_mandate_status(invoice_id)
            
            if pre_mandate_status is not True:
                return Response({
                    'success': False,
                    'error_code': 'PRE_MANDATE_NOT_APPROVED',
                    'error_message': 'Pre-mandate must be approved before proceeding with payment'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Prepare data for A2A/AP2 processing
            validated_data = {
                'invoice_id': invoice.invoice_id,
                'amount': invoice.amount_cents / 100,
                'currency': invoice.currency,
                'payment_method': invoice.payment_method,
                'customer_name': invoice.customer_name,
                'approved_by': data.get('approved_by', 'judge@company.com')
            }
            
            # Process collection using A2A and AP2 protocols
            a2a_ap2_result = process_collection_with_a2a_ap2(validated_data)
            
            if a2a_ap2_result['success']:
                # Update invoice status
                invoice.status = 'completed' if a2a_ap2_result['status'] == 'settled' else 'processing'
                invoice.save()
                
                # Log agent action
                from invoice_collections.models import AgentAction
                AgentAction.objects.create(
                    invoice=invoice,
                    action_type='payment_processed_after_approval',
                    decision='proceed_after_approval',
                    payload=a2a_ap2_result,
                    human_actor=data.get('approved_by', 'judge@company.com'),
                    notes=f'Payment processed after pre-mandate approval via A2A conversation {a2a_ap2_result["conversation_id"]} and AP2 request {a2a_ap2_result["ap2_request_id"]}'
                )
                
                return Response({
                    'success': True,
                    'invoice_id': invoice.invoice_id,
                    'status': a2a_ap2_result['status'],
                    'message': a2a_ap2_result['message'],
                    'conversation_id': a2a_ap2_result['conversation_id'],
                    'ap2_request_id': a2a_ap2_result['ap2_request_id'],
                    'transaction_id': a2a_ap2_result['transaction_id'],
                    'estimated_completion': timezone.now() + timedelta(minutes=1)
                })
            else:
                # A2A/AP2 processing failed
                invoice.status = 'failed'
                invoice.save()
                
                return Response({
                    'success': False,
                    'error_code': 'PAYMENT_PROCESSING_FAILED',
                    'error_message': a2a_ap2_result.get('message', 'Payment processing failed')
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
                
        except Exception as e:
            logger.error(f"Error proceeding with payment: {e}", exc_info=True)
            return Response({
                'success': False,
                'error_code': 'INTERNAL_ERROR',
                'error_message': 'An internal error occurred while processing payment'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


