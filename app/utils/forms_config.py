FORM_TEMPLATES = [
    {
        "name": "FERPA Authorization Form",
        "form_code": "ferpa_auth",
        "latex_template_path": "latex/ferpa_template.tex",
        "fields_json": {
            "student_name": "text",
            "peoplesoft_id": "text",
            "date": "date",
            "campus":["Clear Lake", "Downtown", "Main", "Victoria"],
            "authorized_offices": ["Registrar", "Financial Aid", "Student Business Services", "University Advancement", "Dean of Students Office", "Other"],
            "info_types": ["Academic Records", "Academic Advising Profile/Information", "All University Records", "Grades/Transcripts", "Billing/Financial Aid", "Disciplinary", "Housing", "Photos", "Scholarship/Honors", "Other"],
            "release_to": "text",
            "purpose_of_disclosure": ["Family", "Educational Institution", "Employer", "Public or Media of Scholarship", "Other"],
            "phone_password": "text"
        }
    },
    {
    "name": "General Petition Form",
    "form_code": "general_petition",
    "latex_template_path": "latex/general_petition_template.tex",
    "fields_json": {
        "student_name": "text",
        "student_id": "text",
        "phone_number": "text",
        "mailing_address": "text",
        "city": "text",
        "state": "text",
        "zip": "text",
        "email": "email",

        "petition_reason_number": {
            "type": "select",
            "options": [
                "1. Update Student’s Program Status / Action (readmit, term activate, etc.)",
                "2. Admission Status Change",
                "3. Add New Career",
                "4. Program Change (From → To)",
                "5. Major Change (From → To)",
                "6. Degree Objective / Plan Change (B.A., B.S., etc.)",
                "7. Requirement Term (UH Catalog / Career)",
                "8. Additional Plan or Courses",
                "9. Add Second Degree In",
                "10. Remove or Change Minor (From → To)",
                "11. Add Additional Minor In",
                "12. Degree Requirement Exception",
                "13. Special Problems Course Request (Include Course Details)",
                "14. Course Overload (Include GPA / Hours)",
                "15. Graduate Studies Leave of Absence",
                "16. Graduate Studies Reinstatement",
                "17. Other"
            ]
        },

        "from_value": "text",
        "to_value": "text",
        "additional_details": "textarea",
        "explanation_of_request": "textarea",
        "date": "auto_date"
    }
}
]