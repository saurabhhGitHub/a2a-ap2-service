"""
Production Demo Setup Script

This script sets up the initial demo data for a production-ready environment.
It creates A2A agents, authorizations, and payment processors.
"""

import os
import sys
import django
from datetime import datetime, timedelta

# Add the project root to the Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Set up Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'collections_agent.settings')
django.setup()

from django.utils import timezone
from a2a_broker.models import A2AAgent, A2AAuthorization
from payment_agent.models import PaymentProcessor
from invoice_collections.models import Invoice


def setup_a2a_agents():
    """Set up A2A agents for the demo."""
    print("Setting up A2A agents...")
    
    # Collections Agent
    collections_agent, created = A2AAgent.objects.get_or_create(
        agent_name='Collections Agent',
        defaults={
            'agent_type': 'collections_agent',
            'status': 'active',
            'capabilities': ['invoice_processing', 'customer_communication', 'payment_initiation'],
            'a2a_endpoint': 'https://collections-agent.example.com/api/v1/',
            'public_key': 'collections-agent-public-key',
            'description': 'Main collections processing agent'
        }
    )
    
    if created:
        print(f"✓ Created Collections Agent: {collections_agent.agent_id}")
    else:
        print(f"✓ Collections Agent already exists: {collections_agent.agent_id}")
    
    # Payment Agent
    payment_agent, created = A2AAgent.objects.get_or_create(
        agent_name='Payment Processing Agent',
        defaults={
            'agent_type': 'payment_agent',
            'status': 'active',
            'capabilities': ['payment_processing', 'settlement', 'fraud_detection'],
            'a2a_endpoint': 'https://payment-agent.example.com/api/v1/',
            'public_key': 'payment-agent-public-key',
            'description': 'Payment processing and settlement agent'
        }
    )
    
    if created:
        print(f"✓ Created Payment Agent: {payment_agent.agent_id}")
    else:
        print(f"✓ Payment Agent already exists: {payment_agent.agent_id}")
    
    return collections_agent, payment_agent


def setup_a2a_authorization(collections_agent, payment_agent):
    """Set up A2A authorization between agents."""
    print("Setting up A2A authorization...")
    
    authorization, created = A2AAuthorization.objects.get_or_create(
        grantor_agent=collections_agent,
        grantee_agent=payment_agent,
        defaults={
            'permission_type': 'payment_initiate',
            'status': 'active',
            'expires_at': timezone.now() + timedelta(days=365),  # 1 year
            'max_amount_cents': 10000000,  # $100,000 max
            'max_frequency_per_hour': 100,
            'scope_data': {
                'description': 'Collections agent can initiate payments via payment agent',
                'created_by': 'system',
                'risk_level': 'low'
            }
        }
    )
    
    if created:
        print(f"✓ Created A2A Authorization: {collections_agent.agent_id} -> {payment_agent.agent_id}")
    else:
        print(f"✓ A2A Authorization already exists: {collections_agent.agent_id} -> {payment_agent.agent_id}")
    
    return authorization


def setup_payment_processors():
    """Set up payment processors for the demo."""
    print("Setting up payment processors...")
    
    # Stripe Processor
    stripe_processor, created = PaymentProcessor.objects.get_or_create(
        processor_name='Stripe Payment Processor',
        defaults={
            'processor_type': 'stripe',
            'status': 'active',
            'api_endpoint': 'https://api.stripe.com/v1',
            'webhook_endpoint': 'https://your-domain.com/webhooks/stripe/',
            'api_key': 'sk_test_stripe_demo_key',
            'secret_key': 'whsec_stripe_demo_secret',
            'supported_methods': ['card', 'ach'],
            'supported_currencies': ['USD', 'EUR', 'GBP'],
            'description': 'Stripe payment processor for demo'
        }
    )
    
    if created:
        print(f"✓ Created Stripe Processor: {stripe_processor.processor_id}")
    else:
        print(f"✓ Stripe Processor already exists: {stripe_processor.processor_id}")
    
    # Adyen Processor
    adyen_processor, created = PaymentProcessor.objects.get_or_create(
        processor_name='Adyen Payment Processor',
        defaults={
            'processor_type': 'adyen',
            'status': 'active',
            'api_endpoint': 'https://checkout-test.adyen.com/v1',
            'webhook_endpoint': 'https://your-domain.com/webhooks/adyen/',
            'api_key': 'AQEyhmfxLI3JaBVDw0m/n3Q5qf3VaY9UCJ1+XWZe9W27jmlZin4w4V4M+J8wv0qkGNZ8/y0lw9J2k5c2v5m9k8==',
            'secret_key': 'DemoMerchant',
            'supported_methods': ['card', 'ach', 'wire'],
            'supported_currencies': ['USD', 'EUR', 'GBP'],
            'description': 'Adyen payment processor for demo'
        }
    )
    
    if created:
        print(f"✓ Created Adyen Processor: {adyen_processor.processor_id}")
    else:
        print(f"✓ Adyen Processor already exists: {adyen_processor.processor_id}")
    
    return stripe_processor, adyen_processor


def setup_demo_invoices():
    """Set up demo invoices for testing."""
    print("Setting up demo invoices...")
    
    demo_invoices = [
        {
            'invoice_id': 'INV-2024-001',
            'external_invoice_id': 'SF-INV-001',
            'amount_cents': 50000,  # $500.00
            'currency': 'USD',
            'customer_id': 'CUST-001',
            'customer_name': 'Acme Corporation',
            'mandate_id': 'MANDATE-001',
            'payment_method': 'ACH',
            'due_date': timezone.now() + timedelta(days=30),
            'status': 'pending',
            'idempotency_key': 'demo-inv-001'
        },
        {
            'invoice_id': 'INV-2024-002',
            'external_invoice_id': 'SF-INV-002',
            'amount_cents': 75000,  # $750.00
            'currency': 'USD',
            'customer_id': 'CUST-002',
            'customer_name': 'TechStart Inc',
            'mandate_id': 'MANDATE-002',
            'payment_method': 'CARD',
            'due_date': timezone.now() + timedelta(days=15),
            'status': 'pending',
            'idempotency_key': 'demo-inv-002'
        },
        {
            'invoice_id': 'INV-2024-003',
            'external_invoice_id': 'SF-INV-003',
            'amount_cents': 100000,  # $1000.00
            'currency': 'USD',
            'customer_id': 'CUST-003',
            'customer_name': 'Global Solutions Ltd',
            'mandate_id': 'MANDATE-003',
            'payment_method': 'ACH',
            'due_date': timezone.now() + timedelta(days=45),
            'status': 'pending',
            'idempotency_key': 'demo-inv-003'
        }
    ]
    
    created_count = 0
    for invoice_data in demo_invoices:
        invoice, created = Invoice.objects.get_or_create(
            invoice_id=invoice_data['invoice_id'],
            defaults=invoice_data
        )
        if created:
            created_count += 1
            print(f"✓ Created demo invoice: {invoice.invoice_id}")
    
    if created_count == 0:
        print("✓ Demo invoices already exist")
    else:
        print(f"✓ Created {created_count} demo invoices")


def setup_production_demo():
    """Main setup function for production demo."""
    print("🚀 Setting up Production Demo Environment...")
    print("=" * 50)
    
    try:
        # Set up A2A agents
        collections_agent, payment_agent = setup_a2a_agents()
        
        # Set up A2A authorization
        setup_a2a_authorization(collections_agent, payment_agent)
        
        # Set up payment processors
        setup_payment_processors()
        
        # Set up demo invoices
        setup_demo_invoices()
        
        print("=" * 50)
        print("✅ Production Demo Setup Complete!")
        print("\n📋 Summary:")
        print(f"   • A2A Agents: 2 (Collections + Payment)")
        print(f"   • A2A Authorizations: 1")
        print(f"   • Payment Processors: 2 (Stripe + Adyen)")
        print(f"   • Demo Invoices: 3")
        print("\n🔗 Available Endpoints:")
        print("   • Salesforce Webhook: /api/v1/integration/salesforce/webhook/")
        print("   • A2A Broker: /api/v1/a2a/")
        print("   • AP2 Payment: /api/v1/ap2/")
        print("   • Invoice Collections: /api/v1/invoices/")
        print("\n🎯 Ready for hackathon demo!")
        
    except Exception as e:
        print(f"❌ Error during setup: {e}")
        raise


if __name__ == '__main__':
    setup_production_demo()
