"""
Integration Services

Services for communicating with external systems like Slack and Salesforce.
"""

import logging
import requests
from typing import Dict, Any, Optional
from django.conf import settings
from django.utils import timezone
from .salesforce_service import salesforce_service

logger = logging.getLogger(__name__)


class NotificationService:
    """Service for sending notifications to external systems."""
    
    def __init__(self):
        self.slack_webhook_url = getattr(settings, 'SLACK_WEBHOOK_URL', None)
        self.salesforce_webhook_url = getattr(settings, 'SALESFORCE_WEBHOOK_URL', None)
    
    def notify_slack(self, message: str, channel: str = None, blocks: list = None) -> bool:
        """
        Send notification to Slack.
        
        Args:
            message: Text message to send
            channel: Slack channel (optional)
            blocks: Slack blocks for rich formatting (optional)
            
        Returns:
            True if successful, False otherwise
        """
        if not self.slack_webhook_url:
            logger.warning("Slack webhook URL not configured")
            return False
        
        try:
            payload = {
                'text': message,
                'channel': channel,
                'username': 'Collections Agent',
                'icon_emoji': ':money_with_wings:'
            }
            
            if blocks:
                payload['blocks'] = blocks
            
            response = requests.post(
                self.slack_webhook_url,
                json=payload,
                timeout=10
            )
            
            if response.status_code == 200:
                logger.info(f"Slack notification sent successfully: {message[:50]}...")
                return True
            else:
                logger.error(f"Slack notification failed: {response.status_code} - {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"Error sending Slack notification: {e}")
            return False
    
    def notify_salesforce(self, data: Dict[str, Any]) -> bool:
        """
        Send status update to Salesforce using OAuth authentication.
        
        Args:
            data: Data to send to Salesforce
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Use the new Salesforce service with OAuth
            invoice_id = data.get('invoice_id')
            status = data.get('status')
            transaction_id = data.get('transaction_id')
            
            if invoice_id and status:
                success = salesforce_service.update_invoice_status(
                    invoice_id=invoice_id,
                    status=status,
                    transaction_id=transaction_id
                )
                
                if success:
                    logger.info(f"Salesforce notification sent successfully for invoice {invoice_id}")
                    return True
                else:
                    logger.error(f"Failed to update Salesforce for invoice {invoice_id}")
                    return False
            else:
                logger.error("Missing required fields for Salesforce notification")
                return False
                
        except Exception as e:
            logger.error(f"Error sending Salesforce notification: {e}")
            return False
    
    def send_invoice_status_update(self, invoice_id: str, status: str, 
                                 customer_name: str, amount_cents: int, 
                                 currency: str = 'USD') -> bool:
        """
        Send invoice status update to both Slack and Salesforce.
        
        Args:
            invoice_id: Invoice ID
            status: New status
            customer_name: Customer name
            amount_cents: Amount in cents
            currency: Currency code
            
        Returns:
            True if at least one notification was successful
        """
        amount_dollars = amount_cents / 100
        
        # Prepare Slack message
        status_emoji = {
            'completed': '✅',
            'failed': '❌',
            'processing': '⏳',
            'cancelled': '🚫'
        }.get(status, '📋')
        
        slack_message = (
            f"{status_emoji} Invoice #{invoice_id} Status Update\n"
            f"Customer: {customer_name}\n"
            f"Amount: {currency} ${amount_dollars:.2f}\n"
            f"Status: {status.title()}\n"
            f"Time: {timezone.now().strftime('%Y-%m-%d %H:%M:%S UTC')}"
        )
        
        # Prepare Salesforce data
        salesforce_data = {
            'invoice_id': invoice_id,
            'status': status,
            'customer_name': customer_name,
            'amount_cents': amount_cents,
            'currency': currency,
            'updated_at': timezone.now().isoformat(),
            'source': 'collections_agent'
        }
        
        # Send notifications
        slack_success = self.notify_slack(slack_message)
        salesforce_success = self.notify_salesforce(salesforce_data)
        
        return slack_success or salesforce_success
    
    def send_approval_request(self, invoice_id: str, customer_name: str, 
                            amount_cents: int, currency: str = 'USD',
                            days_overdue: int = 0) -> bool:
        """
        Send approval request to Slack.
        
        Args:
            invoice_id: Invoice ID
            customer_name: Customer name
            amount_cents: Amount in cents
            currency: Currency code
            days_overdue: Days overdue
            
        Returns:
            True if successful, False otherwise
        """
        amount_dollars = amount_cents / 100
        
        # Create Slack blocks for interactive message
        blocks = [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Invoice Collection Request*\n\n"
                           f"*Invoice:* #{invoice_id}\n"
                           f"*Customer:* {customer_name}\n"
                           f"*Amount:* {currency} ${amount_dollars:.2f}\n"
                           f"*Days Overdue:* {days_overdue}\n"
                           f"*Time:* {timezone.now().strftime('%Y-%m-%d %H:%M:%S UTC')}"
                }
            },
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {
                            "type": "plain_text",
                            "text": "Approve Payment"
                        },
                        "style": "primary",
                        "action_id": "approve_payment",
                        "value": invoice_id
                    },
                    {
                        "type": "button",
                        "text": {
                            "type": "plain_text",
                            "text": "Reject"
                        },
                        "style": "danger",
                        "action_id": "reject_payment",
                        "value": invoice_id
                    }
                ]
            }
        ]
        
        message = f"Invoice #{invoice_id} ({customer_name}) - {currency} ${amount_dollars:.2f} - {days_overdue} days overdue"
        
        return self.notify_slack(message, blocks=blocks)


class WebhookService:
    """Service for handling webhook communications."""
    
    def __init__(self):
        self.notification_service = NotificationService()
    
    def process_payment_completion(self, invoice_id: str, status: str, 
                                 transaction_id: str = None, 
                                 error_message: str = None) -> bool:
        """
        Process payment completion and notify external systems.
        
        Args:
            invoice_id: Invoice ID
            status: Payment status
            transaction_id: External transaction ID
            error_message: Error message if failed
            
        Returns:
            True if successful, False otherwise
        """
        try:
            from invoice_collections.models import Invoice
            
            # Get invoice
            invoice = Invoice.objects.get(invoice_id=invoice_id)
            
            # Update invoice status
            invoice.status = status
            invoice.save()
            
            # Prepare notification data
            if status == 'completed':
                message = f"✅ Payment completed for Invoice #{invoice_id}"
                if transaction_id:
                    message += f" (Transaction: {transaction_id})"
            elif status == 'failed':
                message = f"❌ Payment failed for Invoice #{invoice_id}"
                if error_message:
                    message += f"\nError: {error_message}"
            else:
                message = f"📋 Payment status updated for Invoice #{invoice_id}: {status}"
            
            # Send notifications
            self.notification_service.notify_slack(message)
            self.notification_service.notify_salesforce({
                'invoice_id': invoice_id,
                'status': status,
                'transaction_id': transaction_id,
                'error_message': error_message,
                'updated_at': timezone.now().isoformat()
            })
            
            return True
            
        except Exception as e:
            logger.error(f"Error processing payment completion: {e}")
            return False
    
    def handle_approval_response(self, invoice_id: str, decision: str, 
                               user_name: str, reason: str = None) -> bool:
        """
        Handle approval response from Slack.
        
        Args:
            invoice_id: Invoice ID
            decision: Approval decision (approve/reject)
            user_name: User who made the decision
            reason: Reason for decision
            
        Returns:
            True if successful, False otherwise
        """
        try:
            from invoice_collections.models import Invoice, AgentAction
            
            # Get invoice
            invoice = Invoice.objects.get(invoice_id=invoice_id)
            
            # Update invoice status
            if decision == 'approve':
                invoice.status = 'processing'
                message = f"✅ Payment approved by {user_name} for Invoice #{invoice_id}"
            else:
                invoice.status = 'cancelled'
                message = f"🚫 Payment rejected by {user_name} for Invoice #{invoice_id}"
            
            invoice.save()
            
            # Log agent action
            AgentAction.objects.create(
                invoice=invoice,
                action_type='status_updated',
                decision=decision,
                payload={
                    'user_name': user_name,
                    'reason': reason,
                    'source': 'slack'
                },
                human_actor=user_name,
                notes=f'Payment {decision} by {user_name} via Slack'
            )
            
            # Send notifications
            self.notification_service.notify_slack(message)
            
            return True
            
        except Exception as e:
            logger.error(f"Error handling approval response: {e}")
            return False


# Global service instances
notification_service = NotificationService()
webhook_service = WebhookService()
