"""
Custom authentication classes for the Collections Agent API.
"""

from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.permissions import BasePermission
from django.conf import settings
from django.contrib.auth.models import AnonymousUser
from webhook_handlers.models import AuditLog


class APIKeyAuthentication(BaseAuthentication):
    """
    API Key authentication for Salesforce and other external systems.
    """
    
    def authenticate(self, request):
        """
        Authenticate the request using API key from header.
        """
        api_key = self.get_api_key(request)
        
        if not api_key:
            return None
        
        if not self.validate_api_key(api_key):
            # Log failed authentication attempt
            self.log_auth_attempt(request, api_key, success=False)
            raise AuthenticationFailed('Invalid API key')
        
        # Log successful authentication
        self.log_auth_attempt(request, api_key, success=True)
        
        # Return a tuple of (user, auth) - we don't have users, so return AnonymousUser
        return (AnonymousUser(), api_key)
    
    def get_api_key(self, request):
        """
        Extract API key from request headers.
        """
        api_key_header = getattr(settings, 'API_KEY_HEADER', 'X-API-Key')
        return request.META.get(f'HTTP_{api_key_header.upper().replace("-", "_")}')
    
    def validate_api_key(self, api_key):
        """
        Validate the provided API key against configured keys.
        """
        valid_keys = [
            settings.SALESFORCE_API_KEY,
            # Add other valid API keys here
        ]
        
        # Remove empty/None keys
        valid_keys = [key for key in valid_keys if key]
        
        return api_key in valid_keys
    
    def log_auth_attempt(self, request, api_key, success=True):
        """
        Log authentication attempts for audit purposes.
        """
        try:
            AuditLog.objects.create(
                action_type='api_request',
                action_description=f'API Authentication {"Success" if success else "Failed"}',
                actor_type='api',
                actor_id=api_key[:8] + '...' if api_key else 'unknown',
                ip_address=self.get_client_ip(request),
                user_agent=request.META.get('HTTP_USER_AGENT', ''),
                request_id=request.META.get('HTTP_X_REQUEST_ID', ''),
                metadata={
                    'endpoint': request.path,
                    'method': request.method,
                    'success': success,
                    'api_key_prefix': api_key[:8] + '...' if api_key else None,
                }
            )
        except Exception:
            # Don't let logging errors break authentication
            pass
    
    def get_client_ip(self, request):
        """
        Get the client IP address from the request.
        """
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip
    
    def authenticate_header(self, request):
        """
        Return the authentication header value.
        """
        return 'Api-Key'


class StripeWebhookAuthentication(BaseAuthentication):
    """
    Authentication for Stripe webhook requests using signature verification.
    """
    
    def authenticate(self, request):
        """
        Authenticate Stripe webhook using signature verification.
        """
        import stripe
        import hashlib
        import hmac
        
        # Get the signature from headers
        signature = request.META.get('HTTP_STRIPE_SIGNATURE')
        if not signature:
            return None
        
        # Get the webhook secret
        webhook_secret = settings.STRIPE_WEBHOOK_SECRET
        if not webhook_secret:
            raise AuthenticationFailed('Webhook secret not configured')
        
        # Get the raw body
        body = request.body
        
        try:
            # Verify the signature
            stripe.Webhook.construct_event(
                body, signature, webhook_secret
            )
            
            # Log successful webhook authentication
            self.log_webhook_auth(request, success=True)
            
            return (AnonymousUser(), 'stripe_webhook')
            
        except ValueError:
            # Invalid payload
            self.log_webhook_auth(request, success=False, error='Invalid payload')
            raise AuthenticationFailed('Invalid payload')
        except stripe.error.SignatureVerificationError:
            # Invalid signature
            self.log_webhook_auth(request, success=False, error='Invalid signature')
            raise AuthenticationFailed('Invalid signature')
    
    def log_webhook_auth(self, request, success=True, error=None):
        """
        Log webhook authentication attempts.
        """
        try:
            AuditLog.objects.create(
                action_type='webhook_received',
                action_description=f'Stripe Webhook Authentication {"Success" if success else "Failed"}',
                actor_type='webhook',
                actor_id='stripe',
                ip_address=self.get_client_ip(request),
                user_agent=request.META.get('HTTP_USER_AGENT', ''),
                metadata={
                    'endpoint': request.path,
                    'method': request.method,
                    'success': success,
                    'error': error,
                    'webhook_type': 'stripe',
                }
            )
        except Exception:
            # Don't let logging errors break authentication
            pass
    
    def get_client_ip(self, request):
        """
        Get the client IP address from the request.
        """
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip
    
    def authenticate_header(self, request):
        """
        Return the authentication header value.
        """
        return 'Stripe-Signature'


class APIKeyPermission(BasePermission):
    """
    Custom permission class for API key authentication.
    Allows access if the request has been authenticated with an API key.
    """
    
    def has_permission(self, request, view):
        """
        Return True if the request has been authenticated with an API key.
        """
        # Check if the request has been authenticated
        # For API key auth, we return (AnonymousUser(), api_key) from authenticate()
        return (hasattr(request, 'user') and 
                hasattr(request, 'auth') and 
                request.auth is not None)
