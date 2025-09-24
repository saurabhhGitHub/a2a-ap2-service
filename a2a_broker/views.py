"""
A2A Broker Views

This module handles A2A (Agent-to-Agent) communication using Google A2A SDK
for sub-agent conversations and authorization.
"""

import logging
import json
import uuid
from django.utils import timezone
from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.conf import settings
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework import status

from .models import A2AAgent, A2AConversation, A2AMessage, A2AAuthorization
from .utils import verify_a2a_signature, create_conversation_token, validate_authorization

logger = logging.getLogger(__name__)


@api_view(['POST'])
@authentication_classes([])
@permission_classes([AllowAny])
def a2a_conversation_initiate(request):
    """
    POST /api/v1/a2a/conversations/initiate/
    
    Initiate a new A2A conversation between agents.
    """
    try:
        # Verify A2A signature
        if not verify_a2a_signature(request):
            logger.warning("Invalid A2A signature")
            return Response({
                'error': 'Unauthorized',
                'error_code': 'INVALID_SIGNATURE'
            }, status=status.HTTP_401_UNAUTHORIZED)
        
        # Parse request data
        data = request.data
        
        # Validate required fields
        required_fields = ['initiator_agent_id', 'target_agent_id', 'conversation_type', 'context_data']
        for field in required_fields:
            if field not in data:
                return Response({
                    'error': f'Missing required field: {field}',
                    'error_code': 'MISSING_FIELD'
                }, status=status.HTTP_400_BAD_REQUEST)
        
        # Get agents
        try:
            initiator_agent = A2AAgent.objects.get(agent_id=data['initiator_agent_id'])
            target_agent = A2AAgent.objects.get(agent_id=data['target_agent_id'])
        except A2AAgent.DoesNotExist:
            return Response({
                'error': 'Agent not found',
                'error_code': 'AGENT_NOT_FOUND'
            }, status=status.HTTP_404_NOT_FOUND)
        
        # Check if agents are active
        if initiator_agent.status != 'active' or target_agent.status != 'active':
            return Response({
                'error': 'One or more agents are not active',
                'error_code': 'AGENT_INACTIVE'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Check authorization
        if not validate_authorization(initiator_agent, target_agent, data['conversation_type']):
            return Response({
                'error': 'Insufficient authorization for this conversation type',
                'error_code': 'INSUFFICIENT_AUTHORIZATION'
            }, status=status.HTTP_403_FORBIDDEN)
        
        # Create conversation
        conversation = A2AConversation.objects.create(
            initiator_agent=initiator_agent,
            target_agent=target_agent,
            conversation_type=data['conversation_type'],
            context_data=data['context_data'],
            authorization_token=create_conversation_token(initiator_agent, target_agent),
            expires_at=timezone.now() + timezone.timedelta(hours=1)
        )
        
        # Create initial message
        initial_message = A2AMessage.objects.create(
            conversation=conversation,
            message_type='request',
            sender_agent=initiator_agent,
            payload=data.get('payload', {}),
            signature=create_conversation_token(initiator_agent, target_agent)
        )
        
        # Update conversation status
        conversation.status = 'active'
        conversation.started_at = timezone.now()
        conversation.save()
        
        logger.info(f"A2A conversation initiated: {conversation.conversation_id}")
        
        return Response({
            'conversation_id': str(conversation.conversation_id),
            'authorization_token': conversation.authorization_token,
            'expires_at': conversation.expires_at.isoformat(),
            'message_id': str(initial_message.message_id)
        }, status=status.HTTP_201_CREATED)
        
    except Exception as e:
        logger.error(f"Error initiating A2A conversation: {e}", exc_info=True)
        return Response({
            'error': 'Internal server error',
            'error_code': 'INTERNAL_ERROR'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@authentication_classes([])
@permission_classes([AllowAny])
def a2a_conversation_message(request, conversation_id):
    """
    POST /api/v1/a2a/conversations/{conversation_id}/messages/
    
    Send a message in an A2A conversation.
    """
    try:
        # Verify A2A signature
        if not verify_a2a_signature(request):
            logger.warning("Invalid A2A signature")
            return Response({
                'error': 'Unauthorized',
                'error_code': 'INVALID_SIGNATURE'
            }, status=status.HTTP_401_UNAUTHORIZED)
        
        # Get conversation
        try:
            conversation = A2AConversation.objects.get(conversation_id=conversation_id)
        except A2AConversation.DoesNotExist:
            return Response({
                'error': 'Conversation not found',
                'error_code': 'CONVERSATION_NOT_FOUND'
            }, status=status.HTTP_404_NOT_FOUND)
        
        # Check if conversation is active
        if conversation.status != 'active':
            return Response({
                'error': 'Conversation is not active',
                'error_code': 'CONVERSATION_INACTIVE'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Check if conversation has expired
        if conversation.is_expired():
            conversation.status = 'timeout'
            conversation.save()
            return Response({
                'error': 'Conversation has expired',
                'error_code': 'CONVERSATION_EXPIRED'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Parse request data
        data = request.data
        
        # Get sender agent
        sender_agent_id = data.get('sender_agent_id')
        if not sender_agent_id:
            return Response({
                'error': 'Missing sender_agent_id',
                'error_code': 'MISSING_SENDER'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            sender_agent = A2AAgent.objects.get(agent_id=sender_agent_id)
        except A2AAgent.DoesNotExist:
            return Response({
                'error': 'Sender agent not found',
                'error_code': 'SENDER_NOT_FOUND'
            }, status=status.HTTP_404_NOT_FOUND)
        
        # Verify sender is part of conversation
        if sender_agent not in [conversation.initiator_agent, conversation.target_agent]:
            return Response({
                'error': 'Sender is not part of this conversation',
                'error_code': 'UNAUTHORIZED_SENDER'
            }, status=status.HTTP_403_FORBIDDEN)
        
        # Create message
        message = A2AMessage.objects.create(
            conversation=conversation,
            message_type=data.get('message_type', 'request'),
            sender_agent=sender_agent,
            payload=data.get('payload', {}),
            signature=data.get('signature', '')
        )
        
        # Process message based on type
        if message.message_type == 'response':
            # Mark conversation as completed if this is a final response
            if data.get('final_response', False):
                conversation.status = 'completed'
                conversation.completed_at = timezone.now()
                conversation.result_data = data.get('result_data', {})
                conversation.save()
        
        logger.info(f"A2A message sent: {message.message_id} in conversation {conversation_id}")
        
        return Response({
            'message_id': str(message.message_id),
            'conversation_status': conversation.status,
            'processed': message.processed
        }, status=status.HTTP_201_CREATED)
        
    except Exception as e:
        logger.error(f"Error sending A2A message: {e}", exc_info=True)
        return Response({
            'error': 'Internal server error',
            'error_code': 'INTERNAL_ERROR'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@authentication_classes([])
@permission_classes([AllowAny])
def a2a_conversation_status(request, conversation_id):
    """
    GET /api/v1/a2a/conversations/{conversation_id}/status/
    
    Get the status of an A2A conversation.
    """
    try:
        # Verify A2A signature
        if not verify_a2a_signature(request):
            logger.warning("Invalid A2A signature")
            return Response({
                'error': 'Unauthorized',
                'error_code': 'INVALID_SIGNATURE'
            }, status=status.HTTP_401_UNAUTHORIZED)
        
        # Get conversation
        try:
            conversation = A2AConversation.objects.get(conversation_id=conversation_id)
        except A2AConversation.DoesNotExist:
            return Response({
                'error': 'Conversation not found',
                'error_code': 'CONVERSATION_NOT_FOUND'
            }, status=status.HTTP_404_NOT_FOUND)
        
        # Get messages
        messages = conversation.messages.all().order_by('created_at')
        messages_data = []
        for message in messages:
            messages_data.append({
                'message_id': str(message.message_id),
                'message_type': message.message_type,
                'sender_agent': str(message.sender_agent.agent_id),
                'payload': message.payload,
                'created_at': message.created_at.isoformat(),
                'processed': message.processed
            })
        
        return Response({
            'conversation_id': str(conversation.conversation_id),
            'status': conversation.status,
            'conversation_type': conversation.conversation_type,
            'initiator_agent': str(conversation.initiator_agent.agent_id),
            'target_agent': str(conversation.target_agent.agent_id),
            'created_at': conversation.created_at.isoformat(),
            'started_at': conversation.started_at.isoformat() if conversation.started_at else None,
            'completed_at': conversation.completed_at.isoformat() if conversation.completed_at else None,
            'expires_at': conversation.expires_at.isoformat(),
            'result_data': conversation.result_data,
            'error_message': conversation.error_message,
            'messages': messages_data
        })
        
    except Exception as e:
        logger.error(f"Error getting A2A conversation status: {e}", exc_info=True)
        return Response({
            'error': 'Internal server error',
            'error_code': 'INTERNAL_ERROR'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@authentication_classes([])
@permission_classes([AllowAny])
def a2a_agent_register(request):
    """
    POST /api/v1/a2a/agents/register/
    
    Register a new A2A agent.
    """
    try:
        # Verify A2A signature (DISABLED FOR REGISTRATION - BOOTSTRAP ISSUE)
        # if not verify_a2a_signature(request):
        #     logger.warning("Invalid A2A signature")
        #     return Response({
        #         'error': 'Unauthorized',
        #         'error_code': 'INVALID_SIGNATURE'
        #     }, status=status.HTTP_401_UNAUTHORIZED)
        
        # Parse request data
        data = request.data
        
        # Validate required fields
        required_fields = ['agent_name', 'agent_type', 'a2a_endpoint', 'public_key', 'capabilities']
        for field in required_fields:
            if field not in data:
                return Response({
                    'error': f'Missing required field: {field}',
                    'error_code': 'MISSING_FIELD'
                }, status=status.HTTP_400_BAD_REQUEST)
        
        # Check if agent already exists
        if A2AAgent.objects.filter(agent_name=data['agent_name']).exists():
            return Response({
                'error': 'Agent with this name already exists',
                'error_code': 'AGENT_EXISTS'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Create agent
        agent = A2AAgent.objects.create(
            agent_name=data['agent_name'],
            agent_type=data['agent_type'],
            description=data.get('description', ''),
            a2a_endpoint=data['a2a_endpoint'],
            public_key=data['public_key'],
            capabilities=data['capabilities']
        )
        
        logger.info(f"A2A agent registered: {agent.agent_name} ({agent.agent_id})")
        
        return Response({
            'agent_id': str(agent.agent_id),
            'agent_name': agent.agent_name,
            'status': agent.status,
            'created_at': agent.created_at.isoformat()
        }, status=status.HTTP_201_CREATED)
        
    except Exception as e:
        logger.error(f"Error registering A2A agent: {e}", exc_info=True)
        return Response({
            'error': 'Internal server error',
            'error_code': 'INTERNAL_ERROR'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@authentication_classes([])
@permission_classes([AllowAny])
def a2a_authorization_grant(request):
    """
    POST /api/v1/a2a/authorizations/grant/
    
    Grant authorization between agents.
    """
    try:
        # Verify A2A signature
        if not verify_a2a_signature(request):
            logger.warning("Invalid A2A signature")
            return Response({
                'error': 'Unauthorized',
                'error_code': 'INVALID_SIGNATURE'
            }, status=status.HTTP_401_UNAUTHORIZED)
        
        # Parse request data
        data = request.data
        
        # Validate required fields
        required_fields = ['grantor_agent_id', 'grantee_agent_id', 'permission_type']
        for field in required_fields:
            if field not in data:
                return Response({
                    'error': f'Missing required field: {field}',
                    'error_code': 'MISSING_FIELD'
                }, status=status.HTTP_400_BAD_REQUEST)
        
        # Get agents
        try:
            grantor_agent = A2AAgent.objects.get(agent_id=data['grantor_agent_id'])
            grantee_agent = A2AAgent.objects.get(agent_id=data['grantee_agent_id'])
        except A2AAgent.DoesNotExist:
            return Response({
                'error': 'Agent not found',
                'error_code': 'AGENT_NOT_FOUND'
            }, status=status.HTTP_404_NOT_FOUND)
        
        # Create authorization
        authorization = A2AAuthorization.objects.create(
            grantor_agent=grantor_agent,
            grantee_agent=grantee_agent,
            permission_type=data['permission_type'],
            scope_data=data.get('scope_data', {}),
            max_amount_cents=data.get('max_amount_cents'),
            max_frequency_per_hour=data.get('max_frequency_per_hour'),
            expires_at=timezone.now() + timezone.timedelta(days=30)  # Default 30 days
        )
        
        logger.info(f"A2A authorization granted: {grantor_agent.agent_name} -> {grantee_agent.agent_name}")
        
        return Response({
            'authorization_id': str(authorization.authorization_id),
            'permission_type': authorization.permission_type,
            'status': authorization.status,
            'expires_at': authorization.expires_at.isoformat()
        }, status=status.HTTP_201_CREATED)
        
    except Exception as e:
        logger.error(f"Error granting A2A authorization: {e}", exc_info=True)
        return Response({
            'error': 'Internal server error',
            'error_code': 'INTERNAL_ERROR'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@authentication_classes([])
@permission_classes([AllowAny])
def a2a_agents_list(request):
    """
    GET /api/v1/a2a/agents/
    
    List all registered A2A agents.
    """
    try:
        # Verify A2A signature
        if not verify_a2a_signature(request):
            logger.warning("Invalid A2A signature")
            return Response({
                'error': 'Unauthorized',
                'error_code': 'INVALID_SIGNATURE'
            }, status=status.HTTP_401_UNAUTHORIZED)
        
        # Get agents
        agents = A2AAgent.objects.filter(status='active').order_by('agent_name')
        
        agents_data = []
        for agent in agents:
            agents_data.append({
                'agent_id': str(agent.agent_id),
                'agent_name': agent.agent_name,
                'agent_type': agent.agent_type,
                'description': agent.description,
                'capabilities': agent.capabilities,
                'status': agent.status,
                'last_heartbeat': agent.last_heartbeat.isoformat() if agent.last_heartbeat else None,
                'created_at': agent.created_at.isoformat()
            })
        
        return Response({
            'agents': agents_data,
            'total_count': len(agents_data)
        })
        
    except Exception as e:
        logger.error(f"Error listing A2A agents: {e}", exc_info=True)
        return Response({
            'error': 'Internal server error',
            'error_code': 'INTERNAL_ERROR'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
