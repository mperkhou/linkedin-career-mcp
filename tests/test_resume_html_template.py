from pathlib import Path

import yaml

from scripts.render_resume_html import render_resume_html


def test_resume_html_template_renders_trimmed_application_object(tmp_path: Path) -> None:
    yaml_path = tmp_path / "trimmed-resume.yaml"
    yaml_path.write_text(
        yaml.safe_dump(
            {
                "header_top": {
                    "line_1_name_header_text": "Max Perkhounkov",
                    "contact_items": ["Iowa City, IA", "mperkhounkov1@gmail.com"],
                },
                "core_technical_skills": {
                    "bullet_points": [
                        {
                            "category": "AI Platform",
                            "items": ["Python", "Jinja2", "OpenRouter"],
                        },
                        {
                            "category": "Languages & Frameworks",
                            "items": {
                                "primary": ["Python", "Ruby"],
                                "additional": ["R", "MATLAB", "AutoIT"],
                            },
                            "jod_matched_items": ["MATLAB", "Not in inventory", "Python"],
                        },
                        "Plain fallback skill row",
                    ]
                },
                "professional_experience": {
                    "jobs": [
                        {
                            "render": True,
                            "line_1": {"company_name_text": "Oracle | Remote"},
                            "bullet_points": [
                                {
                                    "bold_label": "Agentic Workflow",
                                    "text": "Built a dynamic renderer prototype.",
                                    "render": True,
                                },
                                {
                                    "bold_label": "Hidden Workflow",
                                    "text": "This bullet should not render.",
                                    "render": False,
                                },
                                "Plain fallback experience bullet.",
                            ],
                        },
                        {
                            "render": False,
                            "line_1": {"company_name_text": "Hidden Company"},
                            "bullet_points": [
                                {
                                    "bold_label": "Hidden Job",
                                    "text": "This job should not render.",
                                    "render": True,
                                }
                            ],
                        }
                    ]
                },
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    html = render_resume_html(
        yaml_path=yaml_path,
        template_path=Path("templates/resume/master_resume.html.j2"),
    )

    assert "Core Technical Skills" in html
    assert "Professional Experience" in html
    assert "Education &amp; Certifications" not in html
    assert "Professional Summary" not in html
    assert "<strong>AI Platform:</strong> Python, Jinja2, OpenRouter" in html
    assert "<strong>Languages &amp; Frameworks:</strong> Python, Ruby, MATLAB" in html
    assert "Not in inventory" not in html
    assert "<strong>Agentic Workflow:</strong> Built a dynamic renderer prototype." in html
    assert "This bullet should not render" not in html
    assert "Hidden Company" not in html
    assert "This job should not render" not in html


def test_resume_html_template_honors_section_render_flags(tmp_path: Path) -> None:
    yaml_path = tmp_path / "section-render-flags.yaml"
    yaml_path.write_text(
        yaml.safe_dump(
            {
                "header_top": {
                    "render": True,
                    "line_1_name_header_text": "Max Perkhounkov",
                    "contact_items": ["Iowa City, IA"],
                },
                "professional_summary": {
                    "render": False,
                    "paragraph": "This summary should not render.",
                },
                "core_technical_skills": {
                    "render": False,
                    "bullet_points": [{"category": "Hidden Skills", "items": ["Python"]}],
                },
                "professional_experience": {
                    "render": False,
                    "jobs": [
                        {
                            "render": True,
                            "line_1": {"company_name_text": "Hidden Employer"},
                            "bullet_points": ["This job should not render."],
                        }
                    ],
                },
                "education": {
                    "render": True,
                    "header_text": "Education",
                    "entries": [
                        {
                            "line_1": {"institution_name_text": "University of Iowa"},
                            "line_2": {
                                "degree_name_text": "Bachelor of Science",
                                "degree_dates_text": "2009 - 2013",
                            },
                            "bullet_points": [
                                {"text": "Visible education detail.", "render": True},
                                {"text": "Hidden education detail.", "render": False},
                            ],
                        }
                    ],
                },
                "certifications": {
                    "render": True,
                    "header_text": "Certifications",
                    "bullet_points": [
                        {"text": "Visible certification.", "render": True},
                        {"text": "Hidden certification.", "render": False},
                    ],
                },
                "portfolio": {
                    "render": True,
                    "header_text": "Portfolio",
                    "projects": [
                        {
                            "title_text": "Visible Project",
                            "url": "https://example.com/project",
                            "description_text": "Visible portfolio detail.",
                            "render": True,
                        },
                        {
                            "title_text": "Hidden Project",
                            "description_text": "Hidden portfolio detail.",
                            "render": False,
                        },
                    ],
                },
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    html = render_resume_html(
        yaml_path=yaml_path,
        template_path=Path("templates/resume/master_resume.html.j2"),
    )

    assert "This summary should not render" not in html
    assert "Hidden Skills" not in html
    assert "Hidden Employer" not in html
    assert "University of Iowa" in html
    assert "Visible education detail" in html
    assert "Hidden education detail" not in html
    assert "Visible certification" in html
    assert "Hidden certification" not in html
    assert "Visible Project" in html
    assert "Visible portfolio detail" in html
    assert "Hidden Project" not in html
