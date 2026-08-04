/**
 * EFS Test Case Generator Web Client-side Javascript application (v3.0).
 * Handles UI events, state synchronizations, local storage caching,
 * JSON save/load, server-side shareable report sessions, and server communication.
 * v3.0: Project Dashboard, Master Dashboard, Duplicate Project, User Manual.
 */

// ─── STATE MANAGEMENT ────────────────────────────────────────────────
const API_BASE = "/testvault";

let state = {
    project: {
        info: {
            project_code: "",
            customer_name: "",
            done_by: "",
            date_of_validation: new Date().toLocaleDateString('en-GB').replace(/\//g, '-'),
            validator_type: "Self",
            validator_name: "",
            testing_phase: "FAT"
        },
        sections: []
    },
    // Editable fields that live on the server-side TestVaultProject row (tracker_project link,
    // prepared_by/validator_employee FKs) rather than in the engine's Project/ProjectInfo shape.
    currentProjectMeta: null,
    selectedSectionIndex: null,
    testGroupsData: { categories: [] },
    permanentCustomTestCases: [],
    guidedCurrentIndex: 0,
    guidedTestCases: [],
    customEditingOldName: null,
    isViewOnlyLink: false,
    selectedClusterId: null,
    currentProjectId: null,
    activeReportId: null
};

// Server-persisted project state — replaces the old per-project localStorage cache.
// Fire-and-forget: callers don't await this (matches the old synchronous autosave feel).
function saveStateToCache() {
    if (state.isViewOnlyLink) return;
    if (!state.currentProjectId) return;
    postJSON(`${API_BASE}/api/projects/${state.currentProjectId}/save/`, {
        project: state.project,
        meta: collectProjectMetaFromUI(),
    }).catch(e => console.error("Failed to save project state", e));
}

// ─── API UTILITIES ───────────────────────────────────────────────────
function getCSRFToken() {
    const el = document.querySelector('[name=csrfmiddlewaretoken]');
    return el ? el.value : '';
}

async function fetchAPI(endpoint, options = {}) {
    const opts = { ...options, headers: { ...(options.headers || {}) } };
    const method = (opts.method || "GET").toUpperCase();
    if (method !== "GET" && method !== "HEAD") {
        opts.headers["X-CSRFToken"] = getCSRFToken();
    }
    const res = await fetch(endpoint, opts);
    if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.error || `HTTP error ${res.status}`);
    }
    return res.json();
}

function postJSON(endpoint, data) {
    return fetchAPI(endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(data || {}),
    });
}

// Reads the editable info-card fields that live on the server-side TestVaultProject row
// (not part of the engine's Project/ProjectInfo JSON blob) so they ride along on every save.
function collectProjectMetaFromUI() {
    const meta = {
        date_of_validation: document.getElementById("date-of-validation")?.value || "",
        validator_type: document.getElementById("validator-type")?.value || "Self",
        testing_phase: document.getElementById("testing-phase")?.value || "Emulation",
    };
    const preparedSel = document.getElementById("prepared-by-select");
    if (preparedSel) meta.prepared_by_id = preparedSel.value || null;
    const validatorSel = document.getElementById("validator-employee-select");
    if (validatorSel) meta.validator_employee_id = validatorSel.value || null;
    const validatorNameEl = document.getElementById("validator-name");
    if (validatorNameEl) meta.validator_name = validatorNameEl.value || "";
    return meta;
}

// Populates the Prepared By / Validator <select> elements from employees.Employee via the
// lookup endpoint. Called once on app init and again whenever a project is opened, so the
// current selection (from state.currentProjectMeta) can be pre-selected.
async function populateEmployeeSelects() {
    let employees = [];
    try {
        const res = await fetchAPI(`${API_BASE}/api/lookup/employees/`);
        employees = res.results || [];
    } catch (e) {
        console.error("Failed to load employees", e);
    }
    [document.getElementById("prepared-by-select"), document.getElementById("validator-employee-select")].forEach(sel => {
        if (!sel) return;
        const current = sel.value;
        sel.innerHTML = '<option value="">— Select —</option>' + employees.map(
            e => `<option value="${e.id}">${escapeHTML(e.name)}</option>`
        ).join("");
        if (current) sel.value = current;
    });
}

// ─── ON PAGE LOAD ────────────────────────────────────────────────────
document.addEventListener("DOMContentLoaded", async () => {
    // 1. Check if loading a shared view-only link
    checkSharedLinkQuery();

    if (state.isViewOnlyLink) {
        // Direct to app with view-only data
        await initAppData();
        showScreen("app");
        document.getElementById("btn-back-to-projects").classList.add("hidden");
        applyProjectToUI();
        initEventListeners();
        selectSection(0);
        lockUIForViewOnly();
        return;
    }

    // 2. Django's own session already authenticated this request (TestVaultAuthRequiredMiddleware
    // gates /testvault/) -- go straight to the project dashboard.
    await initAppData();
    initEventListeners();
    showScreen("projects");
});

async function initAppData() {
    try {
        const groupsRes = await fetchAPI(`${API_BASE}/api/test-groups/`);
        state.testGroupsData = groupsRes;

        // If selections list is missing, auto-populate from categories/groups
        if (!state.testGroupsData.selections) {
            const types = new Set(["Conveyor", "VRC"]);
            state.testGroupsData.categories.forEach(cat => {
                cat.groups.forEach(g => {
                    if (g.section_type) {
                        const name = g.section_type.charAt(0).toUpperCase() + g.section_type.slice(1);
                        types.add(name);
                    }
                });
            });
            state.testGroupsData.selections = Array.from(types);
            await saveTestGroupsDataPermanently();
        }

        const customRes = await fetchAPI(`${API_BASE}/api/custom-test-cases/`);
        state.permanentCustomTestCases = customRes.custom_test_cases || [];

        if (state.project) {
            migrateProjectSelectionsToGlobal();
        }
    } catch (e) {
        console.error("Failed to load reference metadata from server.", e);
    }
}

function showScreen(screenName) {
    document.getElementById("project-mgmt-screen").classList.add("hidden");
    document.getElementById("app-screen").classList.add("hidden");
    document.getElementById("edit-tc-overlay").classList.add("hidden");
    document.getElementById("master-dashboard-screen").classList.add("hidden");

    // Clear auto-refresh interval on screen change
    if (window.dashRefreshInterval) {
        clearInterval(window.dashRefreshInterval);
        window.dashRefreshInterval = null;
    }

    if (screenName === "projects") {
        document.getElementById("project-mgmt-screen").classList.remove("hidden");
        renderProjectCards();
    } else if (screenName === "app") {
        document.getElementById("app-screen").classList.remove("hidden");
    } else if (screenName === "editOverlay") {
        document.getElementById("edit-tc-overlay").classList.remove("hidden");
    } else if (screenName === "masterDashboard") {
        document.getElementById("master-dashboard-screen").classList.remove("hidden");
        renderMasterDashboard();
        updateLiveTime();
        
        // Start 5 minutes auto-refresh
        window.dashRefreshInterval = setInterval(() => {
            renderMasterDashboard();
        }, 5 * 60 * 1000);
    }
}

// ─── CHECK VIEW-ONLY QUERY STRING ───────────────────────────────────
function checkSharedLinkQuery() {
    const params = new URLSearchParams(window.location.search);
    const viewData = params.get("view");
    if (viewData) {
        try {
            const decoded = decodeURIComponent(escape(atob(viewData)));
            const parsed = JSON.parse(decoded);
            if (parsed && parsed.info && parsed.sections) {
                state.project = parsed;
                state.isViewOnlyLink = true;
                showStatus("Opened Shared View-Only Link Mode", "#3b82f6");
            }
        } catch (e) {
            console.error("Failed to parse view query link data", e);
            alert("The shareable link appears to be corrupted or invalid.");
        }
    }
}

// Lock all state-modifying fields
function lockUIForViewOnly() {
    // Disable inputs
    const inputs = document.querySelectorAll("input, select, textarea");
    inputs.forEach(el => {
        if (el.id !== "view-search") {
            el.disabled = true;
        }
    });

    // Hide edit/save buttons
    const hiddenIDs = [
        "btn-add-section",
        "new-section-name",
        "btn-delete-section",
        "btn-duplicate-section",
        "btn-custom-save",
        "btn-save-project",
        "btn-load-project",
        "chk-unlocked",
        "chk-view-only"
    ];
    hiddenIDs.forEach(id => {
        const el = document.getElementById(id);
        if (el) el.classList.add("hidden");
    });

    // Add view-only notification top banner
    const banner = document.createElement("div");
    banner.style.background = "#1e3a8a";
    banner.style.color = "white";
    banner.style.textAlign = "center";
    banner.style.padding = "8px";
    banner.style.fontWeight = "bold";
    banner.style.fontSize = "13px";
    banner.style.borderRadius = "6px";
    banner.style.border = "1px solid #3b82f6";
    banner.textContent = "Read-Only Mode: You are viewing a shared project. Edits are disabled.";
    
    const container = document.querySelector(".app-container");
    container.insertBefore(banner, document.getElementById("project-info-section"));
}

// ─── BIND FORM CONTROLS ──────────────────────────────────────────────
function safeAddListener(id, event, callback) {
    const el = document.getElementById(id);
    if (el) {
        el.addEventListener(event, callback);
    }
}

function initEventListeners() {
    // Project info inputs. project-code/customer-name are read-only (sourced from the linked
    // tracker.Project) and intentionally not bound here.
    const infoBindings = [
        { id: "date-of-validation", field: "date_of_validation" },
        { id: "validator-name", field: "validator_name" }
    ];

    infoBindings.forEach(binding => {
        const el = document.getElementById(binding.id);
        if (el) {
            el.addEventListener("input", (e) => {
                state.project.info[binding.field] = e.target.value;
                saveStateToCache();
            });
        }
    });

    safeAddListener("prepared-by-select", "change", (e) => {
        const selected = e.target.selectedOptions[0];
        state.project.info.done_by = selected && selected.value ? selected.textContent : "";
        if (!state.currentProjectMeta) state.currentProjectMeta = {};
        state.currentProjectMeta.prepared_by_id = e.target.value || null;
        saveStateToCache();
    });

    safeAddListener("validator-employee-select", "change", (e) => {
        const selected = e.target.selectedOptions[0];
        state.project.info.validator_name = selected && selected.value ? selected.textContent : "";
        if (!state.currentProjectMeta) state.currentProjectMeta = {};
        state.currentProjectMeta.validator_employee_id = e.target.value || null;
        saveStateToCache();
    });

    safeAddListener("validator-type", "change", (e) => {
        state.project.info.validator_type = e.target.value;
        toggleValidatorNameVisibility();
        saveStateToCache();
    });

    safeAddListener("testing-phase", "change", (e) => {
        state.project.info.testing_phase = e.target.value;
        saveStateToCache();
    });

    // Sections sidebars
    safeAddListener("btn-add-section", "click", addSection);
    safeAddListener("new-section-name", "keypress", (e) => {
        if (e.key === "Enter") addSection();
    });
    safeAddListener("btn-delete-section", "click", deleteSelectedSection);
    safeAddListener("btn-duplicate-section", "click", duplicateActiveSection);

    // Select/Deselect All buttons
    safeAddListener("btn-select-all-tcs", "click", selectAllVisibleTCs);
    safeAddListener("btn-deselect-all-tcs", "click", deselectAllVisibleTCs);

    // Section type change will be handled dynamically in renderSectionTypeToggles

    // Tab view switcher
    const tabBtns = document.querySelectorAll(".tab-btn");
    tabBtns.forEach(btn => {
        btn.addEventListener("click", (e) => {
            tabBtns.forEach(b => b.classList.remove("active"));
            e.target.classList.add("active");
            
            const tabId = e.target.getAttribute("data-tab");
            document.querySelectorAll(".tab-content").forEach(c => c.classList.remove("active"));
            const tabEl = document.getElementById(tabId);
            if (tabEl) tabEl.classList.add("active");
            
            // Reload specific tab views
            if (tabId === "tab-view") {
                reloadViewTab();
            } else if (tabId === "tab-guided") {
                reloadGuidedTab();
            } else if (tabId === "tab-summary") {
                renderSummaryTab();
            } else if (tabId === "tab-custom") {
                reloadCustomManagerTab();
            }
        });
    });

    // View table search
    safeAddListener("view-search", "input", reloadViewTab);
    
    // View table excel export
    safeAddListener("btn-export-excel", "click", exportSingleSectionExcel);

    // Maximize/Restore fullscreen buttons
    document.querySelectorAll(".btn-maximize").forEach(btn => {
        btn.addEventListener("click", (e) => {
            const isFull = document.body.classList.toggle("fullscreen-mode");
            document.querySelectorAll(".btn-maximize").forEach(b => {
                b.textContent = isFull ? "Restore" : "Maximize";
            });
        });
    });

    // Global test group search
    safeAddListener("global-search", "input", (e) => {
        const query = e.target.value.toLowerCase();
        // Switch to Selection tab if they search
        const selTab = document.querySelector('.tab-btn[data-tab="tab-selection"]');
        if (selTab) selTab.click();
        filterSelectionAccordions(query);
    });

    // Guided Results Segmented Buttons
    document.querySelectorAll("#guided-result-segmented .segment-btn").forEach(btn => {
        btn.addEventListener("click", (e) => {
            document.querySelectorAll("#guided-result-segmented .segment-btn").forEach(b => b.classList.remove("active"));
            e.target.classList.add("active");
            saveGuidedProgress();
        });
    });

    // Guided observation typing
    safeAddListener("guided-observation", "input", saveGuidedProgress);

    // Guided search input
    safeAddListener("guided-search-input", "input", onGuidedSearchTyping);

    // Guided navigation
    safeAddListener("guided-btn-prev", "click", guidedPrev);
    safeAddListener("guided-btn-skip", "click", guidedSkip);
    safeAddListener("guided-btn-next", "click", guidedNext);

    // Custom Manager textarea Enter key handlers (Shift+Enter for newline, Enter to submit)
    const textareas = ["custom-tc-prereq", "custom-tc-action", "custom-tc-expected"];
    textareas.forEach(id => {
        const el = document.getElementById(id);
        if (el) {
            el.addEventListener("keydown", (e) => {
                if (e.key === "Enter") {
                    if (e.shiftKey) {
                        // Shift + Enter: Allow default newline insertion
                    } else {
                        e.preventDefault();
                        saveCustomTestCase(); // Submit
                    }
                }
            });
        }
    });

    // Custom Manager buttons
    safeAddListener("btn-custom-save", "click", saveCustomTestCase);
    safeAddListener("btn-custom-cancel", "click", clearCustomForm);

    // Manager View Option Selectors
    safeAddListener("btn-mgr-opt-template", "click", () => showManagerScreen("template"));
    safeAddListener("btn-mgr-opt-selection", "click", () => showManagerScreen("selection"));
    safeAddListener("btn-manager-back", "click", () => showManagerScreen("menu"));
    
    // Add Using Template Download & Upload listeners
    safeAddListener("template-target-selection", "change", (e) => {
        const val = e.target.value;
        document.getElementById("btn-template-upload").disabled = !val;
    });
    safeAddListener("btn-template-download", "click", () => {
        window.location.href = `${API_BASE}/api/template/download/`;
    });
    safeAddListener("btn-template-upload", "click", () => {
        document.getElementById("file-template-upload").click();
    });
    safeAddListener("file-template-upload", "change", handleTemplateUpload);

    // Add New Selection listener
    safeAddListener("btn-create-selection", "click", createNewSelection);
    safeAddListener("btn-cancel-selection-edit", "click", cancelSelectionEdit);

    // Built-in Test Cases Editor buttons
    safeAddListener("edit-selection-select", "change", onEditSelectionChanged);
    safeAddListener("edit-group-select", "change", onEditGroupSelected);
    safeAddListener("btn-edit-cat-add", "click", onEditCategoryAdd);
    safeAddListener("btn-edit-cat-rename", "click", onEditCategoryRename);
    safeAddListener("btn-edit-cat-delete", "click", onEditCategoryDelete);
    safeAddListener("btn-edit-group-add", "click", onEditGroupAdd);
    safeAddListener("btn-edit-group-rename", "click", onEditGroupRename);
    safeAddListener("btn-edit-group-delete", "click", onEditGroupDelete);
    safeAddListener("btn-edit-group-move-up", "click", () => moveEditGroup(-1));
    safeAddListener("btn-edit-group-move-down", "click", () => moveEditGroup(1));
    safeAddListener("btn-edit-move-up", "click", () => moveEditTC(-1));
    safeAddListener("btn-edit-move-down", "click", () => moveEditTC(1));
    safeAddListener("btn-edit-save", "click", saveEditedTC);
    safeAddListener("btn-edit-add-tc", "click", onEditAddTC);
    safeAddListener("btn-edit-delete-tc", "click", deleteEditedTC);

    // Bottom action panel: Generate Excel popup choice modal triggers
    safeAddListener("btn-save-project", "click", saveProjectToFile);
    safeAddListener("btn-load-project", "click", () => {
        const fileInput = document.getElementById("project-file-input");
        if (fileInput) fileInput.click();
    });
    safeAddListener("project-file-input", "change", loadProjectFromFile);
    
    safeAddListener("chk-unlocked", "change", handleUnlockedCheckboxChange);
    safeAddListener("chk-view-only", "change", handleViewOnlyCheckboxChange);
    safeAddListener("btn-generate-action", "click", openExportChoiceModal);

    // Export Options Modal handlers
    safeAddListener("export-modal-close", "click", closeExportChoiceModal);
    safeAddListener("btn-opt-excel-export", "click", () => {
        closeExportChoiceModal();
        generateProjectExcel();
    });
    safeAddListener("btn-opt-shareable-link", "click", generateShareableViewOnlyLink);
    safeAddListener("btn-copy-shareable-link", "click", copyShareableLinkToClipboard);

    // Changelog modals
    safeAddListener("btn-changelog", "click", openChangelogModal);
    safeAddListener("btn-changelog-mgmt", "click", openChangelogModal);
    safeAddListener("changelog-modal-close-icon", "click", closeChangelogModal);
    safeAddListener("changelog-modal-close-btn", "click", closeChangelogModal);

    // ─── PROJECT MANAGEMENT LISTENERS ─────────────────────────────────
    // Back to Projects
    safeAddListener("btn-back-to-projects", "click", backToProjectManagement);

    // Project CRUD
    safeAddListener("btn-create-project", "click", openNewProjectModal);
    safeAddListener("new-project-modal-close", "click", closeNewProjectModal);
    safeAddListener("btn-confirm-create-project", "click", confirmCreateProject);
    safeAddListener("new-project-source-select", "change", refreshNewProjectSourceOptions);

    // Edit TC overlay (from project management) -- access follows the same "any logged-in
    // TestVault user" model as the rest of the app; no separate gate here.
    safeAddListener("btn-edit-tc-global", "click", openEditTCOverlay);
    safeAddListener("btn-overlay-back", "click", closeEditTCOverlay);
    
    // REDESIGNED v2.6 Page-based Navigation Menu bindings
    safeAddListener("btn-menu-manage-selections", "click", () => showEditPage("manage-selections"));
    safeAddListener("btn-menu-edit-library", "click", () => showEditPage("select-selection"));
    
    // Page 1: Manage Selections
    safeAddListener("btn-sel-add", "click", addGlobalSelection);
    safeAddListener("btn-sel-rename", "click", renameGlobalSelection);
    safeAddListener("btn-sel-delete", "click", deleteGlobalSelection);
    
    // Page 3: Manage Types
    safeAddListener("btn-type-add", "click", addGlobalType);
    safeAddListener("btn-type-rename", "click", renameGlobalType);
    safeAddListener("btn-type-delete", "click", deleteGlobalType);
    safeAddListener("btn-type-move-up", "click", () => moveGlobalType(-1));
    safeAddListener("btn-type-move-down", "click", () => moveGlobalType(1));
    
    // Page 4: Manage Clusters
    safeAddListener("btn-cluster-add", "click", addGlobalCluster);
    safeAddListener("btn-cluster-rename", "click", renameGlobalCluster);
    safeAddListener("btn-cluster-delete", "click", deleteGlobalCluster);
    safeAddListener("btn-cluster-move-up", "click", () => moveGlobalCluster(-1));
    safeAddListener("btn-cluster-move-down", "click", () => moveGlobalCluster(1));
    
    // Page 5: Manage Test Cases
    safeAddListener("btn-tc-add", "click", addGlobalTestCase);
    safeAddListener("btn-tc-edit", "click", editGlobalTestCase);
    safeAddListener("btn-tc-delete", "click", deleteGlobalTestCase);
    safeAddListener("btn-tc-move-up", "click", () => moveGlobalTestCase(-1));
    safeAddListener("btn-tc-move-down", "click", () => moveGlobalTestCase(1));
    
    // Back navigation buttons
    document.querySelectorAll(".btn-back-nav").forEach(btn => {
        btn.addEventListener("click", (e) => {
            const target = e.target.getAttribute("data-target");
            showEditPage(target);
        });
    });

    // Test Case Edit Modal
    safeAddListener("edit-tc-modal-close", "click", closeEditTCModal);
    safeAddListener("btn-save-modal-tc", "click", saveModalTestCase);
    
    // Modal Textareas Enter key handler (Shift+Enter for newline, Enter to save)
    const modalTextareas = ["edit-modal-tc-prereq", "edit-modal-tc-action", "edit-modal-tc-expected"];
    modalTextareas.forEach(id => {
        const el = document.getElementById(id);
        if (el) {
            el.addEventListener("keydown", (e) => {
                if (e.key === "Enter") {
                    if (e.shiftKey) {
                        // Shift+Enter: default newline behavior
                    } else {
                        e.preventDefault();
                        saveModalTestCase();
                    }
                }
            });
        }
    });

    // ─── v3.0: Master Dashboard & Changelog from Dashboard ───────────
    safeAddListener("btn-master-dashboard", "click", () => showScreen("masterDashboard"));
    safeAddListener("btn-dash-back", "click", () => showScreen("projects"));
    safeAddListener("btn-changelog-dash", "click", openChangelogModal);

    // Project Detail Modal in Master Dashboard
    safeAddListener("dash-project-detail-modal-close", "click", () => {
        document.getElementById("dash-project-detail-modal").classList.remove("open");
    });
    safeAddListener("dash-project-detail-modal-close-btn", "click", () => {
        document.getElementById("dash-project-detail-modal").classList.remove("open");
    });
    safeAddListener("btn-dash-refresh", "click", () => {
        renderMasterDashboard();
        showStatus("Dashboard data refreshed!", "var(--success-color)");
    });
}

// ─── APPLY STATE TO UI ───────────────────────────────────────────────
function applyProjectToUI() {
    // Project info card values. project-code/customer-name are read-only, always sourced
    // from the linked tracker.Project -- never written back.
    document.getElementById("project-code").value = state.project.info.project_code || "";
    document.getElementById("customer-name").value = state.project.info.customer_name || "";
    document.getElementById("validator-type").value = state.project.info.validator_type || "Self";
    document.getElementById("validator-name").value = state.project.info.validator_name || "";
    document.getElementById("testing-phase").value = state.project.info.testing_phase || "FAT";

    const meta = state.currentProjectMeta || {};
    const preparedSel = document.getElementById("prepared-by-select");
    if (preparedSel) preparedSel.value = meta.prepared_by_id || "";
    const validatorSel = document.getElementById("validator-employee-select");
    if (validatorSel) validatorSel.value = meta.validator_employee_id || "";

    toggleValidatorNameVisibility();
    renderSectionList();
}

function getActiveSection() {
    if (state.selectedSectionIndex !== null && state.selectedSectionIndex < state.project.sections.length) {
        return state.project.sections[state.selectedSectionIndex];
    }
    return null;
}

function toggleValidatorNameVisibility() {
    const valType = document.getElementById("validator-type").value;
    const nameGroup = document.getElementById("validator-name-group");
    const employeeGroup = document.getElementById("validator-employee-group");

    if (valType === "External Validator") {
        nameGroup.classList.remove("hidden");
        employeeGroup.classList.add("hidden");
    } else if (valType === "Internal Validator") {
        nameGroup.classList.add("hidden");
        document.getElementById("validator-name").value = "";
        state.project.info.validator_name = "";
        employeeGroup.classList.remove("hidden");
    } else {
        nameGroup.classList.add("hidden");
        employeeGroup.classList.add("hidden");
        document.getElementById("validator-name").value = "";
        state.project.info.validator_name = "";
        const validatorSel = document.getElementById("validator-employee-select");
        if (validatorSel) validatorSel.value = "";
    }
}

// ─── SECTIONS LIST ───────────────────────────────────────────────────
function renderSectionList() {
    const container = document.getElementById("sections-list");
    container.innerHTML = "";
    
    state.project.sections.forEach((sec, idx) => {
        const btn = document.createElement("button");
        btn.className = `section-btn ${idx === state.selectedSectionIndex ? 'active' : ''}`;
        if (state.isViewOnlyLink) btn.disabled = false; // allow switching tabs even if view only
        
        const label = document.createElement("span");
        const typeTag = sec.section_type === "conveyor" ? "CONV" : (sec.section_type === "vrc" ? "VRC" : sec.section_type.toUpperCase().substring(0, 4));
        label.textContent = `[${typeTag}] ${sec.name}`;
        
        btn.appendChild(label);
        
        const grpCount = sec.selected_groups.length;
        if (grpCount > 0) {
            const badge = document.createElement("span");
            badge.className = "section-badge";
            badge.textContent = grpCount;
            btn.appendChild(badge);
        }
        
        btn.addEventListener("click", () => selectSection(idx));
        container.appendChild(btn);
    });

    const deleteBtn = document.getElementById("btn-delete-section");
    deleteBtn.disabled = state.project.sections.length <= 1 || state.isViewOnlyLink;

    const duplicateBtn = document.getElementById("btn-duplicate-section");
    if (duplicateBtn) {
        duplicateBtn.disabled = state.selectedSectionIndex === null || state.isViewOnlyLink;
    }
}

function selectSection(index) {
    state.selectedClusterId = null;
    state.selectedSectionIndex = index;
    renderSectionList();
    
    const sec = getActiveSection();
    if (sec) {
        // Render Section type radio buttons dynamically
        renderSectionTypeToggles();
        
        renderSelectionTree();
        reloadActiveTabs();
    }
}

function addSection() {
    if (state.isViewOnlyLink) return;
    const input = document.getElementById("new-section-name");
    const name = input.value.trim();
    if (!name) return;
    
    // Check duplication
    if (state.project.sections.some(s => s.name.toLowerCase() === name.toLowerCase())) {
        alert("A zone with this name already exists.");
        return;
    }
    
    state.project.sections.push({
        name: name,
        section_type: "conveyor",
        selected_groups: [],
        dropdown_selections: {},
        results: {},
        observations: {},
        project_only_test_cases: []
    });
    
    input.value = "";
    saveStateToCache();
    selectSection(state.project.sections.length - 1);
}

function deleteSelectedSection() {
    if (state.isViewOnlyLink || state.project.sections.length <= 1) return;
    const sec = getActiveSection();
    if (!sec) return;
    
    if (confirm(`Are you sure you want to delete zone '${sec.name}'?`)) {
        state.project.sections.splice(state.selectedSectionIndex, 1);
        saveStateToCache();
        selectSection(0);
    }
}

// ─── TAB 1: SELECTION TREE ───────────────────────────────────────────
function renderSelectionTree() {
    const container = document.getElementById("categories-accordion");
    container.innerHTML = "";
    
    const sec = getActiveSection();
    if (!sec) return;
    
    const type = sec.section_type;
    let renderedAny = false;
    
    state.testGroupsData.categories.forEach((cat, catIdx) => {
        // Filter groups for this section type (include "any" type groups too)
        const typeGroups = cat.groups.filter(g => g.section_type === type || g.section_type === "any");
        if (typeGroups.length === 0) return;
        renderedAny = true;
        
        const item = document.createElement("div");
        item.className = "accordion-item open"; // Default open
        
        const header = document.createElement("button");
        header.className = "accordion-header";
        
        const titleSpan = document.createElement("span");
        titleSpan.textContent = cat.name;
        header.appendChild(titleSpan);
        
        const arrow = document.createElement("span");
        arrow.className = "accordion-arrow";
        arrow.textContent = "\u203A";
        header.appendChild(arrow);
        
        header.addEventListener("click", () => {
            item.classList.toggle("open");
        });
        
        item.appendChild(header);
        
        const content = document.createElement("div");
        content.className = "accordion-content";
        
        const listDiv = document.createElement("div");
        listDiv.className = "groups-list";
        
        typeGroups.forEach(group => {
            const card = document.createElement("div");
            card.className = "group-card";
            if (state.selectedClusterId === group.id) {
                card.classList.add("selected-cluster");
            }
            
            const cardHeader = document.createElement("div");
            cardHeader.className = "group-card-header";
            
            cardHeader.addEventListener("click", (e) => {
                if (e.target.closest(".checkbox-control")) {
                    return;
                }
                if (state.selectedClusterId === group.id) {
                    state.selectedClusterId = null;
                } else {
                    state.selectedClusterId = group.id;
                }
                renderSelectionTree();
            });
            
            const check = document.createElement("input");
            check.type = "checkbox";
            check.id = `chk-group-${group.id}`;
            check.checked = sec.selected_groups.includes(group.id);
            if (state.isViewOnlyLink) check.disabled = true;
            
            check.addEventListener("change", (e) => {
                if (e.target.checked) {
                    if (!sec.selected_groups.includes(group.id)) {
                        sec.selected_groups.push(group.id);
                    }
                    state.selectedClusterId = group.id; // Auto-select when checked
                } else {
                    sec.selected_groups = sec.selected_groups.filter(id => id !== group.id);
                    delete sec.dropdown_selections[group.id];
                    if (state.selectedClusterId === group.id) {
                        state.selectedClusterId = null;
                    }
                }
                saveStateToCache();
                renderSectionList();
                renderSelectionTree();
            });
            
            const checkLabel = document.createElement("label");
            checkLabel.className = "checkbox-control";
            checkLabel.appendChild(check);
            
            const lblSpan = document.createElement("span");
            lblSpan.textContent = group.label;
            checkLabel.appendChild(lblSpan);
            
            cardHeader.appendChild(checkLabel);
            card.appendChild(cardHeader);
            
            if (group.ui_type === "dropdown") {
                const casesDiv = document.createElement("div");
                casesDiv.className = `dropdown-cases-list ${sec.selected_groups.includes(group.id) ? '' : 'hidden'}`;
                
                const baseTCs = sec.session_test_cases?.[group.id] || group.test_cases || [];
                baseTCs.forEach(tc => {
                    const subLabel = document.createElement("label");
                    subLabel.className = "checkbox-control";
                    
                    const subCheck = document.createElement("input");
                    subCheck.type = "checkbox";
                    const savedSel = sec.dropdown_selections[group.id] || [];
                    subCheck.checked = savedSel.includes(tc.name);
                    if (state.isViewOnlyLink) subCheck.disabled = true;
                    
                    subCheck.addEventListener("change", (e) => {
                        let selections = sec.dropdown_selections[group.id] || [];
                        if (e.target.checked) {
                            if (!selections.includes(tc.name)) selections.push(tc.name);
                        } else {
                            selections = selections.filter(n => n !== tc.name);
                        }
                        
                        if (selections.length > 0) {
                            sec.dropdown_selections[group.id] = selections;
                            if (!sec.selected_groups.includes(group.id)) {
                                sec.selected_groups.push(group.id);
                                document.getElementById(`chk-group-${group.id}`).checked = true;
                            }
                        } else {
                            delete sec.dropdown_selections[group.id];
                        }
                        saveStateToCache();
                        renderSectionList();
                    });
                    
                    subLabel.appendChild(subCheck);
                    
                    const tcSpan = document.createElement("span");
                    tcSpan.textContent = tc.name;
                    subLabel.appendChild(tcSpan);
                    
                    casesDiv.appendChild(subLabel);
                });
                
                card.appendChild(casesDiv);
            }
            
            if (state.selectedClusterId === group.id) {
                if (!sec.session_test_cases) {
                    sec.session_test_cases = {};
                }
                if (!sec.session_test_cases[group.id]) {
                    const baseTCs = group.test_cases || [];
                    const projTCs = (sec.project_only_test_cases || []).filter(tc => tc.group_id === group.id);
                    sec.session_test_cases[group.id] = [...baseTCs, ...projTCs].map(tc => ({...tc}));
                }

                const customizerDiv = document.createElement("div");
                customizerDiv.className = "cluster-tc-customizer";
                customizerDiv.style = "margin-left: 28px; margin-top: 8px; border-left: 2px solid var(--border-color); padding-left: 14px; margin-bottom: 12px; display: flex; flex-direction: column; gap: 8px;";

                const subt = document.createElement("div");
                const prCode = (state.project.info.project_code || "").trim();
                const onlyLabel = prCode ? `${prCode} Only` : "Current Project Only";
                subt.textContent = `Customize Test Cases (${onlyLabel}):`;
                subt.style = "font-weight: 600; font-size: 11px; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.5px;";
                customizerDiv.appendChild(subt);

                const tcsList = document.createElement("div");
                tcsList.style = "display: flex; flex-direction: column; gap: 4px;";
                
                const sessionTCs = sec.session_test_cases[group.id];
                if (sessionTCs.length === 0) {
                    const emptyInfo = document.createElement("div");
                    emptyInfo.textContent = "No test cases in this cluster.";
                    emptyInfo.style = "font-size: 12px; color: var(--text-muted); font-style: italic;";
                    tcsList.appendChild(emptyInfo);
                } else {
                    sessionTCs.forEach((tc, tcIdx) => {
                        const tcItem = document.createElement("div");
                        tcItem.style = "display: flex; align-items: center; justify-content: space-between; gap: 10px; padding: 4px 8px; background: var(--bg-body); border-radius: 4px; border: 1px solid var(--border-color);";

                        const tcNameSpan = document.createElement("span");
                        tcNameSpan.textContent = tc.name;
                        tcNameSpan.style = "font-size: 12px; font-weight: 500; color: var(--text-color); overflow: hidden; text-overflow: ellipsis; white-space: nowrap;";
                        tcItem.appendChild(tcNameSpan);

                        if (!state.isViewOnlyLink) {
                            const removeBtn = document.createElement("button");
                            removeBtn.className = "btn btn-danger btn-sm";
                            removeBtn.textContent = "Remove";
                            removeBtn.style = "padding: 2px 6px; font-size: 10px; background-color: #ef4444; border-color: #ef4444; color: white;";
                            removeBtn.addEventListener("click", () => {
                                sec.session_test_cases[group.id].splice(tcIdx, 1);
                                if (group.ui_type === "dropdown" && sec.dropdown_selections[group.id]) {
                                    sec.dropdown_selections[group.id] = sec.dropdown_selections[group.id].filter(n => n !== tc.name);
                                }
                                saveStateToCache();
                                renderSelectionTree();
                                reloadActiveTabs();
                            });
                            tcItem.appendChild(removeBtn);
                        }

                        tcsList.appendChild(tcItem);
                    });
                }
                customizerDiv.appendChild(tcsList);

                if (!state.isViewOnlyLink) {
                    const addForm = document.createElement("div");
                    addForm.style = "display: none; flex-direction: column; gap: 6px; background: var(--bg-card); padding: 8px; border: 1px solid var(--border-color); border-radius: 6px; margin-top: 4px;";

                    const nameIn = document.createElement("input");
                    nameIn.type = "text";
                    nameIn.placeholder = "Test Case Name...";
                    nameIn.className = "form-input";
                    nameIn.style = "font-size: 11px; padding: 4px 8px; height: 26px;";
                    addForm.appendChild(nameIn);

                    const prereqIn = document.createElement("textarea");
                    prereqIn.placeholder = "Prerequisites (Shift + Enter for new line)...";
                    prereqIn.className = "form-input";
                    prereqIn.style = "font-size: 11px; padding: 6px 8px; height: 50px; resize: vertical; font-family: inherit;";
                    addForm.appendChild(prereqIn);

                    const actionIn = document.createElement("textarea");
                    actionIn.placeholder = "Action / Procedure (Shift + Enter for new line)...";
                    actionIn.className = "form-input";
                    actionIn.style = "font-size: 11px; padding: 6px 8px; height: 50px; resize: vertical; font-family: inherit;";
                    addForm.appendChild(actionIn);

                    const expectedIn = document.createElement("textarea");
                    expectedIn.placeholder = "Expected Result (Shift + Enter for new line)...";
                    expectedIn.className = "form-input";
                    expectedIn.style = "font-size: 11px; padding: 6px 8px; height: 50px; resize: vertical; font-family: inherit;";
                    addForm.appendChild(expectedIn);

                    const actionsRow = document.createElement("div");
                    actionsRow.style = "display: flex; gap: 6px;";

                    const saveBtn = document.createElement("button");
                    saveBtn.className = "btn btn-success btn-sm";
                    saveBtn.textContent = "Add";
                    saveBtn.style = "padding: 2px 8px; font-size: 10px;";
                    
                    const handleKeydown = (e) => {
                        if (e.key === "Enter" && !e.shiftKey) {
                            e.preventDefault();
                            saveBtn.click();
                        }
                    };
                    prereqIn.addEventListener("keydown", handleKeydown);
                    actionIn.addEventListener("keydown", handleKeydown);
                    expectedIn.addEventListener("keydown", handleKeydown);
                    saveBtn.style = "padding: 2px 8px; font-size: 10px;";
                    saveBtn.addEventListener("click", () => {
                        const tcName = nameIn.value.trim();
                        if (!tcName) {
                            alert("Test Case Name cannot be empty.");
                            return;
                        }
                        const newTC = {
                            name: tcName,
                            pre_required_state: prereqIn.value.trim(),
                            action: actionIn.value.trim(),
                            expected_result: expectedIn.value.trim()
                        };
                        sec.session_test_cases[group.id].push(newTC);
                        
                        if (group.ui_type === "dropdown") {
                            if (!sec.dropdown_selections[group.id]) {
                                sec.dropdown_selections[group.id] = [];
                            }
                            if (!sec.dropdown_selections[group.id].includes(tcName)) {
                                sec.dropdown_selections[group.id].push(tcName);
                            }
                        }

                        saveStateToCache();
                        renderSelectionTree();
                        reloadActiveTabs();
                    });
                    actionsRow.appendChild(saveBtn);

                    const cancelBtn = document.createElement("button");
                    cancelBtn.className = "btn btn-secondary btn-sm";
                    cancelBtn.textContent = "Cancel";
                    cancelBtn.style = "padding: 2px 8px; font-size: 10px;";
                    cancelBtn.addEventListener("click", () => {
                        addForm.style.display = "none";
                        toggleAddBtn.style.display = "inline-block";
                    });
                    actionsRow.appendChild(cancelBtn);
                    addForm.appendChild(actionsRow);

                    const toggleAddBtn = document.createElement("button");
                    toggleAddBtn.className = "btn btn-secondary btn-sm";
                    toggleAddBtn.textContent = "+ Add Test Case";
                    toggleAddBtn.style = "padding: 2px 8px; font-size: 11px; align-self: flex-start; margin-top: 4px;";
                    toggleAddBtn.addEventListener("click", () => {
                        addForm.style.display = "flex";
                        toggleAddBtn.style.display = "none";
                        nameIn.focus();
                    });

                    customizerDiv.appendChild(toggleAddBtn);
                    customizerDiv.appendChild(addForm);
                }

                card.appendChild(customizerDiv);
            }
            
            listDiv.appendChild(card);
        });
        
        content.appendChild(listDiv);
        item.appendChild(content);
        container.appendChild(item);
    });

    if (!renderedAny) {
        container.innerHTML = '<div style="text-align: center; padding: 40px; color: var(--text-muted); font-style: italic;">No test groups defined for this selection type.</div>';
    }
}

function filterSelectionAccordions(query) {
    document.querySelectorAll(".group-card").forEach(card => {
        const text = card.textContent.toLowerCase();
        if (text.includes(query)) {
            card.classList.remove("hidden");
        } else {
            card.classList.add("hidden");
        }
    });
}

// ─── TAB 2: VIEW TEST CASES ──────────────────────────────────────────
async function reloadViewTab() {
    const tbody = document.getElementById("view-table-body");
    tbody.innerHTML = '<tr><td colspan="7" style="text-align: center; padding: 20px;">Generating test cases preview...</td></tr>';
    
    const sec = getActiveSection();
    if (!sec) {
        tbody.innerHTML = '<tr><td colspan="7" style="text-align: center; padding: 20px;">No active section.</td></tr>';
        return;
    }

    try {
        const res = await fetchAPI(`${API_BASE}/api/generate-test-cases/`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(sec)
        });
        
        const testCases = res.test_cases || [];
        const searchQuery = document.getElementById("view-search").value.toLowerCase();
        
        // Filter in real time
        const filtered = testCases.filter(tc => {
            return tc.test_case_name.toLowerCase().includes(searchQuery) ||
                   (tc.pre_required_state && tc.pre_required_state.toLowerCase().includes(searchQuery)) ||
                   (tc.action && tc.action.toLowerCase().includes(searchQuery));
        });
        
        document.getElementById("view-count-label").textContent = `Showing ${filtered.length} test cases`;
        
        tbody.innerHTML = "";
        if (filtered.length === 0) {
            tbody.innerHTML = '<tr><td colspan="7" style="text-align: center; padding: 20px;">No matching test cases found.</td></tr>';
            return;
        }

        // Output grouped by Category dividers
        let currentCategory = null;
        filtered.forEach(tc => {
            if (tc.category !== currentCategory) {
                currentCategory = tc.category;
                
                // Add Category Section Divider Row
                const divTr = document.createElement("tr");
                divTr.className = "category-divider-row";
                
                const divTd = document.createElement("td");
                divTd.colSpan = 7;
                divTd.textContent = currentCategory;
                divTd.style.fontWeight = "bold";
                divTd.style.backgroundColor = "#1e293b";
                divTd.style.color = "#38bdf8";
                divTd.style.padding = "10px 12px";
                divTd.style.fontSize = "12px";
                divTd.style.textAlign = "left";
                
                divTr.appendChild(divTd);
                tbody.appendChild(divTr);
            }

            const tr = document.createElement("tr");
            
            const tdSr = document.createElement("td");
            tdSr.className = "cell-center";
            tdSr.textContent = tc.sr_no;
            tr.appendChild(tdSr);
            
            const tdName = document.createElement("td");
            tdName.textContent = tc.test_case_name;
            tr.appendChild(tdName);
            
            const tdPre = document.createElement("td");
            tdPre.textContent = tc.pre_required_state || "-";
            tr.appendChild(tdPre);
            
            const tdAct = document.createElement("td");
            tdAct.textContent = tc.action || "-";
            tr.appendChild(tdAct);
            
            const tdExp = document.createElement("td");
            tdExp.textContent = tc.expected_result || "-";
            tr.appendChild(tdExp);

            const tdRes = document.createElement("td");
            tdRes.className = "cell-center";
            const savedRes = sec.results[tc.test_case_name] || "Pending";
            tdRes.textContent = savedRes;
            if (savedRes === "Pass") tdRes.className += " cell-pass";
            if (savedRes === "Fail") tdRes.className += " cell-fail";
            tr.appendChild(tdRes);

            const tdObs = document.createElement("td");
            tdObs.textContent = sec.observations[tc.test_case_name] || "-";
            tr.appendChild(tdObs);
            
            tbody.appendChild(tr);
        });
    } catch (e) {
        tbody.innerHTML = `<tr><td colspan="7" style="text-align: center; padding: 20px; color: #ef4444;">Error building preview: ${e.message}</td></tr>`;
    }
}

// ─── TAB 3: GUIDED TEST EXECUTION ────────────────────────────────────
async function reloadGuidedTab() {
    const sec = getActiveSection();
    const mainCard = document.getElementById("guided-main-card");
    const emptyMsg = document.getElementById("guided-empty-message");

    if (!sec) {
        mainCard.classList.add("hidden");
        emptyMsg.classList.remove("hidden");
        return;
    }

    try {
        const res = await fetchAPI(`${API_BASE}/api/generate-test-cases/`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(sec)
        });
        
        state.guidedTestCases = res.test_cases || [];
        if (state.guidedTestCases.length === 0) {
            mainCard.classList.add("hidden");
            emptyMsg.classList.remove("hidden");
            return;
        }

        mainCard.classList.remove("hidden");
        emptyMsg.classList.add("hidden");
        
        if (state.guidedCurrentIndex >= state.guidedTestCases.length) {
            state.guidedCurrentIndex = Math.max(0, state.guidedTestCases.length - 1);
        }

        showGuidedTestCase();
    } catch (e) {
        showStatus("Error loading guided execution list", "#ef4444");
    }
}

function showGuidedTestCase() {
    const tc = state.guidedTestCases[state.guidedCurrentIndex];
    if (!tc) return;
    const sec = getActiveSection();

    const count = state.guidedTestCases.length;
    document.getElementById("guided-progress-label").textContent = `Test Case ${state.guidedCurrentIndex + 1} of ${count}`;
    document.getElementById("guided-progress-bar").style.width = `${((state.guidedCurrentIndex + 1) / count) * 100}%`;

    document.getElementById("guided-title").textContent = `${tc.sr_no}. ${tc.test_case_name}`;
    document.getElementById("guided-prereq").textContent = tc.pre_required_state || "-";
    document.getElementById("guided-action").textContent = tc.action || "-";
    document.getElementById("guided-expected").textContent = tc.expected_result || "-";

    const savedRes = sec.results[tc.test_case_name] || "Pending";
    document.querySelectorAll("#guided-result-segmented .segment-btn").forEach(btn => {
        if (btn.getAttribute("data-val") === savedRes) {
            btn.classList.add("active");
        } else {
            btn.classList.remove("active");
        }
    });

    document.getElementById("guided-observation").value = sec.observations[tc.test_case_name] || "";

    document.getElementById("guided-btn-prev").disabled = state.guidedCurrentIndex === 0;
    
    const nextBtn = document.getElementById("guided-btn-next");
    if (state.guidedCurrentIndex === count - 1) {
        nextBtn.textContent = "Finish";
    } else {
        nextBtn.textContent = "Next";
    }
}

function saveGuidedProgress() {
    const tc = state.guidedTestCases[state.guidedCurrentIndex];
    if (!tc) return;
    const sec = getActiveSection();

    const resBtn = document.querySelector("#guided-result-segmented .segment-btn.active");
    const result = resBtn ? resBtn.getAttribute("data-val") : "Pending";
    const obs = document.getElementById("guided-observation").value.trim();

    sec.results[tc.test_case_name] = result;
    if (obs) {
        sec.observations[tc.test_case_name] = obs;
    } else {
        delete sec.observations[tc.test_case_name];
    }
    saveStateToCache();
    pushReportUpdate();
}

function guidedPrev() {
    saveGuidedProgress();
    if (state.guidedCurrentIndex > 0) {
        state.guidedCurrentIndex--;
        showGuidedTestCase();
    }
}

// Navigation validation: Must mark Pass or Fail to proceed forward
function validateGuidedPassFail() {
    const tc = state.guidedTestCases[state.guidedCurrentIndex];
    if (!tc) return false;
    const sec = getActiveSection();
    const result = sec.results[tc.test_case_name] || "Pending";
    
    if (result !== "Pass" && result !== "Fail") {
        alert("Validation Error: Please mark this test case as either Pass or Fail before proceeding.");
        return false;
    }
    return true;
}

function guidedNext() {
    if (!validateGuidedPassFail()) return;
    saveGuidedProgress();
    if (state.guidedCurrentIndex < state.guidedTestCases.length - 1) {
        state.guidedCurrentIndex++;
        showGuidedTestCase();
    } else {
        reloadGuidedTab();
    }
}

function guidedSkip() {
    saveGuidedProgress();
    if (state.guidedCurrentIndex < state.guidedTestCases.length - 1) {
        state.guidedCurrentIndex++;
        showGuidedTestCase();
    }
}

// ─── TAB 4: TEST CASE MANAGER ─────────────────────────────────
function reloadCustomManagerTab() {
    showManagerScreen("menu");
}

async function loadCustomTCsList() {
    const groupSelect = document.getElementById("custom-tc-group");
    groupSelect.innerHTML = "";
    
    const sec = getActiveSection();
    if (sec && sec.section_type !== "conveyor" && sec.section_type !== "vrc") {
        const clusters = sec.custom_clusters || [];
        clusters.forEach(cluster => {
            const opt = document.createElement("option");
            opt.value = cluster.id;
            opt.textContent = cluster.name;
            groupSelect.appendChild(opt);
        });
    } else {
        state.testGroupsData.categories.forEach(cat => {
            cat.groups.forEach(group => {
                const opt = document.createElement("option");
                opt.value = group.id;
                opt.textContent = `${group.label} (${cat.name})`;
                groupSelect.appendChild(opt);
            });
        });
    }

    const listContainer = document.getElementById("custom-tcs-list");
    listContainer.innerHTML = '<p style="padding: 15px; text-align: center;">Loading custom test cases...</p>';

    if (!sec) {
        listContainer.innerHTML = '<p style="padding: 15px; text-align: center;">Please select a section first.</p>';
        return;
    }

    try {
        const customRes = await fetchAPI(`${API_BASE}/api/custom-test-cases/`);
        state.permanentCustomTestCases = customRes.custom_test_cases || [];

        const allCustom = [];
        state.permanentCustomTestCases.forEach(tc => {
            allCustom.push({ tc, scope: "Permanent" });
        });
        sec.project_only_test_cases.forEach(tc => {
            allCustom.push({ tc, scope: "Project Only" });
        });

        listContainer.innerHTML = "";
        if (allCustom.length === 0) {
            listContainer.innerHTML = '<p style="padding: 15px; text-align: center; color: var(--text-muted);">No custom test cases found.</p>';
            return;
        }

        allCustom.forEach(item => {
            const div = document.createElement("div");
            div.className = "custom-tc-item";

            const details = document.createElement("div");
            details.className = "custom-tc-details";

            const name = document.createElement("span");
            name.className = "custom-tc-name";
            name.textContent = item.tc.name;
            details.appendChild(name);

            const meta = document.createElement("span");
            meta.className = `custom-tc-meta ${item.scope === 'Permanent' ? 'scope-perm' : ''}`;
            
            let groupLabel = item.tc.group_id;
            state.testGroupsData.categories.forEach(c => {
                const g = c.groups.find(gr => gr.id === item.tc.group_id);
                if (g) groupLabel = g.label;
            });

            meta.textContent = `Scope: ${item.scope}  |  Group: ${groupLabel}`;
            details.appendChild(meta);
            div.appendChild(details);

            const actions = document.createElement("div");
            actions.className = "custom-tc-actions";

            const editBtn = document.createElement("button");
            editBtn.className = "btn btn-secondary btn-sm";
            editBtn.textContent = "Edit";
            if (state.isViewOnlyLink) editBtn.disabled = true;
            editBtn.addEventListener("click", () => startEditCustomTestCase(item.tc, item.scope));
            actions.appendChild(editBtn);

            const deleteBtn = document.createElement("button");
            deleteBtn.className = "btn btn-danger btn-sm";
            deleteBtn.textContent = "Delete";
            if (state.isViewOnlyLink) deleteBtn.disabled = true;
            deleteBtn.addEventListener("click", () => deleteCustomTestCase(item.tc, item.scope));
            actions.appendChild(deleteBtn);

            div.appendChild(actions);
            listContainer.appendChild(div);
        });
    } catch (e) {
        listContainer.innerHTML = `<p style="padding: 15px; text-align: center; color: #ef4444;">Error loading custom list: ${e.message}</p>`;
    }
}

function startEditCustomTestCase(tc, scope) {
    if (state.isViewOnlyLink) return;
    state.customEditingOldName = tc.name;

    document.getElementById("custom-tc-name").value = tc.name;
    document.getElementById("custom-tc-prereq").value = tc.pre_required_state || "";
    document.getElementById("custom-tc-action").value = tc.action || "";
    document.getElementById("custom-tc-expected").value = tc.expected_result || "";
    document.getElementById("custom-tc-group").value = tc.group_id;
    
    document.querySelectorAll('input[name="custom-scope"]').forEach(radio => {
        radio.checked = radio.value === scope;
    });

    document.getElementById("custom-form-title").textContent = "Edit Custom Test Case";
    document.getElementById("btn-custom-save").textContent = "Update Test Case";
    document.getElementById("btn-custom-cancel").classList.remove("hidden");
}

function clearCustomForm() {
    state.customEditingOldName = null;
    document.getElementById("custom-tc-name").value = "";
    document.getElementById("custom-tc-prereq").value = "";
    document.getElementById("custom-tc-action").value = "";
    document.getElementById("custom-tc-expected").value = "";
    
    document.getElementById("custom-form-title").textContent = "Add Custom Test Case";
    document.getElementById("btn-custom-save").textContent = "Save Test Case";
    document.getElementById("btn-custom-cancel").classList.add("hidden");
}

async function saveCustomTestCase() {
    if (state.isViewOnlyLink) return;
    const sec = getActiveSection();
    if (!sec) return;

    const name = document.getElementById("custom-tc-name").value.trim();
    const prereq = document.getElementById("custom-tc-prereq").value.trim();
    const action = document.getElementById("custom-tc-action").value.trim();
    const expected = document.getElementById("custom-tc-expected").value.trim();
    const groupId = document.getElementById("custom-tc-group").value;
    
    const scopeBtn = document.querySelector('input[name="custom-scope"]:checked');
    const scope = scopeBtn ? scopeBtn.value : "Project Only";

    if (!name || !prereq || !action || !expected) {
        alert("All fields are required.");
        return;
    }

    const tc = {
        name: name,
        pre_required_state: prereq,
        action: action,
        expected_result: expected,
        group_id: groupId
    };

    try {
        if (state.customEditingOldName) {
            await fetchAPI(`${API_BASE}/api/custom-test-cases/delete/`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ name: state.customEditingOldName })
            });
            sec.project_only_test_cases = sec.project_only_test_cases.filter(item => item.name !== state.customEditingOldName);
        }

        if (scope === "Permanent") {
            await fetchAPI(`${API_BASE}/api/custom-test-cases/add/`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(tc)
            });
        } else {
            sec.project_only_test_cases.push(tc);
        }

        clearCustomForm();
        saveStateToCache();
        refreshEntireUI();
    } catch (e) {
        alert(`Failed to save custom test case: ${e.message}`);
    }
}

async function deleteCustomTestCase(tc, scope) {
    if (state.isViewOnlyLink) return;
    const sec = getActiveSection();
    if (!sec) return;

    if (confirm(`Are you sure you want to delete custom test case '${tc.name}'?`)) {
        try {
            if (scope === "Permanent") {
                await fetchAPI(`${API_BASE}/api/custom-test-cases/delete/`, {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ name: tc.name })
                });
            } else {
                sec.project_only_test_cases = sec.project_only_test_cases.filter(item => item.name !== tc.name);
            }
            saveStateToCache();
            refreshEntireUI();
        } catch (e) {
            alert(`Failed to delete: ${e.message}`);
        }
    }
}

// ─── BOTTOM ACTION BUTTONS ───────────────────────────────────────────
function saveProjectToFile() {
    const filename = `${state.project.info.project_code || 'EFS'}-project-config.json`;
    const jsonStr = JSON.stringify(state.project, null, 2);
    
    const blob = new Blob([jsonStr], { type: "application/json" });
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    showStatus("Project configuration saved.", "#059669");
}

function loadProjectFromFile(e) {
    if (state.isViewOnlyLink) return;
    const file = e.target.files[0];
    if (!file) return;

    const reader = new FileReader();
    reader.onload = (evt) => {
        try {
            const parsed = JSON.parse(evt.target.result);
            if (parsed && parsed.info && parsed.sections) {
                state.project = parsed;
                applyProjectToUI();
                selectSection(0);
                saveStateToCache();
                showStatus("Project configuration loaded successfully.", "#059669");
            } else {
                alert("Invalid project file structure.");
            }
        } catch (err) {
            alert("Failed to parse project file.");
        }
    };
    reader.readAsText(file);
    e.target.value = ""; // Clear file picker
}

function handleUnlockedCheckboxChange(e) {
    if (e.target.checked) {
        document.getElementById("chk-view-only").checked = false; // Deselect view-only
        showStatus("Export unlocked.", "#059669");
    }
}

function handleViewOnlyCheckboxChange(e) {
    if (e.target.checked) {
        document.getElementById("chk-unlocked").checked = false; // Deselect unlocked
        showStatus("View-only export enabled (full lock).", "#2563eb");
    }
}

// ─── EXPORT OPTIONS CHOICE MODAL ACTIONS ─────────────────────────────
function openExportChoiceModal() {
    // 1. Mandatory Validator Name check before allowing export dialog
    const valType = document.getElementById("validator-type").value;
    const valName = document.getElementById("validator-name").value.trim();
    
    if ((valType === "Internal Validator" || valType === "External Validator") && !valName) {
        showStatus("Validation Error: Validator Name is mandatory.", "#ef4444");
        alert("Please enter the Validator Name before generating the test sheet.");
        return;
    }

    document.getElementById("export-choice-modal").classList.add("open");
    document.getElementById("shareable-link-box").classList.add("hidden");
    document.getElementById("shareable-link-url").value = "";
}

function closeExportChoiceModal() {
    document.getElementById("export-choice-modal").classList.remove("open");
}

function generateShareableViewOnlyLink() {
    // Use server-side report session for true network sharing
    fetch(`${API_BASE}/api/report/create/`, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-CSRFToken": getCSRFToken() },
        body: JSON.stringify({ project: state.project })
    })
    .then(res => res.json())
    .then(data => {
        if (data.success && data.report_id) {
            state.activeReportId = data.report_id;
            const shareableUrl = `${window.location.origin}${API_BASE}/report/?id=${data.report_id}`;

            const urlInput = document.getElementById("shareable-link-url");
            urlInput.value = shareableUrl;
            
            document.getElementById("shareable-link-box").classList.remove("hidden");
            showStatus("Live shareable link generated. Updates will sync automatically.", "#059669");
        } else {
            throw new Error(data.error || "Failed to create report session");
        }
    })
    .catch(e => {
        alert("Failed to generate shareable link: " + e.message);
    });
}

// Push updated project data to an active report session
function pushReportUpdate() {
    if (!state.activeReportId) return;
    fetch(`${API_BASE}/api/report/update/${state.activeReportId}/`, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-CSRFToken": getCSRFToken() },
        body: JSON.stringify({ project: state.project })
    }).catch(e => console.warn("Report update failed:", e));
}

function copyShareableLinkToClipboard() {
    const urlInput = document.getElementById("shareable-link-url");
    urlInput.select();
    urlInput.setSelectionRange(0, 99999); // Mobile
    navigator.clipboard.writeText(urlInput.value);
    showStatus("Link copied to clipboard!", "#059669");
    alert("Shareable View-Only Link copied to clipboard!");
}

// ─── EXCEL WORKBOOK GENERATOR ────────────────────────────────────────
async function generateProjectExcel() {
    showStatus("Generating Excel sheet...", "#3b82f6");

    try {
        const protect = !document.getElementById("chk-unlocked").checked;
        const viewOnly = document.getElementById("chk-view-only").checked;

        const res = await fetch(`${API_BASE}/api/generate-workbook/`, {
            method: "POST",
            headers: { "Content-Type": "application/json", "X-CSRFToken": getCSRFToken() },
            body: JSON.stringify({
                project: state.project,
                protect_sheets: protect,
                view_only: viewOnly
            })
        });

        if (!res.ok) {
            const err = await res.json();
            throw new Error(err.error || "Generation failed");
        }

        const blob = await res.blob();
        const header = res.headers.get("Content-Disposition");
        let filename = "EFS-Commissioning-Test-Cases.xlsx";
        if (header) {
            const filenameRegex = /filename[^;=\n]*=((['"]).*?\2|[^;\n]*)/;
            const matches = filenameRegex.exec(header);
            if (matches != null && matches[1]) {
                filename = matches[1].replace(/['"]/g, '');
            }
        }

        const link = document.createElement("a");
        link.href = URL.createObjectURL(blob);
        link.download = filename;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);

        showStatus("Excel workbook generated successfully!", "#059669");
    } catch (e) {
        showStatus(`Excel Generation Error: ${e.message}`, "#ef4444");
        alert(`Failed to generate Excel: ${e.message}`);
    }
}

// Single section direct export from View tab
async function exportSingleSectionExcel() {
    const sec = getActiveSection();
    if (!sec) return;

    const dummyProject = {
        info: state.project.info,
        sections: [sec]
    };

    const btn = document.getElementById("btn-export-excel");
    btn.disabled = true;
    btn.textContent = "Exporting...";

    try {
        const protect = !document.getElementById("chk-unlocked").checked;
        const viewOnly = document.getElementById("chk-view-only").checked;

        const res = await fetch(`${API_BASE}/api/generate-workbook/`, {
            method: "POST",
            headers: { "Content-Type": "application/json", "X-CSRFToken": getCSRFToken() },
            body: JSON.stringify({
                project: dummyProject,
                protect_sheets: protect,
                view_only: viewOnly
            })
        });

        if (!res.ok) throw new Error("Export failed");

        const blob = await res.blob();
        const link = document.createElement("a");
        link.href = URL.createObjectURL(blob);
        link.download = `${sec.name}-TEST-CASES.xlsx`;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);

        showStatus(`Zone '${sec.name}' exported successfully!`, "#059669");
    } catch (e) {
        alert("Failed to export zone to Excel.");
    } finally {
        btn.disabled = false;
        btn.textContent = "Export to Excel";
    }
}

// ─── CHANGELOG MODAL ACTIONS ─────────────────────────────────────────
async function openChangelogModal() {
    const modal = document.getElementById("changelog-modal");
    const body = document.getElementById("changelog-modal-body");
    body.innerHTML = "<p>Loading version logs...</p>";
    modal.classList.add("open");

    try {
        const res = await fetchAPI(`${API_BASE}/api/changelog/`);
        body.innerHTML = "";
        
        res.changelog.forEach(entry => {
            const div = document.createElement("div");
            div.className = "changelog-entry"
            div.style.marginBottom = "15px";
            div.style.borderBottom = "1px solid var(--border-color)";
            div.style.paddingBottom = "10px";

            const h4 = document.createElement("h4");
            h4.style.fontSize = "14px";
            h4.style.color = "var(--primary-color)";
            h4.textContent = `Version ${entry.version} (${entry.date})`;
            div.appendChild(h4);

            const ul = document.createElement("ul");
            ul.style.paddingLeft = "20px";
            ul.style.marginTop = "5px";
            ul.style.fontSize = "12px";

            entry.changes.forEach(change => {
                const li = document.createElement("li");
                li.style.marginBottom = "4px";
                li.textContent = change;
                ul.appendChild(li);
            });

            div.appendChild(ul);
            body.appendChild(div);
        });
    } catch (e) {
        body.innerHTML = `<p style="color: #ef4444;">Failed to load logs: ${e.message}</p>`;
    }
}

function closeChangelogModal() {
    document.getElementById("changelog-modal").classList.remove("open");
}

// ─── RELOAD UTILITIES ────────────────────────────────────────────────
function reloadActiveTabs() {
    const activeTab = document.querySelector(".tab-btn.active");
    if (!activeTab) return;
    
    const tabId = activeTab.getAttribute("data-tab");
    if (tabId === "tab-view") reloadViewTab();
    else if (tabId === "tab-guided") reloadGuidedTab();
    else if (tabId === "tab-summary") renderSummaryTab();
}

function refreshEntireUI() {
    renderSelectionTree();
    renderSectionList();
    renderSectionTypeToggles();
    if (typeof reloadViewTab === "function") reloadViewTab();
    if (typeof reloadGuidedTab === "function") reloadGuidedTab();
    if (typeof renderSummaryTab === "function") renderSummaryTab();
    if (typeof loadCustomTCsList === "function") loadCustomTCsList();
    if (typeof loadSelectionsList === "function") loadSelectionsList();
}

function showStatus(msg, color) {
    const el = document.getElementById("panel-status-text");
    el.textContent = msg;
    if (color) el.style.color = color;
}

// ─── v2.3 RELEASE HELPER FUNCTIONS ──────────────────────────────────
function selectAllVisibleTCs() {
    const sec = getActiveSection();
    if (!sec) return;
    const type = sec.section_type;
    
    state.testGroupsData.categories.forEach(cat => {
        const typeGroups = cat.groups.filter(g => g.section_type === type);
        typeGroups.forEach(group => {
            if (!sec.selected_groups.includes(group.id)) {
                sec.selected_groups.push(group.id);
            }
            if (group.ui_type === "dropdown") {
                const baseTCs = sec.session_test_cases?.[group.id] || group.test_cases || [];
                const allNames = baseTCs.map(tc => tc.name);
                sec.dropdown_selections[group.id] = allNames;
            }
        });
    });
    
    saveStateToCache();
    renderSelectionTree();
    reloadActiveTabs();
    showStatus("Selected all visible test cases", "#10b981");
}

function deselectAllVisibleTCs() {
    const sec = getActiveSection();
    if (!sec) return;
    const type = sec.section_type;
    
    state.testGroupsData.categories.forEach(cat => {
        const typeGroups = cat.groups.filter(g => g.section_type === type);
        typeGroups.forEach(group => {
            sec.selected_groups = sec.selected_groups.filter(id => id !== group.id);
            delete sec.dropdown_selections[group.id];
        });
    });
    
    saveStateToCache();
    renderSelectionTree();
    reloadActiveTabs();
    showStatus("Deselected all visible test cases", "#3b82f6");
}

function duplicateActiveSection() {
    const sec = getActiveSection();
    if (!sec) return;
    
    const newName = prompt("Enter a name for the duplicated zone:", `${sec.name}_Copy`);
    if (!newName) return;
    
    const cleanName = newName.trim();
    if (!cleanName) return;
    
    if (state.project.sections.some(s => s.name.toLowerCase() === cleanName.toLowerCase())) {
        alert("Error: A zone with this name already exists.");
        return;
    }
    
    const copy = {
        name: cleanName,
        section_type: sec.section_type,
        selected_groups: [...sec.selected_groups],
        dropdown_selections: JSON.parse(JSON.stringify(sec.dropdown_selections || {})),
        results: JSON.parse(JSON.stringify(sec.results || {})),
        observations: JSON.parse(JSON.stringify(sec.observations || {})),
        project_only_test_cases: JSON.parse(JSON.stringify(sec.project_only_test_cases || []))
    };
    
    state.project.sections.push(copy);
    state.selectedSectionIndex = state.project.sections.length - 1;
    
    saveStateToCache();
    renderSectionList();
    selectSection(state.selectedSectionIndex);
    showStatus(`Duplicated section as '${cleanName}'`, "#10b981");
}

function onGuidedSearchTyping(e) {
    const query = e.target.value.toLowerCase().trim();
    const resultsDiv = document.getElementById("guided-search-results");
    resultsDiv.innerHTML = "";

    if (!query || state.guidedTestCases.length === 0) {
        resultsDiv.classList.add("hidden");
        return;
    }

    const matches = state.guidedTestCases.filter(tc => 
        tc.sr_no.toLowerCase().includes(query) || 
        tc.test_case_name.toLowerCase().includes(query)
    );

    if (matches.length === 0) {
        const item = document.createElement("div");
        item.className = "guided-search-item";
        item.textContent = "No matches found";
        resultsDiv.appendChild(item);
    } else {
        matches.forEach(tc => {
            const item = document.createElement("div");
            item.className = "guided-search-item";
            item.textContent = `[${tc.sr_no}] ${tc.test_case_name}`;
            item.addEventListener("click", () => {
                const idx = state.guidedTestCases.findIndex(t => t.test_case_name === tc.test_case_name);
                if (idx !== -1) {
                    saveGuidedProgress();
                    state.guidedCurrentIndex = idx;
                    showGuidedTestCase();
                    resultsDiv.classList.add("hidden");
                    document.getElementById("guided-search-input").value = "";
                }
            });
            resultsDiv.appendChild(item);
        });
    }
    resultsDiv.classList.remove("hidden");
}

// Close guided search results on clicking outside
document.addEventListener("click", (e) => {
    const resultsDiv = document.getElementById("guided-search-results");
    if (resultsDiv && !e.target.closest(".guided-search-container")) {
        resultsDiv.classList.add("hidden");
    }
});

function showManagerScreen(viewName) {
    const selection = document.getElementById("manager-selection-screen");
    const customView = document.getElementById("custom-tc-manager-view");
    const editView = document.getElementById("edit-tc-manager-view");
    const templateView = document.getElementById("template-manager-view");
    const selectionView = document.getElementById("selection-manager-view");
    const backBtn = document.getElementById("btn-manager-back");

    selection.classList.add("hidden");
    customView.classList.add("hidden");
    editView.classList.add("hidden");
    if (templateView) templateView.classList.add("hidden");
    if (selectionView) selectionView.classList.add("hidden");
    backBtn.classList.add("hidden");

    if (viewName === "menu") {
        selection.classList.remove("hidden");
    } else if (viewName === "custom") {
        customView.classList.remove("hidden");
        backBtn.classList.remove("hidden");
        loadCustomTCsList();
    } else if (viewName === "edit") {
        editView.classList.remove("hidden");
        backBtn.classList.remove("hidden");
        reloadEditTCManagerTab();
    } else if (viewName === "template") {
        if (templateView) templateView.classList.remove("hidden");
        backBtn.classList.remove("hidden");
        
        const targetSelect = document.getElementById("template-target-selection");
        if (targetSelect) {
            targetSelect.innerHTML = '<option value="">-- Choose Selection --</option>';
            
            const activeTypes = getActiveSelectionTypes();
            activeTypes.forEach(t => {
                const opt = document.createElement("option");
                const lower = t.toLowerCase();
                opt.value = (lower === "conveyor" || lower === "vrc") ? lower : t;
                opt.textContent = t.charAt(0).toUpperCase() + t.slice(1);
                targetSelect.appendChild(opt);
            });
            
            targetSelect.value = "";
            document.getElementById("btn-template-upload").disabled = true;
        }
    } else if (viewName === "selection") {
        if (selectionView) selectionView.classList.remove("hidden");
        backBtn.classList.remove("hidden");
        loadSelectionsList();
        cancelSelectionEdit();
    }
}

function reloadEditTCManagerTab() {
    const selSelect = editEl("edit-selection-select");
    if (!selSelect) return;
    
    selSelect.innerHTML = "";
    
    const activeTypes = getActiveSelectionTypes();
    activeTypes.forEach(name => {
        const opt = document.createElement("option");
        opt.value = name;
        opt.textContent = name;
        selSelect.appendChild(opt);
    });
    
    onEditSelectionChanged();
}

function onEditSelectionChanged() {
    const selSelect = editEl("edit-selection-select");
    const select = editEl("edit-group-select");
    if (!selSelect || !select) return;
    
    const selectedSelection = selSelect.value;
    const selectedSelectionLower = selectedSelection.toLowerCase();
    
    select.innerHTML = "";
    
    state.testGroupsData.categories.forEach(cat => {
        cat.groups.forEach(group => {
            const grpType = group.section_type || "any";
            if (grpType === "any" || grpType === selectedSelectionLower) {
                const opt = document.createElement("option");
                opt.value = group.id;
                opt.textContent = `${group.label} (${cat.name})`;
                select.appendChild(opt);
            }
        });
    });
    
    populateTargetGroupDropdown();
    onEditGroupSelected();
}

async function saveTestGroupsDataPermanently() {
    try {
        await fetchAPI(`${API_BASE}/api/edit-test-groups/`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ categories: state.testGroupsData.categories })
        });
        showStatus("Test library updated permanently.", "#10b981");
    } catch (e) {
        alert(`Failed to save changes: ${e.message}`);
    }
}

async function onEditGroupAdd() {
    const selSelect = editEl("edit-selection-select");
    if (!selSelect) return;
    const targetSelection = selSelect.value;
    if (!targetSelection) {
        alert("Please select a Selection type first.");
        return;
    }
    
    const catName = prompt("Enter Type Name (e.g. Conveyor Operation):");
    if (!catName || !catName.trim()) return;
    const cleanCatName = catName.trim();
    
    const groupLabel = prompt("Enter Cluster Label (e.g. Standard Features):");
    if (!groupLabel || !groupLabel.trim()) return;
    const cleanGroupLabel = groupLabel.trim();
    
    let targetCat = state.testGroupsData.categories.find(c => c.name.toLowerCase() === cleanCatName.toLowerCase());
    if (!targetCat) {
        const catId = "cat_" + Date.now();
        const catNum = state.testGroupsData.categories.length + 1;
        targetCat = {
            name: cleanCatName,
            id: catId,
            category_number: catNum,
            groups: []
        };
        state.testGroupsData.categories.push(targetCat);
    }
    
    const groupId = "group_" + Date.now();
    const newGroup = {
        id: groupId,
        label: cleanGroupLabel,
        section_type: targetSelection.toLowerCase(),
        ui_type: "checkbox",
        test_cases: []
    };
    targetCat.groups.push(newGroup);
    
    await saveTestGroupsDataPermanently();
    reloadEditTCManagerTab();
    
    const fullLabel = `${cleanGroupLabel} (${targetCat.name})`;
    const select = editEl("edit-group-select");
    for (let i = 0; i < select.options.length; i++) {
        if (select.options[i].text === fullLabel) {
            select.selectedIndex = i;
            break;
        }
    }
    onEditGroupSelected();
    refreshEntireUI();
}

async function onEditGroupRename() {
    const groupId = editEl("edit-group-select").value;
    if (!groupId) {
        alert("Please select a Cluster first.");
        return;
    }
    
    let targetGroup = null;
    let targetCat = null;
    state.testGroupsData.categories.forEach(cat => {
        cat.groups.forEach(group => {
            if (group.id === groupId) {
                targetGroup = group;
                targetCat = cat;
            }
        });
    });
    
    if (!targetGroup) return;
    
    const newLabel = prompt("Rename Cluster to:", targetGroup.label);
    if (!newLabel || !newLabel.trim() || newLabel.trim() === targetGroup.label) return;
    const cleanNewLabel = newLabel.trim();
    
    targetGroup.label = cleanNewLabel;
    
    await saveTestGroupsDataPermanently();
    reloadEditTCManagerTab();
    
    const fullLabel = `${cleanNewLabel} (${targetCat.name})`;
    const select = editEl("edit-group-select");
    for (let i = 0; i < select.options.length; i++) {
        if (select.options[i].text === fullLabel) {
            select.selectedIndex = i;
            break;
        }
    }
    onEditGroupSelected();
    refreshEntireUI();
}

async function onEditGroupDelete() {
    const groupId = editEl("edit-group-select").value;
    if (!groupId) {
        alert("Please select a Cluster first.");
        return;
    }
    
    let targetGroup = null;
    let targetCat = null;
    state.testGroupsData.categories.forEach(cat => {
        cat.groups.forEach(group => {
            if (group.id === groupId) {
                targetGroup = group;
                targetCat = cat;
            }
        });
    });
    
    if (!targetGroup) return;
    
    if (!confirm(`Are you sure you want to delete the Cluster "${targetGroup.label}"?\nAll test cases inside this cluster will be permanently deleted.`)) {
        return;
    }
    
    targetCat.groups = targetCat.groups.filter(g => g.id !== groupId);
    if (targetCat.groups.length === 0) {
        state.testGroupsData.categories = state.testGroupsData.categories.filter(c => c.id !== targetCat.id);
    }
    
    await saveTestGroupsDataPermanently();
    reloadEditTCManagerTab();
    refreshEntireUI();
}

async function moveEditGroup(direction) {
    const groupId = editEl("edit-group-select").value;
    if (!groupId) return;
    
    let targetGroup = null;
    let targetCat = null;
    state.testGroupsData.categories.forEach(cat => {
        cat.groups.forEach(group => {
            if (group.id === groupId) {
                targetGroup = group;
                targetCat = cat;
            }
        });
    });
    
    if (!targetGroup || !targetCat) return;
    
    const groups = targetCat.groups;
    const idx = groups.indexOf(targetGroup);
    const nextIdx = idx + direction;
    if (nextIdx < 0 || nextIdx >= groups.length) return;
    
    // Swap
    groups[idx] = groups[nextIdx];
    groups[nextIdx] = targetGroup;
    
    await saveTestGroupsDataPermanently();
    
    const fullLabel = `${targetGroup.label} (${targetCat.name})`;
    reloadEditTCManagerTab();
    
    const select = editEl("edit-group-select");
    for (let i = 0; i < select.options.length; i++) {
        if (select.options[i].text === fullLabel) {
            select.selectedIndex = i;
            break;
        }
    }
    onEditGroupSelected();
    refreshEntireUI();
}

async function onEditAddTC() {
    const groupId = editEl("edit-group-select").value;
    if (!groupId) {
        alert("Please select a Group/Cluster first.");
        return;
    }
    
    let targetGroup = null;
    state.testGroupsData.categories.forEach(cat => {
        cat.groups.forEach(group => {
            if (group.id === groupId) {
                targetGroup = group;
            }
        });
    });
    
    if (!targetGroup) return;
    
    const name = prompt("Enter Test Case Name:");
    if (!name || !name.trim()) return;
    
    const newTC = {
        name: name.trim(),
        pre_required_state: "",
        action: "",
        expected_result: ""
    };
    
    if (!targetGroup.test_cases) {
        targetGroup.test_cases = [];
    }
    targetGroup.test_cases.push(newTC);
    
    await saveTestGroupsDataPermanently();
    
    onEditGroupSelected();
    
    setTimeout(() => {
        const listDiv = editEl("edit-tcs-list");
        const cards = listDiv.querySelectorAll(".edit-tc-item");
        if (cards.length > 0) {
            cards[cards.length - 1].click();
        }
    }, 100);
    
    refreshEntireUI();
}


let currentEditGroupTestCases = [];
let selectedEditTCIndex = null;
let _editPrefix = ""; // "" for in-app, "overlay-" for overlay

function editEl(shortId) {
    return document.getElementById(_editPrefix + shortId);
}

function onEditGroupSelected() {
    const groupId = editEl("edit-group-select").value;
    selectedEditTCIndex = null;
    clearEditFormFields();

    currentEditGroupTestCases = [];
    state.testGroupsData.categories.forEach(cat => {
        cat.groups.forEach(group => {
            if (group.id === groupId) {
                currentEditGroupTestCases = group.test_cases || [];
            }
        });
    });

    renderEditTCList();
}

function renderEditTCList() {
    const list = editEl("edit-tcs-list");
    list.innerHTML = "";

    currentEditGroupTestCases.forEach((tc, idx) => {
        const div = document.createElement("div");
        div.className = "edit-tc-item";
        if (idx === selectedEditTCIndex) {
            div.classList.add("selected");
        }
        div.textContent = tc.name;
        div.addEventListener("click", () => {
            selectedEditTCIndex = idx;
            renderEditTCList();
            loadEditTCFields(tc);
        });
        list.appendChild(div);
    });
}

function populateTargetGroupDropdown() {
    const selSelect = editEl("edit-selection-select");
    const targetDropdown = editEl("edit-tc-target-group");
    if (!selSelect || !targetDropdown) return;
    
    const selectedSelection = selSelect.value;
    const selectedSelectionLower = selectedSelection.toLowerCase();
    
    targetDropdown.innerHTML = "";
    
    // Add empty option
    const emptyOpt = document.createElement("option");
    emptyOpt.value = "";
    emptyOpt.textContent = "-- Select Cluster --";
    targetDropdown.appendChild(emptyOpt);
    
    state.testGroupsData.categories.forEach(cat => {
        cat.groups.forEach(group => {
            const grpType = group.section_type || "any";
            if (grpType === "any" || grpType === selectedSelectionLower) {
                const opt = document.createElement("option");
                opt.value = group.id;
                opt.textContent = `${group.label} (${cat.name})`;
                targetDropdown.appendChild(opt);
            }
        });
    });
}

function loadEditTCFields(tc) {
    editEl("edit-tc-name").value = tc.name;
    editEl("edit-tc-prereq").value = tc.pre_required_state || "";
    editEl("edit-tc-action").value = tc.action || "";
    editEl("edit-tc-expected").value = tc.expected_result || "";
    
    const groupId = editEl("edit-group-select").value;
    const targetDropdown = editEl("edit-tc-target-group");
    if (targetDropdown) {
        targetDropdown.value = groupId;
    }
}

function clearEditFormFields() {
    editEl("edit-tc-name").value = "";
    editEl("edit-tc-prereq").value = "";
    editEl("edit-tc-action").value = "";
    editEl("edit-tc-expected").value = "";
    
    const targetDropdown = editEl("edit-tc-target-group");
    if (targetDropdown) {
        targetDropdown.value = "";
    }
}

async function saveEditedTC() {
    if (selectedEditTCIndex === null) {
        alert("Please select a test case to edit first.");
        return;
    }

    const name = editEl("edit-tc-name").value.trim();
    const prereq = editEl("edit-tc-prereq").value.trim();
    const action = editEl("edit-tc-action").value.trim();
    const expected = editEl("edit-tc-expected").value.trim();
    const newGroupId = editEl("edit-tc-target-group").value;

    if (!name) {
        alert("Test Case Name is required.");
        return;
    }

    const tc = currentEditGroupTestCases[selectedEditTCIndex];
    tc.name = name;
    tc.pre_required_state = prereq;
    tc.action = action;
    tc.expected_result = expected;

    const oldGroupId = editEl("edit-group-select").value;

    try {
        if (oldGroupId !== newGroupId && newGroupId) {
            // Remove from old group
            let oldGroup = null;
            state.testGroupsData.categories.forEach(cat => {
                cat.groups.forEach(g => {
                    if (g.id === oldGroupId) {
                        oldGroup = g;
                    }
                });
            });
            if (oldGroup) {
                oldGroup.test_cases = oldGroup.test_cases.filter((tcVal, idx) => idx !== selectedEditTCIndex);
            }
            
            // Add to new group
            let newGroup = null;
            state.testGroupsData.categories.forEach(cat => {
                cat.groups.forEach(g => {
                    if (g.id === newGroupId) {
                        newGroup = g;
                    }
                });
            });
            if (newGroup) {
                newGroup.test_cases = newGroup.test_cases || [];
                newGroup.test_cases.push(tc);
            }
            
            // Save to server
            await fetchAPI(`${API_BASE}/api/edit-test-groups/`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ categories: state.testGroupsData.categories })
            });
            
            showStatus("Test case moved and updated permanently.", "#10b981");
            
            // Switch target dropdown
            editEl("edit-group-select").value = newGroupId;
            onEditGroupSelected();
            selectedEditTCIndex = newGroup.test_cases.length - 1;
            renderEditTCList();
            loadEditTCFields(tc);
            refreshEntireUI();
            return;
        }

        // Standard save (no group change)
        await fetchAPI(`${API_BASE}/api/edit-test-groups/`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ categories: state.testGroupsData.categories })
        });
        showStatus("Test case updated permanently.", "#10b981");
        renderEditTCList();
        refreshEntireUI();
    } catch (e) {
        alert(`Failed to save changes: ${e.message}`);
    }
}

async function deleteEditedTC() {
    if (selectedEditTCIndex === null) {
        alert("Please select a test case to delete first.");
        return;
    }
    
    const tc = currentEditGroupTestCases[selectedEditTCIndex];
    if (!confirm(`Are you sure you want to permanently delete the test case "${tc.name}"?`)) {
        return;
    }
    
    const groupId = editEl("edit-group-select").value;
    let targetGroup = null;
    state.testGroupsData.categories.forEach(cat => {
        cat.groups.forEach(g => {
            if (g.id === groupId) {
                targetGroup = g;
            }
        });
    });
    
    if (targetGroup) {
        targetGroup.test_cases = targetGroup.test_cases.filter((tcVal, idx) => idx !== selectedEditTCIndex);
    }
    
    try {
        await fetchAPI(`${API_BASE}/api/edit-test-groups/`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ categories: state.testGroupsData.categories })
        });
        showStatus("Test case deleted permanently.", "#ef4444");
        onEditGroupSelected();
        refreshEntireUI();
    } catch (e) {
        alert(`Failed to delete test case: ${e.message}`);
    }
}

async function onEditCategoryAdd() {
    const catName = prompt("Enter New Type Name (e.g. Conveyor Operation):");
    if (!catName || !catName.trim()) return;
    const cleanCatName = catName.trim();
    
    const exists = state.testGroupsData.categories.some(cat => cat.name.toLowerCase() === cleanCatName.toLowerCase());
    if (exists) {
        alert("A Type with this name already exists.");
        return;
    }
    
    const selSelect = editEl("edit-selection-select");
    if (!selSelect) return;
    const targetSelection = selSelect.value;
    if (!targetSelection) {
        alert("Please select a Selection type first.");
        return;
    }
    
    const catId = "cat_" + Date.now();
    const groupId = "group_" + Date.now();
    
    const newCat = {
        id: catId,
        name: cleanCatName,
        category_number: state.testGroupsData.categories.length + 1,
        groups: [
            {
                id: groupId,
                label: "General",
                section_type: targetSelection.toLowerCase(),
                ui_type: "checkbox",
                test_cases: []
            }
        ]
    };
    
    state.testGroupsData.categories.push(newCat);
    
    try {
        await fetchAPI(`${API_BASE}/api/edit-test-groups/`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ categories: state.testGroupsData.categories })
        });
        showStatus(`Type "${cleanCatName}" created permanently.`, "#10b981");
        onEditSelectionChanged();
        editEl("edit-group-select").value = groupId;
        onEditGroupSelected();
        refreshEntireUI();
    } catch (e) {
        alert(`Failed to create Type: ${e.message}`);
    }
}

async function onEditCategoryRename() {
    const groupId = editEl("edit-group-select").value;
    if (!groupId) {
        alert("Please select a group/cluster first to determine the active Type.");
        return;
    }
    
    let targetCat = null;
    state.testGroupsData.categories.forEach(cat => {
        cat.groups.forEach(g => {
            if (g.id === groupId) {
                targetCat = cat;
            }
        });
    });
    
    if (!targetCat) return;
    
    const newName = prompt("Rename Type to:", targetCat.name);
    if (!newName || !newName.trim() || newName.trim() === targetCat.name) return;
    
    const cleanNewName = newName.trim();
    targetCat.name = cleanNewName;
    
    try {
        await fetchAPI(`${API_BASE}/api/edit-test-groups/`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ categories: state.testGroupsData.categories })
        });
        showStatus("Type renamed permanently.", "#10b981");
        onEditSelectionChanged();
        editEl("edit-group-select").value = groupId;
        onEditGroupSelected();
        refreshEntireUI();
    } catch (e) {
        alert(`Failed to rename Type: ${e.message}`);
    }
}

async function onEditCategoryDelete() {
    const groupId = editEl("edit-group-select").value;
    if (!groupId) {
        alert("Please select a group/cluster first to determine the active Type.");
        return;
    }
    
    let targetCat = null;
    state.testGroupsData.categories.forEach(cat => {
        cat.groups.forEach(g => {
            if (g.id === groupId) {
                targetCat = cat;
            }
        });
    });
    
    if (!targetCat) return;
    
    if (!confirm(`Are you sure you want to permanently delete the Type "${targetCat.name}" and all of its clusters and test cases?`)) {
        return;
    }
    
    state.testGroupsData.categories = state.testGroupsData.categories.filter(cat => cat.id !== targetCat.id);
    
    try {
        await fetchAPI(`${API_BASE}/api/edit-test-groups/`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ categories: state.testGroupsData.categories })
        });
        showStatus("Type deleted permanently.", "#ef4444");
        onEditSelectionChanged();
        refreshEntireUI();
    } catch (e) {
        alert(`Failed to delete Type: ${e.message}`);
    }
}

async function moveEditTC(direction) {
    if (selectedEditTCIndex === null) return;
    const idx = selectedEditTCIndex;
    const nextIdx = idx + direction;

    if (nextIdx < 0 || nextIdx >= currentEditGroupTestCases.length) return;

    const temp = currentEditGroupTestCases[idx];
    currentEditGroupTestCases[idx] = currentEditGroupTestCases[nextIdx];
    currentEditGroupTestCases[nextIdx] = temp;

    selectedEditTCIndex = nextIdx;

    try {
        await fetchAPI(`${API_BASE}/api/edit-test-groups/`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ categories: state.testGroupsData.categories })
        });
        renderEditTCList();
        refreshEntireUI();
    } catch (e) {
        alert(`Failed to save reordered list: ${e.message}`);
    }
}

async function handleTemplateUpload(e) {
    if (state.isViewOnlyLink) return;
    const file = e.target.files[0];
    if (!file) return;

    const targetSelection = document.getElementById("template-target-selection").value;
    if (!targetSelection) {
        alert("Please select a target Selection first.");
        return;
    }

    const formData = new FormData();
    formData.append("file", file);
    formData.append("project", JSON.stringify(state.project));
    formData.append("target_selection", targetSelection);

    try {
        showStatus("Uploading and parsing template...", "#38bdf8");
        const res = await fetch(`${API_BASE}/api/template/upload/`, {
            method: "POST",
            headers: { "X-CSRFToken": getCSRFToken() },
            body: formData
        });
        const data = await res.json();
        if (!res.ok || data.error) {
            throw new Error(data.error || "Failed to upload template.");
        }

        // Update project state
        state.project = data.project;

        // Update test groups data from server response
        if (data.test_groups) {
            // Collect group IDs that existed before the import
            const oldGroupIds = new Set();
            (state.testGroupsData.categories || []).forEach(cat => {
                (cat.groups || []).forEach(g => oldGroupIds.add(g.id));
            });

            state.testGroupsData = data.test_groups;

            // Find newly imported group IDs
            const newGroupIds = [];
            (data.test_groups.categories || []).forEach(cat => {
                (cat.groups || []).forEach(g => {
                    if (!oldGroupIds.has(g.id) && g.section_type === targetSelection.toLowerCase()) {
                        newGroupIds.push(g.id);
                    }
                });
            });

            // Auto-select newly imported groups for all sections matching the target selection
            if (newGroupIds.length > 0) {
                (state.project.sections || []).forEach(sec => {
                    if (sec.section_type === targetSelection.toLowerCase()) {
                        newGroupIds.forEach(gid => {
                            if (!sec.selected_groups.includes(gid)) {
                                sec.selected_groups.push(gid);
                            }
                        });
                    }
                });
            }
        }

        // Select the first section if needed
        if (state.project.sections.length > 0 && (state.selectedSectionIndex === null || state.selectedSectionIndex >= state.project.sections.length)) {
            state.selectedSectionIndex = 0;
        }

        saveStateToCache();
        refreshEntireUI();

        alert(data.message);
        showStatus("Template imported successfully!", "#10b981");
    } catch (err) {
        alert(`Import Error: ${err.message}`);
        showStatus("Import failed", "#ef4444");
    } finally {
        e.target.value = "";
    }
}

function renderSectionTypeToggles() {
    const container = document.getElementById("section-type-toggles-container");
    if (!container) return;

    const types = getActiveSelectionTypes();
    const sec = getActiveSection();
    const currentType = sec ? sec.section_type.toLowerCase() : "";

    container.innerHTML = "";
    types.forEach(type => {
        const label = document.createElement("label");
        label.className = "radio-label";

        const displayLabel = type.charAt(0).toUpperCase() + type.slice(1);

        const radio = document.createElement("input");
        radio.type = "radio";
        radio.name = "section-type";
        const val = type.toLowerCase();
        radio.value = (val === "conveyor" || val === "vrc") ? val : type;
        radio.checked = val === currentType;
        if (state.isViewOnlyLink) radio.disabled = true;

        radio.addEventListener("change", (e) => {
            const activeSec = getActiveSection();
            if (activeSec) {
                activeSec.section_type = e.target.value;
                activeSec.selected_groups = [];
                activeSec.dropdown_selections = {};
                saveStateToCache();
                renderSelectionTree();
                renderSectionList();
                reloadActiveTabs();
            }
        });

        label.appendChild(radio);
        label.appendChild(document.createTextNode(" " + displayLabel));
        container.appendChild(label);
    });
}

function getActiveSelectionTypes() {
    if (state.testGroupsData && state.testGroupsData.selections) {
        return state.testGroupsData.selections;
    }
    return ["Conveyor", "VRC"];
}

let editingSelectionName = null;

function loadSelectionsList() {
    const listContainer = document.getElementById("selections-list");
    if (!listContainer) return;
    listContainer.innerHTML = "";
    
    // Built-in Selections (only render if not deleted)
    const builtins = ["Conveyor", "VRC"];
    const deleted = (state.project.deleted_selection_types || []).map(t => t.toLowerCase());
    
    builtins.forEach(name => {
        if (deleted.includes(name.toLowerCase())) return;
        
        const item = document.createElement("div");
        item.className = "custom-tc-item";
        item.style = "padding: 10px 15px; display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid var(--border-color);";
        
        const info = document.createElement("div");
        info.innerHTML = `<strong style="color: var(--text-muted); font-size: 13px;">${name}</strong> <span style="font-size: 11px; color: var(--text-muted); margin-left: 8px;">(System)</span>`;
        item.appendChild(info);
        
        const btnBox = document.createElement("div");
        btnBox.style = "display: flex; gap: 6px;";
        
        const editBtn = document.createElement("button");
        editBtn.className = "btn btn-secondary btn-sm";
        editBtn.textContent = "Rename";
        editBtn.disabled = true;
        btnBox.appendChild(editBtn);
        
        const deleteBtn = document.createElement("button");
        deleteBtn.className = "btn btn-danger btn-sm";
        deleteBtn.textContent = "Delete";
        if (state.isViewOnlyLink) deleteBtn.disabled = true;
        deleteBtn.addEventListener("click", () => deleteSelection(name));
        btnBox.appendChild(deleteBtn);
        
        item.appendChild(btnBox);
        listContainer.appendChild(item);
    });
    
    // Custom Selections
    const customTypes = state.project.custom_selection_types || [];
    customTypes.forEach(name => {
        const item = document.createElement("div");
        item.className = "custom-tc-item";
        item.style = "padding: 10px 15px; display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid var(--border-color);";
        
        const info = document.createElement("div");
        info.innerHTML = `<strong style="color: var(--text-color); font-size: 13px;">${name}</strong> <span style="font-size: 11px; color: var(--success-color); margin-left: 8px;">(Custom)</span>`;
        item.appendChild(info);
        
        const btnBox = document.createElement("div");
        btnBox.style = "display: flex; gap: 6px;";
        
        const editBtn = document.createElement("button");
        editBtn.className = "btn btn-secondary btn-sm";
        editBtn.textContent = "Rename";
        editBtn.addEventListener("click", () => startEditSelection(name));
        btnBox.appendChild(editBtn);
        
        const deleteBtn = document.createElement("button");
        deleteBtn.className = "btn btn-danger btn-sm";
        deleteBtn.textContent = "Delete";
        if (state.isViewOnlyLink) deleteBtn.disabled = true;
        deleteBtn.addEventListener("click", () => deleteSelection(name));
        btnBox.appendChild(deleteBtn);
        
        item.appendChild(btnBox);
        listContainer.appendChild(item);
    });
}

function startEditSelection(name) {
    if (state.isViewOnlyLink) return;
    editingSelectionName = name;
    
    document.getElementById("new-selection-name-input").value = name;
    document.getElementById("selection-form-title").textContent = "Rename Selection";
    document.getElementById("btn-create-selection").textContent = "Update Selection Name";
    document.getElementById("btn-cancel-selection-edit").classList.remove("hidden");
}

function cancelSelectionEdit() {
    editingSelectionName = null;
    document.getElementById("new-selection-name-input").value = "";
    document.getElementById("selection-form-title").textContent = "Create New Selection";
    document.getElementById("btn-create-selection").textContent = "Create Selection";
    document.getElementById("btn-cancel-selection-edit").classList.add("hidden");
}

async function deleteSelection(name) {
    if (state.isViewOnlyLink) return;
    if (!confirm(`Are you sure you want to delete the Selection "${name}"?\nThis will remove all associated Types/Clusters and test cases.`)) {
        return;
    }
    
    const lowerName = name.toLowerCase();
    const builtins = ["conveyor", "vrc"];
    if (builtins.includes(lowerName)) {
        if (!state.project.deleted_selection_types) {
            state.project.deleted_selection_types = [];
        }
        if (!state.project.deleted_selection_types.map(t => t.toLowerCase()).includes(lowerName)) {
            state.project.deleted_selection_types.push(name);
        }
    } else {
        state.project.custom_selection_types = (state.project.custom_selection_types || []).filter(t => t !== name);
    }
    
    state.project.sections = (state.project.sections || []).filter(sec => sec.section_type.toLowerCase() !== lowerName);
    
    if (state.selectedSectionIndex >= state.project.sections.length) {
        state.selectedSectionIndex = state.project.sections.length > 0 ? 0 : null;
    }
    
    saveStateToCache();
    refreshEntireUI();
    cancelSelectionEdit();
    showStatus(`Deleted Selection "${name}"`, "#ef4444");
}

async function createNewSelection() {
    if (state.isViewOnlyLink) return;
    const input = document.getElementById("new-selection-name-input");
    if (!input) return;
    const rawName = input.value.trim();
    if (!rawName) {
        alert("Selection Name is required.");
        return;
    }

    if (!state.project.custom_selection_types) {
        state.project.custom_selection_types = [];
    }

    if (editingSelectionName) {
        const oldName = editingSelectionName;
        if (oldName.toLowerCase() === rawName.toLowerCase()) {
            cancelSelectionEdit();
            return;
        }

        const existing = ["conveyor", "vrc", ...state.project.custom_selection_types].map(t => t.toLowerCase());
        if (existing.includes(rawName.toLowerCase()) && rawName.toLowerCase() !== oldName.toLowerCase()) {
            alert(`A selection type named "${rawName}" already exists.`);
            return;
        }

        const idx = state.project.custom_selection_types.indexOf(oldName);
        if (idx !== -1) {
            state.project.custom_selection_types[idx] = rawName;
        }

        state.project.sections.forEach(sec => {
            if (sec.section_type === oldName) {
                sec.section_type = rawName;
            }
        });

        alert(`Selection renamed to "${rawName}" successfully!`);
        showStatus(`Renamed Selection to "${rawName}"`, "#10b981");
    } else {
        const existing = ["conveyor", "vrc", ...state.project.custom_selection_types].map(t => t.toLowerCase());
        if (existing.includes(rawName.toLowerCase())) {
            alert(`A selection type named "${rawName}" already exists.`);
            return;
        }

        state.project.custom_selection_types.push(rawName);
        alert(`Selection type "${rawName}" created successfully!`);
        showStatus(`Created Selection "${rawName}"`, "#10b981");
    }

    saveStateToCache();
    refreshEntireUI();
    cancelSelectionEdit();
}

// ═══════════════════════════════════════════════════════════════════════
// ═══ PROJECT REGISTRY (server-backed via TestVaultProject) ════════════
// ═══════════════════════════════════════════════════════════════════════

// Cache of the last /api/projects/ fetch, keyed by id, so per-card actions (duplicate/
// delete/rename) don't each need their own round trip just to read a project's current stats.
let projectListCache = [];

async function fetchProjectsList() {
    const res = await fetchAPI(`${API_BASE}/api/projects/`);
    projectListCache = res.projects || [];
    return projectListCache;
}

// ═══════════════════════════════════════════════════════════════════════
// ═══ PROJECT MANAGEMENT CRUD ═══════════════════════════════════════════
// ═══════════════════════════════════════════════════════════════════════

// ═══════════════════════════════════════════════════════════════════════
// ═══ v3.0: COMPUTE PROJECT STATS ══════════════════════════════════════
// ═══════════════════════════════════════════════════════════════════════

function generateTestCasesLocal(section, testGroupsData, permanentCustomTestCases) {
    if (!section) return [];
    const collected = [];
    const seenNames = new Set();
    const permCustom = permanentCustomTestCases || [];
    const sectionType = section.section_type || "conveyor";
    
    if (sectionType !== "conveyor" && sectionType !== "vrc") {
        const customCls = section.custom_clusters || [];
        const projectOnlyTCs = section.project_only_test_cases || [];
        
        customCls.forEach(cluster => {
            const cid = cluster.id;
            const cname = cluster.name;
            projectOnlyTCs.forEach(tc => {
                if (tc.group_id === cid) {
                    if (!seenNames.has(tc.name)) {
                        collected.push({ categoryName: cname, tc });
                        seenNames.add(tc.name);
                    }
                }
            });
        });
        
        const fallbackCat = `Custom ${sectionType.charAt(0).toUpperCase() + sectionType.slice(1)}`;
        projectOnlyTCs.forEach(tc => {
            if (!seenNames.has(tc.name)) {
                collected.push({ categoryName: fallbackCat, tc });
                seenNames.add(tc.name);
            }
        });
    } else {
        const categories = testGroupsData?.categories || [];
        categories.forEach(category => {
            const catName = category.name;
            const groups = category.groups || [];
            groups.forEach(group => {
                const groupId = group.id;
                const grpType = group.section_type || "any";
                
                if (grpType !== "any" && grpType !== sectionType) return;
                
                const selectedGroups = section.selected_groups || [];
                if (!selectedGroups.includes(groupId)) return;
                
                const uiType = group.ui_type || "checkbox";
                let allTestCases = [];
                const sessionCustom = section.session_test_cases ? section.session_test_cases[groupId] : null;
                if (sessionCustom) {
                    allTestCases = Array.isArray(sessionCustom) ? sessionCustom : [];
                } else {
                    const baseTestCases = Array.isArray(group.test_cases) ? group.test_cases : [];
                    const groupPerm = permCustom.filter(tc => tc.group_id === groupId);
                    const groupProj = (section.project_only_test_cases || []).filter(tc => tc.group_id === groupId);
                    allTestCases = baseTestCases.concat(groupPerm).concat(groupProj);
                }
                
                if (uiType === "dropdown") {
                    const dropdownSels = section.dropdown_selections || {};
                    const selectedTcNames = dropdownSels[groupId] || [];
                    allTestCases.forEach(tc => {
                        if (selectedTcNames.includes(tc.name)) {
                            if (!seenNames.has(tc.name)) {
                                collected.push({ categoryName: catName, tc });
                                seenNames.add(tc.name);
                            }
                        }
                    });
                } else {
                    allTestCases.forEach(tc => {
                        if (!seenNames.has(tc.name)) {
                            collected.push({ categoryName: catName, tc });
                            seenNames.add(tc.name);
                        }
                    });
                }
            });
        });
    }
    return collected;
}

function computeProjectStats(projectData) {
    const stats = { total: 0, pass: 0, fail: 0, pending: 0, completion: 0 };
    if (!projectData || !projectData.sections) return stats;
    
    const testGroups = state.testGroupsData;
    const permCustom = state.permanentCustomTestCases || [];
    
    // Defensive fallback if state metadata is not loaded yet
    if (!testGroups || !testGroups.categories) {
        projectData.sections.forEach(sec => {
            const results = sec.results || {};
            Object.values(results).forEach(val => {
                stats.total++;
                if (val === "Pass") stats.pass++;
                else if (val === "Fail") stats.fail++;
                else stats.pending++;
            });
        });
        stats.completion = stats.total > 0 ? Math.round(((stats.pass + stats.fail) / stats.total) * 100) : 0;
        return stats;
    }
    
    projectData.sections.forEach(sec => {
        const generated = generateTestCasesLocal(sec, testGroups, permCustom);
        const results = sec.results || {};
        
        generated.forEach(item => {
            stats.total++;
            const tcName = item.tc.name;
            const val = results[tcName];
            if (val === "Pass") stats.pass++;
            else if (val === "Fail") stats.fail++;
            else stats.pending++;
        });
    });
    
    stats.completion = stats.total > 0 ? Math.round(((stats.pass + stats.fail) / stats.total) * 100) : 0;
    return stats;
}

function getProjectStatus(stats) {
    if (stats.total === 0) {
        return { label: "Not Started", cls: "status-not-started", progressCls: "" };
    }
    if (stats.pass === stats.total) {
        return { label: "Complete", cls: "status-complete", progressCls: "progress-complete" };
    }
    if (stats.pass + stats.fail === stats.total) {
        return { label: "Complete (Failed TCs)", cls: "status-warning", progressCls: "progress-warning" };
    }
    if (stats.pass + stats.fail > 0) {
        return { label: "In Progress", cls: "status-in-progress", progressCls: "" };
    }
    return { label: "Not Started", cls: "status-not-started", progressCls: "" };
}

// ═══════════════════════════════════════════════════════════════════════
// ═══ v3.0: ENHANCED PROJECT DASHBOARD CARDS ═══════════════════════════
// ═══════════════════════════════════════════════════════════════════════

async function renderProjectCards() {
    const container = document.getElementById("project-cards-container");
    if (!container) return;

    let projects;
    try {
        projects = await fetchProjectsList();
    } catch (e) {
        container.innerHTML = `<div class="empty-projects-message"><p>Failed to load projects: ${escapeHTML(e.message)}</p></div>`;
        return;
    }
    container.innerHTML = "";

    if (projects.length === 0) {
        container.innerHTML = `
            <div class="empty-projects-message">
                <p>No projects yet.</p>
                <p>Create your first project to get started.</p>
                <button class="btn btn-primary" onclick="openNewProjectModal()">+ New Project</button>
            </div>
        `;
        return;
    }

    // Already sorted by -updated_at from the server.
    projects.forEach(proj => {
        const card = document.createElement("div");
        card.className = "project-card";

        const stats = {
            total: proj.stats.total_test_cases,
            pass: proj.stats.passed,
            fail: proj.stats.failed,
            pending: proj.stats.pending,
            completion: proj.stats.completion_percentage,
        };
        const status = getProjectStatus(stats);
        const title = proj.zone_name ? `${proj.project_code} — ${proj.zone_name}` : proj.project_code;
        const modifiedDate = new Date(proj.updated_at).toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric" });

        card.innerHTML = `
            <div class="project-card-header">
                <h3>${escapeHTML(title)}</h3>
                <span class="project-card-status ${status.cls}">${status.label}</span>
            </div>
            <div class="project-card-body">
                <div class="project-card-meta">
                    <span>Customer: ${escapeHTML(proj.customer_name || "—")}</span>
                    <span>Modified: ${modifiedDate}</span>
                </div>
                <div class="project-card-progress">
                    <div class="project-progress-track">
                        <div class="project-progress-fill ${status.progressCls}" style="width: ${stats.completion}%"></div>
                    </div>
                    <span class="progress-pct">${stats.completion}% complete</span>
                </div>
            </div>
            <div class="project-card-actions">
                <button class="btn btn-primary" onclick="openProject(${proj.id})">Open</button>
                <button class="btn btn-secondary" onclick="duplicateProject(${proj.id})">Duplicate</button>
                <button class="btn btn-secondary" onclick="renameProject(${proj.id})">Rename Zone</button>
                <button class="btn btn-danger" onclick="deleteProject(${proj.id})">Delete</button>
            </div>
        `;

        container.appendChild(card);
    });
}

function escapeHTML(str) {
    const div = document.createElement("div");
    div.textContent = str;
    return div.innerHTML;
}

let newProjectTrackerOptions = [];
let newProjectPlannerOptions = [];

async function refreshNewProjectSourceOptions() {
    const source = document.getElementById("new-project-source-select").value;
    const select = document.getElementById("new-project-tracker-project-select");
    select.innerHTML = "";
    try {
        if (source === "planner") {
            if (!newProjectPlannerOptions.length) {
                const res = await fetchAPI(`${API_BASE}/api/lookup/planner-projects/`);
                newProjectPlannerOptions = res.results || [];
            }
            select.innerHTML = newProjectPlannerOptions.map(
                p => `<option value="${p.id}">${escapeHTML(p.project_id)} — ${escapeHTML(p.customer_name)}${p.tracker_project_id ? "" : "  (not linked to Tracker yet)"}</option>`
            ).join("");
        } else {
            if (!newProjectTrackerOptions.length) {
                const res = await fetchAPI(`${API_BASE}/api/lookup/tracker-projects/`);
                newProjectTrackerOptions = res.results || [];
            }
            select.innerHTML = newProjectTrackerOptions.map(
                p => `<option value="${p.id}">${escapeHTML(p.code)} — ${escapeHTML(p.customer_name)}</option>`
            ).join("");
        }
    } catch (e) {
        select.innerHTML = `<option value="">Failed to load: ${escapeHTML(e.message)}</option>`;
    }
}

function openNewProjectModal() {
    document.getElementById("new-project-modal").classList.add("open");
    document.getElementById("new-project-zone-input").value = "";
    document.getElementById("new-project-source-select").value = "tracker";
    refreshNewProjectSourceOptions();
}

function closeNewProjectModal() {
    document.getElementById("new-project-modal").classList.remove("open");
}

async function confirmCreateProject() {
    const source = document.getElementById("new-project-source-select").value;
    const projectSelect = document.getElementById("new-project-tracker-project-select");
    const selectedId = projectSelect.value;
    if (!selectedId) {
        alert("Please select a project to link to.");
        return;
    }

    const payload = {
        source,
        zone_name: document.getElementById("new-project-zone-input").value.trim(),
    };
    if (source === "planner") {
        payload.planner_project_id = selectedId;
    } else {
        payload.tracker_project_id = selectedId;
    }

    try {
        await postJSON(`${API_BASE}/api/projects/create/`, payload);
        closeNewProjectModal();
        renderProjectCards();
    } catch (e) {
        alert(`Failed to create project: ${e.message}`);
    }
}

async function renameProject(projectId) {
    const proj = projectListCache.find(p => p.id === projectId);
    const currentZone = proj ? proj.zone_name : "";

    const newZone = prompt("Enter new Zone Name for this project:", currentZone);
    if (newZone === null || newZone.trim() === currentZone) return;

    try {
        await postJSON(`${API_BASE}/api/projects/${projectId}/save/`, { meta: { zone_name: newZone.trim() } });
        renderProjectCards();
    } catch (e) {
        alert(`Failed to rename: ${e.message}`);
    }
}

async function deleteProject(projectId) {
    const proj = projectListCache.find(p => p.id === projectId);
    const label = proj ? (proj.zone_name || proj.project_code) : "this project";
    const isEmpty = proj && proj.stats.total_test_cases === 0;

    if (isEmpty) {
        if (!confirm(`Delete the empty project "${label}"?`)) return;
    } else if (!confirm(`This project contains data. Delete "${label}"? You'll be asked to confirm your password.`)) {
        return;
    }

    const pwd = prompt("Enter your account password to confirm deletion:");
    if (pwd === null) return;

    try {
        await postJSON(`${API_BASE}/api/projects/${projectId}/delete/`, { password: pwd });
        renderProjectCards();
    } catch (e) {
        alert(`Failed to delete: ${e.message}`);
    }
}

// ═══════════════════════════════════════════════════════════════════════
// ═══ DUPLICATE PROJECT ═════════════════════════════════════════════════
// ═══════════════════════════════════════════════════════════════════════

async function duplicateProject(sourceId) {
    try {
        await postJSON(`${API_BASE}/api/projects/${sourceId}/duplicate/`, {});
        renderProjectCards();
    } catch (e) {
        alert(`Failed to duplicate project: ${e.message}`);
    }
}

// ═══════════════════════════════════════════════════════════════════════
// ═══ v3.0: MASTER DASHBOARD ══════════════════════════════════════════
// ═══════════════════════════════════════════════════════════════════════

async function computeAllProjectsStats() {
    const projects = await fetchProjectsList();
    const totals = { projects: projects.length, ongoing: 0, completed: 0, total: 0, pass: 0, fail: 0, pending: 0, completion: 0 };
    const perProject = [];

    projects.forEach(proj => {
        const stats = { total: proj.stats.total_test_cases, pass: proj.stats.passed, fail: proj.stats.failed, pending: proj.stats.pending, completion: proj.stats.completion_percentage };
        const status = getProjectStatus(stats);
        totals.total += stats.total;
        totals.pass += stats.pass;
        totals.fail += stats.fail;
        totals.pending += stats.pending;

        if (status.label === "Complete") {
            totals.completed++;
        } else if (status.label === "In Progress" || status.label === "Complete (Failed TCs)") {
            totals.ongoing++;
        }

        perProject.push({
            name: proj.zone_name ? `${proj.project_code} — ${proj.zone_name}` : proj.project_code,
            id: proj.id,
            projectCode: proj.project_code,
            lastModified: proj.updated_at,
            statusLabel: status.label,
            statusCls: status.cls,
            progressCls: status.progressCls,
            ...stats
        });
    });

    totals.completion = totals.total > 0 ? Math.round(((totals.pass + totals.fail) / totals.total) * 100) : 0;
    // Already sorted by -updated_at from the server; perProject preserves that order.

    return { totals, perProject };
}

async function renderMasterDashboard() {
    const { totals, perProject } = await computeAllProjectsStats();

    // ── Stat Cards ──
    const statsRow = document.getElementById("dash-stats-row");
    statsRow.innerHTML = `
        <div class="dash-stat-card" data-color="blue">
            <div class="dash-stat-value">${totals.projects}</div>
            <div class="dash-stat-label">Total Projects</div>
        </div>
        <div class="dash-stat-card" data-color="green">
            <div class="dash-stat-value">${totals.completed}</div>
            <div class="dash-stat-label">Completed Projects</div>
        </div>
        <div class="dash-stat-card" data-color="yellow">
            <div class="dash-stat-value">${totals.ongoing}</div>
            <div class="dash-stat-label">Ongoing Projects</div>
        </div>
        <div class="dash-stat-card" data-color="purple">
            <div class="dash-stat-value">${totals.completion}%</div>
            <div class="dash-stat-label">Overall Completion</div>
        </div>
    `;
    
    // ── Project Cards ──
    const cardsContainer = document.getElementById("dash-project-cards");
    if (!cardsContainer) return;
    
    if (perProject.length === 0) {
        cardsContainer.innerHTML = '<div style="text-align:center; padding:40px; color:var(--text-muted); font-size:14px;">No projects yet. Create a project to see it here.</div>';
        return;
    }
    
    cardsContainer.innerHTML = perProject.map(p => {
        return `
        <div class="dash-project-card" style="cursor: pointer;" onclick="showMasterProjectDetail('${p.id}')">
            <div class="dash-pc-header">
                <div class="dash-pc-title">${escapeHTML(p.name)}</div>
                <span class="project-card-status ${p.statusCls}">${p.statusLabel}</span>
            </div>
            ${p.projectCode ? `<div class="dash-pc-meta"><span>Code: ${escapeHTML(p.projectCode)}</span></div>` : ""}
            <div class="dash-pc-progress">
                <div class="project-progress-track">
                    <div class="project-progress-fill ${p.progressCls}" style="width: ${p.completion}%"></div>
                </div>
                <span class="progress-pct">${p.completion}%</span>
            </div>
        </div>`;
    }).join("");
}

async function showMasterProjectDetail(projectId) {
    let detail;
    try {
        detail = await fetchAPI(`${API_BASE}/api/projects/${projectId}/`);
    } catch (e) {
        alert("Could not load project details.");
        return;
    }
    const projectData = detail.project;

    // Set project name in modal
    const label = projectData.info.zone_name
        ? `${projectData.info.project_code} — ${projectData.info.zone_name}`
        : projectData.info.project_code;
    document.getElementById("dash-modal-project-name").textContent = label || "Project Details";

    const sections = projectData.sections || [];
    const testGroups = state.testGroupsData;
    const permCustom = state.permanentCustomTestCases || [];
    
    // Aggregate stats across all sections for this project
    let totalTC = 0, totalPass = 0, totalFail = 0;
    const sectionStats = [];
    
    sections.forEach(sec => {
        const results = sec.results || {};
        let pass = 0, fail = 0, pending = 0;
        
        const generated = generateTestCasesLocal(sec, testGroups, permCustom);
        const sectionTotal = generated.length;
        
        generated.forEach(item => {
            const tcName = item.tc.name;
            const val = results[tcName];
            if (val === "Pass") pass++;
            else if (val === "Fail") fail++;
            else pending++;
        });
        
        const completed = pass + fail;
        const completion = sectionTotal > 0 ? Math.round((completed / sectionTotal) * 100) : 0;
        
        totalTC += sectionTotal;
        totalPass += pass;
        totalFail += fail;
        
        sectionStats.push({
            name: sec.name || "Unnamed Zone",
            sectionType: sec.section_type || "conveyor",
            total: sectionTotal,
            pass,
            fail,
            completed,
            pending,
            completion
        });
    });
    
    const totalCompleted = totalPass + totalFail;
    const overallCompletion = totalTC > 0 ? Math.round((totalCompleted / totalTC) * 100) : 0;
    
    // Build popup content HTML
    let html = "";
    if (sections.length === 0) {
        html = '<div style="text-align:center; padding:20px; color:var(--text-muted);">No zones configured in this project yet.</div>';
    } else {
        html = `
        <div class="summary-stats-row" style="margin-bottom: 20px;">
            <div class="summary-stat-card" data-color="cyan">
                <div class="summary-stat-value">${totalTC}</div>
                <div class="summary-stat-label">Total Test Cases</div>
            </div>
            <div class="summary-stat-card" data-color="green">
                <div class="summary-stat-value">${totalPass}</div>
                <div class="summary-stat-label">Passed</div>
            </div>
            <div class="summary-stat-card" data-color="red">
                <div class="summary-stat-value">${totalFail}</div>
                <div class="summary-stat-label">Failed</div>
            </div>
            <div class="summary-stat-card" data-color="purple">
                <div class="summary-stat-value">${overallCompletion}%</div>
                <div class="summary-stat-label">Overall Completion</div>
            </div>
        </div>
        <div class="summary-sections-list">
        `;
        
        sectionStats.forEach(sec => {
            const selectionLabel = sec.sectionType.charAt(0).toUpperCase() + sec.sectionType.slice(1);
            const secStatus = getProjectStatus({ total: sec.total, pass: sec.pass, fail: sec.fail });
            html += `
            <div class="summary-section-card">
                <div class="summary-sec-header">
                    <div class="summary-sec-name">${escapeHTML(sec.name)}</div>
                    <span class="summary-sec-type">${selectionLabel}</span>
                </div>
                <div class="summary-sec-stats">
                    <span>Total: <strong>${sec.total}</strong></span>
                    <span class="stat-pass">Passed: <strong>${sec.pass}</strong></span>
                    <span class="stat-fail">Failed: <strong>${sec.fail}</strong></span>
                    <span>Completed: <strong>${sec.completed}/${sec.total}</strong></span>
                </div>
                <div class="summary-sec-progress">
                    <div class="project-progress-track">
                        <div class="project-progress-fill ${secStatus.progressCls}" style="width: ${sec.completion}%"></div>
                    </div>
                    <span class="progress-pct">${sec.completion}%</span>
                </div>
            </div>`;
        });
        html += '</div>';
    }
    
    document.getElementById("dash-modal-body").innerHTML = html;
    document.getElementById("dash-project-detail-modal").classList.add("open");
}

// ═══════════════════════════════════════════════════════════════════════
// ═══ v3.0: SUMMARY TAB (PER-PROJECT) ════════════════════════════════
// ═══════════════════════════════════════════════════════════════════════

function renderSummaryTab() {
    const container = document.getElementById("summary-tab-content");
    if (!container) return;
    
    const sections = state.project?.sections || [];
    
    if (sections.length === 0) {
        container.innerHTML = '<div style="text-align:center; padding:30px; color:var(--text-muted);">No zones configured yet.</div>';
        return;
    }
    
    const testGroups = state.testGroupsData;
    const permCustom = state.permanentCustomTestCases || [];
    
    // If metadata is not loaded, show placeholder
    if (!testGroups || !testGroups.categories) {
        container.innerHTML = '<div style="text-align:center; padding:30px; color:var(--text-muted);">Loading summary data...</div>';
        return;
    }
    
    // Aggregate stats across all sections using actual client-side test case counts
    let totalTC = 0, totalPass = 0, totalFail = 0;
    const sectionStats = [];
    
    sections.forEach(sec => {
        const results = sec.results || {};
        let pass = 0, fail = 0, pending = 0;
        
        const generated = generateTestCasesLocal(sec, testGroups, permCustom);
        const sectionTotal = generated.length;
        
        generated.forEach(item => {
            const tcName = item.tc.name;
            const val = results[tcName];
            if (val === "Pass") pass++;
            else if (val === "Fail") fail++;
            else pending++;
        });
        
        const completed = pass + fail;
        const completion = sectionTotal > 0 ? Math.round((completed / sectionTotal) * 100) : 0;
        
        totalTC += sectionTotal;
        totalPass += pass;
        totalFail += fail;
        
        sectionStats.push({
            name: sec.name || "Unnamed Zone",
            sectionType: sec.section_type || "conveyor",
            total: sectionTotal,
            pass,
            fail,
            completed,
            pending,
            completion
        });
    });
    
    const totalCompleted = totalPass + totalFail;
    const overallCompletion = totalTC > 0 ? Math.round((totalCompleted / totalTC) * 100) : 0;
    
    // ── Render Stats Row ──
    let html = `
    <div class="summary-stats-row">
        <div class="summary-stat-card" data-color="cyan">
            <div class="summary-stat-value">${totalTC}</div>
            <div class="summary-stat-label">Total Test Cases</div>
        </div>
        <div class="summary-stat-card" data-color="green">
            <div class="summary-stat-value">${totalPass}</div>
            <div class="summary-stat-label">Passed</div>
        </div>
        <div class="summary-stat-card" data-color="red">
            <div class="summary-stat-value">${totalFail}</div>
            <div class="summary-stat-label">Failed</div>
        </div>
        <div class="summary-stat-card" data-color="purple">
            <div class="summary-stat-value">${overallCompletion}%</div>
            <div class="summary-stat-label">Overall Completion</div>
        </div>
    </div>
    `;
    
    // ── Render Per-Section Breakdown ──
    html += '<div class="summary-sections-list">';
    sectionStats.forEach(sec => {
        const selectionLabel = sec.sectionType.charAt(0).toUpperCase() + sec.sectionType.slice(1);
        const secStatus = getProjectStatus({ total: sec.total, pass: sec.pass, fail: sec.fail });
        html += `
        <div class="summary-section-card">
            <div class="summary-sec-header">
                <div class="summary-sec-name">${escapeHTML(sec.name)}</div>
                <span class="summary-sec-type">${selectionLabel}</span>
            </div>
            <div class="summary-sec-stats">
                <span>Total: <strong>${sec.total}</strong></span>
                <span class="stat-pass">Passed: <strong>${sec.pass}</strong></span>
                <span class="stat-fail">Failed: <strong>${sec.fail}</strong></span>
                <span>Completed: <strong>${sec.completed}/${sec.total}</strong></span>
            </div>
            <div class="summary-sec-progress">
                <div class="project-progress-track">
                    <div class="project-progress-fill ${secStatus.progressCls}" style="width: ${sec.completion}%"></div>
                </div>
                <span class="progress-pct">${sec.completion}%</span>
            </div>
        </div>`;
    });
    html += '</div>';
    
    container.innerHTML = html;
}

async function openProject(projectId) {
    let detail;
    try {
        detail = await fetchAPI(`${API_BASE}/api/projects/${projectId}/`);
    } catch (e) {
        alert(`Failed to load project: ${e.message}`);
        return;
    }

    state.currentProjectId = projectId;
    state.project = detail.project;
    state.currentProjectMeta = detail.meta;

    // Ensure at least one section exists
    if (state.project.sections.length === 0) {
        state.project.sections.push({
            name: "Inbound",
            section_type: "conveyor",
            selected_groups: [],
            dropdown_selections: {},
            results: {},
            observations: {},
            project_only_test_cases: []
        });
    }

    // Set default date if empty
    if (!state.project.info.date_of_validation) {
        state.project.info.date_of_validation = new Date().toLocaleDateString('en-GB').replace(/\//g, '-');
    }
    document.getElementById("date-of-validation").value = state.project.info.date_of_validation;

    // Show app screen
    showScreen("app");
    await populateEmployeeSelects();
    applyProjectToUI();
    selectSection(0);
}

function backToProjectManagement() {
    // Save current project before leaving
    if (state.currentProjectId) {
        saveStateToCache();
    }

    state.currentProjectId = null;
    state.currentProjectMeta = null;
    state.selectedSectionIndex = null;

    showScreen("projects");
}

// ═══════════════════════════════════════════════════════════════════════
// ═══ v2.6: REDESIGNED EDIT TEST CASE LIBRARY (PAGE-BASED WORKFLOW) ════
// ═══════════════════════════════════════════════════════════════════════

let currentEditPage = "menu"; // menu, manage-selections, select-selection, manage-types, manage-clusters, manage-test-cases
let selectedSelectionName = null;
let selectedTypeId = null;
let selectedClusterId = null;
let selectedTCIndex = null;

let editSelectionContext = null; // string e.g. "Conveyor"
let editTypeContext = null; // Category object
let editClusterContext = null; // Group object
let editTCContextIndex = null; // Index inside editClusterContext.test_cases

function openEditTCOverlay() {
    showScreen("editOverlay");
    showEditPage("menu");
}

function closeEditTCOverlay() {
    showScreen("projects");
}

// ─── PAGE NAVIGATION ─────────────────────────────────────────────────
function showEditPage(pageName) {
    currentEditPage = pageName;
    
    // Hide all pages
    document.querySelectorAll(".edit-page").forEach(page => page.classList.add("hidden"));
    
    // Reset selection states
    selectedSelectionName = null;
    selectedTypeId = null;
    selectedClusterId = null;
    selectedTCIndex = null;
    
    // Show target page
    const pageEl = document.getElementById(`edit-page-${pageName}`);
    if (pageEl) pageEl.classList.remove("hidden");
    
    // Disable action buttons by default
    updateToolbarButtonStates();
    
    // Render breadcrumbs
    renderBreadcrumbs();
    
    // Load page data
    if (pageName === "manage-selections") {
        renderSelectionsGrid("selections-grid-manage", true);
    } else if (pageName === "select-selection") {
        renderSelectionsGrid("selections-grid-select", false);
    } else if (pageName === "manage-types") {
        renderTypesPage();
    } else if (pageName === "manage-clusters") {
        renderClustersPage();
    } else if (pageName === "manage-test-cases") {
        renderTestCasesPage();
    }
}

function updateToolbarButtonStates() {
    // Page 1
    const btnSelRename = document.getElementById("btn-sel-rename");
    const btnSelDelete = document.getElementById("btn-sel-delete");
    if (btnSelRename) btnSelRename.disabled = !selectedSelectionName;
    if (btnSelDelete) btnSelDelete.disabled = !selectedSelectionName;
    
    // Page 3
    const btnTypeRename = document.getElementById("btn-type-rename");
    const btnTypeDelete = document.getElementById("btn-type-delete");
    const btnTypeUp = document.getElementById("btn-type-move-up");
    const btnTypeDown = document.getElementById("btn-type-move-down");
    if (btnTypeRename) btnTypeRename.disabled = !selectedTypeId;
    if (btnTypeDelete) btnTypeDelete.disabled = !selectedTypeId;
    if (btnTypeUp) btnTypeUp.disabled = !selectedTypeId;
    if (btnTypeDown) btnTypeDown.disabled = !selectedTypeId;
    
    // Page 4
    const btnClusterRename = document.getElementById("btn-cluster-rename");
    const btnClusterDelete = document.getElementById("btn-cluster-delete");
    const btnClusterUp = document.getElementById("btn-cluster-move-up");
    const btnClusterDown = document.getElementById("btn-cluster-move-down");
    if (btnClusterRename) btnClusterRename.disabled = !selectedClusterId;
    if (btnClusterDelete) btnClusterDelete.disabled = !selectedClusterId;
    if (btnClusterUp) btnClusterUp.disabled = !selectedClusterId;
    if (btnClusterDown) btnClusterDown.disabled = !selectedClusterId;
    
    // Page 5
    const btnTCEdit = document.getElementById("btn-tc-edit");
    const btnTCDelete = document.getElementById("btn-tc-delete");
    const btnTCUp = document.getElementById("btn-tc-move-up");
    const btnTCDown = document.getElementById("btn-tc-move-down");
    if (btnTCEdit) btnTCEdit.disabled = selectedTCIndex === null;
    if (btnTCDelete) btnTCDelete.disabled = selectedTCIndex === null;
    if (btnTCUp) btnTCUp.disabled = selectedTCIndex === null;
    if (btnTCDown) btnTCDown.disabled = selectedTCIndex === null;
}

function renderBreadcrumbs() {
    const container = document.getElementById("edit-tc-breadcrumbs");
    if (!container) return;
    
    container.innerHTML = "";
    
    const crumbs = [];
    crumbs.push({ label: "Home", target: "menu" });
    
    if (currentEditPage === "manage-selections") {
        crumbs.push({ label: "Manage Selections", target: "manage-selections" });
    } else if (currentEditPage === "select-selection") {
        crumbs.push({ label: "Edit Test Case Library", target: "select-selection" });
    } else if (currentEditPage === "manage-types") {
        crumbs.push({ label: "Edit Test Case Library", target: "select-selection" });
        crumbs.push({ label: editSelectionContext, target: "manage-types" });
    } else if (currentEditPage === "manage-clusters") {
        crumbs.push({ label: "Edit Test Case Library", target: "select-selection" });
        crumbs.push({ label: editSelectionContext, target: "manage-types" });
        crumbs.push({ label: editTypeContext ? editTypeContext.name : "Type", target: "manage-clusters" });
    } else if (currentEditPage === "manage-test-cases") {
        crumbs.push({ label: "Edit Test Case Library", target: "select-selection" });
        crumbs.push({ label: editSelectionContext, target: "manage-types" });
        crumbs.push({ label: editTypeContext ? editTypeContext.name : "Type", target: "manage-clusters" });
        crumbs.push({ label: editClusterContext ? editClusterContext.label : "Cluster", target: "manage-test-cases" });
    }
    
    crumbs.forEach((crumb, idx) => {
        if (idx > 0) {
            const separator = document.createElement("span");
            separator.className = "breadcrumb-separator";
            separator.innerHTML = "&gt;";
            container.appendChild(separator);
        }
        
        const span = document.createElement("span");
        span.className = "breadcrumb-item";
        if (idx === crumbs.length - 1) {
            span.classList.add("active");
        } else {
            span.addEventListener("click", () => showEditPage(crumb.target));
        }
        span.textContent = crumb.label;
        container.appendChild(span);
    });
}

// ─── RENDERERS ───────────────────────────────────────────────────────
function renderSelectionsGrid(elementId, isManageMode) {
    const grid = document.getElementById(elementId);
    if (!grid) return;
    grid.innerHTML = "";
    
    const selections = getActiveSelectionTypes();
    selections.forEach(sel => {
        const card = document.createElement("div");
        card.className = "card-item";
        if (isManageMode && selectedSelectionName === sel) {
            card.classList.add("selected");
        }
        
        // Count how many types/groups/test cases this selection has
        let tcCount = 0;
        state.testGroupsData.categories.forEach(cat => {
            cat.groups.forEach(g => {
                if (g.section_type && g.section_type.toLowerCase() === sel.toLowerCase()) {
                    tcCount += (g.test_cases || []).length;
                }
            });
        });
        
        card.innerHTML = `
            <h3>${escapeHTML(sel)}</h3>
            <div class="card-meta">${tcCount} Test Case${tcCount !== 1 ? "s" : ""}</div>
        `;
        
        if (!isManageMode) {
            const openBtn = document.createElement("button");
            openBtn.className = "card-item-open-btn";
            openBtn.innerHTML = "Edit Library &rarr;";
            openBtn.addEventListener("click", (e) => {
                e.stopPropagation();
                editSelectionContext = sel;
                showEditPage("manage-types");
            });
            card.appendChild(openBtn);
            
            // Double click to navigate
            card.addEventListener("dblclick", () => {
                editSelectionContext = sel;
                showEditPage("manage-types");
            });
        }
        
        card.addEventListener("click", () => {
            if (isManageMode) {
                selectedSelectionName = sel;
                // Highlight card
                grid.querySelectorAll(".card-item").forEach(c => c.classList.remove("selected"));
                card.classList.add("selected");
                updateToolbarButtonStates();
            }
        });
        
        grid.appendChild(card);
    });
}

function renderTypesPage() {
    const grid = document.getElementById("types-grid");
    if (!grid) return;
    grid.innerHTML = "";
    
    const lowerSel = editSelectionContext.toLowerCase();
    
    // Filter Categories/Types belonging to this selection
    const types = state.testGroupsData.categories.filter(cat => {
        return cat.groups.some(g => g.section_type && g.section_type.toLowerCase() === lowerSel);
    });
    
    if (types.length === 0) {
        grid.innerHTML = `
            <div class="empty-projects-message" style="grid-column: 1 / -1;">
                <p>No Types created for this selection yet.</p>
                <p>Add a Type using the toolbar above to get started.</p>
            </div>
        `;
        return;
    }
    
    types.forEach(type => {
        const card = document.createElement("div");
        card.className = "card-item";
        if (selectedTypeId === type.id) {
            card.classList.add("selected");
        }
        
        const clusters = type.groups.filter(g => g.section_type && g.section_type.toLowerCase() === lowerSel);
        const clusterCount = clusters.length;
        
        card.innerHTML = `
            <h3>${escapeHTML(type.name)}</h3>
            <div class="card-meta">${clusterCount} Cluster${clusterCount !== 1 ? "s" : ""}</div>
        `;
        
        const openBtn = document.createElement("button");
        openBtn.className = "card-item-open-btn";
        openBtn.innerHTML = "Open Clusters &rarr;";
        openBtn.addEventListener("click", (e) => {
            e.stopPropagation();
            editTypeContext = type;
            showEditPage("manage-clusters");
        });
        card.appendChild(openBtn);
        
        // Double click to navigate
        card.addEventListener("dblclick", () => {
            editTypeContext = type;
            showEditPage("manage-clusters");
        });
        
        card.addEventListener("click", () => {
            selectedTypeId = type.id;
            grid.querySelectorAll(".card-item").forEach(c => c.classList.remove("selected"));
            card.classList.add("selected");
            updateToolbarButtonStates();
        });
        
        grid.appendChild(card);
    });
}

function renderClustersPage() {
    const grid = document.getElementById("clusters-grid");
    if (!grid) return;
    grid.innerHTML = "";
    
    const lowerSel = editSelectionContext.toLowerCase();
    
    // Filter Clusters/Groups inside the current Type category that match the Selection
    const clusters = editTypeContext.groups.filter(g => g.section_type && g.section_type.toLowerCase() === lowerSel);
    
    if (clusters.length === 0) {
        grid.innerHTML = `
            <div class="empty-projects-message" style="grid-column: 1 / -1;">
                <p>No Clusters created for this Type yet.</p>
                <p>Add a Cluster using the toolbar above.</p>
            </div>
        `;
        return;
    }
    
    clusters.forEach(cluster => {
        const card = document.createElement("div");
        card.className = "card-item";
        if (selectedClusterId === cluster.id) {
            card.classList.add("selected");
        }
        
        const tcCount = (cluster.test_cases || []).length;
        
        card.innerHTML = `
            <h3>${escapeHTML(cluster.label)}</h3>
            <div class="card-meta">${tcCount} Test Case${tcCount !== 1 ? "s" : ""}</div>
        `;
        
        const openBtn = document.createElement("button");
        openBtn.className = "card-item-open-btn";
        openBtn.innerHTML = "Open Test Cases &rarr;";
        openBtn.addEventListener("click", (e) => {
            e.stopPropagation();
            editClusterContext = cluster;
            showEditPage("manage-test-cases");
        });
        card.appendChild(openBtn);
        
        // Double click to navigate
        card.addEventListener("dblclick", () => {
            editClusterContext = cluster;
            showEditPage("manage-test-cases");
        });
        
        card.addEventListener("click", () => {
            selectedClusterId = cluster.id;
            grid.querySelectorAll(".card-item").forEach(c => c.classList.remove("selected"));
            card.classList.add("selected");
            updateToolbarButtonStates();
        });
        
        grid.appendChild(card);
    });
}

function renderTestCasesPage() {
    const container = document.getElementById("tc-cards-container");
    if (!container) return;
    container.innerHTML = "";
    
    const tcs = editClusterContext.test_cases || [];
    
    if (tcs.length === 0) {
        container.innerHTML = `
            <div class="empty-projects-message">
                <p>No Test Cases in this cluster yet.</p>
                <p>Add a Test Case using the toolbar above.</p>
            </div>
        `;
        return;
    }
    
    tcs.forEach((tc, idx) => {
        const card = document.createElement("div");
        card.className = "tc-card";
        if (selectedTCIndex === idx) {
            card.classList.add("selected");
        }
        
        card.innerHTML = `
            <div class="tc-card-header">
                <span class="tc-card-sr">${idx + 1}</span>
                <h4 class="tc-card-title">${escapeHTML(tc.name)}</h4>
            </div>
            <div class="tc-card-body">
                <div class="tc-card-preview-block">
                    <span class="tc-card-preview-lbl">Prerequisites</span>
                    <span class="tc-card-preview-val">${escapeHTML(tc.pre_required_state || "—")}</span>
                </div>
                <div class="tc-card-preview-block">
                    <span class="tc-card-preview-lbl">Action / Procedure</span>
                    <span class="tc-card-preview-val">${escapeHTML(tc.action || "—")}</span>
                </div>
                <div class="tc-card-preview-block">
                    <span class="tc-card-preview-lbl">Expected Result</span>
                    <span class="tc-card-preview-val">${escapeHTML(tc.expected_result || "—")}</span>
                </div>
            </div>
        `;
        
        card.addEventListener("click", () => {
            selectedTCIndex = idx;
            container.querySelectorAll(".tc-card").forEach(c => c.classList.remove("selected"));
            card.classList.add("selected");
            updateToolbarButtonStates();
        });
        
        card.addEventListener("dblclick", () => {
            selectedTCIndex = idx;
            editGlobalTestCase();
        });
        
        container.appendChild(card);
    });
}

// ─── SELECTION CRUD ACTIONS ──────────────────────────────────────────
async function addGlobalSelection() {
    const name = prompt("Enter new Selection name (e.g. Shuttle, ASRS):");
    if (!name || !name.trim()) return;
    const cleanName = name.trim();
    
    const selections = getActiveSelectionTypes();
    if (selections.map(s => s.toLowerCase()).includes(cleanName.toLowerCase())) {
        alert(`A Selection named "${cleanName}" already exists.`);
        return;
    }
    
    if (!state.testGroupsData.selections) {
        state.testGroupsData.selections = ["Conveyor", "VRC"];
    }
    state.testGroupsData.selections.push(cleanName);
    
    // Automatically seed a default Type and Cluster for the new Selection
    const catId = "cat_" + Date.now();
    const groupId = "group_" + Date.now();
    const newCat = {
        id: catId,
        name: "General",
        category_number: state.testGroupsData.categories.length + 1,
        groups: [
            {
                id: groupId,
                label: "General",
                section_type: cleanName.toLowerCase(),
                ui_type: "checkbox",
                test_cases: []
            }
        ]
    };
    state.testGroupsData.categories.push(newCat);
    
    await saveTestGroupsDataPermanently();
    showStatus(`Created Selection "${cleanName}"`, "#10b981");
    renderSelectionsGrid("selections-grid-manage", true);
}

async function renameGlobalSelection() {
    if (!selectedSelectionName) return;
    
    const builtins = ["conveyor", "vrc"];
    const isBuiltin = builtins.includes(selectedSelectionName.toLowerCase());
    if (isBuiltin) {
        alert("Built-in selections (Conveyor, VRC) cannot be renamed.");
        return;
    }
    
    const newName = prompt(`Rename Selection "${selectedSelectionName}" to:`, selectedSelectionName);
    if (!newName || !newName.trim() || newName.trim() === selectedSelectionName) return;
    const cleanName = newName.trim();
    
    const selections = getActiveSelectionTypes();
    if (selections.map(s => s.toLowerCase()).includes(cleanName.toLowerCase()) && cleanName.toLowerCase() !== selectedSelectionName.toLowerCase()) {
        alert(`A Selection named "${cleanName}" already exists.`);
        return;
    }
    
    // Update selections list
    const idx = state.testGroupsData.selections.indexOf(selectedSelectionName);
    if (idx !== -1) {
        state.testGroupsData.selections[idx] = cleanName;
    }
    
    // Update category section types
    state.testGroupsData.categories.forEach(cat => {
        cat.groups.forEach(g => {
            if (g.section_type && g.section_type.toLowerCase() === selectedSelectionName.toLowerCase()) {
                g.section_type = cleanName.toLowerCase();
            }
        });
    });
    
    // Sync all projects
    await renameSelectionInProjects(selectedSelectionName, cleanName);

    await saveTestGroupsDataPermanently();
    showStatus(`Renamed Selection to "${cleanName}"`, "#10b981");
    selectedSelectionName = cleanName;
    renderSelectionsGrid("selections-grid-manage", true);
}

async function deleteGlobalSelection() {
    if (!selectedSelectionName) return;
    
    if (!confirm(`Are you sure you want to permanently delete the Selection "${selectedSelectionName}"?\nThis will remove all associated Types, Clusters, and Test Cases from the Master Library and all existing projects.`)) {
        return;
    }
    
    const lowerName = selectedSelectionName.toLowerCase();
    
    // Remove from selections list
    state.testGroupsData.selections = (state.testGroupsData.selections || []).filter(s => s.toLowerCase() !== lowerName);
    
    // Remove groups from all Categories
    state.testGroupsData.categories.forEach(cat => {
        cat.groups = cat.groups.filter(g => !g.section_type || g.section_type.toLowerCase() !== lowerName);
    });
    
    // Filter out empty categories
    state.testGroupsData.categories = state.testGroupsData.categories.filter(cat => cat.groups.length > 0);
    
    // Sync all projects
    await cleanupProjectsForDeletedSelection(selectedSelectionName);

    await saveTestGroupsDataPermanently();
    showStatus(`Deleted Selection "${selectedSelectionName}"`, "#ef4444");
    selectedSelectionName = null;
    renderSelectionsGrid("selections-grid-manage", true);
    updateToolbarButtonStates();
}

// Both functions below sync a global Selection rename/delete across every project. Since
// project data now lives server-side (one row per TestVaultProject), each affected project
// needs its own fetch-mutate-save round trip rather than a synchronous localStorage sweep.
async function renameSelectionInProjects(oldName, newName) {
    const oldLower = oldName.toLowerCase();
    const newLower = newName.toLowerCase();
    const projects = await fetchProjectsList();

    for (const proj of projects) {
        let detail;
        try {
            detail = await fetchAPI(`${API_BASE}/api/projects/${proj.id}/`);
        } catch (e) { continue; }
        const projectData = detail.project;

        let modified = false;
        if (projectData.custom_selection_types) {
            projectData.custom_selection_types = projectData.custom_selection_types.map(t => {
                if (t.toLowerCase() === oldLower) {
                    modified = true;
                    return newName;
                }
                return t;
            });
        }
        if (projectData.sections) {
            projectData.sections.forEach(sec => {
                if (sec.section_type.toLowerCase() === oldLower) {
                    sec.section_type = newLower;
                    modified = true;
                }
            });
        }
        if (modified) {
            await postJSON(`${API_BASE}/api/projects/${proj.id}/save/`, { project: projectData });
        }
    }
}

async function cleanupProjectsForDeletedSelection(selectionName) {
    const lowerName = selectionName.toLowerCase();
    const projects = await fetchProjectsList();

    for (const proj of projects) {
        let detail;
        try {
            detail = await fetchAPI(`${API_BASE}/api/projects/${proj.id}/`);
        } catch (e) { continue; }
        const projectData = detail.project;

        let modified = false;
        if (projectData.custom_selection_types) {
            const lenBefore = projectData.custom_selection_types.length;
            projectData.custom_selection_types = projectData.custom_selection_types.filter(t => t.toLowerCase() !== lowerName);
            if (projectData.custom_selection_types.length !== lenBefore) modified = true;
        }
        if (projectData.sections) {
            const lenBefore = projectData.sections.length;
            projectData.sections = projectData.sections.filter(sec => sec.section_type.toLowerCase() !== lowerName);
            if (projectData.sections.length !== lenBefore) modified = true;

            if (projectData.sections.length === 0) {
                const activeSelections = getActiveSelectionTypes();
                const fallbackType = activeSelections.length > 0 ? activeSelections[0].toLowerCase() : "conveyor";
                projectData.sections.push({
                    name: "Inbound",
                    section_type: fallbackType,
                    selected_groups: [],
                    dropdown_selections: {},
                    results: {},
                    observations: {},
                    project_only_test_cases: []
                });
                modified = true;
            }
        }
        if (modified) {
            await postJSON(`${API_BASE}/api/projects/${proj.id}/save/`, { project: projectData });
        }
    }
}

// ─── TYPE CRUD ACTIONS ───────────────────────────────────────────────
async function addGlobalType() {
    const name = prompt("Enter new Type name (e.g. Safety Interlock, Conveyor Operation):");
    if (!name || !name.trim()) return;
    const cleanName = name.trim();
    
    // Check if category already exists globally
    const exists = state.testGroupsData.categories.some(c => c.name.toLowerCase() === cleanName.toLowerCase());
    if (exists) {
        alert(`A Type with name "${cleanName}" already exists.`);
        return;
    }
    
    const catId = "cat_" + Date.now();
    const groupId = "group_" + Date.now();
    const newCat = {
        id: catId,
        name: cleanName,
        category_number: state.testGroupsData.categories.length + 1,
        groups: [
            {
                id: groupId,
                label: "General",
                section_type: editSelectionContext.toLowerCase(),
                ui_type: "checkbox",
                test_cases: []
            }
        ]
    };
    state.testGroupsData.categories.push(newCat);
    
    await saveTestGroupsDataPermanently();
    showStatus(`Created Type "${cleanName}"`, "#10b981");
    renderTypesPage();
}

async function renameGlobalType() {
    if (!selectedTypeId) return;
    
    const typeObj = state.testGroupsData.categories.find(c => c.id === selectedTypeId);
    if (!typeObj) return;
    
    const newName = prompt(`Rename Type to:`, typeObj.name);
    if (!newName || !newName.trim() || newName.trim() === typeObj.name) return;
    const cleanName = newName.trim();
    
    typeObj.name = cleanName;
    
    await saveTestGroupsDataPermanently();
    showStatus(`Renamed Type to "${cleanName}"`, "#10b981");
    renderTypesPage();
}

async function deleteGlobalType() {
    if (!selectedTypeId) return;
    
    const typeObj = state.testGroupsData.categories.find(c => c.id === selectedTypeId);
    if (!typeObj) return;
    
    if (!confirm(`Are you sure you want to permanently delete the Type "${typeObj.name}"?\nThis will remove it and all of its clusters/test cases from Selection "${editSelectionContext}".`)) {
        return;
    }
    
    const lowerSel = editSelectionContext.toLowerCase();
    
    // Remove groups of this selection type
    typeObj.groups = typeObj.groups.filter(g => !g.section_type || g.section_type.toLowerCase() !== lowerSel);
    
    // If the Category/Type has no groups left at all, delete it from categories list
    if (typeObj.groups.length === 0) {
        state.testGroupsData.categories = state.testGroupsData.categories.filter(c => c.id !== selectedTypeId);
    }
    
    await saveTestGroupsDataPermanently();
    showStatus("Deleted Type permanently.", "#ef4444");
    selectedTypeId = null;
    renderTypesPage();
    updateToolbarButtonStates();
}

async function moveGlobalType(direction) {
    if (!selectedTypeId) return;
    
    const categories = state.testGroupsData.categories;
    const idx = categories.findIndex(c => c.id === selectedTypeId);
    if (idx === -1) return;
    
    const lowerSel = editSelectionContext.toLowerCase();
    
    // Find adjacent category belonging to the current selection to swap with
    let targetIdx = -1;
    if (direction === -1) { // up
        for (let i = idx - 1; i >= 0; i--) {
            if (categories[i].groups.some(g => g.section_type && g.section_type.toLowerCase() === lowerSel)) {
                targetIdx = i;
                break;
            }
        }
    } else { // down
        for (let i = idx + 1; i < categories.length; i++) {
            if (categories[i].groups.some(g => g.section_type && g.section_type.toLowerCase() === lowerSel)) {
                targetIdx = i;
                break;
            }
        }
    }
    
    if (targetIdx !== -1) {
        // Swap category ordering
        const temp = categories[idx];
        categories[idx] = categories[targetIdx];
        categories[targetIdx] = temp;
        
        await saveTestGroupsDataPermanently();
        renderTypesPage();
    }
}

// ─── CLUSTER CRUD ACTIONS ────────────────────────────────────────────
async function addGlobalCluster() {
    const label = prompt("Enter new Cluster name:");
    if (!label || !label.trim()) return;
    const cleanLabel = label.trim();
    
    const exists = editTypeContext.groups.some(g => g.label.toLowerCase() === cleanLabel.toLowerCase() && g.section_type && g.section_type.toLowerCase() === editSelectionContext.toLowerCase());
    if (exists) {
        alert(`A Cluster named "${cleanLabel}" already exists in this Type.`);
        return;
    }
    
    const newGroup = {
        id: "group_" + Date.now(),
        label: cleanLabel,
        section_type: editSelectionContext.toLowerCase(),
        ui_type: "checkbox",
        test_cases: []
    };
    editTypeContext.groups.push(newGroup);
    
    await saveTestGroupsDataPermanently();
    showStatus(`Created Cluster "${cleanLabel}"`, "#10b981");
    renderClustersPage();
}

async function renameGlobalCluster() {
    if (!selectedClusterId) return;
    
    const cluster = editTypeContext.groups.find(g => g.id === selectedClusterId);
    if (!cluster) return;
    
    const newLabel = prompt("Rename Cluster to:", cluster.label);
    if (!newLabel || !newLabel.trim() || newLabel.trim() === cluster.label) return;
    const cleanLabel = newLabel.trim();
    
    cluster.label = cleanLabel;
    
    await saveTestGroupsDataPermanently();
    showStatus(`Renamed Cluster to "${cleanLabel}"`, "#10b981");
    renderClustersPage();
}

async function deleteGlobalCluster() {
    if (!selectedClusterId) return;
    
    const cluster = editTypeContext.groups.find(g => g.id === selectedClusterId);
    if (!cluster) return;
    
    if (!confirm(`Are you sure you want to permanently delete the Cluster "${cluster.label}" and all its test cases?`)) {
        return;
    }
    
    editTypeContext.groups = editTypeContext.groups.filter(g => g.id !== selectedClusterId);
    
    await saveTestGroupsDataPermanently();
    showStatus("Deleted Cluster permanently.", "#ef4444");
    selectedClusterId = null;
    renderClustersPage();
    updateToolbarButtonStates();
}

async function moveGlobalCluster(direction) {
    if (!selectedClusterId) return;
    
    const groups = editTypeContext.groups;
    const idx = groups.findIndex(g => g.id === selectedClusterId);
    if (idx === -1) return;
    
    const lowerSel = editSelectionContext.toLowerCase();
    
    let targetIdx = -1;
    if (direction === -1) { // up
        for (let i = idx - 1; i >= 0; i--) {
            if (groups[i].section_type && groups[i].section_type.toLowerCase() === lowerSel) {
                targetIdx = i;
                break;
            }
        }
    } else { // down
        for (let i = idx + 1; i < groups.length; i++) {
            if (groups[i].section_type && groups[i].section_type.toLowerCase() === lowerSel) {
                targetIdx = i;
                break;
            }
        }
    }
    
    if (targetIdx !== -1) {
        const temp = groups[idx];
        groups[idx] = groups[targetIdx];
        groups[targetIdx] = temp;
        
        await saveTestGroupsDataPermanently();
        renderClustersPage();
    }
}

// ─── TEST CASE CRUD ACTIONS ──────────────────────────────────────────
async function addGlobalTestCase() {
    const name = prompt("Enter new Test Case Name:");
    if (!name || !name.trim()) return;
    const cleanName = name.trim();
    
    const newTC = {
        name: cleanName,
        pre_required_state: "",
        action: "",
        expected_result: ""
    };
    
    if (!editClusterContext.test_cases) {
        editClusterContext.test_cases = [];
    }
    editClusterContext.test_cases.push(newTC);
    
    await saveTestGroupsDataPermanently();
    showStatus(`Created Test Case "${cleanName}"`, "#10b981");
    renderTestCasesPage();
    
    // Automatically select and open the edit modal for the newly added testcase
    selectedTCIndex = editClusterContext.test_cases.length - 1;
    editGlobalTestCase();
}

function editGlobalTestCase() {
    if (selectedTCIndex === null) return;
    
    const tc = editClusterContext.test_cases[selectedTCIndex];
    if (!tc) return;
    
    document.getElementById("edit-modal-tc-name").value = tc.name || "";
    document.getElementById("edit-modal-tc-prereq").value = tc.pre_required_state || "";
    document.getElementById("edit-modal-tc-action").value = tc.action || "";
    document.getElementById("edit-modal-tc-expected").value = tc.expected_result || "";
    
    document.getElementById("edit-tc-modal").classList.add("open");
}

function closeEditTCModal() {
    document.getElementById("edit-tc-modal").classList.remove("open");
}

async function saveModalTestCase() {
    if (selectedTCIndex === null) return;
    
    const name = document.getElementById("edit-modal-tc-name").value.trim();
    const prereq = document.getElementById("edit-modal-tc-prereq").value.trim();
    const action = document.getElementById("edit-modal-tc-action").value.trim();
    const expected = document.getElementById("edit-modal-tc-expected").value.trim();
    
    if (!name) {
        alert("Test Case Name is required.");
        return;
    }
    
    const tc = editClusterContext.test_cases[selectedTCIndex];
    if (tc) {
        tc.name = name;
        tc.pre_required_state = prereq;
        tc.action = action;
        tc.expected_result = expected;
    }
    
    closeEditTCModal();
    await saveTestGroupsDataPermanently();
    showStatus("Test case updated permanently.", "#10b981");
    renderTestCasesPage();
}

async function deleteGlobalTestCase() {
    if (selectedTCIndex === null) return;
    
    const tc = editClusterContext.test_cases[selectedTCIndex];
    if (!tc) return;
    
    if (!confirm(`Are you sure you want to permanently delete the test case "${tc.name}"?`)) {
        return;
    }
    
    editClusterContext.test_cases = editClusterContext.test_cases.filter((_, idx) => idx !== selectedTCIndex);
    
    await saveTestGroupsDataPermanently();
    showStatus("Deleted Test Case permanently.", "#ef4444");
    selectedTCIndex = null;
    renderTestCasesPage();
    updateToolbarButtonStates();
}

async function moveGlobalTestCase(direction) {
    if (selectedTCIndex === null) return;
    
    const tcs = editClusterContext.test_cases || [];
    const idx = selectedTCIndex;
    const nextIdx = idx + direction;
    
    if (nextIdx < 0 || nextIdx >= tcs.length) return;
    
    const temp = tcs[idx];
    tcs[idx] = tcs[nextIdx];
    tcs[nextIdx] = temp;
    
    selectedTCIndex = nextIdx;
    
    await saveTestGroupsDataPermanently();
    renderTestCasesPage();
}

// ─── AUTO-MIGRATION OF LOCAL PROJECTS SELECTIONS ─────────────────────
function migrateProjectSelectionsToGlobal() {
    if (!state.testGroupsData || !state.testGroupsData.selections) return;
    if (!state.project || !state.project.custom_selection_types) return;
    
    let modified = false;
    state.project.custom_selection_types.forEach(t => {
        const selectionsLower = state.testGroupsData.selections.map(s => s.toLowerCase());
        if (!selectionsLower.includes(t.toLowerCase())) {
            state.testGroupsData.selections.push(t);
            modified = true;
        }
    });
    
    if (modified) {
        saveTestGroupsDataPermanently();
    }
}

function updateLiveTime() {
    const el = document.getElementById("dash-live-time");
    if (!el) return;
    const now = new Date();
    const options = { day: "2-digit", month: "short", year: "numeric" };
    const dateStr = now.toLocaleDateString("en-GB", options);
    const timeStr = now.toLocaleTimeString("en-GB", { hour12: false });
    el.textContent = `${dateStr}  ${timeStr}`;
}
setInterval(updateLiveTime, 1000);
