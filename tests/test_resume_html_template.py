from pathlib import Path

import yaml
from bs4 import BeautifulSoup

from scripts.render_resume_html import render_resume_html

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CANONICAL_RESUME_PATH = PROJECT_ROOT / "profile" / "MASTER-RESUME.yml"
RESUME_TEMPLATE_PATH = PROJECT_ROOT / "templates" / "resume" / "master_resume.html.j2"


def test_resume_html_template_renders_trimmed_application_object(tmp_path: Path) -> None:
    yaml_path = tmp_path / "trimmed-resume.yaml"
    yaml_path.write_text(
        yaml.safe_dump(
            {
                "header_top": {
                    "line_1_name_header_text": "Max Perkhounkov",
                    "line_2_header_text": "<b>Platform Automation Engineer</b>",
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
                                "additional": ["R", "MATLAB", "AutoIT", "RESTful APIs"],
                                "match_terms": {
                                    "RESTful APIs": ["REST APIs"],
                                },
                            },
                            "jod_matched_items": [
                                "MATLAB",
                                "Not in inventory",
                                "Python",
                                "REST APIs",
                            ],
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
                                    "text": "Built a <b>dynamic</b> renderer prototype.",
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
    assert '<p class="resume-headline"><b>Platform Automation Engineer</b></p>' in html
    assert "Education &amp; Certifications" not in html
    assert "Professional Summary" not in html
    assert "<strong>AI Platform:</strong> Python, Jinja2, OpenRouter" in html
    assert (
        "<strong>Languages &amp; Frameworks:</strong> Ruby, MATLAB, RESTful APIs"
        in html
    )
    assert "Not in inventory" not in html
    assert "REST APIs" not in html
    assert (
        "<strong>Agentic Workflow:</strong> Built a <b>dynamic</b> renderer prototype."
        in html
    )
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
                    "line_2_header_text": "",
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
    assert '<p class="resume-headline">' not in html
    assert "Hidden Skills" not in html
    assert "Hidden Employer" not in html
    assert "University of Iowa" in html
    assert "Visible education detail" in html
    assert "Hidden education detail" not in html
    soup = BeautifulSoup(html, "html.parser")
    education_heading = soup.find("h2", string="Education")
    assert education_heading is not None
    education_section = education_heading.find_parent("section")
    assert education_section is not None
    education_entry = education_section.find("article", class_="education-item")
    assert education_entry is not None
    assert education_entry.find_parent("li") is None
    assert education_entry.find("h3", class_="job-company").get_text(strip=True) == (
        "University of Iowa"
    )
    degree_text = education_entry.find("p", class_="job-title").get_text(" ", strip=True)
    assert " ".join(degree_text.split()) == "Bachelor of Science | 2009 - 2013"
    assert education_entry.find("ul", class_="nested-list") is None
    assert education_entry.find("ul", class_="bullet-list").find("li").get_text(
        " ",
        strip=True,
    ) == "Visible education detail."
    assert "Visible certification" in html
    assert "Hidden certification" not in html
    assert "Visible Project" in html
    assert "Visible portfolio detail" in html
    assert "Hidden Project" not in html


def test_resume_html_template_caps_matched_additional_skills(tmp_path: Path) -> None:
    yaml_path = tmp_path / "capped-skills.yaml"
    additional = [f"Extra Skill {index}" for index in range(1, 11)]
    yaml_path.write_text(
        yaml.safe_dump(
            {
                "header_top": {"line_1_name_header_text": "Max Perkhounkov"},
                "core_technical_skills": {
                    "bullet_points": [
                        {
                            "category": "Platform",
                            "items": {
                                "primary": ["Python"],
                                "additional": additional,
                            },
                            "jod_matched_items": additional,
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

    assert "Extra Skill 8" in html
    assert "Extra Skill 9" not in html
    assert "<strong>Platform:</strong> Python" in html


def test_resume_html_template_renders_generic_summary_note_http_links(tmp_path: Path) -> None:
    yaml_path = tmp_path / "summary-note-http-links.yaml"
    yaml_path.write_text(
        yaml.safe_dump(
            {
                "header_top": {"line_1_name_header_text": "Max Perkhounkov"},
                "professional_summary": {
                    "paragraph": "Platform engineer.",
                    "summary_note": (
                        "See https://example.com/portfolio and http://example.test/guide."
                    ),
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

    assert '<p class="summary-note">' in html
    assert (
        '<a href="https://example.com/portfolio">https://example.com/portfolio</a>'
        in html
    )
    assert '<a href="http://example.test/guide">http://example.test/guide</a>.' in html


def test_canonical_resume_omits_automation_disclaimer_and_preserves_portfolio() -> None:
    master_resume = yaml.safe_load(CANONICAL_RESUME_PATH.read_text(encoding="utf-8"))
    summary = master_resume["professional_summary"]
    project = master_resume["portfolio"]["projects"][0]

    assert summary.get("summary_note", "") == ""
    assert "custom tailored for every job position" not in yaml.safe_dump(master_resume)
    assert project["title_text"] == "LinkedIn Career MCP"
    assert project["url"] == "https://github.com/mperkhou/linkedin-career-mcp"
    assert project["description_text"] == (
        "A local-first Python and MCP platform for orchestrating evidence-grounded "
        "career data and document workflows, with SQLite-backed state, versioned "
        "artifacts, retryable batch processing, ATS diagnostics, human review gates, "
        "and agentic workflow controls."
    )

    html = render_resume_html(
        yaml_path=CANONICAL_RESUME_PATH,
        template_path=RESUME_TEMPLATE_PATH,
    )

    assert "custom tailored for every job position" not in html.lower()
    assert "automated agentic workflow" not in html.lower()
    assert "LinkedIn Career MCP" in html
    assert project["description_text"] in html
    assert 'href="https://github.com/mperkhou/linkedin-career-mcp"' in html


def test_resume_html_template_groups_supporting_sections_with_optional_page_break(
    tmp_path: Path,
) -> None:
    yaml_path = tmp_path / "supporting-sections-page-two.yaml"
    resume = {
        "header_top": {
            "line_1_name_header_text": "Max Perkhounkov",
            "contact_items": ["Iowa City, IA"],
        },
        "professional_summary": {"paragraph": "Senior platform engineer."},
        "professional_experience": {
            "jobs": [
                {
                    "line_1": {"company_name_text": "Oracle"},
                    "bullet_points": ["Built cloud automation."],
                }
            ]
        },
        "education": {
            "entries": [
                {
                    "line_1": {"institution_name_text": "University of Iowa"},
                    "line_2": {"degree_name_text": "Bachelor of Science"},
                }
            ]
        },
        "certifications": {"bullet_points": ["AWS Certified Cloud Practitioner"]},
        "portfolio": {
            "projects": [
                {
                    "title_text": "linkedin-career-mcp",
                    "url": "https://github.com/mperkhou/linkedin-career-mcp",
                }
            ]
        },
    }
    yaml_path.write_text(yaml.safe_dump(resume, sort_keys=False), encoding="utf-8")

    html = render_resume_html(
        yaml_path=yaml_path,
        template_path=Path("templates/resume/master_resume.html.j2"),
    )

    assert 'class="resume-supporting-sections"' in html
    assert "resume-supporting-sections resume-supporting-page" not in html
    assert html.index("Professional Experience") < html.index("Education")
    assert "break-inside: avoid" in html

    resume["resume_layout"] = {"supporting_sections_start_on_page_2": True}
    yaml_path.write_text(yaml.safe_dump(resume, sort_keys=False), encoding="utf-8")

    page_break_html = render_resume_html(
        yaml_path=yaml_path,
        template_path=Path("templates/resume/master_resume.html.j2"),
    )

    assert 'class="resume-supporting-sections resume-supporting-page"' in page_break_html
    assert "break-before: page" in page_break_html


def test_resume_html_template_decodes_escaped_streamdown_header(tmp_path: Path) -> None:
    yaml_path = tmp_path / "escaped-header.yaml"
    yaml_path.write_text(
        yaml.safe_dump(
            {
                "header_top": {
                    "line_1_name_header_text": "Max Perkhounkov",
                    "line_2_header_text": (
                        '&lt;span class=&#34;font-semibold&#34; '
                        'data-streamdown=&#34;strong&#34;&gt;'
                        "Staff Site Reliability Engineer | AI Enablement "
                        "&amp;amp; Platform Infrastructure&lt;/span&gt;"
                    ),
                    "contact_items": ["Iowa City, IA"],
                },
                "professional_summary": {"render": False},
                "core_technical_skills": {"render": False},
                "professional_experience": {"render": False},
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    html = render_resume_html(
        yaml_path=yaml_path,
        template_path=Path("templates/resume/master_resume.html.j2"),
    )

    assert (
        '<p class="resume-headline"><b>Staff Site Reliability Engineer | '
        "AI Enablement &amp; Platform Infrastructure</b></p>"
    ) in html
    assert "&amp;lt;span" not in html
    assert "data-streamdown" not in html
