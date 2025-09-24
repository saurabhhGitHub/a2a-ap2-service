"""
A2A Broker URLs

URL patterns for A2A broker endpoints.
"""

from django.urls import path
from . import views

app_name = 'a2a_broker'

urlpatterns = [
    # A2A Conversations
    path('conversations/initiate/', views.a2a_conversation_initiate, name='a2a_conversation_initiate'),
    path('conversations/<uuid:conversation_id>/messages/', views.a2a_conversation_message, name='a2a_conversation_message'),
    path('conversations/<uuid:conversation_id>/status/', views.a2a_conversation_status, name='a2a_conversation_status'),
    
    # A2A Agents
    path('agents/register/', views.a2a_agent_register, name='a2a_agent_register'),
    path('agents/', views.a2a_agents_list, name='a2a_agents_list'),
    
    # A2A Authorizations
    path('authorizations/grant/', views.a2a_authorization_grant, name='a2a_authorization_grant'),
]
