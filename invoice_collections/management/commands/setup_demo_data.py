"""
Management command to set up demo data for testing and development.
"""

from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from invoice_collections.models import Invoice, AgentAction, CollectionRequest
from payment_processing.models import PaymentMethod, Payment


class Command(BaseCommand):
    help = 'Set up demo data for testing and development'

    def add_arguments(self, parser):
        parser.add_argument(
            '--clear',
            action='store_true',
            help='Clear existing demo data before creating new data',
        )

    def handle(self, *args, **options):
        if options['clear']:
            self.stdout.write('Clearing existing demo data...')
            Invoice.objects.all().delete()
            PaymentMethod.objects.all().delete()
            CollectionRequest.objects.all().delete()

        self.stdout.write('Creating demo data...')

        # Create demo payment methods
        payment_methods = [
            {
                'stripe_payment_method_id': 'pm_demo_card_visa',
                'customer_id': 'acme_corp',
                'customer_name': 'Acme Corporation',
                'type': 'card',
                'last_four': '4242',
                'brand': 'visa',
                'exp_month': 12,
                'exp_year': 2025,
                'mandate_id': 'pm_demo_card_visa',
            },
            {
                'stripe_payment_method_id': 'pm_demo_ach',
                'customer_id': 'tech_startup',
                'customer_name': 'Tech Startup Inc',
                'type': 'ach',
                'bank_name': 'Chase Bank',
                'account_type': 'checking',
                'mandate_id': 'pm_demo_ach',
            },
        ]

        for pm_data in payment_methods:
            payment_method, created = PaymentMethod.objects.get_or_create(
                stripe_payment_method_id=pm_data['stripe_payment_method_id'],
                defaults=pm_data
            )
            if created:
                self.stdout.write(f'Created payment method: {payment_method.customer_name}')

        # Create demo invoices
        demo_invoices = [
            {
                'invoice_id': 'INV-001',
                'sf_invoice_id': 'a1b2c3d4e5f6g7h8',
                'amount_cents': 1023050,  # $10,230.50
                'currency': 'USD',
                'customer_id': 'acme_corp',
                'customer_name': 'Acme Corporation',
                'mandate_id': 'pm_demo_card_visa',
                'payment_method': 'CARD',
                'approved_by': 'finance@acme.com',
                'due_date': timezone.now() + timedelta(days=30),
                'idempotency_key': 'demo_inv_001_20241201_001',
                'status': 'pending',
            },
            {
                'invoice_id': 'INV-002',
                'sf_invoice_id': 'b2c3d4e5f6g7h8i9',
                'amount_cents': 500000,  # $5,000.00
                'currency': 'USD',
                'customer_id': 'tech_startup',
                'customer_name': 'Tech Startup Inc',
                'mandate_id': 'pm_demo_ach',
                'payment_method': 'ACH',
                'approved_by': 'admin@techstartup.com',
                'due_date': timezone.now() + timedelta(days=15),
                'idempotency_key': 'demo_inv_002_20241201_001',
                'status': 'processing',
            },
            {
                'invoice_id': 'INV-003',
                'sf_invoice_id': 'c3d4e5f6g7h8i9j0',
                'amount_cents': 250000,  # $2,500.00
                'currency': 'USD',
                'customer_id': 'acme_corp',
                'customer_name': 'Acme Corporation',
                'mandate_id': 'pm_demo_card_visa',
                'payment_method': 'CARD',
                'approved_by': 'finance@acme.com',
                'due_date': timezone.now() - timedelta(days=5),  # Overdue
                'idempotency_key': 'demo_inv_003_20241201_001',
                'status': 'completed',
            },
        ]

        for invoice_data in demo_invoices:
            invoice, created = Invoice.objects.get_or_create(
                invoice_id=invoice_data['invoice_id'],
                defaults=invoice_data
            )
            if created:
                self.stdout.write(f'Created invoice: {invoice.invoice_id} - {invoice.customer_name}')

                # Create agent action
                AgentAction.objects.create(
                    invoice=invoice,
                    action_type='collection_initiated',
                    decision='auto_process',
                    payload={
                        'invoice_id': invoice_data['invoice_id'],
                        'amount_cents': invoice_data['amount_cents'],
                        'customer_name': invoice_data['customer_name'],
                        'mandate_id': invoice_data['mandate_id'],
                    },
                    human_actor=invoice_data['approved_by'],
                    notes=f'Demo invoice created: {invoice.invoice_id}'
                )

        # Create demo collection request
        collection_request, created = CollectionRequest.objects.get_or_create(
            idempotency_key='demo_collection_001',
            defaults={
                'raw_request_data': {
                    'invoice_id': 'INV-001',
                    'amount': 10230.50,
                    'currency': 'USD',
                    'customer_name': 'Acme Corporation',
                },
                'status': 'completed',
            }
        )

        if created:
            collection_request.invoice = Invoice.objects.get(invoice_id='INV-001')
            collection_request.save()
            self.stdout.write('Created demo collection request')

        self.stdout.write(
            self.style.SUCCESS('Demo data setup completed successfully!')
        )
        self.stdout.write('\nDemo data created:')
        self.stdout.write(f'- {PaymentMethod.objects.count()} payment methods')
        self.stdout.write(f'- {Invoice.objects.count()} invoices')
        self.stdout.write(f'- {AgentAction.objects.count()} agent actions')
        self.stdout.write(f'- {CollectionRequest.objects.count()} collection requests')
