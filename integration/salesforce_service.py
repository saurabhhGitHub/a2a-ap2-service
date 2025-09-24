"""
Salesforce Integration Service

This service handles OAuth authentication and API calls to Salesforce.
"""

import requests
import json
import logging
from django.conf import settings
from typing import Dict, Optional, Any

logger = logging.getLogger(__name__)


class SalesforceService:
    """
    Service for interacting with Salesforce APIs
    """
    
    def __init__(self):
        self.client_id = getattr(settings, 'SALESFORCE_CLIENT_ID', None)
        self.client_secret = getattr(settings, 'SALESFORCE_CLIENT_SECRET', None)
        self.username = getattr(settings, 'SALESFORCE_USERNAME', None)
        self.password = getattr(settings, 'SALESFORCE_PASSWORD', None)
        self.security_token = getattr(settings, 'SALESFORCE_SECURITY_TOKEN', None)
        self.instance_url = getattr(settings, 'SALESFORCE_INSTANCE_URL', None)
        self.webhook_url = getattr(settings, 'SALESFORCE_WEBHOOK_URL', None)
        
        self.access_token = None
        self.token_expires_at = None
    
    def authenticate(self) -> bool:
        """
        Authenticate with Salesforce using OAuth 2.0 Username-Password flow
        """
        try:
            auth_url = f"{self.instance_url}/services/oauth2/token"
            
            payload = {
                'grant_type': 'password',
                'client_id': self.client_id,
                'client_secret': self.client_secret,
                'username': self.username,
                'password': self.password  # No security token needed for this org
            }
            
            headers = {
                'Content-Type': 'application/x-www-form-urlencoded'
            }
            
            response = requests.post(auth_url, data=payload, headers=headers, timeout=30)
            
            if response.status_code == 200:
                auth_data = response.json()
                self.access_token = auth_data.get('access_token')
                self.instance_url = auth_data.get('instance_url')
                
                logger.info("Successfully authenticated with Salesforce")
                return True
            else:
                logger.error(f"Salesforce authentication failed: {response.status_code} - {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"Error authenticating with Salesforce: {e}", exc_info=True)
            return False
    
    def get_access_token(self) -> Optional[str]:
        """
        Get valid access token, refreshing if necessary
        """
        if not self.access_token:
            if not self.authenticate():
                return None
        
        return self.access_token
    
    def update_invoice_status(self, invoice_id: str, status: str, transaction_id: str = None) -> bool:
        """
        Update invoice status in Salesforce
        """
        try:
            access_token = self.get_access_token()
            if not access_token:
                logger.error("No valid access token for Salesforce")
                return False
            
            # Use the webhook URL to update invoice status
            if self.webhook_url:
                return self._call_salesforce_webhook(invoice_id, status, transaction_id)
            else:
                # Fallback to direct API call
                return self._update_via_sobject_api(invoice_id, status, transaction_id, access_token)
                
        except Exception as e:
            logger.error(f"Error updating invoice status in Salesforce: {e}", exc_info=True)
            return False
    
    def _call_salesforce_webhook(self, invoice_id: str, status: str, transaction_id: str = None) -> bool:
        """
        Call Salesforce webhook to update invoice status
        """
        try:
            access_token = self.get_access_token()
            if not access_token:
                return False
            
            payload = {
                'invoice_id': invoice_id,
                'status': status,
                'transaction_id': transaction_id,
                'updated_at': self._get_current_timestamp()
            }
            
            headers = {
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {access_token}'
            }
            
            response = requests.post(self.webhook_url, json=payload, headers=headers, timeout=30)
            
            if response.status_code in [200, 201]:
                logger.info(f"Successfully updated invoice {invoice_id} status to {status} in Salesforce")
                return True
            else:
                logger.error(f"Failed to update Salesforce invoice status: {response.status_code} - {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"Error calling Salesforce webhook: {e}", exc_info=True)
            return False
    
    def _update_via_sobject_api(self, invoice_id: str, status: str, transaction_id: str, access_token: str) -> bool:
        """
        Update invoice status via Salesforce SObject API
        """
        try:
            # First, find the invoice record
            query_url = f"{self.instance_url}/services/data/v58.0/query/"
            query = f"SELECT Id FROM Invoice__c WHERE Invoice_ID__c = '{invoice_id}'"
            
            headers = {
                'Authorization': f'Bearer {access_token}',
                'Content-Type': 'application/json'
            }
            
            response = requests.get(f"{query_url}?q={query}", headers=headers, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                records = data.get('records', [])
                
                if records:
                    record_id = records[0]['Id']
                    
                    # Update the record
                    update_url = f"{self.instance_url}/services/data/v58.0/sobjects/Invoice__c/{record_id}"
                    update_data = {
                        'Status__c': status
                    }
                    
                    if transaction_id:
                        update_data['Transaction_ID__c'] = transaction_id
                    
                    response = requests.patch(update_url, json=update_data, headers=headers, timeout=30)
                    
                    if response.status_code == 204:
                        logger.info(f"Successfully updated invoice {invoice_id} status to {status} in Salesforce")
                        return True
                    else:
                        logger.error(f"Failed to update Salesforce record: {response.status_code} - {response.text}")
                        return False
                else:
                    logger.error(f"Invoice {invoice_id} not found in Salesforce")
                    return False
            else:
                logger.error(f"Failed to query Salesforce: {response.status_code} - {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"Error updating Salesforce via SObject API: {e}", exc_info=True)
            return False
    
    def get_invoice_details(self, invoice_id: str) -> Optional[Dict[str, Any]]:
        """
        Get invoice details from Salesforce
        """
        try:
            access_token = self.get_access_token()
            if not access_token:
                return None
            
            query_url = f"{self.instance_url}/services/data/v58.0/query/"
            query = f"SELECT Id, Name, Amount__c, Status__c, Customer_Name__c FROM Invoice__c WHERE Invoice_ID__c = '{invoice_id}'"
            
            headers = {
                'Authorization': f'Bearer {access_token}',
                'Content-Type': 'application/json'
            }
            
            response = requests.get(f"{query_url}?q={query}", headers=headers, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                records = data.get('records', [])
                
                if records:
                    return records[0]
                else:
                    logger.warning(f"Invoice {invoice_id} not found in Salesforce")
                    return None
            else:
                logger.error(f"Failed to query Salesforce invoice: {response.status_code} - {response.text}")
                return None
                
        except Exception as e:
            logger.error(f"Error getting invoice details from Salesforce: {e}", exc_info=True)
            return None
    
    def _get_current_timestamp(self) -> str:
        """
        Get current timestamp in ISO format
        """
        from datetime import datetime
        return datetime.now().isoformat() + 'Z'

    def get_pre_mandate_status(self, invoice_id: str) -> Optional[bool]:
        """
        Get pre_approved status from Salesforce for a given invoice.
        Returns True if pre_approved is true, False if not, None if error.
        """
        if not self.access_token:
            if not self.authenticate():
                logger.error("Failed to authenticate, cannot get pre-mandate status.")
                return None

        try:
            # Query Salesforce to get pre_approved status
            # This assumes you have a custom object or field that stores this information
            # You may need to adjust the SOQL query based on your Salesforce setup
            
            # For demo purposes, we'll simulate checking the Account object
            # In real implementation, you might query Invoice__c or related objects
            query_url = f"{self.instance_url}/services/data/v58.0/query/"
             
            # Example SOQL query - adjust based on your Salesforce schema
            soql_query = f"SELECT pre_approved__c FROM Account WHERE Invoice_ID__c = '{invoice_id}' LIMIT 1"
            
            headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json"
            }
            
            params = {
                "q": soql_query
            }
            
            response = requests.get(query_url, headers=headers, params=params, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            records = data.get('records', [])
            
            if records:
                pre_approved_value = records[0].get('pre_approved__c', False)
                logger.info(f"Retrieved pre_approved status {pre_approved_value} for invoice {invoice_id}")
                return pre_approved_value
            else:
                logger.warning(f"No records found for invoice {invoice_id}, defaulting to False")
                return False
                
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to get pre-mandate status from Salesforce: {e.response.status_code} - {e.response.text}")
            return None
        except Exception as e:
            logger.error(f"An unexpected error occurred while getting pre-mandate status: {e}", exc_info=True)
            return None

    def update_pre_mandate_status(self, invoice_id: str, pre_mandate: bool) -> bool:
        """
        Update pre_approved field in Salesforce using the existing InvoiceStatusUpdate endpoint.
        """
        if not self.access_token:
            if not self.authenticate():
                logger.error("Failed to authenticate, cannot update pre-mandate status.")
                return False

        try:
            # Use the existing InvoiceStatusUpdate endpoint to update pre_mandate
            update_url = self.webhook_url  # This is the InvoiceStatusUpdate endpoint
            
            payload = {
                "invoice_id": invoice_id,
                "pre_approved": pre_mandate,
                "status": "pre_mandate_updated"
            }

            headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json"
            }
            
            response = requests.post(update_url, json=payload, headers=headers, timeout=10)
            response.raise_for_status()
            
            response_data = response.json()
            if response_data.get('success'):
                logger.info(f"Successfully updated pre_approved to {pre_mandate} for invoice {invoice_id} in Salesforce")
                return True
            else:
                logger.error(f"Salesforce API returned error for pre_mandate update: {response_data.get('message')}")
                return False
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to update pre_mandate status in Salesforce: {e.response.status_code} - {e.response.text}")
            return False
        except Exception as e:
            logger.error(f"An unexpected error occurred while updating Salesforce pre_mandate status: {e}", exc_info=True)
            return False


# Global instance
salesforce_service = SalesforceService()
