"""
URL configuration for Webhook Handlers app.
"""

from django.urls import path
from . import views

app_name = 'webhook_handlers'

urlpatterns = [
    # Webhook endpoints
    path('webhooks/stripe/', views.stripe_webhook, name='stripe_webhook'),
    path('webhooks/notify-salesforce/', views.salesforce_webhook, name='salesforce_webhook'),
    path('webhooks/status/', views.webhook_status, name='webhook_status'),
    path('webhooks/test/', views.test_webhook, name='test_webhook'),
]
