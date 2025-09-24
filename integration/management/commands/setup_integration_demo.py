"""
Management command to set up demo data for integration testing.
"""

from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from invoice_collections.models import Invoice, AgentAction
from a2a_broker.models import A2AAgent


class Command(BaseCommand):
    help = 'Set up demo data for integration testing'

    def handle(self, *args, **options):
        self.stdout.write('Setting up integration demo data...')
        
        # Create demo A2A agents
        self.create_demo_agents()
        
        # Create demo invoices
        self.create_demo_invoices()
        
        self.stdout.write(
            self.style.SUCCESS('Successfully set up integration demo data!')
        )

    def create_demo_agents(self):
        """Create demo A2A agents."""
        agents_data = [
            {
                'agent_name': 'salesforce_collections_agent',
                'agent_type': 'collections_agent',
                'description': 'Salesforce Agentforce Collections Agent',
                'a2a_endpoint': 'https://salesforce-agentforce.com/a2a/',
                'public_key': 'demo-public-key-123',
                'capabilities': ['payment_initiation', 'customer_verification']
            },
            {
                'agent_name': 'payment_agent',
                'agent_type': 'payment_agent',
                'description': 'AP2 Payment Processing Agent',
                'a2a_endpoint': 'https://payment-agent.com/a2a/',
                'public_key': 'demo-public-key-456',
                'capabilities': ['payment_processing', 'settlement']
            },
            {
                'agent_name': 'slack_notification_agent',
                'agent_type': 'customer_support_agent',
                'description': 'Slack Notification Agent',
                'a2a_endpoint': 'https://slack-agent.com/a2a/',
                'public_key': 'demo-public-key-789',
                'capabilities': ['notifications', 'approvals']
            }
        ]
        
        for agent_data in agents_data:
            agent, created = A2AAgent.objects.get_or_create(
                agent_name=agent_data['agent_name'],
                defaults=agent_data
            )
            if created:
                self.stdout.write(f'Created A2A agent: {agent.agent_name}')
            else:
                self.stdout.write(f'A2A agent already exists: {agent.agent_name}')

    def create_demo_invoices(self):
        """Create demo invoices for testing."""
        invoices_data = [
            {
                'invoice_id': 'INV-2024-001',
                'external_invoice_id': 'SF-001234',
                'amount_cents': 1023000,  # $10,230.00
                'currency': 'USD',
                'customer_id': 'CUST-001',
                'customer_name': 'Acme Corp',
                'mandate_id': 'mandate_abc123',
                'payment_method': 'ACH',
                'approved_by': 'finance@company.com',
                'due_date': timezone.now() - timedelta(days=10),  # 10 days overdue
                'idempotency_key': 'demo-key-001',
                'status': 'pending'
            },
            {
                'invoice_id': 'INV-2024-002',
                'external_invoice_id': 'SF-001235',
                'amount_cents': 550000,  # $5,500.00
                'currency': 'USD',
                'customer_id': 'CUST-002',
                'customer_name': 'Tech Solutions Inc',
                'mandate_id': 'mandate_def456',
                'payment_method': 'ACH',
                'approved_by': 'finance@company.com',
                'due_date': timezone.now() - timedelta(days=5),  # 5 days overdue
                'idempotency_key': 'demo-key-002',
                'status': 'processing'
            },
            {
                'invoice_id': 'INV-2024-003',
                'external_invoice_id': 'SF-001236',
                'amount_cents': 2500000,  # $25,000.00
                'currency': 'USD',
                'customer_id': 'CUST-003',
                'customer_name': 'Global Enterprises Ltd',
                'mandate_id': 'mandate_ghi789',
                'payment_method': 'ACH',
                'approved_by': 'finance@company.com',
                'due_date': timezone.now() + timedelta(days=5),  # Due in 5 days
                'idempotency_key': 'demo-key-003',
                'status': 'pending'
            }
        ]
        
        for invoice_data in invoices_data:
            invoice, created = Invoice.objects.get_or_create(
                invoice_id=invoice_data['invoice_id'],
                defaults=invoice_data
            )
            if created:
                self.stdout.write(f'Created invoice: {invoice.invoice_id}')
                
                # Create demo agent action
                AgentAction.objects.create(
                    invoice=invoice,
                    action_type='collection_initiated',
                    decision='auto_process',
                    payload={
                        'invoice_id': invoice_data['invoice_id'],
                        'amount_cents': invoice_data['amount_cents'],
                        'customer_name': invoice_data['customer_name'],
                        'payment_method': invoice_data['payment_method']
                    },
                    human_actor=invoice_data['approved_by'],
                    notes=f'Demo collection initiated for invoice {invoice.invoice_id}'
                )
            else:
                self.stdout.write(f'Invoice already exists: {invoice.invoice_id}')
