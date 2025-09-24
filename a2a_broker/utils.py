"""
A2A Broker Utilities

Helper functions for A2A communication, signature verification, and authorization.
"""

import hmac
import hashlib
import json
import time
from typing import Dict, Any, Optional
from django.conf import settings
from django.utils import timezone

from .models import A2AAgent, A2AAuthorization


def verify_a2a_signature(request) -> bool:
    """
    Verify A2A request signature for security.
    
    Args:
        request: Django request object
        
    Returns:
        True if signature is valid, False otherwise
    """
    try:
        # Get signature and timestamp from headers
        signature = request.META.get('HTTP_X_A2A_SIGNATURE', '')
        timestamp = request.META.get('HTTP_X_A2A_TIMESTAMP', '')
        agent_id = request.META.get('HTTP_X_A2A_AGENT_ID', '')
        
        if not signature or not timestamp or not agent_id:
            return False
        
        # Check timestamp (prevent replay attacks)
        if abs(time.time() - int(timestamp)) > 60 * 5:  # 5 minutes
            return False
        
        # Get agent's public key
        try:
            agent = A2AAgent.objects.get(agent_id=agent_id)
        except A2AAgent.DoesNotExist:
            return False
        
        # Create signature
        sig_basestring = f"{timestamp}:{request.body.decode('utf-8')}"
        expected_signature = hmac.new(
            agent.public_key.encode('utf-8'),
            sig_basestring.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        
        # Compare signatures
        return hmac.compare_digest(signature, expected_signature)
        
    except Exception:
        return False


def create_conversation_token(initiator_agent: A2AAgent, target_agent: A2AAgent) -> str:
    """
    Create a conversation token for A2A communication.
    
    Args:
        initiator_agent: Initiating agent
        target_agent: Target agent
        
    Returns:
        Conversation token string
    """
    import uuid
    
    token_data = {
        'initiator_id': str(initiator_agent.agent_id),
        'target_id': str(target_agent.agent_id),
        'timestamp': timezone.now().isoformat(),
        'nonce': str(uuid.uuid4())
    }
    
    # Create token using HMAC
    token_string = json.dumps(token_data, sort_keys=True)
    token = hmac.new(
        settings.SECRET_KEY.encode('utf-8'),
        token_string.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()
    
    return token


def validate_authorization(grantor_agent: A2AAgent, grantee_agent: A2AAgent, permission_type: str) -> bool:
    """
    Validate if grantee agent has authorization from grantor agent for a specific permission.
    
    Args:
        grantor_agent: Agent granting permission
        grantee_agent: Agent requesting permission
        permission_type: Type of permission requested
        
    Returns:
        True if authorized, False otherwise
    """
    try:
        # Check for active authorization
        authorization = A2AAuthorization.objects.filter(
            grantor_agent=grantor_agent,
            grantee_agent=grantee_agent,
            permission_type=permission_type,
            status='active'
        ).first()
        
        if not authorization:
            return False
        
        # Check if authorization is valid and not expired
        return authorization.is_valid()
        
    except Exception:
        return False


def create_agent_heartbeat(agent: A2AAgent) -> bool:
    """
    Update agent heartbeat timestamp.
    
    Args:
        agent: A2A agent
        
    Returns:
        True if successful, False otherwise
    """
    try:
        agent.last_heartbeat = timezone.now()
        agent.consecutive_failures = 0
        agent.save()
        return True
    except Exception:
        return False


def mark_agent_failure(agent: A2AAgent) -> None:
    """
    Mark agent as having a failure.
    
    Args:
        agent: A2A agent
    """
    try:
        agent.consecutive_failures += 1
        if agent.consecutive_failures >= 5:  # Mark as error after 5 consecutive failures
            agent.status = 'error'
        agent.save()
    except Exception:
        pass


def get_agent_capabilities(agent: A2AAgent) -> list:
    """
    Get agent capabilities.
    
    Args:
        agent: A2A agent
        
    Returns:
        List of capabilities
    """
    return agent.capabilities or []


def can_agent_perform_action(agent: A2AAgent, action: str) -> bool:
    """
    Check if agent can perform a specific action.
    
    Args:
        agent: A2A agent
        action: Action to check
        
    Returns:
        True if agent can perform action, False otherwise
    """
    capabilities = get_agent_capabilities(agent)
    return action in capabilities


def create_payment_authorization_request(
    collections_agent: A2AAgent,
    payment_agent: A2AAgent,
    invoice_id: str,
    amount_cents: int,
    mandate_id: str
) -> Dict[str, Any]:
    """
    Create a payment authorization request for A2A communication.
    
    Args:
        collections_agent: Collections agent
        payment_agent: Payment agent
        invoice_id: Invoice ID
        amount_cents: Amount in cents
        mandate_id: Mandate ID
        
    Returns:
        Authorization request dictionary
    """
    return {
        'request_type': 'payment_authorization',
        'initiator_agent_id': str(collections_agent.agent_id),
        'target_agent_id': str(payment_agent.agent_id),
        'conversation_type': 'payment_initiation',
        'context_data': {
            'invoice_id': invoice_id,
            'amount_cents': amount_cents,
            'mandate_id': mandate_id
        },
        'payload': {
            'action': 'authorize_payment',
            'invoice_id': invoice_id,
            'amount_cents': amount_cents,
            'mandate_id': mandate_id,
            'timestamp': timezone.now().isoformat()
        }
    }


def create_customer_verification_request(
    collections_agent: A2AAgent,
    customer_support_agent: A2AAgent,
    customer_id: str,
    customer_name: str
) -> Dict[str, Any]:
    """
    Create a customer verification request for A2A communication.
    
    Args:
        collections_agent: Collections agent
        customer_support_agent: Customer support agent
        customer_id: Customer ID
        customer_name: Customer name
        
    Returns:
        Verification request dictionary
    """
    return {
        'request_type': 'customer_verification',
        'initiator_agent_id': str(collections_agent.agent_id),
        'target_agent_id': str(customer_support_agent.agent_id),
        'conversation_type': 'customer_verification',
        'context_data': {
            'customer_id': customer_id,
            'customer_name': customer_name
        },
        'payload': {
            'action': 'verify_customer',
            'customer_id': customer_id,
            'customer_name': customer_name,
            'timestamp': timezone.now().isoformat()
        }
    }


def create_fraud_check_request(
    collections_agent: A2AAgent,
    fraud_detection_agent: A2AAgent,
    invoice_id: str,
    amount_cents: int,
    customer_id: str
) -> Dict[str, Any]:
    """
    Create a fraud check request for A2A communication.
    
    Args:
        collections_agent: Collections agent
        fraud_detection_agent: Fraud detection agent
        invoice_id: Invoice ID
        amount_cents: Amount in cents
        customer_id: Customer ID
        
    Returns:
        Fraud check request dictionary
    """
    return {
        'request_type': 'fraud_check',
        'initiator_agent_id': str(collections_agent.agent_id),
        'target_agent_id': str(fraud_detection_agent.agent_id),
        'conversation_type': 'fraud_check',
        'context_data': {
            'invoice_id': invoice_id,
            'amount_cents': amount_cents,
            'customer_id': customer_id
        },
        'payload': {
            'action': 'check_fraud',
            'invoice_id': invoice_id,
            'amount_cents': amount_cents,
            'customer_id': customer_id,
            'timestamp': timezone.now().isoformat()
        }
    }


def send_a2a_request(endpoint: str, request_data: Dict[str, Any], agent: A2AAgent) -> Optional[Dict[str, Any]]:
    """
    Send an A2A request to another agent.
    
    Args:
        endpoint: Target agent endpoint
        request_data: Request data
        agent: Sending agent
        
    Returns:
        Response data or None if failed
    """
    try:
        import requests
        
        # Create signature
        timestamp = str(int(time.time()))
        sig_basestring = f"{timestamp}:{json.dumps(request_data)}"
        signature = hmac.new(
            agent.public_key.encode('utf-8'),
            sig_basestring.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        
        # Send request
        headers = {
            'Content-Type': 'application/json',
            'X-A2A-Signature': signature,
            'X-A2A-Timestamp': timestamp,
            'X-A2A-Agent-ID': str(agent.agent_id)
        }
        
        response = requests.post(
            endpoint,
            json=request_data,
            headers=headers,
            timeout=30
        )
        
        if response.status_code == 200:
            return response.json()
        else:
            return None
            
    except Exception as e:
        print(f"Error sending A2A request: {e}")
        return None


def parse_a2a_response(response_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Parse A2A response data.
    
    Args:
        response_data: Response data from A2A agent
        
    Returns:
        Parsed response dictionary
    """
    return {
        'success': response_data.get('success', False),
        'conversation_id': response_data.get('conversation_id'),
        'result_data': response_data.get('result_data', {}),
        'error_message': response_data.get('error_message', ''),
        'timestamp': response_data.get('timestamp', timezone.now().isoformat())
    }
