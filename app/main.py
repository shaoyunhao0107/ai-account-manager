"""FastAPI 主应用"""
import io
import base64
from datetime import date
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Request, Depends, Form, HTTPException, Response, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, select, func

from . import database, models, security, auth
from .auth import check_login, make_session_cookie, require_auth
from .category_model import Category

BASE_DIR = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

# 自定义过滤器：UTF-8 字符串转 base64（用于把节点 URL 安全传给 JS，避免 & 被转义）
def _b64encode_filter(s: str) -> str:
    if not s:
        return ""
    return base64.b64encode(s.encode("utf-8")).decode("ascii")

templates.env.filters["b64encode"] = _b64encode_filter

app = FastAPI(title="AI 账号资产管理系统")
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

# 凭证图片上传目录
VOUCHER_DIR = BASE_DIR / "data" / "vouchers"
VOUCHER_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/vouchers", StaticFiles(directory=str(VOUCHER_DIR)), name="vouchers")


# ---------- Jinja 过滤器 ----------
def _mask_url(url: str, keep: int = 30) -> str:
    """节点 URL 在列表页只显示前 keep 个字符 + ...，避免整段裸露"""
    if not url:
        return ""
    if len(url) <= keep:
        return url
    return url[:keep] + "…"


templates.env.filters["mask_url"] = _mask_url


@app.on_event("startup")
def _startup():
    database.init_db()
    # 初始化默认分类（仅当 categories 表为空时）
    _seed_categories()


def _seed_categories():
    """首次启动写入默认的账号选型预设"""
    from sqlmodel import Session, select
    with Session(database.engine) as s:
        existing = s.exec(select(Category).where(Category.kind == "plan_type")).all()
        if existing:
            return
        defaults = ["Codex 5X", "Codex 20X", "Claude Code 5X", "Claude Code 20X", "Claude Code-pro"]
        for i, v in enumerate(defaults):
            s.add(Category(kind="plan_type", value=v, sort_order=i))
        s.commit()


def get_categories(kind: str, session) -> list[str]:
    """取某类（plan_type/department）的预设列表，已排序"""
    rows = session.exec(
        select(Category).where(Category.kind == kind).order_by(Category.sort_order, Category.id)
    ).all()
    return [r.value for r in rows]


def upsert_category(kind: str, value: str, session):
    """把值加入分类预设（已存在则跳过）"""
    v = (value or "").strip()
    if not v:
        return
    exists = session.exec(select(Category).where(Category.kind == kind, Category.value == v)).first()
    if exists:
        return
    # 计算下一个 sort_order
    all_rows = session.exec(select(Category).where(Category.kind == kind)).all()
    next_order = max([c.sort_order for c in all_rows], default=-1) + 1
    session.add(Category(kind=kind, value=v, sort_order=next_order))


# ---------- 登录 / 登出 ----------
@app.get("/login", response_class=HTMLResponse)
def login_form(request: Request, err: Optional[str] = None):
    return templates.TemplateResponse(request, "login.html", {"err": err})


@app.post("/login")
def login_submit(password: str = Form(...)):
    if check_login(password):
        resp = RedirectResponse(url="/", status_code=303)
        resp.set_cookie(
            key="aam_session",
            value=make_session_cookie(),
            httponly=True,
            samesite="lax",
            path="/",
            max_age=60 * 60 * 12,  # 12h
        )
        return resp
    return RedirectResponse(url="/login?err=1", status_code=303)


@app.post("/logout")
def logout():
    resp = RedirectResponse(url="/login", status_code=303)
    resp.delete_cookie("aam_session")
    return resp


# ---------- 分类预设管理（账号选型 / 部门） ----------
@app.get("/categories", response_class=HTMLResponse, dependencies=[Depends(require_auth)])
def categories_page(request: Request, session: Session = Depends(database.get_session)):
    plan_types = session.exec(select(Category).where(Category.kind == "plan_type").order_by(Category.sort_order, Category.id)).all()
    departments = session.exec(select(Category).where(Category.kind == "department").order_by(Category.sort_order, Category.id)).all()

    # 查每个部门下的用户列表（只统计未删除的账号）
    dept_members = {}  # {部门名: [(id, user_name), ...]}
    for dept in departments:
        members = session.exec(
            select(models.Account.id, models.Account.user_name)
            .where(models.Account.deleted_at.is_(None), models.Account.department == dept.value)
            .order_by(models.Account.user_name)
        ).all()
        dept_members[dept.id] = members

    # 统计部门为空的用户
    no_dept_users = session.exec(
        select(models.Account.id, models.Account.user_name)
        .where(models.Account.deleted_at.is_(None))
        .where((models.Account.department == "") | (models.Account.department.is_(None)))
        .order_by(models.Account.user_name)
    ).all()

    return templates.TemplateResponse(request, "categories.html", {
        "plan_types": plan_types,
        "departments": departments,
        "dept_members": dept_members,
        "no_dept_users": no_dept_users,
    })


@app.post("/categories/add", dependencies=[Depends(require_auth)])
def category_add(
    kind: str = Form(...),         # plan_type / department
    value: str = Form(...),
    session: Session = Depends(database.get_session),
):
    value = (value or "").strip()
    if not value or kind not in ("plan_type", "department"):
        raise HTTPException(400, "参数错误")
    # 去重
    exists = session.exec(select(Category).where(Category.kind == kind, Category.value == value)).first()
    if exists:
        return RedirectResponse(url=f"/categories#{kind}", status_code=303)
    max_order = session.exec(select(Category).where(Category.kind == kind)).all()
    next_order = max([c.sort_order for c in max_order], default=-1) + 1
    session.add(Category(kind=kind, value=value, sort_order=next_order))
    session.commit()
    return RedirectResponse(url=f"/categories#{kind}", status_code=303)


@app.post("/categories/{cid}/delete", dependencies=[Depends(require_auth)])
def category_delete(cid: int, session: Session = Depends(database.get_session)):
    c = session.get(Category, cid)
    if c:
        session.delete(c)
        session.commit()
    return RedirectResponse(url=f"/categories#{c.kind if c else ''}", status_code=303)


@app.post("/categories/{cid}/up", dependencies=[Depends(require_auth)])
def category_up(cid: int, session: Session = Depends(database.get_session)):
    """上移（与同 kind 的上一条交换 sort_order）"""
    c = session.get(Category, cid)
    if not c:
        raise HTTPException(404)
    same_kind = session.exec(select(Category).where(Category.kind == c.kind).order_by(Category.sort_order, Category.id)).all()
    idx = next((i for i, x in enumerate(same_kind) if x.id == cid), -1)
    if idx > 0:
        prev = same_kind[idx - 1]
        c.sort_order, prev.sort_order = prev.sort_order, c.sort_order
        session.add(c); session.add(prev); session.commit()
    return RedirectResponse(url=f"/categories#{c.kind}", status_code=303)


@app.post("/categories/import", dependencies=[Depends(require_auth)])
async def category_import(
    request: Request,
    kind: str = Form(...),
    text: str = Form(""),
    file: UploadFile = File(None),
    session: Session = Depends(database.get_session),
):
    """批量导入：每行一个值。支持粘贴文本或上传 txt/csv 文件"""
    if kind not in ("plan_type", "department"):
        raise HTTPException(400, "kind 非法")
    content = text or ""
    if file:
        raw = await file.read()
        try: content = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            try: content = raw.decode("gbk")
            except UnicodeDecodeError: content = raw.decode("utf-8", errors="replace")
        content = (text or "") + "\n" + content

    existing = set(session.exec(select(Category.value).where(Category.kind == kind)).all())
    max_order = max([c.sort_order for c in session.exec(select(Category).where(Category.kind == kind)).all()] or [-1])
    added = 0
    for i, line in enumerate(content.splitlines()):
        v = line.strip().strip(",").strip()
        if v and v not in existing:
            max_order += 1
            session.add(Category(kind=kind, value=v, sort_order=max_order))
            existing.add(v)
            added += 1
    session.commit()
    return RedirectResponse(url=f"/categories#{kind}", status_code=303)


@app.post("/categories/import-users", dependencies=[Depends(require_auth)])
async def category_import_users(
    request: Request,
    file: UploadFile = File(None),
    text: str = Form(""),
    session: Session = Depends(database.get_session),
):
    """导入 用户-部门 对应表 CSV/文本。
    格式：每行一条，列分隔符支持 逗号/Tab/空格
    - 第一列：用户名
    - 第二列：部门
    用户已存在（按 user_name 匹配）→ 更新 department
    用户不存在 → 创建一条只含 user_name+department 的账号记录
    同时把部门加入 categories 预设
    """
    content = text or ""
    if file:
        raw = await file.read()
        try: content = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            try: content = raw.decode("gbk")
            except UnicodeDecodeError: content = raw.decode("utf-8", errors="replace")

    import csv as _csv
    import io as _io

    updated, created, errors = 0, 0, []
    lines = content.splitlines()
    if not lines:
        return RedirectResponse(url="/categories#department", status_code=303)

    # 尝试自动识别分隔符（逗号 / Tab）
    sample = lines[0]
    delimiter = "\t" if "\t" in sample else ","

    reader = _csv.reader(_io.StringIO(content), delimiter=delimiter)
    for i, row in enumerate(reader, start=1):
        if not row or len(row) < 2:
            continue
        # 跳过表头（如果第一列是"用户"之类的）
        user_name = row[0].strip()
        department = row[1].strip()
        if not user_name or user_name in ("用户", "姓名", "user", "name", "Username"):
            continue
        if not department:
            continue

        # 查现有用户
        existing = session.exec(
            select(models.Account).where(models.Account.user_name == user_name, models.Account.deleted_at.is_(None))
        ).first()
        if existing:
            existing.department = department
            session.add(existing)
            updated += 1
        else:
            session.add(models.Account(user_name=user_name, department=department))
            created += 1
        # 部门加到预设
        upsert_category("department", department, session)

    try:
        session.commit()
    except Exception as e:
        session.rollback()
        return RedirectResponse(url=f"/categories#department?err={e}", status_code=303)

    return RedirectResponse(
        url=f"/categories#department?msg=导入完成：更新 {updated} 条，新建 {created} 条",
        status_code=303,
    )


@app.post("/categories/bulk-delete", dependencies=[Depends(require_auth)])
async def category_bulk_delete(request: Request, session: Session = Depends(database.get_session)):
    """批量删除分类（ids[]）"""
    form = await request.form()
    ids = form.getlist("ids")
    kind = ""
    for cid_str in ids:
        try: cid = int(cid_str)
        except (ValueError, TypeError): continue
        c = session.get(Category, cid)
        if c:
            kind = c.kind
            session.delete(c)
    session.commit()
    return RedirectResponse(url=f"/categories#{kind}", status_code=303)


@app.post("/categories/{cid}/edit", dependencies=[Depends(require_auth)])
def category_edit(
    cid: int,
    value: str = Form(...),
    session: Session = Depends(database.get_session),
):
    """重命名某个分类值"""
    c = session.get(Category, cid)
    if not c:
        raise HTTPException(404)
    new_value = (value or "").strip()
    if not new_value:
        raise HTTPException(400, "值不能为空")
    # 检查重名（同 kind 下）
    dup = session.exec(
        select(Category).where(Category.kind == c.kind, Category.value == new_value, Category.id != cid)
    ).first()
    if dup:
        return RedirectResponse(url=f"/categories#{c.kind}", status_code=303)
    c.value = new_value
    session.add(c)
    session.commit()
    return RedirectResponse(url=f"/categories#{c.kind}", status_code=303)


# ---------- 列表 ----------
@app.get("/", response_class=HTMLResponse, dependencies=[Depends(require_auth)])
def list_accounts(
    request: Request,
    q: Optional[str] = None,
    department: Optional[str] = None,
    status: Optional[str] = None,
    plan_type: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
    sort: str = "id",
    order: str = "desc",
    session: Session = Depends(database.get_session),
):
    stmt = select(models.Account).where(models.Account.deleted_at.is_(None))
    if q:
        like = f"%{q}%"
        stmt = stmt.where(
            models.Account.user_name.contains(q)
            | models.Account.cc_email.contains(q)
            | models.Account.server_order.contains(q)
            | models.Account.vps_ip_masked.contains(q)
            | models.Account.verge_url.contains(q)
            | models.Account.vlmess_url.contains(q)
            | models.Account.new_vps_address.contains(q)
            | models.Account.first_batch_alloc.contains(q)
        )
    if department:
        stmt = stmt.where(models.Account.department == department)
    if status:
        stmt = stmt.where(models.Account.status == status)
    if plan_type:
        stmt = stmt.where(models.Account.plan_type == plan_type)
    # 排序：白名单字段，防注入
    SORT_FIELDS = {
        "id": models.Account.id,
        "user_name": models.Account.user_name,
        "department": models.Account.department,
        "plan_type": models.Account.plan_type,
        "status": models.Account.status,
    }
    sort_col = SORT_FIELDS.get(sort, models.Account.id)
    if order.lower() == "asc":
        stmt = stmt.order_by(sort_col.asc())
    else:
        stmt = stmt.order_by(sort_col.desc())

    # 统计总数（分页前）
    from sqlmodel import func as _func
    count_stmt = select(_func.count()).select_from(stmt.subquery())
    total = session.exec(count_stmt).one()
    total = int(total or 0)

    # 分页
    page = max(1, page)
    page_size = max(1, min(200, page_size))
    total_pages = max(1, (total + page_size - 1) // page_size)
    page = min(page, total_pages)
    offset = (page - 1) * page_size
    rows = session.exec(stmt.offset(offset).limit(page_size)).all()

    # 过滤器选项：优先从 categories 预设表取，回退到数据 distinct
    plan_types = get_categories("plan_type", session)
    departments = get_categories("department", session)
    if not plan_types:
        plan_types = [p for p in session.exec(select(models.Account.plan_type).distinct()).all() if p]
    if not departments:
        departments = [d for d in session.exec(select(models.Account.department).distinct()).all() if d]
    statuses = [s for s in session.exec(select(models.Account.status).distinct()).all() if s]

    # 计算分页导航的页码范围（显示当前页前后 2 页）
    page_range_start = max(1, page - 2)
    page_range_end = min(total_pages, page + 2)
    page_numbers = list(range(page_range_start, page_range_end + 1))

    return templates.TemplateResponse(
        request,
        "list.html",
        {
            "rows": rows,
            "q": q or "",
            "department": department or "",
            "status_filter": status or "",
            "plan_type": plan_type or "",
            "departments": departments,
            "statuses": statuses,
            "plan_types": plan_types,
            # 排序
            "sort": sort,
            "order": order.lower(),
            # 分页
            "page": page,
            "page_size": page_size,
            "total": total,
            "total_pages": total_pages,
            "page_numbers": page_numbers,
            "has_prev": page > 1,
            "has_next": page < total_pages,
            "prev_page": page - 1,
            "next_page": page + 1,
            "start_index": offset + 1 if total > 0 else 0,
            "end_index": min(offset + page_size, total),
        },
    )


# ---------- 新增 / 编辑 表单 ----------
@app.get("/accounts/new", response_class=HTMLResponse, dependencies=[Depends(require_auth)])
def new_form(request: Request, session: Session = Depends(database.get_session)):
    return templates.TemplateResponse(request, "form.html", {
        "a": None,
        "plan_types": get_categories("plan_type", session),
        "departments": get_categories("department", session),
    })


@app.get("/accounts/{aid}/edit", response_class=HTMLResponse, dependencies=[Depends(require_auth)])
def edit_form(request: Request, aid: int, session: Session = Depends(database.get_session)):
    a = session.get(models.Account, aid)
    if not a:
        raise HTTPException(404)
    # 解密密码字段供编辑回填，放进 context 而不是动态属性
    ctx = {
        "a": a,
        "email_password_plain": security.decrypt_field(a.email_password_enc),
        "gpt_password_plain": security.decrypt_field(a.gpt_password_enc),
        "plan_types": get_categories("plan_type", session),
        "departments": get_categories("department", session),
    }
    return templates.TemplateResponse(request, "form.html", ctx)


def _parse_date(s: str) -> Optional[date]:
    s = (s or "").strip()
    if not s:
        return None
    # 兼容 2025-05-31 / 2025/5/31 / 5月31日 这种半格式
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%m月%d日"):
        try:
            from datetime import datetime
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


@app.post("/accounts", dependencies=[Depends(require_auth)])
def create_account(
    user_name: str = Form(...),
    department: str = Form(""),
    plan_type: str = Form(""),
    first_open_date: str = Form(""),
    status: str = Form("可用"),
    delivered: bool = Form(False),
    delivery_date: str = Form(""),
    installed: bool = Form(False),
    installer: str = Form(""),
    os_version: str = Form(""),
    server_order: str = Form(""),
    vps_ip_masked: str = Form(""),
    vps_pure: bool = Form(False),
    vps_in_use: bool = Form(False),
    new_vps_address: str = Form(""),
    verge_url: str = Form(""),
    vlmess_url: str = Form(""),
    cc_email: str = Form(""),
    email_password: str = Form(""),
    gpt_password: str = Form(""),
    plan_amount: str = Form(""),
    converted_to_codex: bool = Form(False),
    plan_start_date: str = Form(""),
    plan_end_date: str = Form(""),
    distributed: bool = Form(False),
    first_batch_alloc: str = Form(""),
    ban1_is_banned: bool = Form(False),
    ban1_date: str = Form(""),
    ban2_delivered: str = Form(""),
    second_voucher: str = Form(""),
    ban2_is_banned: bool = Form(False),
    ban2_date: str = Form(""),
    ban3_delivered: str = Form(""),
    third_voucher: str = Form(""),
    ban3_is_banned: bool = Form(False),
    notes: str = Form(""),
    session: Session = Depends(database.get_session),
):
    a = models.Account(
        user_name=user_name,
        department=department,
        plan_type=plan_type,
        first_open_date=_parse_date(first_open_date),
        status=status,
        delivered=delivered,
        delivery_date=_parse_date(delivery_date),
        installed=installed,
        installer=installer,
        os_version=os_version,
        server_order=server_order,
        vps_ip_masked=vps_ip_masked,
        vps_pure=vps_pure,
        vps_in_use=vps_in_use,
        new_vps_address=new_vps_address,
        verge_url=verge_url,
        vlmess_url=vlmess_url,
        cc_email=cc_email,
        email_password_enc=security.encrypt_field(email_password),
        gpt_password_enc=security.encrypt_field(gpt_password),
        plan_amount=plan_amount,
        converted_to_codex=converted_to_codex,
        plan_start_date=_parse_date(plan_start_date),
        plan_end_date=_parse_date(plan_end_date),
        distributed=distributed,
        first_batch_alloc=first_batch_alloc,
        ban1_is_banned=ban1_is_banned,
        ban1_date=_parse_date(ban1_date),
        ban2_delivered=ban2_delivered,
        second_voucher=second_voucher,
        ban2_is_banned=ban2_is_banned,
        ban2_date=_parse_date(ban2_date),
        ban3_delivered=ban3_delivered,
        third_voucher=third_voucher,
        ban3_is_banned=ban3_is_banned,
        notes=notes,
    )
    session.add(a)
    # 同步部门 / 选型到分类预设
    upsert_category("department", department, session)
    upsert_category("plan_type", plan_type, session)
    session.commit()
    return RedirectResponse(url=f"/accounts/{a.id}", status_code=303)


@app.post("/accounts/{aid}", dependencies=[Depends(require_auth)])
def update_account(
    aid: int,
    user_name: str = Form(...),
    department: str = Form(""),
    plan_type: str = Form(""),
    first_open_date: str = Form(""),
    status: str = Form("可用"),
    delivered: bool = Form(False),
    delivery_date: str = Form(""),
    installed: bool = Form(False),
    installer: str = Form(""),
    os_version: str = Form(""),
    server_order: str = Form(""),
    vps_ip_masked: str = Form(""),
    vps_pure: bool = Form(False),
    vps_in_use: bool = Form(False),
    new_vps_address: str = Form(""),
    verge_url: str = Form(""),
    vlmess_url: str = Form(""),
    cc_email: str = Form(""),
    email_password: str = Form(""),
    gpt_password: str = Form(""),
    plan_amount: str = Form(""),
    converted_to_codex: bool = Form(False),
    plan_start_date: str = Form(""),
    plan_end_date: str = Form(""),
    distributed: bool = Form(False),
    first_batch_alloc: str = Form(""),
    ban1_is_banned: bool = Form(False),
    ban1_date: str = Form(""),
    ban2_delivered: str = Form(""),
    second_voucher: str = Form(""),
    ban2_is_banned: bool = Form(False),
    ban2_date: str = Form(""),
    ban3_delivered: str = Form(""),
    third_voucher: str = Form(""),
    ban3_is_banned: bool = Form(False),
    notes: str = Form(""),
    session: Session = Depends(database.get_session),
):
    a = session.get(models.Account, aid)
    if not a:
        raise HTTPException(404)
    a.user_name = user_name
    a.department = department
    a.plan_type = plan_type
    a.first_open_date = _parse_date(first_open_date)
    a.status = status
    a.delivered = delivered
    a.delivery_date = _parse_date(delivery_date)
    a.installed = installed
    a.installer = installer
    a.os_version = os_version
    a.server_order = server_order
    a.vps_ip_masked = vps_ip_masked
    a.vps_pure = vps_pure
    a.vps_in_use = vps_in_use
    a.new_vps_address = new_vps_address
    a.verge_url = verge_url
    a.vlmess_url = vlmess_url
    a.cc_email = cc_email
    # 密码：表单为空则不覆盖（保留原密文）
    if email_password:
        a.email_password_enc = security.encrypt_field(email_password)
    if gpt_password:
        a.gpt_password_enc = security.encrypt_field(gpt_password)
    a.plan_amount = plan_amount
    a.converted_to_codex = converted_to_codex
    a.plan_start_date = _parse_date(plan_start_date)
    a.plan_end_date = _parse_date(plan_end_date)
    a.distributed = distributed
    a.first_batch_alloc = first_batch_alloc
    a.ban1_is_banned = ban1_is_banned
    a.ban1_date = _parse_date(ban1_date)
    a.ban2_delivered = ban2_delivered
    a.second_voucher = second_voucher
    a.ban2_is_banned = ban2_is_banned
    a.ban2_date = _parse_date(ban2_date)
    a.ban3_delivered = ban3_delivered
    a.third_voucher = third_voucher
    a.ban3_is_banned = ban3_is_banned
    a.notes = notes
    session.add(a)
    # 同步部门 / 选型到分类预设
    upsert_category("department", department, session)
    upsert_category("plan_type", plan_type, session)
    session.commit()
    return RedirectResponse(url=f"/accounts/{aid}", status_code=303)


# ---------- 详情 ----------
@app.get("/accounts/{aid}", response_class=HTMLResponse, dependencies=[Depends(require_auth)])
def account_detail(
    request: Request,
    aid: int,
    reveal: Optional[str] = None,
    session: Session = Depends(database.get_session),
):
    a = session.get(models.Account, aid)
    if not a:
        raise HTTPException(404)
    bans = session.exec(
        select(models.BanHistory).where(models.BanHistory.account_id == aid).order_by(models.BanHistory.ban_sequence)
    ).all()

    # reveal=email_pwd / gpt_pwd 时显示明文（按需解密）
    email_pwd_plain = security.decrypt_field(a.email_password_enc) if reveal == "email_pwd" else None
    gpt_pwd_plain = security.decrypt_field(a.gpt_password_enc) if reveal == "gpt_pwd" else None
    next_ban_seq = (bans[-1].ban_sequence + 1) if bans else 1

    return templates.TemplateResponse(
        request,
        "detail.html",
        {
            "a": a,
            "bans": bans,
            "email_pwd_plain": email_pwd_plain,
            "gpt_pwd_plain": gpt_pwd_plain,
            "next_ban_seq": next_ban_seq,
        },
    )


# ---------- 封号记录 ----------
@app.post("/accounts/{aid}/ban", dependencies=[Depends(require_auth)])
def add_ban(
    aid: int,
    ban_sequence: int = Form(...),
    ban_date: str = Form(""),
    ban_reason: str = Form(""),
    replacement_date: str = Form(""),
    replacement_voucher: str = Form(""),
    status_after: str = Form(""),
    session: Session = Depends(database.get_session),
):
    a = session.get(models.Account, aid)
    if not a:
        raise HTTPException(404)
    b = models.BanHistory(
        account_id=aid,
        ban_sequence=ban_sequence,
        ban_date=_parse_date(ban_date),
        ban_reason=ban_reason,
        replacement_date=_parse_date(replacement_date),
        replacement_voucher=replacement_voucher,
        status_after=status_after,
    )
    session.add(b)
    # 如果补号后状态非空，同步主表 status
    if status_after:
        a.status = status_after
        session.add(a)
    session.commit()
    return RedirectResponse(url=f"/accounts/{aid}#ban-{b.id}", status_code=303)


@app.post("/ban/{bid}/delete", dependencies=[Depends(require_auth)])
def delete_ban(bid: int, session: Session = Depends(database.get_session)):
    b = session.get(models.BanHistory, bid)
    if not b:
        raise HTTPException(404)
    aid = b.account_id
    session.delete(b)
    session.commit()
    return RedirectResponse(url=f"/accounts/{aid}", status_code=303)


# ---------- 凭证图片上传 ----------
@app.post("/upload/voucher/{aid}/{field}", dependencies=[Depends(require_auth)])
async def upload_voucher(
    aid: int,
    field: str,
    request: Request,
    session: Session = Depends(database.get_session),
):
    """上传凭证图片。支持两种方式：
    1. multipart/form-data 文件上传（file 字段）
    2. application/json 粘贴：{"data": "data:image/png;base64,xxxx"}
    field 取值：ban1_voucher / second_voucher / third_voucher
    """
    if field not in ("ban1_voucher", "second_voucher", "third_voucher"):
        raise HTTPException(400, "field 非法")

    a = session.get(models.Account, aid)
    if not a:
        raise HTTPException(404)

    content_type = request.headers.get("content-type", "")

    if content_type.startswith("multipart/"):
        form = await request.form()
        upload_file = form.get("file")
        if not upload_file or not hasattr(upload_file, "read"):
            raise HTTPException(400, "缺少 file 字段")
        raw = await upload_file.read()
        ext = ".png"
        if upload_file.content_type == "image/jpeg":
            ext = ".jpg"
        elif upload_file.content_type == "image/gif":
            ext = ".gif"
        elif upload_file.content_type == "image/webp":
            ext = ".webp"
    else:
        # JSON 粘贴
        body = await request.json()
        data_url = body.get("data", "")
        if not data_url.startswith("data:image"):
            raise HTTPException(400, "data 字段必须是 data:image/...;base64,... 格式")
        import re as _re
        m = _re.match(r"data:image/(\w+);base64,(.+)", data_url)
        if not m:
            raise HTTPException(400, "data URL 格式错误")
        fmt, b64data = m.group(1), m.group(2)
        raw = base64.b64decode(b64data)
        ext = ".png" if fmt == "png" else f".{fmt}"

    import time as _time
    filename = f"{aid}_{field}_{int(_time.time())}{ext}"
    filepath = VOUCHER_DIR / filename
    filepath.write_bytes(raw)

    # 更新数据库
    setattr(a, field, f"/vouchers/{filename}")
    session.add(a)
    session.commit()

    return JSONResponse({"ok": True, "path": f"/vouchers/{filename}"})


@app.post("/upload/voucher/{aid}/{field}/delete", dependencies=[Depends(require_auth)])
def delete_voucher(aid: int, field: str, session: Session = Depends(database.get_session)):
    """删除凭证图片"""
    if field not in ("ban1_voucher", "second_voucher", "third_voucher"):
        raise HTTPException(400, "field 非法")
    a = session.get(models.Account, aid)
    if not a:
        raise HTTPException(404)
    old_path = getattr(a, field, "")
    setattr(a, field, "")
    session.add(a)
    session.commit()
    # 删除文件
    if old_path:
        import os
        filename = old_path.split("/")[-1]
        try:
            (VOUCHER_DIR / filename).unlink(missing_ok=True)
        except Exception:
            pass
    return JSONResponse({"ok": True})


# ---------- 删除 / 回收站 ----------
@app.post("/bulk-delete", dependencies=[Depends(require_auth)])
async def bulk_delete(request: Request,
                      session: Session = Depends(database.get_session)):
    """批量软删除：把选中的多个账号移入回收站"""
    from datetime import date as _date
    today = _date.today()
    form = await request.form()
    ids = form.getlist("ids")
    for aid_str in ids:
        try:
            aid = int(aid_str)
        except (ValueError, TypeError):
            continue
        a = session.get(models.Account, aid)
        if a and a.deleted_at is None:
            a.deleted_at = today
            session.add(a)
    session.commit()
    return RedirectResponse(url="/", status_code=303)


@app.post("/accounts/{aid}/delete", dependencies=[Depends(require_auth)])
def delete_account(aid: int, session: Session = Depends(database.get_session)):
    """软删除：移入回收站"""
    a = session.get(models.Account, aid)
    if not a:
        raise HTTPException(404)
    from datetime import date as _date
    a.deleted_at = _date.today()
    session.add(a)
    session.commit()
    return RedirectResponse(url="/", status_code=303)


@app.get("/trash", response_class=HTMLResponse, dependencies=[Depends(require_auth)])
def trash_list(request: Request, session: Session = Depends(database.get_session)):
    """回收站：列出已软删除的账号"""
    rows = session.exec(
        select(models.Account).where(models.Account.deleted_at.is_not(None)).order_by(models.Account.deleted_at.desc())
    ).all()
    return templates.TemplateResponse(request, "trash.html", {"rows": rows})


@app.post("/trash/{aid}/restore", dependencies=[Depends(require_auth)])
def trash_restore(aid: int, session: Session = Depends(database.get_session)):
    """从回收站恢复"""
    a = session.get(models.Account, aid)
    if not a:
        raise HTTPException(404)
    a.deleted_at = None
    session.add(a)
    session.commit()
    return RedirectResponse(url="/trash", status_code=303)


@app.post("/trash/{aid}/purge", dependencies=[Depends(require_auth)])
def trash_purge(aid: int, session: Session = Depends(database.get_session)):
    """彻底删除（不可恢复）"""
    a = session.get(models.Account, aid)
    if not a:
        raise HTTPException(404)
    # 先删子表
    bans = session.exec(select(models.BanHistory).where(models.BanHistory.account_id == aid)).all()
    for b in bans:
        session.delete(b)
    session.delete(a)
    session.commit()
    return RedirectResponse(url="/trash", status_code=303)


@app.post("/trash/purge-all", dependencies=[Depends(require_auth)])
def trash_purge_all(session: Session = Depends(database.get_session)):
    """清空回收站"""
    rows = session.exec(select(models.Account).where(models.Account.deleted_at.is_not(None))).all()
    for a in rows:
        bans = session.exec(select(models.BanHistory).where(models.BanHistory.account_id == a.id)).all()
        for b in bans:
            session.delete(b)
        session.delete(a)
    session.commit()
    return RedirectResponse(url="/trash", status_code=303)


# ---------- 导出 Excel ----------
@app.get("/export", dependencies=[Depends(require_auth)])
def export_excel(session: Session = Depends(database.get_session), with_secrets: bool = False):
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.title = "账号列表"
    # 严格按 CSV 原始 28 个字段名和顺序（不增不减）
    headers = [
        "首次开号日期",
        "用户",
        "用户.部门",
        "账号选型",
        "是否交付",
        "安装否",
        "电脑系统及版本",
        "服务器订单",
        "VPS的IP（位号用斜杠替代）",
        "是否纯净",
        "vps是否使用",
        "verge地址（clash小猫咪用）",
        "vlmess地址（小火箭用）",
        "新vps地址",
        "第一批账号分配",
        "CC邮箱提取",
        "第一批账号是否发放",
        "第一次套餐开始时间",
        "第一次是否被封",
        "第一次被封时间",
        "是否转codex",
        "第二次账号交付",
        "第二次账号交付凭证",
        "第二次是否被封",
        "第二次被封时间",
        "第三次账号交付",
        "第三次账号交付凭证",
        "第三次是否被封",
    ]
    ws.append(headers)

    rows = session.exec(select(models.Account).where(models.Account.deleted_at.is_(None)).order_by(models.Account.id)).all()
    for a in rows:
        ws.append([
            str(a.first_open_date) if a.first_open_date else "",
            a.user_name,
            a.department,
            a.plan_type,
            "已交付" if a.delivered else "",
            "已安装" if a.installed else "",
            a.os_version,
            a.server_order,
            a.vps_ip_masked,
            "可用" if a.vps_pure else "",
            "是" if a.vps_in_use else "",
            a.verge_url,
            a.vlmess_url,
            a.new_vps_address,
            a.first_batch_alloc,
            a.cc_email,
            "是" if a.distributed else "",
            str(a.plan_start_date) if a.plan_start_date else "",
            "是" if a.ban1_is_banned else "",
            str(a.ban1_date) if a.ban1_date else "",
            "是" if a.converted_to_codex else "",
            a.ban2_delivered,
            a.second_voucher,
            "是" if a.ban2_is_banned else "",
            str(a.ban2_date) if a.ban2_date else "",
            a.ban3_delivered,
            a.third_voucher,
            "是" if a.ban3_is_banned else "",
        ])

    # 封号历史 sheet
    ws2 = wb.create_sheet("封号历史")
    ws2.append(["ID", "账号ID", "用户", "第几次", "封号日期", "封号原因", "补号日期", "补号凭证", "补号后状态"])
    bans = session.exec(select(models.BanHistory).order_by(models.BanHistory.account_id, models.BanHistory.ban_sequence)).all()
    for b in bans:
        acc = session.get(models.Account, b.account_id)
        ws2.append([
            b.id, b.account_id, acc.user_name if acc else "",
            b.ban_sequence,
            str(b.ban_date) if b.ban_date else "",
            b.ban_reason,
            str(b.replacement_date) if b.replacement_date else "",
            b.replacement_voucher,
            b.status_after,
        ])

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    filename = "ai-accounts-with-secrets.xlsx" if with_secrets else "ai-accounts.xlsx"
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


# ---------- CSV 导入 ----------
# 表头别名映射：完全对齐用户 CSV 的 28 个字段（含中文间隔号、括号说明）
# 用户 CSV 字段顺序（严格按此导入）：
#   首次开号日期 / 用户 / 用户·部门 / 账号选型 / 是否交付 / 安装否 /
#   电脑系统及版本 / 服务器订单 / VPS的IP（位号用斜杠替代）/ 是否纯净 /
#   vps是否使用 / verge地址（clash小猫咪用）/ vlmess地址（小火箭用）/ 新vps地址 /
#   第一批账号分配 / CC邮箱提取 / 第一批账号是否发放 / 第一次套餐开始时间 /
#   第一次是否被封 / 第一次被封时间 / 是否转codex /
#   第二次账号交付 / 第二次账号交付凭证 / 第二次是否被封 / 第二次被封时间 /
#   第三次账号交付 / 第三次账号交付凭证 / 第三次是否被封 / 备注
HEADER_ALIASES = {
    # ===== 基础 =====
    "首次开号日期": "first_open_date", "开号日期": "first_open_date",
    "用户": "user_name", "用户姓名": "user_name", "姓名": "user_name",
    "用户·部门": "department", "用户.部门": "department", "部门": "department",
    "账号选型": "plan_type", "选型": "plan_type",
    "状态": "status", "当前状态": "status",
    # ===== 交付与安装 =====
    "是否交付": "delivered", "交付日期": "delivery_date",
    "安装否": "installed", "是否安装": "installed",
    "安装人": "installer", "安装方式": "installer",
    "电脑系统及版本": "os_version", "电脑系统": "os_version",
    # ===== VPS =====
    "服务器订单": "server_order", "服务器订单号": "server_order",
    # 带括号说明的 IP 字段：
    "VPS的IP（位号用斜杠替代）": "vps_ip_masked",
    "VPS的IP(位号用斜杠替代)": "vps_ip_masked",  # 半角括号兼容
    "VPS的IP": "vps_ip_masked", "VPS IP(脱敏)": "vps_ip_masked", "VPS IP": "vps_ip_masked",
    "是否纯净": "vps_pure", "VPS是否纯净": "vps_pure", "VPS纯净": "vps_pure",
    "vps是否使用": "vps_in_use", "VPS是否使用": "vps_in_use",
    "VPS使用中": "vps_in_use", "VPS 是否使用中": "vps_in_use",
    "新vps地址": "new_vps_address", "新VPS地址": "new_vps_address", "新 VPS 地址": "new_vps_address",
    # ===== 节点 =====
    "verge地址（clash小猫咪用）": "verge_url",
    "verge地址(clash小猫咪用)": "verge_url",  # 半角括号兼容
    "verge地址": "verge_url", "verge": "verge_url", "clash地址": "verge_url",
    "vlmess地址（小火箭用）": "vlmess_url",
    "vlmess地址(小火箭用)": "vlmess_url",
    "vlmess地址": "vlmess_url", "vless地址": "vlmess_url", "小火箭地址": "vlmess_url",
    # ===== 第一批账号分配（多合一原始字段） =====
    "第一批账号分配": "first_batch_alloc",
    # ===== 凭证 =====
    "CC邮箱提取": "cc_email", "CC邮箱": "cc_email", "邮箱": "cc_email", "GPT账号": "cc_email",
    "邮箱密码": "email_password", "GPT密码": "gpt_password",
    "套餐金额": "plan_amount", "套餐": "plan_amount", "充值": "plan_amount",
    "是否转codex": "converted_to_codex", "是否转Codex": "converted_to_codex", "转Codex": "converted_to_codex",
    # ===== 订阅 =====
    "第一次套餐开始时间": "plan_start_date", "套餐开始": "plan_start_date", "套餐开始时间": "plan_start_date",
    "套餐到期": "plan_end_date", "套餐结束": "plan_end_date",
    "第一批账号是否发放": "distributed", "是否已发放": "distributed", "是否发放": "distributed",
    # ===== 第 1/2/3 次封号与补号（主表冗余字段 + 导入时同步写 ban_history） =====
    "第一次是否被封": "ban1_is_banned",
    "第一次被封时间": "ban1_date",
    "第二次账号交付": "ban2_delivered",
    "第二次账号交付凭证": "ban2_delivered_append",
    "第二次是否被封": "ban2_is_banned",
    "第二次被封时间": "ban2_date",
    "第三次账号交付": "ban3_delivered",
    "第三次账号交付凭证": "ban3_delivered_append",
    "第三次是否被封": "ban3_is_banned",
    # ===== 备注 =====
    "备注": "notes", "说明": "notes",
}


def _norm_header(h: str) -> str:
    """把中文表头 / 含空格的英文表头归一化为字段名"""
    h = (h or "").strip()
    if h in HEADER_ALIASES:
        return HEADER_ALIASES[h]
    # 英文字段直接小写去空格
    return h.lower().replace(" ", "_")


def _to_bool(v) -> bool:
    if isinstance(v, bool):
        return v
    s = str(v).strip().lower()
    return s in ("是", "yes", "true", "1", "y", "t", "✓", "已交付", "已安装")


@app.get("/import", response_class=HTMLResponse, dependencies=[Depends(require_auth)])
def import_form(request: Request):
    return templates.TemplateResponse(request, "import.html", {"result": None})


@app.post("/import", dependencies=[Depends(require_auth)])
async def import_csv(
    request: Request,
    file: UploadFile = File(...),
    mode: str = Form("add"),  # add=追加 / replace=先清空再导入
    session: Session = Depends(database.get_session),
):
    import csv

    # 兼容 BOM + GBK/UTF-8
    raw = await file.read()
    if raw.startswith(b"\xef\xbb\xbf"):
        raw = raw[3:]
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        try:
            text = raw.decode("gbk")
        except UnicodeDecodeError:
            text = raw.decode("utf-8", errors="replace")

    reader = csv.DictReader(io.StringIO(text))
    raw_headers = reader.fieldnames or []
    field_map = {h: _norm_header(h) for h in raw_headers}

    if mode == "replace":
        # 清空当前账号（不含回收站） + 对应封号历史
        for a in session.exec(select(models.Account).where(models.Account.deleted_at.is_(None))).all():
            for b in session.exec(select(models.BanHistory).where(models.BanHistory.account_id == a.id)).all():
                session.delete(b)
            session.delete(a)
        session.commit()

    created, skipped, errors = 0, 0, []
    for i, row in enumerate(reader, start=2):  # 数据从第 2 行开始
        data = {}
        for raw_h, field in field_map.items():
            val = (row.get(raw_h) or "").strip()
            if val:
                data[field] = val
        if not data.get("user_name"):
            skipped += 1
            continue
        try:
            a = models.Account(
                user_name=data.get("user_name"),
                department=data.get("department", ""),
                plan_type=data.get("plan_type", ""),
                first_open_date=_parse_date(data.get("first_open_date", "")),
                status=data.get("status", "可用") or "可用",
                delivered=_to_bool(data.get("delivered")),
                delivery_date=_parse_date(data.get("delivery_date", "")),
                installed=_to_bool(data.get("installed")),
                installer=data.get("installer", ""),
                os_version=data.get("os_version", ""),
                server_order=data.get("server_order", ""),
                vps_ip_masked=data.get("vps_ip_masked", ""),
                vps_pure=_to_bool(data.get("vps_pure")),
                vps_in_use=_to_bool(data.get("vps_in_use")),
                new_vps_address=data.get("new_vps_address", ""),
                verge_url=data.get("verge_url", ""),
                vlmess_url=data.get("vlmess_url", ""),
                cc_email=data.get("cc_email", ""),
                email_password_enc=security.encrypt_field(data.get("email_password", "")),
                gpt_password_enc=security.encrypt_field(data.get("gpt_password", "")),
                plan_amount=data.get("plan_amount", ""),
                converted_to_codex=_to_bool(data.get("converted_to_codex")),
                plan_start_date=_parse_date(data.get("plan_start_date", "")),
                plan_end_date=_parse_date(data.get("plan_end_date", "")),
                distributed=_to_bool(data.get("distributed")),
                # 第 1 批 + 多合一凭证字段
                first_batch_alloc=data.get("first_batch_alloc", ""),
                # 第 1/2/3 次封号与交付（CSV 宽表字段）
                ban1_is_banned=_to_bool(data.get("ban1_is_banned")),
                ban1_date=_parse_date(data.get("ban1_date", "")),
                ban2_delivered=(
                    (data.get("ban2_delivered", "") +
                     ("\n" if data.get("ban2_delivered") and data.get("ban2_delivered_append") else "") +
                     data.get("ban2_delivered_append", ""))
                    or ""
                ),
                second_voucher=data.get("ban2_delivered_append", ""),  # 兼容旧字段
                ban2_is_banned=_to_bool(data.get("ban2_is_banned")),
                ban2_date=_parse_date(data.get("ban2_date", "")),
                ban3_delivered=(
                    (data.get("ban3_delivered", "") +
                     ("\n" if data.get("ban3_delivered") and data.get("ban3_delivered_append") else "") +
                     data.get("ban3_delivered_append", ""))
                    or ""
                ),
                third_voucher=data.get("ban3_delivered_append", ""),  # 兼容旧字段
                ban3_is_banned=_to_bool(data.get("ban3_is_banned")),
                # 备注
                notes=data.get("notes", ""),
            )
            session.add(a)
            session.flush()  # 拿到 a.id
            # 同步生成 ban_history 记录（第 1/2/3 次，只要有被封时间或被封标记就生成）
            for seq, banned_key, date_key in [
                (1, "ban1_is_banned", "ban1_date"),
                (2, "ban2_is_banned", "ban2_date"),
                (3, "ban3_is_banned", "ban3_is_banned"),
            ]:
                if _to_bool(data.get(banned_key)) or data.get(date_key):
                    session.add(models.BanHistory(
                        account_id=a.id,
                        ban_sequence=seq,
                        ban_date=_parse_date(data.get(date_key, "")),
                        ban_reason="（CSV 导入）",
                    ))
            # 自动把部门 / 选型加入分类预设（这样导入后筛选器立刻能选到）
            upsert_category("department", data.get("department", ""), session)
            upsert_category("plan_type", data.get("plan_type", ""), session)
            created += 1
        except Exception as e:
            errors.append(f"第 {i} 行: {e}")
    try:
        session.commit()
    except Exception as e:
        session.rollback()
        return templates.TemplateResponse(
            request,
            "import.html",
            {"result": {"ok": False, "msg": f"提交失败：{e}", "created": 0, "skipped": 0, "errors": []}},
            status_code=400,
        )

    return templates.TemplateResponse(
        request,
        "import.html",
        {
            "result": {
                "ok": True,
                "msg": f"导入完成：新增 {created} 条，跳过 {skipped} 条空行" + (f"，{len(errors)} 条错误" if errors else ""),
                "created": created,
                "skipped": skipped,
                "errors": errors[:20],
            }
        },
    )


# ---------- 统计 ----------
@app.get("/api/stats", dependencies=[Depends(require_auth)])
def stats(session: Session = Depends(database.get_session)):
    total = session.exec(select(func.count(models.Account.id))).one()
    by_status = {}
    for row in session.exec(select(models.Account.status, func.count(models.Account.id))).all():
        by_status[row[0] or "未设置"] = row[1]
    by_dept = {}
    for row in session.exec(select(models.Account.department, func.count(models.Account.id))).all():
        by_dept[row[0] or "未设置"] = row[1]
    return JSONResponse({"total": total, "by_status": by_status, "by_department": by_dept})
