"""
Example usage of the logging system in MindSpace
This file demonstrates how to integrate logging throughout your application
"""

# ============================================================================
# Example 1: In models.py
# ============================================================================
from django.db import models
from logging_config import log_change, log_error

class UserProfile(models.Model):
    user = models.OneToOneField('auth.User', on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    
    def save(self, *args, **kwargs):
        is_new = self.pk is None
        super().save(*args, **kwargs)
        
        if is_new:
            log_change('models.UserProfile', 'CREATE', f'Created profile for user: {self.user.username}')
        else:
            log_change('models.UserProfile', 'UPDATE', f'Updated profile for user: {self.user.username}')


# ============================================================================
# Example 2: In views.py
# ============================================================================
from django.shortcuts import render, redirect
from django.views.decorators.http import require_http_methods
from logging_config import log_change, log_error, log_warning

@require_http_methods(["POST"])
def create_assessment(request):
    try:
        # ... your code to create assessment ...
        assessment = Assessment.objects.create(
            user=request.user,
            title=request.POST.get('title')
        )
        log_change('views.assessments', 'CREATE_ASSESSMENT', f'User {request.user.username} created assessment: {assessment.title}')
        return redirect('assessment_detail', pk=assessment.pk)
    
    except Exception as e:
        log_error('views.assessments', f'Failed to create assessment for user {request.user.username}', exception=e)
        log_warning('views.assessments', f'User {request.user.username} encountered an error')
        return render(request, 'error.html', {'error': 'Failed to create assessment'})


# ============================================================================
# Example 3: In management commands
# ============================================================================
from django.core.management.base import BaseCommand
from logging_config import log_change, log_error

class Command(BaseCommand):
    help = 'Process pending user signups'
    
    def handle(self, *args, **options):
        try:
            pending = PendingSignup.objects.filter(processed=False)
            count = pending.count()
            
            for signup in pending:
                signup.process()
            
            log_change('management', 'PROCESS_SIGNUPS', f'Processed {count} pending signups')
            self.stdout.write(self.style.SUCCESS(f'✓ Processed {count} signups'))
        
        except Exception as e:
            log_error('management', 'Failed to process signups', exception=e)
            self.stdout.write(self.style.ERROR('✗ Error processing signups'))


# ============================================================================
# Example 4: In middleware
# ============================================================================
from logging_config import log_change, log_warning

class AuditMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
    
    def __call__(self, request):
        response = self.get_response(request)
        
        # Log admin actions
        if request.user.is_staff and request.method in ['POST', 'PUT', 'DELETE']:
            log_change(
                'admin_action',
                request.method,
                f'Admin {request.user.username} performed {request.method} on {request.path}'
            )
        
        # Log login attempts
        if 'login' in request.path and request.method == 'POST':
            log_change('security', 'LOGIN_ATTEMPT', f'Login attempt from {request.user}')
        
        return response


# ============================================================================
# Example 5: Standalone utility function
# ============================================================================
from logging_config import log_change, log_error, log_debug

def export_user_data(user):
    """Export all user data for GDPR compliance"""
    try:
        log_debug('export', f'Starting data export for user: {user.username}')
        
        # ... export code ...
        
        log_change('export', 'EXPORT_SUCCESS', f'Successfully exported data for user: {user.username}')
        return True
    
    except Exception as e:
        log_error('export', f'Failed to export data for user: {user.username}', exception=e)
        return False


# ============================================================================
# Example 6: In API views
# ============================================================================
from rest_framework.decorators import api_view
from rest_framework.response import Response
from logging_config import log_change, log_error

@api_view(['POST'])
def api_create_record(request):
    try:
        record = Record.objects.create(
            user=request.user,
            data=request.data
        )
        log_change('api', 'CREATE_RECORD', f'API call created record: {record.id}')
        return Response({'id': record.id}, status=201)
    
    except Exception as e:
        log_error('api', f'Failed to create record via API', exception=e)
        return Response({'error': 'Failed to create record'}, status=400)


# ============================================================================
# Usage Summary
# ============================================================================
"""
QUICK REFERENCE:

1. Import the logging functions:
   from logging_config import log_change, log_error, log_warning, log_debug

2. Log successful actions:
   log_change('module_name', 'ACTION', 'Description')

3. Log errors with exception:
   log_error('module_name', 'Error message', exception=e)

4. Log warnings:
   log_warning('module_name', 'Warning message')

5. Log debug info:
   log_debug('module_name', 'Debug message')

RECOMMENDED MODULE NAMING:
- models.{ModelName}
- views.{ViewName} or views.{app_name}
- api.{endpoint}
- management.{command_name}
- admin_action
- security
- export
- migration
- celery_task

RECOMMENDED ACTIONS:
- CREATE, UPDATE, DELETE
- BUGFIX, FEATURE, REFACTOR
- LOGIN_ATTEMPT, LOGOUT
- ERROR, WARNING
- MIGRATION_RUN
- DATA_EXPORT, DATA_IMPORT
"""
