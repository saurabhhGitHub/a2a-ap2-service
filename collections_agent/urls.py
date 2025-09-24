"""
URL configuration for collections_agent project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

urlpatterns = [
    path('admin/', admin.site.urls),
    
    # Legacy API endpoints (for backward compatibility)
    path('api/v1/', include('invoice_collections.urls')),
    path('api/v1/', include('webhook_handlers.urls')),
    path('api/v1/', include('payment_processing.urls')),
    
    # A2A Broker and AP2 Payment Agent endpoints
    path('api/v1/a2a/', include('a2a_broker.urls')),
    path('api/v1/ap2/', include('payment_agent.urls')),
    
    # Integration endpoints for external systems
    path('api/v1/integration/', include('integration.urls')),
    
    # API documentation
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
]
