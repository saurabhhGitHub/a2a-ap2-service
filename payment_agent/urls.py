"""
Payment Agent (AP2) URLs

URL patterns for AP2 payment agent endpoints.
"""

from django.urls import path
from . import views

app_name = 'payment_agent'

urlpatterns = [
    # AP2 Payment Processing
    path('payments/initiate/', views.ap2_payment_initiate, name='ap2_payment_initiate'),
    path('payments/<str:ap2_request_id>/status/', views.ap2_payment_status, name='ap2_payment_status'),
    
    # AP2 Processors
    path('processors/', views.ap2_processors_list, name='ap2_processors_list'),
    
    # AP2 Webhooks
    path('webhooks/<str:processor_name>/', views.ap2_webhook_handler, name='ap2_webhook_handler'),
]
