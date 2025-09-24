"""
URL configuration for Integration app.
"""

from django.urls import path
from . import views
from . import slack_views

app_name = 'integration'

urlpatterns = [
    # Salesforce integration endpoints
    path('salesforce/webhook/', views.SalesforceWebhookView.as_view(), name='salesforce_webhook'),
    
    # Slack integration endpoints
    path('slack/approval/', views.SlackApprovalView.as_view(), name='slack_approval'),
    path('slack/collect/', slack_views.slack_collect_command, name='slack_collect'),
    path('slack/status/', slack_views.slack_status_command, name='slack_status'),
    
    # Status and monitoring endpoints
    path('status/<str:invoice_id>/', views.StatusNotificationView.as_view(), name='status_notification'),
    path('overdue-invoices/', views.OverdueInvoicesView.as_view(), name='overdue_invoices'),
    
    # A2A conversation status
    path('a2a/conversation/<uuid:conversation_id>/', views.A2AConversationStatusView.as_view(), name='a2a_conversation_status'),
    
    # Generic webhook endpoints
    path('webhook/status-update/', views.webhook_status_update, name='webhook_status_update'),
    
    # Demo payment display
    path('stripe/payment-agent-sdk/<str:invoice_id>/', views.DemoPaymentDisplayHTMLView.as_view(), name='demo_payment_display'),
    
    # Pre-mandate approval flow
    path('pre-mandate-approval/<str:invoice_id>/', views.PreMandateApprovalView.as_view(), name='pre_mandate_approval'),
    path('pre-mandate-decision/', views.PreMandateDecisionView.as_view(), name='pre_mandate_decision'),
    path('proceed-with-payment/', views.ProceedWithPaymentView.as_view(), name='proceed_with_payment'),
]
