"""
Management command to register payment processors.
"""

from django.core.management.base import BaseCommand
from django.utils import timezone
from payment_agent.models import PaymentProcessor


class Command(BaseCommand):
    help = 'Register payment processors for AP2 payment processing'

    def handle(self, *args, **options):
        self.stdout.write('Registering payment processors...')
        
        # Create Stripe processor
        stripe_processor, created = PaymentProcessor.objects.get_or_create(
            processor_name='Stripe Demo',
            defaults={
                'processor_type': 'stripe',
                'description': 'Stripe payment processor for demo purposes',
                'api_endpoint': 'https://api.stripe.com/v1/',
                'webhook_endpoint': 'https://collection-agent-7fb01e4a92ee.herokuapp.com/api/v1/payment-processing/stripe/webhook/',
                'api_key': 'sk_test_demo_key',
                'secret_key': 'sk_test_demo_secret',
                'supported_methods': ['ach', 'card', 'sepa'],
                'supported_currencies': ['USD', 'EUR', 'GBP'],
                'status': 'active',
                'last_health_check': timezone.now()
            }
        )
        
        if created:
            self.stdout.write(
                self.style.SUCCESS(f'Created Stripe processor: {stripe_processor.processor_id}')
            )
        else:
            self.stdout.write(
                self.style.WARNING(f'Stripe processor already exists: {stripe_processor.processor_id}')
            )
        
        # Create Adyen processor
        adyen_processor, created = PaymentProcessor.objects.get_or_create(
            processor_name='Adyen Demo',
            defaults={
                'processor_type': 'adyen',
                'description': 'Adyen payment processor for demo purposes',
                'api_endpoint': 'https://checkout-test.adyen.com/v1/',
                'webhook_endpoint': 'https://collection-agent-7fb01e4a92ee.herokuapp.com/api/v1/payment-processing/adyen/webhook/',
                'api_key': 'adyen_demo_key',
                'secret_key': 'adyen_demo_secret',
                'supported_methods': ['ach', 'card', 'sepa', 'bacs'],
                'supported_currencies': ['USD', 'EUR', 'GBP', 'CAD'],
                'status': 'active',
                'last_health_check': timezone.now()
            }
        )
        
        if created:
            self.stdout.write(
                self.style.SUCCESS(f'Created Adyen processor: {adyen_processor.processor_id}')
            )
        else:
            self.stdout.write(
                self.style.WARNING(f'Adyen processor already exists: {adyen_processor.processor_id}')
            )
        
        self.stdout.write(
            self.style.SUCCESS('\n✅ Payment processors registration completed successfully!')
        )
        
        # Display summary
        self.stdout.write('\n💳 Registered Processors:')
        for processor in PaymentProcessor.objects.all():
            self.stdout.write(f'  • {processor.processor_name} ({processor.processor_type}) - {processor.status}')
            self.stdout.write(f'    Methods: {", ".join(processor.supported_methods)}')
            self.stdout.write(f'    Currencies: {", ".join(processor.supported_currencies)}')
