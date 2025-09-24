"""
A2A and AP2 Integration Module

This module handles the integration between A2A (Agent-to-Agent) communication
and AP2 (Account-to-Account Payment Protocol) for the collections agent backend.
"""

import logging
import uuid
from datetime import timedelta
from django.utils import timezone
from django.conf import settings

from a2a_broker.models import A2AAgent, A2AConversation, A2AMessage, A2AAuthorization
from a2a_broker.utils import validate_authorization, create_conversation_token
from payment_agent.models import PaymentProcessor, AP2PaymentRequest
from invoice_collections.models import Invoice

logger = logging.getLogger(__name__)


def create_payment_request_id():
    """Generate a unique payment request ID."""
    return f"ap2_{uuid.uuid4().hex[:16]}"


def process_collection_with_a2a_ap2(validated_data):
    """
    Process collection request using A2A and AP2 protocols.
    This is the core hackathon demo flow.
    """
    
    try:
        logger.info("🚀 Starting A2A/AP2 payment processing flow")
        logger.info(f"📋 Invoice: {validated_data['invoice_id']} | Amount: ${validated_data['amount']} | Method: {validated_data['payment_method']}")
        
        # Step 1: Get A2A Agents
        logger.info("🔍 Step 1: Locating A2A agents...")
        collections_agent = A2AAgent.objects.filter(
            agent_type='collections_agent',
            status='active'
        ).first()
        
        payment_agent = A2AAgent.objects.filter(
            agent_type='payment_agent', 
            status='active'
        ).first()
        
        if not collections_agent or not payment_agent:
            logger.error("❌ A2A agents not found")
            return {
                'success': False,
                'error': 'A2A agents not found. Please register agents first.'
            }
        
        logger.info(f"✅ Collections Agent found: {collections_agent.agent_name} ({collections_agent.agent_id})")
        logger.info(f"✅ Payment Agent found: {payment_agent.agent_name} ({payment_agent.agent_id})")
        
        # Step 2: Validate A2A Authorization
        logger.info("🔐 Step 2: Validating A2A authorization...")
        if not validate_authorization(collections_agent, payment_agent, 'payment_initiate'):
            logger.error("❌ Insufficient A2A authorization for payment initiation")
            return {
                'success': False,
                'error': 'Insufficient A2A authorization for payment initiation'
            }
        logger.info("✅ A2A authorization validated - Collections Agent can initiate payments")
        
        # Step 3: Initiate A2A Conversation
        logger.info("💬 Step 3: Initiating A2A conversation...")
        conversation = A2AConversation.objects.create(
            initiator_agent=collections_agent,
            target_agent=payment_agent,
            conversation_type='payment_initiation',
            context_data={
                'invoice_id': validated_data['invoice_id'],
                'amount_cents': int(validated_data['amount'] * 100),
                'currency': validated_data['currency'],
                'customer_id': validated_data['customer_id'],
                'customer_name': validated_data['customer_name'],
                'mandate_id': validated_data['mandate_id'],
                'payment_method': validated_data['payment_method']
            },
            authorization_token=create_conversation_token(collections_agent, payment_agent),
            expires_at=timezone.now() + timezone.timedelta(hours=1),
            status='active',
            started_at=timezone.now()
        )
        logger.info(f"✅ A2A conversation initiated: {conversation.conversation_id}")
        logger.info(f"   📤 From: {collections_agent.agent_name} → 📥 To: {payment_agent.agent_name}")
        logger.info(f"   🎯 Type: {conversation.conversation_type}")
        logger.info(f"   ⏰ Expires: {conversation.expires_at}")
        
        # Create initial message
        logger.info("📨 Creating A2A request message...")
        request_message = A2AMessage.objects.create(
            conversation=conversation,
            message_type='request',
            sender_agent=collections_agent,
            payload={
                'action': 'initiate_payment',
                'invoice_id': validated_data['invoice_id'],
                'amount_cents': int(validated_data['amount'] * 100),
                'payment_method': validated_data['payment_method']
            },
            signature=create_conversation_token(collections_agent, payment_agent)
        )
        logger.info(f"✅ A2A request message sent: {request_message.message_id}")
        logger.info(f"   📋 Payload: {request_message.payload}")
        
        # Step 4: AP2 Payment Processing
        logger.info("💳 Step 4: Starting AP2 payment processing...")
        logger.info(f"🔍 Looking for processor supporting {validated_data['payment_method']} in {validated_data['currency']}")
        processor = PaymentProcessor.objects.filter(
            supported_methods__contains=[validated_data['payment_method'].lower()],
            supported_currencies__contains=[validated_data['currency'].upper()],
            status='active'
        ).first()
        
        if not processor:
            logger.error("❌ No active payment processor found")
            return {
                'success': False,
                'error': 'No active payment processor found'
            }
        
        logger.info(f"✅ Payment processor found: {processor.processor_name} ({processor.processor_type})")
        logger.info(f"   🏦 Endpoint: {processor.api_endpoint}")
        logger.info(f"   💰 Supported methods: {', '.join(processor.supported_methods)}")
        logger.info(f"   🌍 Supported currencies: {', '.join(processor.supported_currencies)}")
        
        # Get or create invoice for AP2 payment request
        logger.info("📄 Setting up invoice for AP2 payment...")
        invoice = Invoice.objects.filter(invoice_id=validated_data['invoice_id']).first()
        
        if not invoice:
            logger.info("📝 Creating new invoice record...")
            # Create invoice if it doesn't exist
            invoice = Invoice.objects.create(
                invoice_id=validated_data['invoice_id'],
                external_invoice_id=validated_data.get('sf_invoice_id', validated_data['invoice_id']),
                amount_cents=int(validated_data['amount'] * 100),
                currency=validated_data['currency'],
                customer_id=validated_data['customer_id'],
                customer_name=validated_data['customer_name'],
                mandate_id=validated_data['mandate_id'],
                payment_method=validated_data['payment_method'],
                due_date=validated_data.get('due_date', timezone.now()),
                status='processing'
            )
            logger.info(f"✅ Invoice created: {invoice.invoice_id}")
        else:
            logger.info(f"✅ Using existing invoice: {invoice.invoice_id}")
        
        # Create AP2 payment request
        logger.info("🔄 Creating AP2 payment request...")
        ap2_request_id = create_payment_request_id()
        ap2_request = AP2PaymentRequest.objects.create(
            invoice=invoice,
            processor=processor,
            ap2_request_id=ap2_request_id,
            mandate_id=validated_data['mandate_id'],
            payment_method=validated_data['payment_method'].lower(),
            amount_cents=int(validated_data['amount'] * 100),
            currency=validated_data['currency'],
            description=f"Demo payment for {validated_data['customer_name']}",
            idempotency_key=f"a2a_{conversation.conversation_id}_{int(timezone.now().timestamp())}",
            context_data={
                'conversation_id': str(conversation.conversation_id),
                'customer_id': validated_data['customer_id'],
                'customer_name': validated_data['customer_name'],
                'demo_mode': True
            }
        )
        logger.info(f"✅ AP2 payment request created: {ap2_request.ap2_request_id}")
        logger.info(f"   💰 Amount: ${validated_data['amount']} {validated_data['currency']}")
        logger.info(f"   🏦 Processor: {processor.processor_name}")
        logger.info(f"   🔑 Mandate ID: {validated_data['mandate_id']}")
        
        # Process payment (demo mode - simulate success)
        logger.info("⚡ Step 5: Processing payment with AP2...")
        if validated_data['payment_method'].upper() == 'ACH':
            logger.info("🏦 Processing ACH payment (instant settlement simulation)...")
            # Simulate ACH payment success
            ap2_request.status = 'settled'
            ap2_request.external_transaction_id = f"txn_ach_{ap2_request.ap2_request_id}"
            ap2_request.settled_at = timezone.now()
            ap2_request.processed_at = timezone.now()
            ap2_request.save()
            
            message = "Payment settled successfully via ACH."
            status_result = "settled"
            logger.info(f"✅ ACH payment settled instantly: {ap2_request.external_transaction_id}")
        else:
            logger.info("💳 Processing card payment (processing simulation)...")
            # Simulate card payment processing
            ap2_request.status = 'processing'
            ap2_request.external_transaction_id = f"txn_card_{ap2_request.ap2_request_id}"
            ap2_request.processed_at = timezone.now()
            ap2_request.save()
            
            message = "Payment initiated and processing via card."
            status_result = "processing"
            logger.info(f"⏳ Card payment processing: {ap2_request.external_transaction_id}")
        
        logger.info(f"✅ AP2 payment processed: {ap2_request.ap2_request_id} → Status: {ap2_request.status}")
        logger.info(f"   🆔 Transaction ID: {ap2_request.external_transaction_id}")
        logger.info(f"   ⏰ Processed at: {ap2_request.processed_at}")
        
        # Step 6: Send A2A Response Message
        logger.info("📤 Step 6: Sending A2A response message...")
        response_message = A2AMessage.objects.create(
            conversation=conversation,
            message_type='response',
            sender_agent=payment_agent,
            payload={
                'status': ap2_request.status,
                'transaction_id': ap2_request.external_transaction_id,
                'ap2_request_id': ap2_request.ap2_request_id,
                'message': message
            },
            signature=create_conversation_token(payment_agent, collections_agent)
        )
        logger.info(f"✅ A2A response message sent: {response_message.message_id}")
        logger.info(f"   📋 Response payload: {response_message.payload}")
        
        # Update A2A conversation status to completed
        logger.info("🏁 Completing A2A conversation...")
        conversation.status = 'completed'
        conversation.completed_at = timezone.now()
        conversation.result_data = {
            'ap2_request_id': ap2_request.ap2_request_id,
            'transaction_id': ap2_request.external_transaction_id,
            'status': ap2_request.status
        }
        conversation.save()
        
        logger.info(f"✅ A2A conversation completed: {conversation.conversation_id}")
        logger.info(f"   🎯 Final status: {conversation.status}")
        logger.info(f"   ⏰ Completed at: {conversation.completed_at}")
        logger.info(f"   📊 Result data: {conversation.result_data}")
        
        logger.info("🎉 A2A/AP2 payment processing flow completed successfully!")
        logger.info("=" * 80)
        
        return {
            'success': True,
            'conversation_id': str(conversation.conversation_id),
            'ap2_request_id': ap2_request.ap2_request_id,
            'transaction_id': ap2_request.external_transaction_id,
            'status': status_result,
            'message': message
        }
        
    except Exception as e:
        logger.error("❌ Error in A2A/AP2 processing flow")
        logger.error(f"   🚨 Error: {e}", exc_info=True)
        logger.error("=" * 80)
        return {
            'success': False,
            'error': str(e)
        }


def get_a2a_conversation_status(conversation_id):
    """
    Get A2A conversation status and messages for demo display.
    """
    try:
        conversation = A2AConversation.objects.get(conversation_id=conversation_id)
        
        # Get all messages in the conversation
        messages = A2AMessage.objects.filter(conversation=conversation).order_by('created_at')
        
        conversation_data = {
            'conversation_id': str(conversation.conversation_id),
            'initiator_agent': {
                'agent_id': conversation.initiator_agent.agent_id,
                'agent_type': conversation.initiator_agent.agent_type,
                'name': conversation.initiator_agent.name
            },
            'target_agent': {
                'agent_id': conversation.target_agent.agent_id,
                'agent_type': conversation.target_agent.agent_type,
                'name': conversation.target_agent.name
            },
            'conversation_type': conversation.conversation_type,
            'status': conversation.status,
            'started_at': conversation.started_at.isoformat() if conversation.started_at else None,
            'completed_at': conversation.completed_at.isoformat() if conversation.completed_at else None,
            'context_data': conversation.context_data,
            'result_data': conversation.result_data,
            'messages': []
        }
        
        for message in messages:
            message_data = {
                'message_id': str(message.message_id),
                'message_type': message.message_type,
                'sender_agent': {
                    'agent_id': message.sender_agent.agent_id,
                    'agent_type': message.sender_agent.agent_type,
                    'name': message.sender_agent.name
                },
                'payload': message.payload,
                'created_at': message.created_at.isoformat(),
                'signature': message.signature
            }
            conversation_data['messages'].append(message_data)
        
        return conversation_data
        
    except A2AConversation.DoesNotExist:
        return {'error': 'Conversation not found'}
    except Exception as e:
        logger.error(f"Error getting A2A conversation status: {e}", exc_info=True)
        return {'error': str(e)}
