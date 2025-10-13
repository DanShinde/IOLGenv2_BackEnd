# Inventory Management System - Documentation

## Overview

Simple, practical inventory system for tracking **Tools** and **Materials** with complete location history.

## Key Features

### 1. Item Management
- **Tools**: Individual items with unique serial numbers
  - Can be assigned to users
  - Can be dispatched to projects
  - Must be returned

- **Materials**: Stock-based items
  - Track quantity
  - Once dispatched, they are consumed
  - No return needed

### 2. Location Tracking
Every item has:
- **Current Location**: Where the item is RIGHT NOW
- **Complete History**: Every place the item has been

### 3. Simple Workflows

#### Adding Items
1. Go to "Add Item"
2. Choose type: Tool or Material
3. Fill basic info (name, serial number, location, etc.)
4. Add remarks if needed
5. Save

#### Assigning Tools to Users
1. Go to "Transfer/Assign"
2. Select "Assign Tool to User"
3. Pick available tool OR transfer from another user
4. Choose user to assign to
5. Set expected return date
6. Add notes
7. Submit

**Result**: Tool status becomes "ASSIGNED", location tracked to user

#### Dispatching to Projects

**For Tools:**
1. Select "Dispatch to Project"
2. Choose the tool
3. Enter project name and site location
4. Set expected return date
5. Submit

**Result**: Tool goes to project, can be returned later

**For Materials:**
1. Select "Dispatch to Project"
2. Choose the material
3. Enter quantity to dispatch
4. Enter project name and site location
5. Submit

**Result**:
- Stock is reduced by dispatched quantity
- If stock reaches 0, status becomes "CONSUMED"
- History shows where materials went
- **Materials cannot be returned** - they're consumed at project site

#### Returning Items
Tools can be returned:
- From assignments: Click "Return" button
- From dispatches: Use return function
- Material dispatches are permanent (no return)

## Status Types

- **AVAILABLE**: In warehouse, ready to use
- **ASSIGNED**: With a user (tools only)
- **DISPATCHED**: At a project site
- **CONSUMED**: Material used up (materials only)
- **RETIRED**: No longer in service

## History Tracking

Every action creates a history entry showing:
- What happened
- Who did it
- When it happened
- Where the item was/went
- Details about the action

View history:
- On item detail page: See all movements for that item
- In history page: Filter and search all activities

## Reports

Dashboard shows:
- Total tools and materials
- Current status breakdown
- Recent assignments and dispatches
- Low stock alerts for materials

## Remarks Field

Use the "Remarks" field on any item to add:
- Special notes
- Updates
- Maintenance information
- Anything important about the item

This is your flexible notes area!

## Quick Tips

1. **Tools** = Individual items that come back
2. **Materials** = Consumable items that don't come back
3. Every movement is tracked in History
4. Location field always shows current location
5. Use remarks for any special notes

## Admin Access

Admin panel provides:
- Full CRUD for all items
- Assignment management
- Dispatch management
- History view with filters
- Color-coded status badges

## Database Models

### Item
- Basic info (name, serial, make, model)
- Type (TOOL/MATERIAL)
- Status and location
- Quantity (for materials)
- Remarks
- Purchase info

### Assignment
- Tool assignments to users
- Dates (assigned, expected return, actual return)
- Notes
- Tracks who assigned it

### Dispatch
- Dispatches to projects
- Works for both tools and materials
- Materials are consumed on dispatch
- Tools can be returned

### History
- Complete audit trail
- Every action logged with:
  - Action type
  - User
  - Timestamp
  - Details
  - Location

## Installation & Setup

1. **Apply migrations:**
```bash
python manage.py makemigrations inventory
python manage.py migrate
```

2. **Create superuser (if needed):**
```bash
python manage.py createsuperuser
```

3. **Run server:**
```bash
python manage.py runserver
```

4. **Access:**
- Main app: http://localhost:8000/inventory/
- Admin panel: http://localhost:8000/admin/

## URL Patterns

- `/` - Dashboard
- `/items/` - List all items
- `/items/add/` - Add new item
- `/items/<id>/` - Item detail with history
- `/items/<id>/edit/` - Edit item
- `/transfer/` - Assign/Transfer/Dispatch items
- `/history/` - View all history
- `/reports/` - Reports and analytics

## Future Enhancements (Optional)

If you want to add more features later:
- Barcode scanning
- Email notifications for low stock
- PDF export of reports
- Mobile app
- API endpoints

## Support

For issues or questions, check the Django admin interface or review the history logs for tracking issues.

---

**Remember**: Keep it simple! The system tracks WHERE things are and WHERE they've been. That's the core functionality.
