"""Close attendance at 23:59 India time, with audited catch-up after downtime."""
import asyncio
import json
import logging
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy.exc import SQLAlchemyError
from database.db import SessionLocal
from database.models import Attendance, AuditLog, User

INDIA = ZoneInfo('Asia/Kolkata')
AUTO_ACTION = 'AUTO_PUNCH_OUT'


def day_cutoff(punch_in):
    local = punch_in.replace(tzinfo=timezone.utc).astimezone(INDIA)
    cutoff = datetime.combine(local.date(), time(23, 59), INDIA)
    return cutoff.astimezone(timezone.utc).replace(tzinfo=None)


def expire_attendance(db, current=None, user_id=None):
    """Caller commits the transaction. User locks serialize manual and automatic punches."""
    current = current or datetime.now(timezone.utc).replace(tzinfo=None)
    if current.tzinfo is not None:
        current = current.astimezone(timezone.utc).replace(tzinfo=None)
    query = db.query(Attendance).filter(Attendance.punch_out_at.is_(None))
    if user_id is not None:
        query = query.filter_by(user_id=user_id)
    candidates = [
        record for record in query.order_by(Attendance.user_id, Attendance.id)
        if max(day_cutoff(record.punch_in_at), record.punch_in_at) <= current
    ]
    if not candidates:
        return 0
    ids = sorted({record.user_id for record in candidates})
    db.query(User).filter(User.id.in_(ids)).order_by(User.id).with_for_update().all()
    closed = 0
    for record in candidates:
        cutoff = max(day_cutoff(record.punch_in_at), record.punch_in_at)
        changed = db.query(Attendance).filter(
            Attendance.id == record.id, Attendance.punch_out_at.is_(None),
        ).update({
            'punch_out_at': cutoff, 'out_latitude': None,
            'out_longitude': None, 'out_accuracy': None,
        }, synchronize_session=False)
        if not changed:
            continue
        db.add(AuditLog(
            user_id=record.user_id, entity_type='Attendance', entity_id=record.id,
            action=AUTO_ACTION, old_value='OPEN',
            new_value=json.dumps({
                'actor': 'system', 'reason': 'End of punch-in day at 23:59 Asia/Kolkata',
                'effective_punch_out_utc': cutoff.isoformat(),
                'processed_at_utc': current.isoformat(), 'gps_captured': False,
            }),
        ))
        closed += 1
    db.flush()
    # A caller may already have read the open record before a concurrent close.
    db.expire_all()
    return closed


def auto_punch_ids(db):
    return {
        row.entity_id for row in db.query(AuditLog.entity_id).filter(
            AuditLog.entity_type == 'Attendance', AuditLog.action == AUTO_ACTION,
        )
    }


def reconcile():
    with SessionLocal.begin() as db:
        expire_attendance(db)


async def attendance_clock():
    while True:
        try:
            await asyncio.to_thread(reconcile)
        except SQLAlchemyError:
            logging.getLogger(__name__).exception('Automatic attendance closure failed; will retry')
        local = datetime.now(INDIA)
        cutoff = datetime.combine(local.date(), time(23, 59), INDIA)
        if cutoff <= local:
            cutoff += timedelta(days=1)
        await asyncio.sleep(min(60, max(0.1, (cutoff - local).total_seconds())))
