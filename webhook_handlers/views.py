"""
Webhook handlers for external system integrations.

This module contains webhook endpoints for Stripe and Salesforce notifications.
"""

import logging
import json
from django.utils import timezone
from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.conf import settings
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework import status

from .models import WebhookEvent, SalesforceNotification, ExternalSystemIntegration
from invoice_collections.authentication import StripeWebhookAuthentication
from invoice_collections.tasks import handle_stripe_webhook

logger = logging.getLogger(__name__)


@csrf_exempt
@require_http_methods(["POST"])
def stripe_webhook(request):
    """
    POST /api/v1/webhooks/stripe/
    
    Handle Stripe webhook events for payment status updates.
    """
    try:
        # Verify webhook signature
        import stripe
        import hmac
        import hashlib
        
        payload = request.body
        sig_header = request.META.get('HTTP_STRIPE_SIGNATURE')
        webhook_secret = settings.STRIPE_WEBHOOK_SECRET
        
        if not webhook_secret:
            logger.error("Stripe webhook secret not configured")
            return HttpResponse("Webhook secret not configured", status=500)
        
        try:
            # Verify the webhook signature
            event = stripe.Webhook.construct_event(
                payload, sig_header, webhook_secret
            )
        except ValueError:
            logger.error("Invalid payload in Stripe webhook")
            return HttpResponse("Invalid payload", status=400)
        except stripe.error.SignatureVerificationError:
            logger.error("Invalid signature in Stripe webhook")
            return HttpResponse("Invalid signature", status=400)
        
        # Create webhook event record
        webhook_event = WebhookEvent.objects.create(
            source='stripe',
            event_type=event['type'],
            external_id=event['id'],
            payload=event,
            headers=dict(request.META),
            status='received'
        )
        
        # Queue webhook processing task
        handle_stripe_webhook(event)
        
        # Update webhook event status
        webhook_event.status = 'processing'
        webhook_event.save()
        
        logger.info(f"Stripe webhook received: {event['type']} - {event['id']}")
        
        return HttpResponse("Webhook received", status=200)
        
    except Exception as e:
        logger.error(f"Error processing Stripe webhook: {e}", exc_info=True)
        return HttpResponse("Internal server error", status=500)


@api_view(['POST'])
@authentication_classes([])
@permission_classes([AllowAny])
def salesforce_webhook(request):
    """
    POST /api/v1/webhooks/notify-salesforce/
    
    Handle notifications from Salesforce (acknowledgments, etc.).
    """
    try:
        # Parse request data
        try:
            data = request.data
            # Convert to dict if it's a QueryDict or other non-serializable object
            if hasattr(data, 'dict'):
                data = data.dict()
            elif not isinstance(data, dict):
                data = dict(data)
        except Exception as e:
            logger.error(f"Error parsing request data: {e}")
            data = {}
        
        # Create webhook event record
        webhook_event = WebhookEvent.objects.create(
            source='salesforce',
            event_type='notification_received',
            external_id=data.get('notification_id', ''),
            payload=data,
            headers=dict(request.META),
            status='received'
        )
        
        # Process Salesforce notification
        notification_id = data.get('notification_id')
        if notification_id:
            try:
                notification = SalesforceNotification.objects.get(
                    notification_id=notification_id
                )
                notification.status = 'acknowledged'
                notification.acknowledged_at = timezone.now()
                notification.save()
                
                logger.info(f"Salesforce notification acknowledged: {notification_id}")
                
            except SalesforceNotification.DoesNotExist:
                logger.warning(f"Salesforce notification not found: {notification_id}")
        
        # Update webhook event status
        webhook_event.status = 'processed'
        webhook_event.processed_at = timezone.now()
        webhook_event.save()
        
        return Response({
            'success': True,
            'message': 'Notification received'
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        logger.error(f"Error processing Salesforce webhook: {e}", exc_info=True)
        return Response({
            'success': False,
            'error': 'Internal server error'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@authentication_classes([])
@permission_classes([AllowAny])
def webhook_status(request):
    """
    GET /api/v1/webhooks/status/
    
    Get status of recent webhook events.
    """
    try:
        # Get recent webhook events
        recent_events = WebhookEvent.objects.filter(
            received_at__gte=timezone.now() - timezone.timedelta(hours=24)
        ).order_by('-received_at')[:50]
        
        events_data = []
        for event in recent_events:
            events_data.append({
                'event_id': str(event.event_id),
                'source': event.source,
                'event_type': event.event_type,
                'status': event.status,
                'received_at': event.received_at,
                'processed_at': event.processed_at,
                'retry_count': event.retry_count,
                'processing_error': event.processing_error
            })
        
        # Get webhook statistics
        stats = {
            'total_events_24h': WebhookEvent.objects.filter(
                received_at__gte=timezone.now() - timezone.timedelta(hours=24)
            ).count(),
            'failed_events_24h': WebhookEvent.objects.filter(
                received_at__gte=timezone.now() - timezone.timedelta(hours=24),
                status='failed'
            ).count(),
            'pending_events': WebhookEvent.objects.filter(
                status__in=['received', 'processing']
            ).count(),
        }
        
        return Response({
            'success': True,
            'recent_events': events_data,
            'statistics': stats
        })
        
    except Exception as e:
        logger.error(f"Error getting webhook status: {e}", exc_info=True)
        return Response({
            'success': False,
            'error': 'Internal server error'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@authentication_classes([])
@permission_classes([AllowAny])
def test_webhook(request):
    """
    POST /api/v1/webhooks/test/
    
    Test webhook endpoint for development and testing.
    """
    try:
        # Create test webhook event
        webhook_event = WebhookEvent.objects.create(
            source='test',
            event_type='test_event',
            external_id='test_' + str(timezone.now().timestamp()),
            payload=request.data,
            headers=dict(request.META),
            status='received'
        )
        
        # Simulate processing
        webhook_event.status = 'processed'
        webhook_event.processed_at = timezone.now()
        webhook_event.save()
        
        logger.info(f"Test webhook received: {webhook_event.event_id}")
        
        return Response({
            'success': True,
            'message': 'Test webhook received',
            'event_id': str(webhook_event.event_id),
            'timestamp': webhook_event.received_at
        })
        
    except Exception as e:
        logger.error(f"Error processing test webhook: {e}", exc_info=True)
        return Response({
            'success': False,
            'error': 'Internal server error'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)