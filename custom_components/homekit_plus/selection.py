"""Resolve which entities are exposed, from the entry options."""

from __future__ import annotations

from typing import Any

from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er

from .const import (
    CONF_ENTITIES,
    CONF_EXCLUDE_ENTITIES,
    CONF_GROUP_ENTITIES,
    CONF_GROUPS,
    CONF_INCLUDE_AREAS,
    CONF_INCLUDE_DOMAINS,
    CONF_INCLUDE_LABELS,
    SUPPORTED_DOMAINS,
)
from .util import domain_of


def _filter_ok(entry: er.RegistryEntry | None) -> bool:
    """Entities picked up by label/area/domain filters skip hidden/config ones."""
    if entry is None:
        return True
    if entry.hidden_by or entry.disabled_by:
        return False
    return entry.entity_category not in (EntityCategory.CONFIG, EntityCategory.DIAGNOSTIC)


def has_filters(options: dict[str, Any]) -> bool:
    """Return True if any dynamic filter (label/area/domain) is configured."""
    return bool(
        options.get(CONF_INCLUDE_LABELS)
        or options.get(CONF_INCLUDE_AREAS)
        or options.get(CONF_INCLUDE_DOMAINS)
    )


def resolve_exposed(hass: HomeAssistant, options: dict[str, Any]) -> list[str]:
    """Return the sorted list of every exposed entity (incl. group members)."""
    ent_reg = er.async_get(hass)
    dev_reg = dr.async_get(hass)
    exclude = set(options.get(CONF_EXCLUDE_ENTITIES) or [])
    result: set[str] = set(options.get(CONF_ENTITIES) or [])

    candidates: set[str] = set()
    for label in options.get(CONF_INCLUDE_LABELS) or []:
        candidates.update(e.entity_id for e in er.async_entries_for_label(ent_reg, label))
        for device in dr.async_entries_for_label(dev_reg, label):
            candidates.update(
                e.entity_id
                for e in er.async_entries_for_device(ent_reg, device.id)
            )
    for area in options.get(CONF_INCLUDE_AREAS) or []:
        candidates.update(
            e.entity_id
            for e in er.async_entries_for_area(ent_reg, area)
        )
        for device in dr.async_entries_for_area(dev_reg, area):
            candidates.update(
                e.entity_id
                for e in er.async_entries_for_device(ent_reg, device.id)
                # entity explicitly moved to another area -> not in this area
                if e.area_id in (None, area)
            )
    domains = set(options.get(CONF_INCLUDE_DOMAINS) or [])
    if domains:
        candidates.update(
            s.entity_id for s in hass.states.async_all() if s.domain in domains
        )

    result.update(
        eid
        for eid in candidates
        if domain_of(eid) in SUPPORTED_DOMAINS and _filter_ok(ent_reg.async_get(eid))
    )
    for group in options.get(CONF_GROUPS) or []:
        result.update(group.get(CONF_GROUP_ENTITIES) or [])

    return sorted(eid for eid in result if eid not in exclude)
