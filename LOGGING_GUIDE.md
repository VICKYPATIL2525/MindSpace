# MindSpace Project Change Logger

## Overview
This logging system tracks all changes made to the MindSpace project. All logs are stored in `changes.log` in the root directory of the project.

## Features
- ✓ Timestamps for every logged action
- ✓ Organized by module/component
- ✓ Multiple log levels (DEBUG, INFO, WARNING, ERROR)
- ✓ Automatic log rotation (5MB max per file, keeps 5 backups)
- ✓ Easy-to-use API

## How to Use

### Method 1: Manual Logging via Django Management Command
```bash
# Basic usage
python manage.py log_change models CREATE "Added new User Activity model"

# With additional details
python manage.py log_change views UPDATE --details "Fixed bug in dashboard view - Issue #123"

# Different action types
python manage.py log_change settings UPDATE "Updated ALLOWED_HOSTS"
python manage.py log_change templates MODIFY "Updated navbar styling"
python manage.py log_change static UPDATE "Added new CSS rules for responsive design"
```

### Method 2: Programmatic Logging in Python Code
```python
from logging_config import log_change, log_error, log_warning, log_debug

# Log a change
log_change('models', 'CREATE', 'Added UserProfile model with new fields')

# Log an error
log_error('views', 'Database connection failed', exception=e)

# Log a warning
log_warning('settings', 'Using DEBUG=True in production')

# Log debug info
log_debug('migrations', 'Running migration 0003')
```

### Method 3: Import and Use in Django Views/Models
```python
# In views.py, models.py, or any Django module
from logging_config import log_change

def create_user(request):
    # ... your code ...
    user = User.objects.create(username=request.POST.get('username'))
    log_change('accounts_views', 'CREATE_USER', f'Created user: {user.username}')
    return response
```

## Log File Format
```
2026-05-23 14:51:46 [INFO] mindspace: [models] CREATE - Added new Assessment model
2026-05-23 14:52:10 [INFO] mindspace: [views] UPDATE - Fixed dashboard data aggregation
2026-05-23 14:53:30 [WARNING] mindspace: [settings] WARNING - DEBUG mode enabled
2026-05-23 14:54:15 [ERROR] mindspace: [migrations] ERROR: Migration failed
```

## Log Levels
- **DEBUG**: Detailed information for debugging
- **INFO**: General informational messages (most changes)
- **WARNING**: Warning messages about potential issues
- **ERROR**: Error messages about failures

## Conda Environment
This project uses a conda environment named `mindspace`. To activate:
```bash
conda activate mindspace
```

Then run Django commands:
```bash
python manage.py runserver
python manage.py log_change <module> <action> --details "<details>"
```

## Configuration
The logging configuration is set in `logging_config.py`:
- **Log Location**: `/home/shunya/Documents/MS/changes.log` (root directory)
- **Max File Size**: 5 MB
- **Backup Files**: 5 (automatic rotation)
- **Date Format**: YYYY-MM-DD HH:MM:SS

## Viewing Logs
```bash
# View last 50 lines
tail -50 changes.log

# View last 100 lines in real-time
tail -f -100 changes.log

# Search for specific changes
grep "models" changes.log

# Search for errors
grep "ERROR" changes.log

# View logs from specific date
grep "2026-05-23" changes.log
```

## Integration Points
The logging system is integrated in:
- `logging_config.py` - Core logging configuration
- `mindspace/management/commands/log_change.py` - Django management command
- Ready to be imported in any view, model, or utility file

## Next Steps
1. Import `log_change` in your key files (models.py, views.py, etc.)
2. Log important changes as you make them
3. Review `changes.log` regularly to track project evolution
4. Use `tail -f changes.log` in a terminal to monitor changes in real-time
