from django.core.management.base import BaseCommand
from logging_config import log_change, log_error
import sys

class Command(BaseCommand):
    help = 'Log a manual change/action to the changes.log file'
    
    def add_arguments(self, parser):
        parser.add_argument(
            'module',
            type=str,
            help='Module/area where change occurred (e.g., models, views, settings)'
        )
        parser.add_argument(
            'action',
            type=str,
            help='Type of action (e.g., CREATE, UPDATE, DELETE, FIX, FEATURE)'
        )
        parser.add_argument(
            '--details',
            type=str,
            default='',
            help='Additional details about the change'
        )
    
    def handle(self, *args, **options):
        module = options['module']
        action = options['action']
        details = options.get('details', '')
        
        try:
            log_change(module, action, details)
            self.stdout.write(
                self.style.SUCCESS(
                    f'✓ Logged: [{module}] {action}' + 
                    (f' - {details}' if details else '')
                )
            )
        except Exception as e:
            log_error('management_command', str(e), e)
            self.stdout.write(self.style.ERROR(f'✗ Error logging change: {str(e)}'))
            sys.exit(1)
