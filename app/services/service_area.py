"""Xiamen service-area library, coverage assignment, and address matching."""

import json
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.service_area import (
    ServiceArea,
    ServiceAreaAssignment,
    ServiceAreaAssignmentLog,
)
from ..models.store import Store, StoreStatus
from ..models.user import BusinessRole, User
from ..schemas.service_area import BulkAssignmentRequest, BulkClearRequest

_DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "xiamen_service_areas.json"


def _source_data() -> dict:
    return json.loads(_DATA_PATH.read_text(encoding="utf-8"))


async def sync_xiamen_service_areas(db: AsyncSession) -> dict:
    data = _source_data()
    existing = {
        item.code: item
        for item in (await db.execute(select(ServiceArea))).scalars().all()
    }
    created = updated = 0
    source_codes: set[str] = set()
    for row in data["entries"]:
        source_codes.add(row["code"])
        item = existing.get(row["code"])
        values = {
            "province": data["province"],
            "city": data["city"],
            "district": row["district"],
            "street": row["street"],
            "name": row["name"],
            "area_type": row["area_type"],
            "source_name": data["source_name"],
            "source_url": data["source_url"],
            "source_published_at": data["source_published_at"],
            "active": True,
        }
        if item:
            changed = any(getattr(item, key) != value for key, value in values.items())
            if changed:
                for key, value in values.items():
                    setattr(item, key, value)
                updated += 1
        else:
            db.add(ServiceArea(code=row["code"], **values))
            created += 1
    for code, item in existing.items():
        if item.source_name == data["source_name"] and code not in source_codes and item.active:
            item.active = False
            updated += 1
    await db.commit()
    return {
        "created": created,
        "updated": updated,
        "total": len(data["entries"]),
        "source_name": data["source_name"],
        "source_url": data["source_url"],
        "source_published_at": data["source_published_at"],
    }


def _assignment_snapshot(item: ServiceAreaAssignment | None) -> dict | None:
    if not item:
        return None
    return {
        "primary_store_id": item.primary_store_id,
        "backup_store_id": item.backup_store_id,
        "manager_id": item.manager_id,
        "effective_from": item.effective_from.isoformat() if item.effective_from else None,
        "remark": item.remark,
    }


def _assignment_state(
    assignment: ServiceAreaAssignment | None,
    stores: dict[int, Store],
) -> str:
    if not assignment or not any(
        (assignment.primary_store_id, assignment.backup_store_id, assignment.manager_id)
    ):
        return "unassigned"
    primary = stores.get(assignment.primary_store_id) if assignment.primary_store_id else None
    if assignment.primary_store_id and (
        not primary or not primary.enabled or primary.status != StoreStatus.ACTIVE
    ):
        return "conflict"
    if assignment.primary_store_id and assignment.primary_store_id == assignment.backup_store_id:
        return "conflict"
    return "assigned"


async def list_service_areas(
    db: AsyncSession,
    district: str | None = None,
    street: str | None = None,
    q: str | None = None,
    assignment_status: str | None = None,
    skip: int = 0,
    limit: int = 100,
) -> dict:
    areas = list((await db.execute(
        select(ServiceArea).where(ServiceArea.active == True).order_by(  # noqa: E712
            ServiceArea.district, ServiceArea.street, ServiceArea.area_type, ServiceArea.name
        )
    )).scalars().all())
    assignments = {
        item.service_area_id: item
        for item in (await db.execute(select(ServiceAreaAssignment))).scalars().all()
    }
    stores = {item.id: item for item in (await db.execute(select(Store))).scalars().all()}
    users = {item.id: item for item in (await db.execute(select(User))).scalars().all()}

    query_text = (q or "").strip().lower()
    rows: list[tuple[ServiceArea, ServiceAreaAssignment | None, str]] = []
    counts = {"assigned": 0, "unassigned": 0, "conflict": 0}
    for area in areas:
        assignment = assignments.get(area.id)
        state = _assignment_state(assignment, stores)
        if district and area.district != district:
            continue
        if street and area.street != street:
            continue
        if query_text and query_text not in " ".join(
            (area.code, area.district, area.street, area.name)
        ).lower():
            continue
        counts[state] += 1
        if assignment_status and assignment_status != state:
            continue
        rows.append((area, assignment, state))

    items = []
    for area, assignment, state in rows[skip: skip + limit]:
        primary = stores.get(assignment.primary_store_id) if assignment else None
        backup = stores.get(assignment.backup_store_id) if assignment else None
        manager = users.get(primary.manager_id) if primary else None
        items.append({
            "id": area.id,
            "code": area.code,
            "province": area.province,
            "city": area.city,
            "district": area.district,
            "street": area.street,
            "name": area.name,
            "area_type": area.area_type,
            "active": area.active,
            "assignment_id": assignment.id if assignment else None,
            "primary_store_id": assignment.primary_store_id if assignment else None,
            "primary_store_name": primary.name if primary else None,
            "backup_store_id": assignment.backup_store_id if assignment else None,
            "backup_store_name": backup.name if backup else None,
            "manager_id": primary.manager_id if primary else None,
            "manager_name": manager.name if manager else None,
            "assignment_status": state,
            "effective_from": assignment.effective_from if assignment else None,
            "remark": assignment.remark if assignment else None,
        })
    source = _source_data()
    return {
        "items": items,
        "total": len(rows),
        "skip": skip,
        "limit": limit,
        "assigned_count": counts["assigned"],
        "unassigned_count": counts["unassigned"],
        "conflict_count": counts["conflict"],
        "source_name": source["source_name"],
        "source_url": source["source_url"],
        "source_published_at": source["source_published_at"],
    }


async def service_area_filters(db: AsyncSession) -> dict:
    areas = list((await db.execute(
        select(ServiceArea).where(ServiceArea.active == True).order_by(  # noqa: E712
            ServiceArea.district, ServiceArea.street
        )
    )).scalars().all())
    districts: dict[str, dict[str, int]] = {}
    for area in areas:
        district = districts.setdefault(area.district, {})
        district[area.street] = district.get(area.street, 0) + 1
    return {
        "city": "厦门市",
        "total": len(areas),
        "districts": [
            {
                "name": name,
                "count": sum(streets.values()),
                "streets": [
                    {"name": street, "count": count}
                    for street, count in streets.items()
                ],
            }
            for name, streets in districts.items()
        ],
    }


async def _validate_assignment_targets(db: AsyncSession, data: BulkAssignmentRequest) -> None:
    for store_id, label in (
        (data.primary_store_id, "主服务门店"),
        (data.backup_store_id, "备用服务门店"),
    ):
        if not store_id:
            continue
        store = await db.get(Store, store_id)
        if not store or not store.enabled or store.status != StoreStatus.ACTIVE:
            raise ValueError(f"{label}不存在或未启用")
    if data.manager_id:
        manager = await db.get(User, data.manager_id)
        allowed = {
            BusinessRole.STORE_MANAGER.value,
            BusinessRole.CITY_MANAGER.value,
            BusinessRole.PLATFORM_ADMIN.value,
        }
        if not manager or not set(manager.business_roles) & allowed:
            raise ValueError("负责人必须是店长、城市经理或平台管理员")


async def bulk_assign_service_areas(
    db: AsyncSession, data: BulkAssignmentRequest
) -> dict:
    if not data.primary_store_id:
        raise ValueError("请选择主服务门店")
    primary_store = await db.get(Store, data.primary_store_id) if data.primary_store_id else None
    data = data.model_copy(update={"manager_id": primary_store.manager_id if primary_store else None})
    await _validate_assignment_targets(db, data)
    areas = {
        item.id: item
        for item in (await db.execute(
            select(ServiceArea).where(ServiceArea.id.in_(data.service_area_ids))
        )).scalars().all()
    }
    assignments = {
        item.service_area_id: item
        for item in (await db.execute(
            select(ServiceAreaAssignment).where(
                ServiceAreaAssignment.service_area_id.in_(data.service_area_ids)
            )
        )).scalars().all()
    }
    result = {
        "selected": len(data.service_area_ids),
        "created": 0,
        "updated": 0,
        "skipped": 0,
        "unchanged": 0,
        "conflicts": 0,
        "cleared": 0,
        "missing": len(data.service_area_ids) - len(areas),
        "conflict_samples": [],
        "dry_run": data.dry_run,
    }
    now = datetime.now(timezone.utc)
    for area_id in data.service_area_ids:
        area = areas.get(area_id)
        if not area:
            continue
        assignment = assignments.get(area_id)
        before = _assignment_snapshot(assignment)
        has_existing = bool(before and any(
            before.get(key) for key in ("primary_store_id", "backup_store_id", "manager_id")
        ))
        if has_existing:
            result["conflicts"] += 1
            if len(result["conflict_samples"]) < 10:
                result["conflict_samples"].append(
                    f"{area.district} {area.street} {area.name}"
                )
            if data.conflict_mode == "skip":
                result["skipped"] += 1
                continue

        values = {
            "primary_store_id": data.primary_store_id,
            "backup_store_id": data.backup_store_id,
            "manager_id": data.manager_id,
            "effective_from": data.effective_from or now,
            "remark": data.remark,
            "updated_by_user_id": data.operator_user_id,
        }
        if assignment and data.conflict_mode == "fill_empty":
            values = {
                key: (getattr(assignment, key) if getattr(assignment, key) is not None else value)
                for key, value in values.items()
            }
        effective_store = await db.get(Store, values["primary_store_id"]) if values["primary_store_id"] else None
        values["manager_id"] = effective_store.manager_id if effective_store else None
        values["updated_by_user_id"] = data.operator_user_id
        after = {
            key: (value.isoformat() if isinstance(value, datetime) else value)
            for key, value in values.items()
            if key != "updated_by_user_id"
        }
        if before and all(before.get(key) == after.get(key) for key in after):
            result["unchanged"] += 1
            continue
        if data.dry_run:
            result["updated" if assignment else "created"] += 1
            continue
        if assignment:
            for key, value in values.items():
                setattr(assignment, key, value)
            result["updated"] += 1
        else:
            assignment = ServiceAreaAssignment(service_area_id=area_id, **values)
            db.add(assignment)
            await db.flush()
            result["created"] += 1
        db.add(ServiceAreaAssignmentLog(
            service_area_id=area_id,
            assignment_id=assignment.id,
            action="assign" if not before else data.conflict_mode,
            before_json=json.dumps(before, ensure_ascii=False) if before else None,
            after_json=json.dumps(after, ensure_ascii=False),
            operator_user_id=data.operator_user_id,
        ))
    if not data.dry_run:
        await db.commit()
    return result


async def bulk_clear_service_areas(db: AsyncSession, data: BulkClearRequest) -> dict:
    assignments = list((await db.execute(
        select(ServiceAreaAssignment).where(
            ServiceAreaAssignment.service_area_id.in_(data.service_area_ids)
        )
    )).scalars().all())
    result = {
        "selected": len(data.service_area_ids),
        "created": 0,
        "updated": 0,
        "skipped": 0,
        "unchanged": len(data.service_area_ids) - len(assignments),
        "conflicts": 0,
        "cleared": len(assignments),
        "missing": 0,
        "conflict_samples": [],
        "dry_run": data.dry_run,
    }
    if data.dry_run:
        return result
    for assignment in assignments:
        before = _assignment_snapshot(assignment)
        db.add(ServiceAreaAssignmentLog(
            service_area_id=assignment.service_area_id,
            assignment_id=None,
            action="clear",
            before_json=json.dumps(before, ensure_ascii=False),
            after_json=json.dumps({"remark": data.remark}, ensure_ascii=False),
            operator_user_id=data.operator_user_id,
        ))
        await db.delete(assignment)
    await db.commit()
    return result


async def assignment_logs(
    db: AsyncSession,
    service_area_id: int | None = None,
    limit: int = 100,
) -> list[dict]:
    stmt = select(ServiceAreaAssignmentLog).order_by(
        ServiceAreaAssignmentLog.id.desc()
    ).limit(limit)
    if service_area_id:
        stmt = stmt.where(ServiceAreaAssignmentLog.service_area_id == service_area_id)
    logs = list((await db.execute(stmt)).scalars().all())
    area_ids = {item.service_area_id for item in logs}
    areas = {
        item.id: item
        for item in (await db.execute(
            select(ServiceArea).where(ServiceArea.id.in_(area_ids))
        )).scalars().all()
    } if area_ids else {}
    return [
        {
            "id": item.id,
            "service_area_id": item.service_area_id,
            "area_name": " ".join(filter(None, (
                areas.get(item.service_area_id).district if areas.get(item.service_area_id) else None,
                areas.get(item.service_area_id).street if areas.get(item.service_area_id) else None,
                areas.get(item.service_area_id).name if areas.get(item.service_area_id) else None,
            ))),
            "action": item.action,
            "before_json": item.before_json,
            "after_json": item.after_json,
            "operator_user_id": item.operator_user_id,
            "created_at": item.created_at,
        }
        for item in logs
    ]


async def match_service_area(
    db: AsyncSession, address_text: str
) -> tuple[ServiceArea | None, ServiceAreaAssignment | None, Store | None]:
    normalized = "".join((address_text or "").split()).lower()
    if not normalized:
        return None, None, None
    areas = list((await db.execute(
        select(ServiceArea).where(ServiceArea.active == True)  # noqa: E712
    )).scalars().all())
    candidates = []
    for area in areas:
        if area.name.lower() not in normalized:
            continue
        score = len(area.name) * 10
        if area.district.lower() in normalized:
            score += 1000
        if area.street.lower() in normalized:
            score += 500
        candidates.append((score, area))
    if not candidates:
        return None, None, None
    area = max(candidates, key=lambda item: (item[0], len(item[1].name)))[1]
    assignment = (
        await db.execute(
            select(ServiceAreaAssignment).where(
                ServiceAreaAssignment.service_area_id == area.id
            )
        )
    ).scalar_one_or_none()
    if assignment and assignment.effective_from:
        effective = assignment.effective_from
        if effective.tzinfo is None:
            effective = effective.replace(tzinfo=timezone.utc)
        if effective > datetime.now(timezone.utc):
            assignment = None
    store = None
    if assignment:
        for store_id in (assignment.primary_store_id, assignment.backup_store_id):
            if not store_id:
                continue
            candidate = await db.get(Store, store_id)
            if candidate and candidate.enabled and candidate.status == StoreStatus.ACTIVE:
                store = candidate
                break
    return area, assignment, store


async def resolve_open_area(db, area_id):
    area = await db.get(ServiceArea, area_id)
    assignment = (await db.execute(select(ServiceAreaAssignment).where(
        ServiceAreaAssignment.service_area_id == area_id))).scalar_one_or_none()
    if not area or not area.active or not assignment:
        raise ValueError("所选社区尚未开通服务")
    if assignment.effective_from:
        effective = assignment.effective_from
        if effective.tzinfo is None:
            effective = effective.replace(tzinfo=timezone.utc)
        if effective > datetime.now(timezone.utc):
            raise ValueError("所选社区服务尚未生效")
    for store_id in (assignment.primary_store_id, assignment.backup_store_id):
        store = await db.get(Store, store_id) if store_id else None
        if store and store.enabled and store.status == StoreStatus.ACTIVE:
            return area, assignment, store
    raise ValueError("所选社区的服务门店暂未开通")


async def customer_options(db, *, include_order_estates=True):
    from ..models.store import StoreAddress
    from ..models.order import Order
    areas = (await db.execute(select(ServiceArea).join(ServiceAreaAssignment,
        ServiceAreaAssignment.service_area_id == ServiceArea.id).where(ServiceArea.active == True))).scalars().all()
    result = []
    for area in areas:
        try:
            _, assignment, store = await resolve_open_area(db, area.id)
        except ValueError:
            continue
        estates = sorted(set((await db.execute(select(StoreAddress.estate).where(
            StoreAddress.service_area_id == area.id, StoreAddress.enabled == True,
            StoreAddress.estate != ""))).scalars().all()))
        ordered_estates = (await db.execute(select(Order.estate).where(
            Order.service_area_id == area.id, Order.estate.is_not(None), Order.estate != ""))).scalars().all() if include_order_estates else []
        estates = sorted(set(estates + list(ordered_estates)))
        result.append(dict(id=area.id, service_area_id=area.id, name=area.name,
            label=f"{area.district} / {area.street} / {area.name}",
            province=area.province, city=area.city, district=area.district, street=area.street,
            store_id=store.id, store_name=store.name, region_id=store.region_id, estates=estates))
    return result
