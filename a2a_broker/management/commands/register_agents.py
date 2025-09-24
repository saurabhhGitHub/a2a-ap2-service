"""
Management command to register A2A agents.
"""

from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from a2a_broker.models import A2AAgent, A2AAuthorization


class Command(BaseCommand):
    help = 'Register Collection Agent and Payment Agent for A2A communication'

    def handle(self, *args, **options):
        self.stdout.write('Registering A2A agents...')
        
        # Create Collection Agent
        collection_agent, created = A2AAgent.objects.get_or_create(
            agent_name='Collections Agent',
            defaults={
                'agent_type': 'collections_agent',
                'description': 'Handles invoice collection requests and customer communication',
                'a2a_endpoint': 'https://collection-agent-7fb01e4a92ee.herokuapp.com/api/v1/a2a/collections/',
                'public_key': 'collections-agent-public-key-demo',
                'capabilities': [
                    'invoice_processing',
                    'customer_communication',
                    'mandate_verification',
                    'payment_initiation'
                ],
                'status': 'active',
                'last_heartbeat': timezone.now()
            }
        )
        
        if created:
            self.stdout.write(
                self.style.SUCCESS(f'Created Collections Agent: {collection_agent.agent_id}')
            )
        else:
            self.stdout.write(
                self.style.WARNING(f'Collections Agent already exists: {collection_agent.agent_id}')
            )
        
        # Create Payment Agent
        payment_agent, created = A2AAgent.objects.get_or_create(
            agent_name='Payment Agent',
            defaults={
                'agent_type': 'payment_agent',
                'description': 'Handles payment processing via Stripe and other processors',
                'a2a_endpoint': 'https://collection-agent-7fb01e4a92ee.herokuapp.com/api/v1/a2a/payments/',
                'public_key': 'payment-agent-public-key-demo',
                'capabilities': [
                    'payment_processing',
                    'stripe_integration',
                    'mandate_processing',
                    'transaction_verification'
                ],
                'status': 'active',
                'last_heartbeat': timezone.now()
            }
        )
        
        if created:
            self.stdout.write(
                self.style.SUCCESS(f'Created Payment Agent: {payment_agent.agent_id}')
            )
        else:
            self.stdout.write(
                self.style.WARNING(f'Payment Agent already exists: {payment_agent.agent_id}')
            )
        
        # Create authorization for Collections Agent to initiate payments
        auth, created = A2AAuthorization.objects.get_or_create(
            grantor_agent=collection_agent,
            grantee_agent=payment_agent,
            permission_type='payment_initiate',
            defaults={
                'status': 'active',
                'scope_data': {
                    'max_amount_cents': 10000000,  # $100,000
                    'allowed_currencies': ['USD', 'EUR', 'GBP'],
                    'allowed_payment_methods': ['ACH', 'CARD', 'WIRE']
                },
                'max_amount_cents': 10000000,
                'max_frequency_per_hour': 100,
                'expires_at': timezone.now() + timedelta(days=365)  # 1 year
            }
        )
        
        if created:
            self.stdout.write(
                self.style.SUCCESS(f'Created authorization: Collections Agent -> Payment Agent (payment_initiate)')
            )
        else:
            self.stdout.write(
                self.style.WARNING(f'Authorization already exists: Collections Agent -> Payment Agent (payment_initiate)')
            )
        
        # Create authorization for Payment Agent to access customer data
        auth2, created = A2AAuthorization.objects.get_or_create(
            grantor_agent=payment_agent,
            grantee_agent=collection_agent,
            permission_type='customer_data_access',
            defaults={
                'status': 'active',
                'scope_data': {
                    'allowed_data_types': ['customer_id', 'customer_name', 'invoice_amount', 'mandate_id'],
                    'purpose': 'payment_processing'
                },
                'expires_at': timezone.now() + timedelta(days=365)  # 1 year
            }
        )
        
        if created:
            self.stdout.write(
                self.style.SUCCESS(f'Created authorization: Payment Agent -> Collections Agent (customer_data_access)')
            )
        else:
            self.stdout.write(
                self.style.WARNING(f'Authorization already exists: Payment Agent -> Collections Agent (customer_data_access)')
            )
        
        self.stdout.write(
            self.style.SUCCESS('\n✅ A2A agents registration completed successfully!')
        )
        
        # Display summary
        self.stdout.write('\n📋 Registered Agents:')
        for agent in A2AAgent.objects.all():
            self.stdout.write(f'  • {agent.agent_name} ({agent.agent_type}) - {agent.status}')
        
        self.stdout.write('\n🔐 Active Authorizations:')
        for auth in A2AAuthorization.objects.filter(status='active'):
            self.stdout.write(f'  • {auth.grantor_agent.agent_name} -> {auth.grantee_agent.agent_name} ({auth.permission_type})')
