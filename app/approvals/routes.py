# app/approvals/routes.py
import os
from datetime import datetime
from flask import (Blueprint, render_template, request, redirect, url_for, flash, current_app, send_from_directory, session, jsonify)
from werkzeug.utils import secure_filename
from app.models import db, User, Signature, Request, FormTemplate, ApprovalStep
from app.utils.pdf_generator import generate_request_pdf
from app.users.routes import require_login, current_db_user
from datetime import datetime
import json
import requests


approvals_bp = Blueprint("approvals_bp", __name__)

ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg"}
ALLOWED_MIMETYPES = {"image/png", "image/jpeg"}
MAX_BYTES = 2 * 1024 * 1024  # 2MB


def allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


@approvals_bp.get("/signature")
@require_login
def signature_upload_get():
    me = current_db_user()
    sig = Signature.query.filter_by(user_id=me.id).first() if me else None
    image_url = None
    if sig and sig.image_path:
        filename = os.path.basename(sig.image_path)
        image_url = url_for("approvals_bp.serve_signature", filename=filename)
    return render_template("signature_upload.html", signature=sig, image_url=image_url)


@approvals_bp.post("/signature")
@require_login
def signature_upload_post():
    me = current_db_user()
    if not me:
        flash("You must be logged in.", "error")
        return redirect(url_for("approvals_bp.signature_upload_get"))

    file = request.files.get("signature")
    if not file or file.filename == "":
        flash("No file selected.", "error")
        return redirect(url_for("approvals_bp.signature_upload_get"))

    if not allowed_file(file.filename):
        flash("Invalid file type. Please upload a PNG or JPEG image.", "error")
        return redirect(url_for("approvals_bp.signature_upload_get"))

    # Validate mimetype
    if file.mimetype not in ALLOWED_MIMETYPES:
        flash("Invalid file type. Please upload a PNG or JPEG image.", "error")
        return redirect(url_for("approvals_bp.signature_upload_get"))

    # Validate size (up to 2MB)
    pos = file.stream.tell()
    file.stream.seek(0, os.SEEK_END)
    size = file.stream.tell()
    file.stream.seek(pos)
    if size > MAX_BYTES:
        flash("File too large. Maximum size is 2MB.", "error")
        return redirect(url_for("approvals_bp.signature_upload_get"))

    upload_folder = current_app.config.get("UPLOAD_FOLDER", "uploads/signatures")
    # Ensure absolute filesystem path for saving
    base_dir = os.path.abspath(os.path.join(current_app.root_path, os.pardir, upload_folder))
    os.makedirs(base_dir, exist_ok=True)

    ext = file.filename.rsplit(".", 1)[1].lower()
    ts = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    filename = secure_filename(f"{me.id}_{ts}.{ext}")
    abs_path = os.path.join(base_dir, filename)

    # Save file
    file.save(abs_path)

    # Store relative path in DB (relative to project root)
    relative_path = os.path.join(upload_folder, filename).replace("\\", "/")

    sig = Signature.query.filter_by(user_id=me.id).first()
    if sig:
        sig.image_path = relative_path
        sig.uploaded_at = datetime.utcnow()
    else:
        sig = Signature(user_id=me.id, image_path=relative_path)
        db.session.add(sig)

    db.session.commit()

    flash("Signature uploaded successfully", "success")
    return redirect(url_for("approvals_bp.signature_upload_get"))


@approvals_bp.get("/uploads/signatures/<path:filename>")
@require_login
def serve_signature(filename):
    upload_folder = current_app.config.get("UPLOAD_FOLDER", "uploads/signatures")
    base_dir = os.path.abspath(os.path.join(current_app.root_path, os.pardir, upload_folder))
    return send_from_directory(base_dir, filename)


@approvals_bp.get("/generated_pdfs/<path:filename>")
@require_login
def serve_pdf(filename):
    """Serve generated PDF files to authenticated users."""
    pdf_dir = os.path.abspath(os.path.join(current_app.root_path, os.pardir, "generated_pdfs"))
    return send_from_directory(pdf_dir, filename, as_attachment=False, mimetype='application/pdf')


@approvals_bp.route("/new", methods=["GET", "POST"])
def new_request():
    templates = FormTemplate.query.all()

    if request.method == "POST":
        form_template_id = request.form["form_template_id"]
        data = dict(request.form)
        data.pop("form_template_id")

        new_req = Request(
            user_id=current_user.id,
            form_template_id=form_template_id,
            data_json=data,
            status="draft"   # first state
        )
        db.session.add(new_req)
        db.session.commit()
        return redirect(url_for("approvals.view_request", request_id=new_req.id))

    return render_template("approvals/new_request.html", templates=templates)


@approvals_bp.route("/submit/<form_code>", methods=["POST"])
def submit_request(form_code):
    form_template = FormTemplate.query.filter_by(form_code=form_code).first_or_404()

    
    user_info = session.get("user")
    user_email = user_info.get("preferred_username") if user_info else None
    user_name = user_info.get("name") if user_info else "Unknown User"

    user = User.query.filter_by(email=user_email).first()

    
    if not user and user_email:
        user = User(
            name=user_name,
            email=user_email,
            role="basicuser"
        )
        db.session.add(user)
        db.session.commit()



    
    form_data = {}
    for key in request.form:
        form_data[key] = request.form.getlist(key) if len(request.form.getlist(key)) > 1 else request.form.get(key)

    action = request.form.get("action")  

    new_request = Request(
        form_template_id=form_template.id,
        requester_id=user.id,
        form_data_json=form_data,
        status="draft" if action == "draft" else "pending",
    )

    db.session.add(new_request)
    db.session.commit()

    flash("Form saved as draft!" if action == "draft" else "Form submitted for approval!", "success")
    return redirect(url_for("approvals_bp.list_forms"))


@approvals_bp.route("/forms")
def list_forms():
    forms = FormTemplate.query.all()
    external_forms = fetch_external_forms()
    return render_template("forms_list.html", forms=forms, external_forms=external_forms)

def fetch_external_forms():
    api_url = "https://aurora.jguliz.com/approvals/get-forms"

    resp = requests.get(api_url, timeout=5)
    data = resp.json()

    if isinstance(data, list):
        return data
    return []
@approvals_bp.route("/forms/<form_code>", methods=["GET", "POST"])
def fill_form(form_code):
    """Display and handle form creation."""
    form_template = FormTemplate.query.filter_by(form_code=form_code).first_or_404()

    user = session.get("user")
    if not user:
        flash("You must be logged in to submit a form.", "warning")
        return redirect(url_for("auth.login"))

    
    db_user = User.query.filter_by(email=user["preferred_username"]).first()
    if not db_user:
        flash("User not found in database.", "danger")
        return redirect(url_for("auth.login"))

    requester_id = db_user.id

    if request.method == "POST":
        form_data = {}

        for key, field_type in form_template.fields_json.items():
            if isinstance(field_type, dict) and field_type.get("type") == "select":
                form_data[key] = request.form.get(key)
            elif isinstance(field_type, list):
                form_data[key] = request.form.getlist(key)
            elif field_type == "file":
                file = request.files.get(key)
                form_data[key] = file.filename if file else None
            elif field_type == "auto_date":
                form_data[key] = datetime.utcnow().strftime("%Y-%m-%d")
            else:
                form_data[key] = request.form.get(key)

        if request.form.get("action") == "draft":
            status = "draft"
            message = "Saved as draft!"
        else:
            # Check if user has uploaded signature before submitting
            sig = Signature.query.filter_by(user_id=requester_id).first()
            if not sig or not sig.image_path:
                flash("Please upload your signature before submitting the form.", "warning")
                return redirect(url_for("approvals_bp.signature_upload_get"))
            
            status = "pending"
            message = "Form submitted for approval!"

        new_request = Request(
            form_template_id=form_template.id,
            requester_id=requester_id,
            form_data_json=form_data,
            status=status,
            submitted_at=datetime.utcnow() if status == "pending" else None
        )

        db.session.add(new_request)
        db.session.commit()

        # Create approval step for demo (anyone can approve)
        if status == "pending":
            # Get first admin/approver user, or use current user as placeholder
            approver = User.query.filter(User.role.in_(["admin", "approver"])).first()
            if not approver:
                approver = db_user
            
            approval_step = ApprovalStep(
                request_id=new_request.id,
                approver_id=approver.id,
                sequence=1,
                status="pending"
            )
            db.session.add(approval_step)
            db.session.commit()

        flash(message, "success")
        return redirect(url_for("approvals_bp.list_my_requests"))

    return render_template(
        "form_fill.html",
        form_template=form_template,
        current_date=datetime.utcnow().strftime("%Y-%m-%d")
    )



@approvals_bp.route("/request/<int:request_id>/edit", methods=["GET", "POST"])
def edit_request(request_id):
    """Edit a draft request using the same fill form template."""
    req = Request.query.get_or_404(request_id)

    user = session.get("user")
    if not user:
        flash("You must be logged in to edit requests.", "warning")
        return redirect(url_for("auth.login"))

    db_user = User.query.filter_by(email=user["preferred_username"]).first()
    if not db_user:
        flash("User not found in database.", "danger")
        return redirect(url_for("auth.login"))

    requester_id = db_user.id


    if req.requester_id != requester_id:
        flash("You cannot edit someone else's request.", "warning")
        return redirect(url_for("approvals_bp.list_my_requests"))

    if req.status != "draft":
        flash("Only drafts can be edited.", "warning")
        return redirect(url_for("approvals_bp.list_my_requests"))

    form_template = req.form_template

    if request.method == "POST":
        updated_data = {}

        for key, field_type in form_template.fields_json.items():
            if isinstance(field_type, dict) and field_type.get("type") == "select":
                updated_data[key] = request.form.get(key)
            elif isinstance(field_type, list):
                updated_data[key] = request.form.getlist(key)
            elif field_type == "file":
                file = request.files.get(key)
                updated_data[key] = file.filename if file else req.form_data_json.get(key)
            elif field_type == "auto_date":
                updated_data[key] = datetime.utcnow().strftime("%Y-%m-%d")
            else:
                updated_data[key] = request.form.get(key)

        req.form_data_json = updated_data

        if request.form.get("action") == "draft":
            req.status = "draft"
            req.submitted_at = None
            flash("Draft updated!", "success")
        else:
            # Check if user has uploaded signature before submitting
            sig = Signature.query.filter_by(user_id=requester_id).first()
            if not sig or not sig.image_path:
                flash("Please upload your signature before submitting the form.", "warning")
                return redirect(url_for("approvals_bp.signature_upload_get"))
            
            req.status = "pending"
            req.submitted_at = datetime.utcnow()
            
            # Create approval step if resubmitting (e.g., after return)
            if not req.approval_steps:
                approver = User.query.filter(User.role.in_(["admin", "approver"])).first()
                if not approver:
                    approver = db_user
                approval_step = ApprovalStep(
                    request_id=req.id,
                    approver_id=approver.id,
                    sequence=1,
                    status="pending"
                )
                db.session.add(approval_step)
            
            flash("Form submitted for approval!", "success")

        db.session.commit()
        return redirect(url_for("approvals_bp.list_my_requests"))

    return render_template(
        "form_fill.html",
        form_template=form_template,
        current_data=req.form_data_json,
        current_date=datetime.utcnow().strftime("%Y-%m-%d"),
        req=req
    )



@approvals_bp.route("/my_requests")
def list_my_requests():
    user = session.get("user")
    if not user:
        flash("You must be logged in to view your requests.", "warning")
        return redirect(url_for("auth.login"))

    db_user = User.query.filter_by(email=user["preferred_username"]).first()
    if not db_user:
        flash("User not found in database.", "danger")
        return redirect(url_for("auth.login"))

    requester_id = db_user.id

    requests = Request.query.filter_by(requester_id=requester_id).order_by(Request.created_at.desc()).all()

    return render_template("my_requests.html", requests=requests)



from sqlalchemy.orm import joinedload

def _dto_row_for_approver(req_obj: Request, step: ApprovalStep):
    return {
        "id": req_obj.id,
        "student_name": req_obj.requester.name if req_obj.requester else "—",
        "form_name": req_obj.form_template.name if req_obj.form_template else "—",
        "state": req_obj.status.upper(),
        "step_number": step.sequence if step else None,
        "step_status": step.status.upper() if step else None,
        "updated_at": req_obj.updated_at.strftime("%Y-%m-%d %H:%M") if req_obj.updated_at else ""
    }

def _dto_row_for_student(req_obj: Request, current_step: ApprovalStep | None):
    return {
        "id": req_obj.id,
        "form_name": req_obj.form_template.name if req_obj.form_template else "—",
        "state": req_obj.status.upper(),
        "step_number": current_step.sequence if current_step else None,
        "step_status": current_step.status.upper() if current_step else None,
        "updated_at": req_obj.updated_at.strftime("%Y-%m-%d %H:%M") if req_obj.updated_at else ""
    }

def _detail_dto(req_obj: Request):
    # current step = first 'pending' else last step
    pending = next((s for s in req_obj.approval_steps if s.status == "pending"), None)
    last    = req_obj.approval_steps[-1] if req_obj.approval_steps else None
    current = pending or last

    # history timeline
    history = []
    if req_obj.submitted_at:
        history.append({
            "at": req_obj.submitted_at.strftime("%Y-%m-%d %H:%M"),
            "event": "SUBMITTED",
            "by": req_obj.requester.name if req_obj.requester else "System"
        })
    for s in req_obj.approval_steps:
        if s.status in ("approved", "rejected", "returned") and s.actioned_at:
            history.append({
                "at": s.actioned_at.strftime("%Y-%m-%d %H:%M"),
                "event": s.status.upper(),
                "by": s.approver.name if s.approver else "Approver"
            })

    # PDFs from signed_pdf_path on steps
    pdfs = []
    for s in req_obj.approval_steps:
        if s.signed_pdf_path:
            filename = os.path.basename(s.signed_pdf_path)
            pdfs.append({
                "name": filename,
                "url": url_for("approvals_bp.serve_pdf", filename=filename),
                "stateAtGen": s.status.upper(),
                "stepNumber": s.sequence
            })

    # flatten form_data_json
    fields = []
    data = req_obj.form_data_json or {}
    if isinstance(data, dict):
        for k, v in data.items():
            label = k.replace("_", " ").title()
            fields.append({"label": label, "value": v})

    # Check if requester has signature
    requester_sig = Signature.query.filter_by(user_id=req_obj.requester_id).first() if req_obj.requester_id else None
    
    return {
        "id": req_obj.id,
        "form_name": req_obj.form_template.name if req_obj.form_template else "—",
        "student": {
            "name": req_obj.requester.name if req_obj.requester else "—",
            "email": req_obj.requester.email if req_obj.requester else "—",
            "has_signature": bool(requester_sig and requester_sig.image_path)
        },
        "state": req_obj.status.upper(),
        "current_step": {
            "number": current.sequence if current else None,
            "assignee": current.approver.name if current and current.approver else None 
},
        "submitted_at": req_obj.submitted_at.strftime("%Y-%m-%d %H:%M") if req_obj.submitted_at else "",
        "updated_at": req_obj.updated_at.strftime("%Y-%m-%d %H:%M") if req_obj.updated_at else "",
        "fields": fields,
        "history": history,
        "pdfs": pdfs
    }

# -------- Approver Dashboard--------

@approvals_bp.get("/approver/dashboard")
@require_login
def approver_dashboard():
    """Demo-friendly approver dashboard - shows ALL pending requests for anyone to approve."""
    me = current_db_user()
    if not me:
        flash("You must be logged in.", "warning")
        return redirect(url_for("auth.login"))

    state = (request.args.get("state") or "").lower()
    q = (request.args.get("q") or "").strip().lower()

    # For DEMO: Show ALL pending requests, not just assigned to current user
    requests_query = (Request.query
                      .filter(Request.status == "pending")
                      .options(joinedload(Request.form_template),
                               joinedload(Request.requester),
                               joinedload(Request.approval_steps))
                      .order_by(Request.updated_at.desc()))

    rows = []
    for req in requests_query.limit(200).all():
        # Get the first pending step
        pending_step = next((s for s in req.approval_steps if s.status == "pending"), None)
        if not pending_step:
            continue
            
        if q and (q not in str(req.id).lower()
                  and q not in (req.requester.name or "").lower()
                  and q not in (req.form_template.name or "").lower()):
            continue
        rows.append(_dto_row_for_approver(req, pending_step))

    return render_template("approver_dashboard.html", requests=rows)

@approvals_bp.get("/approver/requests/<int:request_id>")
@require_login
def approver_request_detail(request_id: int):
    me = current_db_user()
    if not me:
        flash("You must be logged in.", "warning")
        return redirect(url_for("auth.login"))

    req_obj = (Request.query
               .options(joinedload(Request.form_template),
                        joinedload(Request.requester),
                        
joinedload(Request.approval_steps).joinedload(ApprovalStep.approver))
               .filter_by(id=request_id)
               .first())
    if not req_obj:
        flash("Request not found.", "warning")
        return redirect(url_for("approvals_bp.approver_dashboard"))

    # For DEMO: Allow anyone to view (remove authorization check)
    # In production, you'd check: assigned = any(s.approver_id == me.id for s in req_obj.approval_steps)

    d = _detail_dto(req_obj)
    # determine if current user has a pending step
    has_pending_for_me = any(s.approver_id == me.id and s.status == "pending" for s in req_obj.approval_steps)
    return render_template("request_detail.html", d=d, view="approver", has_pending_for_me=has_pending_for_me)

@approvals_bp.post("/approver/requests/<int:request_id>/approve")
@require_login
def approver_request_approve(request_id: int):
    me = current_db_user()
    if not me:
        flash("You must be logged in.", "warning")
        return redirect(url_for("auth.login"))

    req_obj = (Request.query
               .options(joinedload(Request.approval_steps),
                        joinedload(Request.requester),
                        joinedload(Request.form_template))
               .filter_by(id=request_id)
               .first())
    if not req_obj:
        flash("Request not found.", "warning")
        return redirect(url_for("approvals_bp.approver_dashboard"))

    # For DEMO: Get any pending step and assign to current user
    step = next((s for s in req_obj.approval_steps if s.status == "pending"), None)
    if not step:
        flash("No pending step", "warning")
        return redirect(url_for("approvals_bp.approver_dashboard"))
    
    # Assign this step to current approver if not already assigned
    if step.approver_id != me.id:
        step.approver_id = me.id

    # ensure signature exists
    sig = Signature.query.filter_by(user_id=me.id).first()
    if not sig or not sig.image_path:
        flash("Please upload a signature first", "warning")
        return redirect(url_for("approvals_bp.signature_upload_get"))

    # Collect signature paths: student signature first, then approvers
    signature_paths = []
    
    # Add student/requester signature first
    student_sig = Signature.query.filter_by(user_id=req_obj.requester_id).first()
    if student_sig and student_sig.image_path:
        signature_paths.append(student_sig.image_path)
    
    # Add approver signatures in sequence order
    for s in sorted(req_obj.approval_steps, key=lambda x: x.sequence):
        if s.status == "approved" or s.id == step.id:
            approver_sig = Signature.query.filter_by(user_id=s.approver_id).first()
            if approver_sig and approver_sig.image_path:
                signature_paths.append(approver_sig.image_path)

    # Generate PDF and store relative path
    try:
        print(f"DEBUG: Generating PDF for request {req_obj.id}")
        print(f"DEBUG: Signature paths: {signature_paths}")
        pdf_rel_path = generate_request_pdf(req_obj, signature_paths)
        print(f"DEBUG: PDF generated at: {pdf_rel_path}")
        step.signed_pdf_path = pdf_rel_path
    except Exception as e:
        print(f"ERROR: PDF generation failed: {e}")
        import traceback
        traceback.print_exc()
        flash(f"Failed to generate PDF: {e}", "danger")
        return redirect(url_for("approvals_bp.approver_request_detail", request_id=req_obj.id))

    # Update step
    step.status = "approved"
    step.actioned_at = datetime.utcnow()
    step.comments = request.form.get("comments")

    # If all steps approved, mark request approved
    if all(s.status == "approved" for s in req_obj.approval_steps):
        req_obj.status = "approved"
        flash("Request fully approved ✅", "success")
    else:
        flash("Approved and forwarded to next approver ➡️", "success")

    db.session.commit()
    return redirect(url_for("approvals_bp.approver_dashboard"))

@approvals_bp.post("/approver/requests/<int:request_id>/return")
@require_login
def approver_request_return(request_id: int):
    me = current_db_user()
    if not me:
        flash("You must be logged in.", "warning")
        return redirect(url_for("auth.login"))

    req_obj = (Request.query
               .options(joinedload(Request.approval_steps),
                        joinedload(Request.requester),
                        joinedload(Request.form_template))
               .filter_by(id=request_id)
               .first())
    if not req_obj:
        flash("Request not found.", "warning")
        return redirect(url_for("approvals_bp.approver_dashboard"))

    # For DEMO: Get any pending step
    step = next((s for s in req_obj.approval_steps if s.status == "pending"), None)
    if not step:
        flash("No pending step", "warning")
        return redirect(url_for("approvals_bp.approver_dashboard"))
    
    # Assign to current user if needed
    if step.approver_id != me.id:
        step.approver_id = me.id

    # Update current step
    step.status = "returned"
    step.actioned_at = datetime.utcnow()
    step.comments = request.form.get("comments")

    # Update request
    req_obj.status = "returned"

    # Reset all other steps
    for s in req_obj.approval_steps:
        if s.id != step.id:
            s.status = "pending"
            s.actioned_at = None
            s.signed_pdf_path = None

    db.session.commit()
    flash("Request returned to student for revision 🔙", "success")
    return redirect(url_for("approvals_bp.approver_dashboard"))

# -------- Student Request Detail --------

@approvals_bp.get("/student/requests/<int:request_id>")
@require_login
def student_request_detail(request_id: int):
    me = current_db_user()
    if not me:
        flash("You must be logged in.", "warning")
        return redirect(url_for("auth.login"))

    req_obj = (Request.query
               .options(joinedload(Request.form_template),
                        joinedload(Request.requester),
                        
joinedload(Request.approval_steps).joinedload(ApprovalStep.approver))
               .filter_by(id=request_id)
               .first())
    if not req_obj:
        flash("Request not found.", "warning")
        return redirect(url_for("approvals_bp.list_my_requests"))

    if req_obj.requester_id != me.id and me.role != "admin":
        flash("You are not authorized to view this request.", "warning")
        return redirect(url_for("approvals_bp.list_my_requests"))

    d = _detail_dto(req_obj)
    return render_template("request_detail.html", d=d, view="student")

