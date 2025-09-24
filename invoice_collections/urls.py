"""
URL configuration for Invoice Collections app.
"""

from django.urls import path
from . import views

app_name = 'invoice_collections'

urlpatterns = [
    # Collection endpoints
    path('collections/initiate/', views.CollectionInitiateView.as_view(), name='collection_initiate'),
    path('collections/status/<str:invoice_id>/', views.CollectionStatusView.as_view(), name='collection_status'),
    
    # Health check
    path('health/', views.health_check, name='health_check'),
]
