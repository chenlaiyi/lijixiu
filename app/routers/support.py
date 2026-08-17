"""Support center routes."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import get_db
from ..models.support_ticket import SupportTicket
from ..schemas.support import SupportReplyCreate, SupportTicketCreate, SupportTicketOut
from ..services import support as support_service

router = APIRouter(prefix="/api/v1/support", tags=["support"])


@router.post("/tickets", response_model=SupportTicketOut, status_code=201)
async def create_ticket(data: SupportTicketCreate, db: AsyncSession = Depends(get_db)):
    return await support_service.create_ticket(db, data)


@router.get("/tickets", response_model=list[SupportTicketOut])
async def list_tickets(
    store_id: int | None = None,
    user_id: int | None = None,
    status: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    return await support_service.list_tickets(db, store_id, user_id, status)


@router.post("/tickets/{ticket_id}/reply")
async def reply_ticket(
    ticket_id: int,
    data: SupportReplyCreate,
    db: AsyncSession = Depends(get_db),
):
    ticket = await db.get(SupportTicket, ticket_id)
    if not ticket:
        raise HTTPException(404, "Ticket not found")
    reply = await support_service.reply_ticket(db, ticket, data)
    return {"id": reply.id, "ticket_id": reply.ticket_id, "created_at": reply.created_at}
