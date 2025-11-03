# app/utils/pdf_generator.py
import json
import os
import subprocess
from datetime import datetime
from typing import List, Dict, Any

from app.models import Request  # type: ignore


def _ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def _latex_escape(s: str) -> str:
    # Minimal LaTeX escaping
    replacements = {
        "\\": r"\textbackslash{}",
        "{": r"\{",
        "}": r"\}",
        "#": r"\#",
        "$": r"\$",
        "%": r"\%",
        "&": r"\&",
        "_": r"\_",
        "~": r"\textasciitilde{}",
        "^": r"\textasciicircum{}",
    }
    out = []
    for ch in s:
        out.append(replacements.get(ch, ch))
    return "".join(out)


def _render_list_items(items: List[str]) -> str:
    """Render a list of items as LaTeX itemize."""
    if not items:
        return "None selected"
    lines = ["\\begin{itemize}"]
    for item in items:
        lines.append(f"  \\item {_latex_escape(str(item))}")
    lines.append("\\end{itemize}")
    return "\n".join(lines)


def _render_signature_image(sig_path: str, latex_dir: str) -> str:
    """Render a signature image for LaTeX."""
    if not sig_path or not os.path.exists(sig_path):
        return "\\textit{[No signature]}" 
    rel_path = os.path.relpath(sig_path, latex_dir)
    return f"\\includegraphics[width=0.3\\textwidth]{{{_latex_escape(rel_path)}}}"


def generate_request_pdf(request: Request, signature_paths: List[str]) -> str:
    """
    Generate a PDF for a Request using custom LaTeX templates.

    Returns relative path to the generated PDF.
    Raises RuntimeError if LaTeX compilation fails.
    """
    # Determine repo root and directories
    utils_dir = os.path.dirname(__file__)
    repo_root = os.path.abspath(os.path.join(utils_dir, os.pardir, os.pardir))
    latex_dir = os.path.join(repo_root, "latex_templates")  # Templates only
    output_dir = os.path.join(repo_root, "generated_pdfs")  # Generated files
    _ensure_dir(latex_dir)
    _ensure_dir(output_dir)

    # Get form code and request ID
    form_code = getattr(getattr(request, "form_template", None), "form_code", "form")
    req_id = getattr(request, "id", "unknown")
    base_name = f"{form_code}_{req_id}"
    
    # File paths: template in latex_dir, output in output_dir
    template_path = os.path.join(latex_dir, f"{form_code}_template.tex")
    output_tex_path = os.path.join(output_dir, f"{base_name}.tex")
    pdf_path = os.path.join(output_dir, f"{base_name}.pdf")

    # Check if template exists
    if not os.path.exists(template_path):
        raise RuntimeError(f"Template not found: {template_path}")

    # Read template
    with open(template_path, "r", encoding="utf-8") as f:
        template_content = f.read()

    # Resolve form data
    form_data_raw = getattr(request, "form_data_json", None) or getattr(request, "form_data", {})
    if isinstance(form_data_raw, str):
        form_data = json.loads(form_data_raw or "{}")
    elif isinstance(form_data_raw, dict):
        form_data = form_data_raw
    else:
        form_data = {}

    # Get submitter info
    submitter_name = _latex_escape(getattr(getattr(request, "requester", None), "name", "Unknown"))
    submitted_at = getattr(request, "submitted_at", None)
    submitted_date = submitted_at.strftime("%Y-%m-%d %H:%M") if isinstance(submitted_at, datetime) and submitted_at else datetime.utcnow().strftime("%Y-%m-%d %H:%M")

    # Prepare signature paths
    abs_signature_paths = []
    for p in signature_paths or []:
        if not p:
            continue
        abs_p = p if os.path.isabs(p) else os.path.join(repo_root, p)
        if os.path.exists(abs_p):
            abs_signature_paths.append(abs_p)

    # Build replacements dictionary based on form type
    replacements = {}
    
    if form_code == "ferpa_auth":
        replacements = _build_ferpa_replacements(form_data, submitter_name, submitted_date, abs_signature_paths, output_dir)
    elif form_code == "general_petition":
        replacements = _build_petition_replacements(form_data, submitter_name, submitted_date, abs_signature_paths, output_dir)
    else:
        # Fallback for unknown forms
        replacements = {"FORM_DATA": str(form_data)}

    # Replace placeholders in template
    output_content = template_content
    for placeholder, value in replacements.items():
        output_content = output_content.replace(f"{{{{{placeholder}}}}}", value)

    # Write output .tex file
    with open(output_tex_path, "w", encoding="utf-8") as f:
        f.write(output_content)

    # Write Makefile in output directory
    makefile_path = os.path.join(output_dir, "Makefile")
    if not os.path.exists(makefile_path):
        makefile_contents = (
            "PDFLATEX=pdflatex\n"
            ".SUFFIXES: .tex .pdf\n"
            "%.pdf: %.tex\n\t$(PDFLATEX) -interaction=nonstopmode -halt-on-error $< > build.log 2>&1\n"
            "\nclean:\n\trm -f *.aux *.log *.out *.toc build.log\n"
        )
        with open(makefile_path, "w", encoding="utf-8") as mf:
            mf.write(makefile_contents)

    # Run make to build PDF in output directory
    result = subprocess.run([
        "make", "-C", output_dir, f"{base_name}.pdf"
    ], capture_output=True, text=True)

    if result.returncode != 0 or not os.path.exists(pdf_path):
        stderr = result.stderr or ""
        stdout = result.stdout or ""
        build_log = os.path.join(output_dir, "build.log")
        log_content = ""
        if os.path.exists(build_log):
            try:
                with open(build_log, "r", encoding="utf-8", errors="ignore") as lf:
                    log_content = lf.read()
            except Exception:
                pass
        raise RuntimeError(
            "LaTeX compilation failed.\n"
            f"stdout:\n{stdout}\n"
            f"stderr:\n{stderr}\n"
            f"build.log:\n{log_content}\n"
        )

    # Return project-root-relative path
    return os.path.relpath(pdf_path, repo_root)


def _build_ferpa_replacements(form_data: Dict[str, Any], submitter_name: str, 
                               submitted_date: str, signature_paths: List[str], 
                               latex_dir: str) -> Dict[str, str]:
    """Build replacement dictionary for FERPA form."""
    replacements = {
        "STUDENT_NAME": _latex_escape(form_data.get("student_name", submitter_name)),
        "PEOPLESOFT_ID": _latex_escape(str(form_data.get("peoplesoft_id", "N/A"))),
        "DATE": _latex_escape(str(form_data.get("date", submitted_date))),
        "CAMPUS": _latex_escape(str(form_data.get("campus", "N/A"))),
        "RELEASE_TO": _latex_escape(str(form_data.get("release_to", "N/A"))),
        "PHONE_PASSWORD": _latex_escape(str(form_data.get("phone_password", "N/A"))),
        "SUBMITTED_DATE": _latex_escape(submitted_date),
    }
    
    # Handle list fields
    auth_offices = form_data.get("authorized_offices", [])
    if isinstance(auth_offices, list):
        replacements["AUTHORIZED_OFFICES"] = _render_list_items(auth_offices)
    else:
        replacements["AUTHORIZED_OFFICES"] = _latex_escape(str(auth_offices))
    
    info_types = form_data.get("info_types", [])
    if isinstance(info_types, list):
        replacements["INFO_TYPES"] = _render_list_items(info_types)
    else:
        replacements["INFO_TYPES"] = _latex_escape(str(info_types))
    
    purpose = form_data.get("purpose_of_disclosure", [])
    if isinstance(purpose, list):
        replacements["PURPOSE_OF_DISCLOSURE"] = _render_list_items(purpose)
    else:
        replacements["PURPOSE_OF_DISCLOSURE"] = _latex_escape(str(purpose))
    
    # Student signature (first in list)
    if signature_paths:
        replacements["STUDENT_SIGNATURE"] = _render_signature_image(signature_paths[0], latex_dir)
    else:
        replacements["STUDENT_SIGNATURE"] = "\\textit{[No signature]}"
    
    # Approver signatures
    if len(signature_paths) > 1:
        approver_sigs = []
        for i, sig_path in enumerate(signature_paths[1:], 1):
            sig_img = _render_signature_image(sig_path, latex_dir)
            approver_sigs.append(f"\\noindent\\textbf{{Approver {i}:}} \\\\ {sig_img} \\\\[0.3cm]")
        replacements["APPROVER_SIGNATURES"] = "\n".join(approver_sigs)
    else:
        replacements["APPROVER_SIGNATURES"] = "\\textit{Pending approval}"
    
    return replacements


def _build_petition_replacements(form_data: Dict[str, Any], submitter_name: str,
                                  submitted_date: str, signature_paths: List[str],
                                  latex_dir: str) -> Dict[str, str]:
    """Build replacement dictionary for General Petition form."""
    replacements = {
        "STUDENT_NAME": _latex_escape(form_data.get("student_name", submitter_name)),
        "STUDENT_ID": _latex_escape(str(form_data.get("student_id", "N/A"))),
        "PHONE_NUMBER": _latex_escape(str(form_data.get("phone_number", "N/A"))),
        "EMAIL": _latex_escape(str(form_data.get("email", "N/A"))),
        "MAILING_ADDRESS": _latex_escape(str(form_data.get("mailing_address", "N/A"))),
        "CITY": _latex_escape(str(form_data.get("city", "N/A"))),
        "STATE": _latex_escape(str(form_data.get("state", "N/A"))),
        "ZIP": _latex_escape(str(form_data.get("zip", "N/A"))),
        "PETITION_REASON_NUMBER": _latex_escape(str(form_data.get("petition_reason_number", "N/A"))),
        "DATE": _latex_escape(str(form_data.get("date", submitted_date))),
        "EXPLANATION_OF_REQUEST": _latex_escape(str(form_data.get("explanation_of_request", "N/A"))),
        "SUBMITTED_DATE": _latex_escape(submitted_date),
    }
    
    # Change details (from/to fields)
    from_val = form_data.get("from_value", "")
    to_val = form_data.get("to_value", "")
    additional = form_data.get("additional_details", "")
    
    if from_val or to_val or additional:
        change_details = "\\noindent\\textbf{\\large Change Details}\\\\[0.2cm]\n"
        change_details += "\\begin{tabularx}{\\textwidth}{|l|X|}\n\\hline\n"
        if from_val:
            change_details += f"\\textbf{{From:}} & {_latex_escape(str(from_val))} \\\\\n\\hline\n"
        if to_val:
            change_details += f"\\textbf{{To:}} & {_latex_escape(str(to_val))} \\\\\n\\hline\n"
        if additional:
            change_details += f"\\textbf{{Additional Details:}} & {_latex_escape(str(additional))} \\\\\n\\hline\n"
        change_details += "\\end{tabularx}"
        replacements["CHANGE_DETAILS"] = change_details
    else:
        replacements["CHANGE_DETAILS"] = ""
    
    # Student signature
    if signature_paths:
        replacements["STUDENT_SIGNATURE"] = _render_signature_image(signature_paths[0], latex_dir)
    else:
        replacements["STUDENT_SIGNATURE"] = "\\textit{[No signature]}"
    
    # Approver signatures
    if len(signature_paths) > 1:
        approver_sigs = []
        for i, sig_path in enumerate(signature_paths[1:], 1):
            sig_img = _render_signature_image(sig_path, latex_dir)
            approver_sigs.append(
                f"\\noindent\\begin{{tabularx}}{{\\textwidth}}{{|l|X|}}\n"
                f"\\hline\n"
                f"\\textbf{{Approver {i}:}} & \\\\\n"
                f"& {sig_img} \\\\\n"
                f"& \\\\\n"
                f"\\hline\n"
                f"\\end{{tabularx}}\\\\[0.3cm]"
            )
        replacements["APPROVER_SIGNATURES"] = "\n".join(approver_sigs)
    else:
        replacements["APPROVER_SIGNATURES"] = "\\textit{Pending approval}"
    
    return replacements
