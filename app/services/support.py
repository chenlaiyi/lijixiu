"""Support ticket services."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.support_ticket import SupportReply, SupportTicket, SupportTicketStatus
from ..schemas.support import SupportReplyCreate, SupportTicketCreate


async def create_ticket(db: AsyncSession, data: SupportTicketCreate) -> SupportTicket:
    ticket = SupportTicket(**data.model_dump())
    db.add(ticket)
    await db.commit()
    await db.refresh(ticket)
    return ticket


async def list_tickets(
    db: AsyncSession,
    store_id: int | None = None,
    user_id: int | None = None,
    status: str | None = None,
) -> list[SupportTicket]:
    stmt = select(SupportTicket).order_by(SupportTicket.id.desc())
    if store_id:
        stmt = stmt.where(SupportTicket.store_id == store_id)
    if user_id:
        stmt = stmt.where(SupportTicket.user_id == user_id)
    if status:
        stmt = stmt.where(SupportTicket.status == status)
    return list((await db.execute(stmt)).scalars().all())


async def reply_ticket(
    db: AsyncSession, ticket: SupportTicket, data: SupportReplyCreate
) -> SupportReply:
    reply = SupportReply(ticket_id=ticket.id, user_id=data.user_id, content=data.content)
    db.add(reply)
    ticket.status = SupportTicketStatus.CLOSED if data.close else SupportTicketStatus.REPLIED
    await db.commit()
    await db.refresh(reply)
    return reply
