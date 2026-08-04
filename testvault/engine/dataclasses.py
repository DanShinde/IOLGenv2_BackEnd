"""
Data models for the EFS Test Case Generator.

Section types:
- "conveyor": Shows test groups tagged [1] and conveyor variants of [1/2]
- "vrc": Shows test groups tagged [2] and VRC variants of [1/2]

UI types:
- "checkbox": Select group → all test cases included
- "dropdown": Select group → pick individual test cases
"""
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ProjectInfo:
    """Project metadata entered by the user."""
    project_code: str = ""
    zone_name: str = ""
    customer_name: str = ""
    done_by: str = ""
    date_of_validation: str = ""
    validator_type: str = "Self"
    validator_name: str = ""
    testing_phase: str = "Emulation"

    def to_dict(self) -> dict:
        return {
            "project_code": self.project_code,
            "zone_name": self.zone_name,
            "customer_name": self.customer_name,
            "done_by": self.done_by,
            "date_of_validation": self.date_of_validation,
            "validator_type": self.validator_type,
            "validator_name": self.validator_name,
            "testing_phase": self.testing_phase,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ProjectInfo":
        return cls(
            project_code=data.get("project_code", ""),
            zone_name=data.get("zone_name", ""),
            customer_name=data.get("customer_name", ""),
            done_by=data.get("done_by", ""),
            date_of_validation=data.get("date_of_validation", ""),
            validator_type=data.get("validator_type", "Self"),
            validator_name=data.get("validator_name", ""),
            testing_phase=data.get("testing_phase", "Emulation"),
        )


@dataclass
class GeneratedTestCase:
    """A fully generated test case ready for Excel output."""
    sr_no: str = ""
    test_case_name: str = ""
    pre_required_state: str = ""
    action: str = ""
    expected_result: str = ""
    result: str = "Pending"
    observation: str = ""
    category: str = ""


@dataclass
class Section:
    """
    A project section/area.

    section_type: "conveyor" or "vrc" — controls which test groups are available
    selected_groups: list of group IDs that are checked/enabled
    dropdown_selections: for dropdown-type groups, maps group_id -> list of selected test case names
    """
    name: str = ""
    section_type: str = "conveyor"
    selected_groups: list[str] = field(default_factory=list)
    dropdown_selections: dict[str, list[str]] = field(default_factory=dict)
    results: dict[str, str] = field(default_factory=dict)             # tc_name -> result status
    observations: dict[str, str] = field(default_factory=dict)       # tc_name -> observation text
    project_only_test_cases: list[dict] = field(default_factory=list) # custom test cases
    custom_clusters: list[dict] = field(default_factory=list)         # [{id, name}]
    session_test_cases: dict[str, list[dict]] = field(default_factory=dict) # session custom test cases

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "section_type": self.section_type,
            "selected_groups": list(self.selected_groups),
            "dropdown_selections": dict(self.dropdown_selections),
            "results": dict(self.results),
            "observations": dict(self.observations),
            "project_only_test_cases": list(self.project_only_test_cases),
            "custom_clusters": list(self.custom_clusters),
            "session_test_cases": dict(self.session_test_cases),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Section":
        return cls(
            name=data.get("name", ""),
            section_type=data.get("section_type", "conveyor"),
            selected_groups=data.get("selected_groups", []),
            dropdown_selections=data.get("dropdown_selections", {}),
            results=data.get("results", {}),
            observations=data.get("observations", {}),
            project_only_test_cases=data.get("project_only_test_cases", []),
            custom_clusters=data.get("custom_clusters", []),
            session_test_cases=data.get("session_test_cases", {}),
        )


@dataclass
class Project:
    """Full project configuration."""
    info: ProjectInfo = field(default_factory=ProjectInfo)
    sections: list[Section] = field(default_factory=list)
    custom_selection_types: list[str] = field(default_factory=list)
    deleted_selection_types: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "info": self.info.to_dict(),
            "sections": [s.to_dict() for s in self.sections],
            "custom_selection_types": list(self.custom_selection_types),
            "deleted_selection_types": list(self.deleted_selection_types),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Project":
        return cls(
            info=ProjectInfo.from_dict(data.get("info", {})),
            sections=[Section.from_dict(s) for s in data.get("sections", [])],
            custom_selection_types=data.get("custom_selection_types", []),
            deleted_selection_types=data.get("deleted_selection_types", []),
        )
