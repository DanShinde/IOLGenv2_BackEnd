"""
Test case generation engine — category/group/section-type system.

Data flow:
1. Load test_groups.json (categories → groups → test_cases)
2. For a section: filter groups by section_type, then by selected_groups
3. For checkbox groups: include ALL test cases in the group
4. For dropdown groups: include only the test cases selected in dropdown_selections
5. Deduplicate by test_case_name
6. Group by category in cluster order, assign sequential sr_no
"""
import json
from pathlib import Path
from typing import Optional

from .dataclasses import GeneratedTestCase, Section


class TestCaseEngine:
    """Loads test case data and generates test cases for sections."""

    def __init__(self, data_dir: Optional[Path] = None):
        if data_dir is None:
            # Bundled defaults, used only when the caller doesn't pass an explicit
            # writable dir. Django views always pass settings.TESTVAULT_DATA_DIR.
            data_dir = Path(__file__).parent / "data"
        self.data_dir = data_dir
        self._test_groups_data: dict = {}
        self._load_data()

    def _load_data(self) -> None:
        """Load test groups data from JSON file."""
        tg_file = self.data_dir / "test_groups.json"
        if tg_file.exists():
            with open(tg_file, "r", encoding="utf-8") as f:
                self._test_groups_data = json.load(f)
        else:
            print(f"Warning: Test groups file not found: {tg_file}")
            self._test_groups_data = {"categories": []}

    def get_categories(self) -> list[dict]:
        """Return all categories from test_groups.json."""
        return self._test_groups_data.get("categories", [])

    def get_groups_for_section_type(self, section_type: str) -> list[dict]:
        """
        Return groups applicable to a section type, organized by category.

        Returns list of: {category_name, category_id, groups: [...]}
        """
        result = []
        for category in self.get_categories():
            applicable_groups = []
            for group in category.get("groups", []):
                grp_type = group.get("section_type", "any")
                if grp_type == "any" or grp_type == section_type:
                    applicable_groups.append(group)
            if applicable_groups:
                result.append({
                    "category_name": category["name"],
                    "category_id": category["id"],
                    "category_number": category.get("category_number", 0),
                    "groups": applicable_groups,
                })
        return result

    def generate_test_cases(
        self, section: Section, exclude_custom: bool = False, only_custom: bool = False
    ) -> list[GeneratedTestCase]:
        """
        Generate deduplicated, categorized test cases for a section.

        Args:
            section: Section with section_type, selected_groups, dropdown_selections
            exclude_custom: If True, do not include permanent or project-only custom test cases
            only_custom: If True, include ONLY permanent and project-only custom test cases

        Returns:
            List of GeneratedTestCase objects grouped by category with sequential sr_no
        """
        collected: list[tuple[str, dict]] = []  # (category_name, test_case_dict)
        seen_names: set[str] = set()

        # Load permanent custom test cases
        perm_custom = self._load_permanent_custom_test_cases() if not exclude_custom else []

        # 1. Collect test cases from selected groups in test_groups.json
        #    This applies to ALL section types (conveyor, vrc, AND custom selections)
        for category in self.get_categories():
            cat_name = category["name"]
            for group in category.get("groups", []):
                group_id = group["id"]
                grp_type = group.get("section_type", "any")

                # Skip groups not applicable to this section type
                if grp_type != "any" and grp_type != section.section_type:
                    continue

                # Skip groups not selected by user
                if group_id not in section.selected_groups:
                    continue

                ui_type = group.get("ui_type", "checkbox")
                
                # Check if session-modified test cases exist for this group
                session_custom = None
                if hasattr(section, "session_test_cases") and section.session_test_cases:
                    session_custom = section.session_test_cases.get(group_id)
                
                if session_custom is not None:
                    all_test_cases = list(session_custom)
                else:
                    base_test_cases = list(group.get("test_cases", [])) if not only_custom else []
                    # Inject permanent custom test cases for this group
                    group_perm = [tc for tc in perm_custom if tc.get("group_id") == group_id] if not exclude_custom else []
                    # Inject project-only custom test cases for this group
                    group_proj = [tc for tc in section.project_only_test_cases if tc.get("group_id") == group_id] if not exclude_custom else []
                    all_test_cases = base_test_cases + group_perm + group_proj

                if ui_type == "dropdown":
                    # For dropdown groups, only include selected test cases
                    selected_tc_names = section.dropdown_selections.get(group_id, [])
                    for tc in all_test_cases:
                        if tc["name"] in selected_tc_names:
                            if tc["name"] not in seen_names:
                                collected.append((cat_name, tc))
                                seen_names.add(tc["name"])
                else:
                    # For checkbox groups, include ALL test cases
                    for tc in all_test_cases:
                        if tc["name"] not in seen_names:
                            collected.append((cat_name, tc))
                            seen_names.add(tc["name"])

        # 1b. For custom selection types, also collect project-only test cases
        #     grouped by custom clusters (these are not in test_groups.json)
        if section.section_type not in ("conveyor", "vrc") and not exclude_custom:
            custom_cls = getattr(section, "custom_clusters", []) or []
            cluster_map = {c["id"]: c["name"] for c in custom_cls if "id" in c and "name" in c}
            
            if cluster_map:
                for cluster in custom_cls:
                    cid = cluster["id"]
                    cname = cluster["name"]
                    for tc in section.project_only_test_cases:
                        if tc.get("group_id") == cid:
                            if tc["name"] not in seen_names:
                                collected.append((cname, tc))
                                seen_names.add(tc["name"])
            
            # Fallback group for project-only TCs without a cluster
            fallback_cat = f"Custom {section.section_type.capitalize()}"
            for tc in section.project_only_test_cases:
                if tc["name"] not in seen_names:
                    collected.append((fallback_cat, tc))
                    seen_names.add(tc["name"])

        # 2. Group by category, preserving cluster order from JSON
        category_order: list[str] = []
        category_map: dict[str, list[dict]] = {}
        for cat_name, tc in collected:
            if cat_name not in category_map:
                category_order.append(cat_name)
                category_map[cat_name] = []
            category_map[cat_name].append(tc)

        # 3. Build GeneratedTestCase list with sequential sr_no
        result: list[GeneratedTestCase] = []
        for cat_idx, cat_name in enumerate(category_order, start=1):
            for tc_idx, tc in enumerate(category_map[cat_name], start=1):
                tc_name = tc.get("name", "")
                result.append(
                    GeneratedTestCase(
                        sr_no=f"{cat_idx}.{tc_idx}",
                        test_case_name=tc_name,
                        pre_required_state=tc.get("pre_required_state", ""),
                        action=tc.get("action", ""),
                        expected_result=tc.get("expected_result", ""),
                        result=section.results.get(tc_name, "Pending"),
                        observation=section.observations.get(tc_name, ""),
                        category=cat_name,
                    )
                )

        return result

    def _load_permanent_custom_test_cases(self) -> list[dict]:
        """Load permanent custom test cases from local custom_test_cases.json."""
        custom_file = self.data_dir / "custom_test_cases.json"
        if custom_file.exists():
            try:
                with open(custom_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return []
        return []

    def _save_permanent_custom_test_cases(self, custom_tcs: list[dict]) -> None:
        """Save permanent custom test cases to local custom_test_cases.json."""
        custom_file = self.data_dir / "custom_test_cases.json"
        try:
            with open(custom_file, "w", encoding="utf-8") as f:
                json.dump(custom_tcs, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"Error saving custom test cases: {e}")

    def add_permanent_custom_test_case(self, tc: dict) -> None:
        """Add a custom testcase permanently."""
        custom_tcs = self._load_permanent_custom_test_cases()
        # Remove any existing with same name to avoid duplicate
        custom_tcs = [item for item in custom_tcs if item.get("name") != tc.get("name")]
        custom_tcs.append(tc)
        self._save_permanent_custom_test_cases(custom_tcs)

    def delete_permanent_custom_test_case(self, name: str) -> None:
        """Delete a custom testcase permanently."""
        custom_tcs = self._load_permanent_custom_test_cases()
        custom_tcs = [item for item in custom_tcs if item.get("name") != name]
        self._save_permanent_custom_test_cases(custom_tcs)

    def edit_permanent_custom_test_case(self, old_name: str, tc: dict) -> None:
        """Edit a custom testcase permanently."""
        custom_tcs = self._load_permanent_custom_test_cases()
        # Remove old name
        custom_tcs = [item for item in custom_tcs if item.get("name") != old_name]
        # Append updated one
        custom_tcs.append(tc)
        self._save_permanent_custom_test_cases(custom_tcs)

    def reload_data(self) -> None:
        """Reload all data from JSON files."""
        self._test_groups_data = {}
        self._load_data()

    def save_test_groups_data(self, categories_data: list[dict]) -> None:
        """Save the updated categories list permanently to test_groups.json."""
        self._test_groups_data["categories"] = categories_data
        tg_file = self.data_dir / "test_groups.json"
        try:
            with open(tg_file, "w", encoding="utf-8") as f:
                json.dump(self._test_groups_data, f, indent=2, ensure_ascii=False)
            self.reload_data()
        except Exception as e:
            print(f"Error saving test groups: {e}")

