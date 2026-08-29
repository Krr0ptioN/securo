"""Workspace-scoped loan ledger with simple-interest repayment allocation."""
import uuid
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Literal

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_async_session
from app.core.workspace_context import WorkspaceContext, current_workspace, current_writable_workspace
from app.models.account import Account
from app.models.category import Category
from app.models.debt import Debt, DebtPayment, DebtReceipt
from app.models.payee import Payee
from app.models.transaction import Transaction
from app.providers import get_storage_provider
from app.services.attachment_service import sanitize_filename
from app.services.credit_card_service import apply_effective_date
from app.services.fx_rate_service import stamp_primary_amount

router = APIRouter(prefix="/api/debts", tags=["debts"])
CENT = Decimal("0.01")

class DebtCreate(BaseModel):
    account_id: uuid.UUID; payee_id: uuid.UUID; direction: Literal["receivable", "payable"]
    description: str = Field(min_length=1, max_length=500); principal: Decimal = Field(gt=0)
    currency: str = Field(min_length=3, max_length=3); opened_on: date; due_on: date | None = None; notes: str | None = None
    category_id: uuid.UUID | None = None; annual_interest_rate: Decimal | None = Field(default=None, ge=0, le=100); interest_start_on: date | None = None

class DebtUpdate(BaseModel):
    account_id: uuid.UUID | None = None; payee_id: uuid.UUID | None = None; description: str | None = Field(default=None, min_length=1, max_length=500)
    principal: Decimal | None = Field(default=None, gt=0); opened_on: date | None = None; due_on: date | None = None; notes: str | None = None
    category_id: uuid.UUID | None = None; annual_interest_rate: Decimal | None = Field(default=None, ge=0, le=100); interest_start_on: date | None = None; is_archived: bool | None = None

class PaymentCreate(BaseModel):
    account_id: uuid.UUID; amount: Decimal = Field(gt=0); paid_on: date; notes: str | None = None

class ReceiptUpdate(BaseModel):
    title: str | None = Field(default=None, max_length=255); tags: str | None = Field(default=None, max_length=500)
    category_id: uuid.UUID | None = None; filename: str | None = Field(default=None, max_length=255); is_archived: bool | None = None

def _money(value: Decimal) -> Decimal: return Decimal(value).quantize(CENT, rounding=ROUND_HALF_UP)
async def _payments(session, debt_id): return list((await session.scalars(select(DebtPayment).where(DebtPayment.debt_id == debt_id).order_by(DebtPayment.paid_on, DebtPayment.created_at))).all())
async def _principal_paid(session, debt_id): return Decimal((await session.scalar(select(func.coalesce(func.sum(DebtPayment.principal_amount), 0)).where(DebtPayment.debt_id == debt_id))) or 0)

async def _interest_due(session, debt, through):
    if not debt.annual_interest_rate or not debt.interest_start_on: return Decimal("0")
    principal, cursor, accrued = Decimal(debt.principal), debt.interest_start_on, Decimal("0")
    for payment in await _payments(session, debt.id):
        if payment.paid_on > through: break
        if payment.paid_on < cursor: continue
        accrued += principal * Decimal(debt.annual_interest_rate) / 100 * Decimal((payment.paid_on - cursor).days) / 365
        accrued -= Decimal(payment.interest_amount); principal -= Decimal(payment.principal_amount); cursor = payment.paid_on
    if through >= cursor: accrued += principal * Decimal(debt.annual_interest_rate) / 100 * Decimal((through - cursor).days) / 365
    return max(Decimal("0"), _money(accrued))

async def _read(session, debt, include_payments=False):
    principal_paid = await _principal_paid(session, debt.id); principal_balance = max(Decimal("0"), Decimal(debt.principal) - principal_paid)
    interest_balance = await _interest_due(session, debt, date.today()); payee = await session.get(Payee, debt.payee_id)
    out = {"id": debt.id, "payee_id": debt.payee_id, "payee_name": payee.name if payee else "", "direction": debt.direction, "description": debt.description, "principal": debt.principal, "principal_paid": principal_paid, "interest_paid": await session.scalar(select(func.coalesce(func.sum(DebtPayment.interest_amount), 0)).where(DebtPayment.debt_id == debt.id)), "paid": principal_paid, "principal_balance": principal_balance, "accrued_interest": interest_balance, "balance": principal_balance + interest_balance, "currency": debt.currency, "opened_on": debt.opened_on, "due_on": debt.due_on, "notes": debt.notes, "category_id": debt.category_id, "account_id": debt.account_id, "annual_interest_rate": debt.annual_interest_rate, "interest_start_on": debt.interest_start_on, "is_archived": debt.is_archived, "status": "settled" if principal_balance <= 0 and interest_balance <= 0 else debt.status}
    if include_payments: out["payments"] = [{"id": p.id, "amount": p.amount, "principal_amount": p.principal_amount, "interest_amount": p.interest_amount, "paid_on": p.paid_on, "notes": p.notes, "transaction_id": p.transaction_id, "interest_transaction_id": p.interest_transaction_id} for p in await _payments(session, debt.id)]
    return out

async def _owned(session, model, obj_id, workspace_id, message):
    row = await session.scalar(select(model).where(model.id == obj_id, model.workspace_id == workspace_id))
    if not row: raise HTTPException(404, message)
    return row
async def _category(session, category_id, workspace_id):
    if category_id is not None: await _owned(session, Category, category_id, workspace_id, "Category not found")

@router.get("")
async def list_debts(search: str | None = None, status_filter: str | None = Query(None, alias="status"), direction: Literal["receivable", "payable"] | None = None, payee_id: uuid.UUID | None = None, category_id: uuid.UUID | None = None, archived: bool = False, ctx: WorkspaceContext = Depends(current_workspace), session: AsyncSession = Depends(get_async_session)):
    clauses = [Debt.workspace_id == ctx.workspace.id, Debt.is_archived.is_(archived)]
    if direction: clauses.append(Debt.direction == direction)
    if payee_id: clauses.append(Debt.payee_id == payee_id)
    if category_id: clauses.append(Debt.category_id == category_id)
    if search: clauses.append(or_(Debt.description.ilike(f"%{search}%"), Payee.name.ilike(f"%{search}%")))
    values = [await _read(session, row) for row in (await session.scalars(select(Debt).outerjoin(Payee, Debt.payee_id == Payee.id).where(*clauses).order_by(Debt.opened_on.desc()))).all()]
    return [row for row in values if not status_filter or row["status"] == status_filter]

@router.get("/{debt_id}")
async def get_debt(debt_id: uuid.UUID, ctx: WorkspaceContext = Depends(current_workspace), session: AsyncSession = Depends(get_async_session)):
    return await _read(session, await _owned(session, Debt, debt_id, ctx.workspace.id, "Debt not found"), True)

@router.post("", status_code=status.HTTP_201_CREATED)
async def create_debt(data: DebtCreate, ctx: WorkspaceContext = Depends(current_writable_workspace), session: AsyncSession = Depends(get_async_session)):
    payee = await _owned(session, Payee, data.payee_id, ctx.workspace.id, "Payee not found"); account = await _owned(session, Account, data.account_id, ctx.workspace.id, "Account not found"); await _category(session, data.category_id, ctx.workspace.id)
    tx = Transaction(user_id=ctx.user_id, workspace_id=ctx.workspace.id, account_id=account.id, category_id=data.category_id, payee_id=payee.id, payee=payee.name, description=data.description, amount=data.principal, currency=data.currency.upper(), date=data.opened_on, type="debit" if data.direction == "receivable" else "credit", source="manual", status="posted", notes=data.notes, transfer_pair_id=uuid.uuid4(), related_entity_type="loan", related_entity_id=None, related_entity_name=data.description)
    apply_effective_date(tx, account); session.add(tx); await session.flush(); await stamp_primary_amount(session, ctx.user_id, tx)
    values = data.model_dump(); values.pop("account_id"); values["currency"] = data.currency.upper(); values["interest_start_on"] = values["interest_start_on"] or data.opened_on; values["last_accrual_on"] = values["interest_start_on"]
    debt = Debt(user_id=ctx.user_id, workspace_id=ctx.workspace.id, account_id=account.id, **values, origin_transaction_id=tx.id); session.add(debt); await session.flush(); tx.related_entity_id = debt.id; await session.commit(); await session.refresh(debt)
    return await _read(session, debt)

@router.patch("/{debt_id}")
async def update_debt(debt_id: uuid.UUID, data: DebtUpdate, ctx: WorkspaceContext = Depends(current_writable_workspace), session: AsyncSession = Depends(get_async_session)):
    debt = await _owned(session, Debt, debt_id, ctx.workspace.id, "Debt not found"); changes = data.model_dump(exclude_unset=True)
    if "principal" in changes and changes["principal"] < await _principal_paid(session, debt.id): raise HTTPException(400, "Principal cannot be reduced below paid principal")
    if changes.get("payee_id"): await _owned(session, Payee, changes["payee_id"], ctx.workspace.id, "Payee not found")
    if changes.get("account_id"): await _owned(session, Account, changes["account_id"], ctx.workspace.id, "Account not found")
    await _category(session, changes.get("category_id"), ctx.workspace.id)
    for key, value in changes.items(): setattr(debt, key, value)
    if debt.origin_transaction_id and (tx := await session.get(Transaction, debt.origin_transaction_id)):
        tx.description, tx.amount, tx.date, tx.notes, tx.category_id = debt.description, debt.principal, debt.opened_on, debt.notes, debt.category_id
        if debt.account_id: tx.account_id = debt.account_id
        payee = await session.get(Payee, debt.payee_id); tx.payee_id, tx.payee = debt.payee_id, payee.name if payee else None
        account = await session.get(Account, tx.account_id)
        if account:
            apply_effective_date(tx, account)
        await stamp_primary_amount(session, ctx.user_id, tx)
    await session.commit(); await session.refresh(debt); return await _read(session, debt)

@router.post("/{debt_id}/payments", status_code=status.HTTP_201_CREATED)
async def add_payment(debt_id: uuid.UUID, data: PaymentCreate, ctx: WorkspaceContext = Depends(current_writable_workspace), session: AsyncSession = Depends(get_async_session)):
    debt = await _owned(session, Debt, debt_id, ctx.workspace.id, "Debt not found")
    if debt.is_archived: raise HTTPException(400, "Archived debts cannot receive payments")
    prior = await _payments(session, debt.id)
    if prior and data.paid_on < prior[-1].paid_on: raise HTTPException(400, "Repayment date cannot precede the prior repayment")
    account = await _owned(session, Account, data.account_id, ctx.workspace.id, "Account not found"); before = await _read(session, debt); due_interest = await _interest_due(session, debt, data.paid_on)
    interest_amount = min(data.amount, due_interest); principal_amount = data.amount - interest_amount
    if principal_amount > before["principal_balance"]: raise HTTPException(400, "Payment exceeds remaining balance")
    payee = await session.get(Payee, debt.payee_id); principal_tx = interest_tx = None
    async def post(amount, description, is_transfer):
        tx = Transaction(user_id=ctx.user_id, workspace_id=ctx.workspace.id, account_id=account.id, category_id=debt.category_id if is_transfer else None, payee_id=debt.payee_id, payee=payee.name if payee else None, description=description, amount=amount, currency=debt.currency, date=data.paid_on, type="credit" if debt.direction == "receivable" else "debit", source="manual", status="posted", notes=data.notes, transfer_pair_id=uuid.uuid4() if is_transfer else None, related_entity_type="debt_repayment", related_entity_id=debt.id, related_entity_name=debt.description)
        apply_effective_date(tx, account); session.add(tx); await session.flush(); await stamp_primary_amount(session, ctx.user_id, tx); return tx
    if principal_amount: principal_tx = await post(principal_amount, f"Debt principal: {debt.description}", True)
    if interest_amount: interest_tx = await post(interest_amount, f"Debt interest: {debt.description}", False)
    payment = DebtPayment(debt_id=debt.id, transaction_id=principal_tx.id if principal_tx else None, interest_transaction_id=interest_tx.id if interest_tx else None, amount=data.amount, principal_amount=principal_amount, interest_amount=interest_amount, paid_on=data.paid_on, notes=data.notes)
    debt.last_accrual_on = data.paid_on; session.add(payment); await session.commit(); return await _read(session, debt, True)

def _receipt_read(r): return {key: getattr(r, key) for key in ("id", "debt_payment_id", "transaction_id", "title", "category_id", "tags", "filename", "content_type", "size", "is_archived", "created_at")}
@router.get("/{debt_id}/receipts")
async def list_receipts(debt_id: uuid.UUID, search: str | None = None, archived: bool = False, ctx: WorkspaceContext = Depends(current_workspace), session: AsyncSession = Depends(get_async_session)):
    await _owned(session, Debt, debt_id, ctx.workspace.id, "Debt not found"); query = select(DebtReceipt).join(DebtPayment).where(DebtPayment.debt_id == debt_id, DebtReceipt.workspace_id == ctx.workspace.id, DebtReceipt.is_archived.is_(archived))
    if search: query = query.where(or_(DebtReceipt.filename.ilike(f"%{search}%"), DebtReceipt.title.ilike(f"%{search}%"), DebtReceipt.tags.ilike(f"%{search}%")))
    return [_receipt_read(row) for row in (await session.scalars(query.order_by(DebtReceipt.created_at.desc()))).all()]

@router.post("/{debt_id}/payments/{payment_id}/receipts", status_code=status.HTTP_201_CREATED)
async def upload_receipt(debt_id: uuid.UUID, payment_id: uuid.UUID, file: UploadFile = File(...), title: str | None = None, tags: str | None = None, category_id: uuid.UUID | None = None, ctx: WorkspaceContext = Depends(current_writable_workspace), session: AsyncSession = Depends(get_async_session)):
    debt = await _owned(session, Debt, debt_id, ctx.workspace.id, "Debt not found"); payment = await session.scalar(select(DebtPayment).where(DebtPayment.id == payment_id, DebtPayment.debt_id == debt.id))
    if not payment: raise HTTPException(404, "Payment not found")
    await _category(session, category_id, ctx.workspace.id); data = await file.read()
    if len(data) > 200 * 1024 * 1024: raise HTTPException(400, "File too large. Maximum size is 200 MB.")
    filename = sanitize_filename(file.filename or "unnamed"); stored = await get_storage_provider().upload(f"{ctx.workspace.id}/debt-receipts/{payment.id}/{uuid.uuid4().hex}_{filename}", data, file.content_type or "application/octet-stream")
    receipt = DebtReceipt(debt_payment_id=payment.id, transaction_id=payment.transaction_id or payment.interest_transaction_id, workspace_id=ctx.workspace.id, user_id=ctx.user_id, title=title, tags=tags, category_id=category_id, filename=filename, storage_key=stored.storage_key, content_type=stored.content_type, size=stored.size); session.add(receipt); await session.commit(); await session.refresh(receipt); return _receipt_read(receipt)

@router.patch("/receipts/{receipt_id}")
async def update_receipt(receipt_id: uuid.UUID, data: ReceiptUpdate, ctx: WorkspaceContext = Depends(current_writable_workspace), session: AsyncSession = Depends(get_async_session)):
    receipt = await _owned(session, DebtReceipt, receipt_id, ctx.workspace.id, "Receipt not found"); changes = data.model_dump(exclude_unset=True); await _category(session, changes.get("category_id"), ctx.workspace.id)
    if changes.get("filename"): changes["filename"] = sanitize_filename(changes["filename"])
    for key, value in changes.items(): setattr(receipt, key, value)
    await session.commit(); await session.refresh(receipt); return _receipt_read(receipt)

@router.get("/receipts/{receipt_id}/download")
async def download_receipt(receipt_id: uuid.UUID, inline: bool = False, ctx: WorkspaceContext = Depends(current_workspace), session: AsyncSession = Depends(get_async_session)):
    receipt = await _owned(session, DebtReceipt, receipt_id, ctx.workspace.id, "Receipt not found"); data = await get_storage_provider().download(receipt.storage_key)
    preview = receipt.content_type.startswith("image/") or receipt.content_type == "application/pdf"; disposition = "inline" if inline and preview else "attachment"
    return Response(content=data, media_type=receipt.content_type, headers={"Content-Disposition": f'{disposition}; filename="{sanitize_filename(receipt.filename)}"', "X-Content-Type-Options": "nosniff"})
