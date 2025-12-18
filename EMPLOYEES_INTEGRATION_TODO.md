# Employees App Integration - TODO & Migration Guide

## Summary
Created a unified `employees` app that centralizes employee management across all applications (tracker, planner, and future apps). This provides a single source of truth for personnel data.

## Completed Changes

### 1. Created `employees` App
- ✅ Unified Employee model with designations: Engineer, Team Lead, Manager
- ✅ Links to tracker.Pace via `tracker_pace` OneToOneField
- ✅ Additional fields for future HR features: email, phone, join_date
- ✅ Auto-sync signals to create/update employees when tracker.Pace changes
- ✅ Comprehensive admin interface with import/export capabilities

### 2. Updated `planner` App
- ✅ Removed local Employee model
- ✅ Updated all references to use `employees.Employee`
- ✅ Updated Leave model to reference `employees.Employee`
- ✅ Updated signals to use `employees.Employee`
- ✅ Updated admin to remove Employee registration (now in employees app)

## Migration Steps Required

### 1. Add 'employees' to INSTALLED_APPS
In `settings.py`, add:
```python
INSTALLED_APPS = [
    ...
    'employees',  # Add this
    'tracker',
    'planner',
    ...
]
```

### 2. Run Migrations
```bash
# Create migrations for new employees app
python manage.py makemigrations employees

# Create migrations for updated planner models
python manage.py makemigrations planner

# Review the migration files before applying
# Check for any data migration needs

# Apply migrations
python manage.py migrate employees
python manage.py migrate planner
```

### 3. Data Migration (if needed)
If you have existing data in `planner.Employee`, you may need to:

```python
# Create a data migration to copy planner.Employee to employees.Employee
# Then update foreign keys in planner models
# Finally, remove old planner.Employee table
```

## Future Tracker Changes (When Safe to Modify)

### Option 1: Reference employees.Employee directly (Recommended)
Update `tracker.models.Project` to use `employees.Employee` instead of maintaining separate Pace model:

```python
# In tracker/models.py
from employees.models import Employee

class Project(models.Model):
    ...
    # Replace pace field with direct Employee reference
    team_lead = models.ForeignKey(
        'employees.Employee',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        limit_choices_to={'designation': 'TEAM_LEAD'},
        related_name='tracker_projects'
    )
```

### Option 2: Keep Pace but improve sync (Current approach)
- Keep tracker.Pace as is
- Employees.Employee auto-syncs with Pace via signals
- No changes to tracker (backward compatible)

## Benefits of Unified Employee Model

1. **Single Source of Truth**: One model for all employee data
2. **Reusability**: Can be used by tracker, planner, and future apps
3. **Extensibility**: Easy to add HR features (performance reviews, payroll, etc.)
4. **Consistency**: No data duplication or sync issues
5. **Maintainability**: Changes to employee structure only in one place

## Future Enhancements

### Potential Employee App Features:
- [ ] Performance reviews
- [ ] Attendance tracking
- [ ] Payroll integration
- [ ] Skills/certifications tracking
- [ ] Department/team management
- [ ] Reporting hierarchy
- [ ] Document management (contracts, certifications)
- [ ] Leave balance and approval workflow

### API Endpoints:
- [ ] Employee CRUD operations
- [ ] Search and filter employees
- [ ] Bulk import/export
- [ ] Leave management API
- [ ] Capacity/availability API

## Notes

- **Tracker is live**: No changes made to tracker app to avoid disruption
- **Backward compatible**: All existing functionality preserved
- **Auto-sync**: Employees auto-created when Pace records are created
- **Manual linking**: Admin can manually link existing employees to Pace records

## Testing Checklist

After migration, verify:
- [ ] Existing planner projects display team leads correctly
- [ ] Existing activities display assignees correctly
- [ ] Leave records are accessible and functional
- [ ] New tracker.Pace records auto-create employees
- [ ] Capacity settings work with employee designations
- [ ] Admin interfaces for all models work correctly
- [ ] Import/export functionality works
- [ ] Filtering and searching work in admin

## Rollback Plan

If issues arise:
1. Keep backup of database before migration
2. Migrations can be reversed: `python manage.py migrate planner <previous_migration>`
3. Restore employees app configuration
4. Restore original planner.Employee model if needed

---

**Created**: 2025-12-18
**Status**: Ready for migration
**Contact**: System Administrator
