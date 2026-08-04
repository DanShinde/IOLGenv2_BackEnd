"""
Changelog data for version history display.

Add new versions to the top of the CHANGELOG list.
Each entry has: version, date, and a list of changes.
"""

APP_VERSION = "v3.0"

CHANGELOG = [
    {
        "version": "v3.0",
        "date": "15 Jul 2026",
        "changes": [
            "Remade the Master Dashboard with cards for Total Projects, Completed Projects, Ongoing Projects, and Overall Completion %.",
            "Added interactive expand/popup details modal when clicking any project on the Master Dashboard to view its zone-by-zone progress and statistics.",
            "Redesigned Project Management into a modern Project Dashboard with per-project progress bars, completion status badges, and simplified project cards.",
            "Added Duplicate Project functionality to clone any existing project with all zones, selections, results, observations, and settings.",
            "Added User Manual button on the Login page for quick access to the application documentation without requiring authentication.",
            "Master Dashboard updates automatically whenever project data changes.",
            "Project Dashboard cards now display customer name, current progress percentage, last modified date, and a visual status indicator (Not Started / In Progress / Complete).",
            "Added conditional status coloring: projects and zones are marked 'Complete' (solid green progress bar) only when all test cases passed. Completed projects with active failures display as 'Complete (Failed TCs)' with a solid yellow progress bar."
        ]
    },
    {
        "version": "v2.7",
        "date": "13 Jul 2026",
        "changes": [
            "Added page title headers to Selections and other Edit Test Case Library pages for clearer navigation context.",
            "Fixed typography and letter-spacing issues causing overlapping characters in Type headings and card labels.",
            "Improved Test Case card layout: long text now wraps automatically, preserves line breaks, and cards expand to fit content.",
            "Simplified the Login page by removing the version badge and subtitle for a cleaner appearance.",
            "Redesigned the Shareable Report feature with server-side report sessions for true network-accessible sharing.",
            "Shareable reports now update live as results and observations change during Guided Execution.",
            "Added Auto Refresh toggle to the shared report page with configurable automatic polling.",
            "Changed server binding to 0.0.0.0 so shareable links work across the local network.",
            "Polished the Edit Test Case Library UI with improved spacing, typography, and visual consistency."
        ]
    },
    {
        "version": "v2.6",
        "date": "11 Jul 2026",
        "changes": [
            "Redesigned the Edit Test Case Library into a modern multi-page hierarchy (Home > Selections > Types > Clusters > Test Cases).",
            "Eliminated nested dropdowns, expandable panels, and accordions for a cleaner settings-like user experience.",
            "Converted Selections, Types, and Clusters to large, responsive clickable cards with visual selection and navigation arrows.",
            "Added global Selection management (Add, Rename, Delete) that updates both the master library and all existing project states.",
            "Created a dedicated Test Case cards view showing sequential numbers and previews of prerequisites, actions, and expected results.",
            "Introduced a dedicated Edit Test Case modal with Shift+Enter multi-line support and Enter to save shortcuts.",
            "Implemented clickable breadcrumb navigation and back buttons across all settings pages for easy hierarchy traversal.",
            "Added global selections auto-initialization and project data synchronization to maintain absolute compatibility."
        ]
    },
    {
        "version": "v2.5",
        "date": "11 Jul 2026",
        "changes": [
            "Added user authentication with a professional dark-themed login page.",
            "Introduced multi-project management page with Create, Rename, Delete, and Open operations.",
            "Each project is now fully isolated with its own Zones, Selections, results, and observations.",
            "Relocated the Edit Test Case Library feature from Test Case Manager to the Project Management page for easier access.",
            "Added automatic migration of existing cached project data into a Default Project on first load.",
            "Added Back to Projects navigation button in the application header.",
            "Added Logout functionality that clears the session and returns to the login screen."
        ]
    },
    {
        "version": "v2.4",
        "date": "06 Jul 2026",
        "changes": [
            "Redesigned the Edit Test Case page with a clear 3-step workflow: Select Selection, Select Zone, Manage Test Cases.",
            "Organized Zone and Cluster management actions into grouped toolbars for improved usability.",
            "Replaced the cramped two-column Edit layout with a full-width vertical flow and collapsible editor card.",
            "Removed all emojis from the website and replaced with plain text and standard UI elements for a professional appearance.",
            "General UI polish: fixed text overflow, button overflow, responsive wrapping, and consistent spacing across all pages.",
            "Cleaned up inline style attributes across the HTML and moved them into proper CSS classes.",
            "Restored and improved the Add Using Template feature with separate Download Template and Upload Template actions.",
            "Download Template now generates an Excel file matching the official dark-red/maroon design.",
            "Upload Template now requires selecting a target Selection before importing, with full validation and error handling.",
            "Template import creates new Zones automatically and appends test cases to existing Zones without overwriting.",
            "After successful template upload, the UI updates immediately without requiring a page refresh.",
            "Standardized application terminology: categories/zones within a Selection are consistently named Types, reserving Zone exclusively for user-created worksheets.",
            "Updated Test Case Manager step 2 and edit toolbars to use Select Type / Cluster, Add/Rename/Delete Type.",
            "Allowed deletion of built-in selections (Conveyor and VRC) from the project with full confirmation and cleanups.",
            "Allowed deleting the last remaining Type or Cluster within a Selection, supporting empty selections gracefully."
        ]
    },
    {
        "version": "v2.3",
        "date": "01 Jul 2026",
        "changes": [
            "Redesigned the Test Case Manager UI to present three distinct operations: Add Custom Test Case, Add Using Template, and Add New Selection.",
            "Created placeholder views for Add Using Template (with disabled Download/Upload buttons) and Add New Selection.",
            "Implemented the Download Template feature inside Add Using Template to generate an Excel import template containing 4 standard headers (Test Case Name, Prerequisites, Action, Expected Result) and a merged Section Name row.",
            "Implemented the Upload Template feature with header verification and robust section-based parser to import custom test cases, appending to existing sections or creating new sections automatically.",
            "Implemented the Add New Selection feature inside the Test Case Manager to define custom selection types (e.g. Sorter, Buffer) dynamically, displaying them next to Conveyor and VRC.",
            "Implemented cluster management for custom selection types, allowing users to add, rename, delete, and reorder clusters dynamically per custom selection type, grouping project-only test cases under their respective custom clusters.",
            "Enhanced 'Add Using Template' to require selecting a target Selection dropdown before download/upload actions, enforcing validation and mapping imported sections of that specific type.",
            "Expanded 'Add New Selection' to a complete Selection Management view enabling users to create, edit (rename), and delete custom selections (recursively deleting their associated sections and test cases) while protecting built-ins.",
            "v2.3 Hotfix - Live Updates in Test Case Manager: Made all manager operations (custom test case, template upload, selection CRUD, edit/reorder) update the UI immediately without page refresh.",
            "v2.3 Hotfix - Filter Edit Test Case by Selection: Added Selection target filter to Edit Test Case tab, displaying only relevant groups and test cases for the chosen selection type.",
            "v2.3 Hotfix - Update Company Logo: Updated company logo assets with the new wide Armstrong Dematic branding logo everywhere while preserving correct aspect ratio scaling.",
            "v2.3 Hotfix - Fix Upload Using Template: Refined template parser to correctly detect merged A:D cells as Section Name rows, validate header rows, and append test cases under matching selections.",
            "v2.3 Hotfix - Rename \"Sections\" to \"Zones\": Consistently renamed terminology throughout the application views, dialogs, buttons, and generated Excel charts to refer to \"Zones\" instead of \"Sections\".",
            "v2.3 Hotfix - Correct \"Add Using Template\" Behavior: Configured template Excel uploading to import test cases into the selected Selection's master library within test_groups.json instead of creating Zones.",
            "v2.3 Hotfix - Move Cluster Management: Moved all cluster/category management controls from the Selection page to the Edit Test Case tab inside the Test Case Manager.",
            "v2.3 Hotfix - Redesign Selection Page: Added the ability on the Selection page to temporarily add and remove individual test cases inside selected clusters for the active session only.",
            "v2.3 Hotfix - Shift+Enter Multi-line Support: Enabled multi-line input (using Shift+Enter) for Prerequisites, Action, and Expected Result fields in the Selection page customizer, preserving newlines in UI views and Excel cells.",
            "v2.3 Hotfix - Dynamic Project Code Label: Dynamically renamed the customizer 'Session Only' label to '<Project Code> Only' (or 'Current Project Only' if blank) and configured it to update instantly as the project code input is edited.",
            "v2.3 Hotfix - Consolidated Permanent Test Library Editor: Removed 'Add Custom Test Case' menu and consolidated all permanent test case library operations (add, edit, delete, reorder, move between clusters, and create/rename/delete zones) under the password-protected Edit Test Case panel."
        ]
    },
    {
        "version": "v2.2",
        "date": "30 Jun 2026",
        "changes": [
            "Replaced the company logo with the new Armstrong Dematic wide branding logo and scaled it properly maintaining its aspect ratio.",
            "Added a Duplicate Section option to clone any active section (Conveyor/VRC) under a custom name, retaining settings and test results.",
            "Increased Delete Selected button width to match the Load Project button's width.",
            "Added Select All and Deselect All buttons in the test case selection views.",
            "Renamed Custom Test Case Manager to Test Case Manager, featuring a selection menu for Custom Test Cases and Edit Test Cases.",
            "Grouped custom test cases under a dedicated 'Custom Test Cases' worksheet in generated Excel files placed after standard sheets.",
            "Protected the Edit Test Cases section with password 'simi2005', permitting inline edits of built-in test case names, prerequisites, actions, expected results, and changing their order via Move Up/Down buttons.",
            "Added case-insensitive dropdown search functionality within Guided Execution matching by Sr. No. and Test Case Name.",
            "",
            "=== v2.2 Hotfix ===",
            "Resized the company logo on the main website to fit neatly inside the top banner.",
            "Restored the Selection page UI to its previous layout, preserving only the Select All and Deselect All buttons.",
            "Restored functional modules: View Test Cases, Guided Execution, and Test Case Manager.",
            "Renamed 'Delete Selected' button to 'Delete Selection' in both desktop and web versions.",
            "Matched the width of the 'Delete Selection' and 'Duplicate Section' buttons to the 'Save Project' button.",
            "Fixed server-side 'json' undefined error blocking built-in test case saving and reordering."
        ]
    },
    {
        "version": "v2.1",
        "date": "30 Jun 2026",
        "changes": [
            "Simplified toolbar layout by removing icons from Delete, Export, Skip, view checkboxes, and tab headers (displaying text-only).",
            "Added fullscreen maximize/restore toggle button on View, Guided, and Custom tabs to expand workspace.",
            "Completely removed 'Acceptance Criteria' fields from all application models, views, and Excel sheet exports.",
            "Fixed selection accordion overlapping issue in CSS to properly flow and push subsequent categories.",
            "Integrated category divider header rows inside View Test Cases table matching original Excel template layout.",
            "Added result validation in Guided execution requiring test cases to be marked Pass or Fail before proceeding.",
            "Provided Export Choice modal offering direct Excel sheet downloads or generating Base64 shareable view-only URL links.",
            "Enabled multi-line Prerequisites, Action, and Expected Result textarea fields in Custom Manager supporting Shift + Enter newlines.",
            "Centered the Armstrong Dematic company logo branding at the top center of the web page.",
            "",
            "=== v2.1 Hotfix ===",
            "Resolved Version History / Changelog modal load and display issues.",
            "Fixed Excel workbook generation under standard workflow.",
            "Restored complete Save Project and Load Project operations.",
            "Fixed Guided Execution controls including status updates and navigation triggers.",
            "Restored Unlocked Export passwords verification and worksheets protection controls.",
            "Restored shareable view-only link serialization and loading.",
            "Modified Guided Execution Skip button to bypass Pass/Fail validation and always navigate forward.",
            "Redesigned View-Only Export output to contain only the company logo banner, project metadata block, and test case rows (omitting summary sheets and metadata footers).",
            "Added EFS TestCaseGenerator title text to the top-left of the application header, aligning with larger company logo.",
            "Anchored Delete Selected button to the bottom of the sidebar container.",
            "Created a separate customer-facing View-Only /report route/page displaying only the company logo, project metadata, and a clean read-only test cases table.",
            "Restored the Summary Report worksheet (completion graphs, pass/fail statistics, charts, and overall formatting) for normal Excel exports.",
            "Restored the exact watermark footer wording ('Made by EFS TestCaseGenerator, cannot be edited.') on normal Excel exports."
        ]
    },
    {
        "version": "v2.0",
        "date": "30 Jun 2026",
        "changes": [
            "Introduced fully responsive Web application version of EFS Test Case Generator supporting project management, selection, execution, and export.",
            "Restructured application codebase into Desktop, Web, and Shared segments for unified business logic, models, and data.",
            "Implemented Custom Test Case Manager supporting permanent and project-only custom test case scopes.",
            "Added Guided Test Execution Mode card view with progress tracking, result buttons, and observation comments.",
            "Implemented shareable 'View-Only' fully locked Excel workbook generation.",
            "Added searchable View & Export Test Cases dynamic table with quick single-section Excel export."
        ]
    },
    {
        "version": "v1.9.1",
        "date": "29 Jun 2026",
        "changes": [
            "Added 'Made by EFS TestCaseGenerator , can not be edited.' red italic footer in merged Excel cells E4:G4.",
            "Added dynamic 'Validator Name' input field in GUI when Internal or External Validator is selected, hiding it for Self.",
            "Populated dynamic validator name values into Row 2 of the Excel project information block.",
            "Added optional 'Unlocked Export' toggle beside the Generate button, prompting for password ('simi') to export fully editable workbooks."
        ]
    },
    {
        "version": "v1.9",
        "date": "29 Jun 2026",
        "changes": [
            "Populated detailed prerequisites, actions, and expected results for VRC test cases in Safety Interlock, Manual Mode, and Faults and Alarms categories.",
            "Aligned all VRC metadata parameters exactly to the provided reference screenshots."
        ]
    },
    {
        "version": "v1.8",
        "date": "29 Jun 2026",
        "changes": [
            "Populated detailed prerequisites, actions, and expected results for all conveyor process operations, profile checker tests, and manual jog mode tests using reference screenshots.",
            "Synced both Infeed and Outfeed conveyor test data entries for consistency across section types."
        ]
    },
    {
        "version": "v1.7",
        "date": "29 Jun 2026",
        "changes": [
            "Populated detailed prerequisites, actions, and expected results for category 1 (Safety Interlock & Start/Stop Test) conveyor test cases using reference screenshots.",
            "Designed test case data structure in JSON for easy maintenance of future test case contents."
        ]
    },
    {
        "version": "v1.6",
        "date": "28 Jun 2026",
        "changes": [
            "Added Failed Test Cases column to Summary Report table and pie chart.",
            "Updated Completion % calculation to ignore Pending (completion based on Pass + Fail only).",
            "Updated Completion % graph bar colors (light green series with blue outline).",
            "Formatted all summary percentages to exactly two decimal places.",
            "Arranged Summary Report layout to place completion and distribution charts side-by-side starting at row 13."
        ]
    },
    {
        "version": "v1.5",
        "date": "28 Jun 2026",
        "changes": [
            "Merged Project Information label cells across Columns A and B in Excel.",
            "Updated Project Information formatting with size 12 labels and size 16 italic values.",
            "Added light green conditional formatting for Pass test case results.",
            "Removed the In Progress test result option completely from dropdowns, sheets, and charts.",
            "Fixed Summary Report chart layout with centered pie chart, clean labels, and legend alignment.",
            "Moved Last Updated date beside the Test Case Summary heading."
        ]
    },
    {
        "version": "v1.4",
        "date": "28 Jun 2026",
        "changes": [
            "Renamed the application to EFS Test Case Generator.",
            "Fixed the company logo so it displays correctly in both development mode and the packaged executable.",
            "Updated the generated Excel workbook to match the provided template.",
            "Added automatic changelog update."
        ]
    },
    {
        "version": "v1.3",
        "date": "28 Jun 2026",
        "changes": [
            "Improved dropdown expand/collapse behaviour for a smoother user experience.",
            "Replaced [+] / [-] indicators with expand/collapse arrows.",
            "Added Select All and Deselect All functionality for test groups.",
            "Enhanced search to locate both group names and items inside collapsed groups.",
            "Preserved selected test cases when navigating between sections.",
            "Added automatic file naming based on Project Code, Customer Name, and selected section type.",
            "Added application footer with contact information for bug reports and suggestions.",
            "Added company logo beside the Project Information heading.",
            "Added version number beside the application title.",
            "Introduced Version History (Changelog) dialog.",
            "General UI refinements and stability improvements."
        ]
    },
    {
        "version": "v1.2",
        "date": "27 Jun 2026",
        "changes": [
            "Excel generation now exports only selected test cases.",
            "Removed automatic inclusion of default data.",
            "Excel output now follows the predefined cluster order.",
            "Updated application to use the new clustering structure.",
            "Initial implementation of dropdown animation.",
            "Improved dropdown positioning beneath their respective headings.",
            "Added support for expandable clustering architecture for future updates."
        ]
    },
    {
        "version": "v1.1",
        "date": "26 Jun 2026",
        "changes": [
            "Added Save Project functionality.",
            "Added Load Project functionality.",
            "Added support for multiple project sections.",
            "Added Conveyor and VRC section type selection.",
            "Improved project information handling.",
            "Improved overall application layout and navigation.",
            "Various UI enhancements and bug fixes.",
            "Added changelog."
        ]
    },
    {
        "version": "v1.0",
        "date": "27/06/2026",
        "changes": [
            "Initial release.",
            "Category/group-based test case selection.",
            "Conveyor and VRC section type support.",
            "Excel workbook generation with Summary Report.",
            "Project save/load functionality."
        ]
    }
]
