from __future__ import annotations

import asyncio
from collections import defaultdict
from functools import lru_cache
from math import atan2, cos, radians, sin, sqrt
from typing import Any, Dict, List, Tuple

from telegram import Message
from telegram.constants import ParseMode
from telegram.error import BadRequest, Forbidden
from telegram.ext import ContextTypes

from tchaka.utils import html_format_text, logging, safe_truncate

__all__ = [
    "haversine_distance",
    "group_coordinates",
    "dispatch_msg_in_group",
    "notify_all_user_on_the_same_group_for_join",
    "populate_new_user_to_appropriate_group",
    "clean_all_msg",
]

_LOGGER = logging.getLogger(__name__)
EARTH_RADIUS_KM = 6_371.0088
MAX_BAD_REQUEST_ERROR = 10
_DISTANCE_DEGREE_KM = 111.32  # mean km length of 1° of latitude


## GeoSpatial helpers


@lru_cache
def haversine_distance(
    lat1: float,
    lon1: float,
    lat2: float,
    lon2: float,
    /,
    *,
    radius: float = EARTH_RADIUS_KM,
) -> float:
    """
    Return distance **in kilometres** between two WGS‑84 points.

    See details for the formula :
        https://gis.stackexchange.com/questions/178201/calculate-the-distance-between-two-coordinates-wgs84-in-etrs89
    """
    φ1, λ1, φ2, λ2 = map(radians, (lat1, lon1, lat2, lon2))
    dφ, dλ = φ2 - φ1, λ2 - λ1
    a = sin(dφ / 2) ** 2 + cos(φ1) * cos(φ2) * sin(dλ / 2) ** 2
    return radius * 2 * atan2(sqrt(a), sqrt(1 - a))


def _hash_cell(lat: float, lon: float, cell_km: int) -> tuple[int, int]:
    """Bucket a lat/lon into a square cell of about *cell_km* km."""
    step = cell_km / _DISTANCE_DEGREE_KM
    return int(lat / step), int(lon / step)


async def group_coordinates(
    coordinates: List[Tuple[float, float]],
    *,
    distance_threshold: int = 100,
    user_coords: Tuple[float, float] | None = None,
) -> Tuple[Dict[str, List[Tuple[float, float]]], int]:
    """Cluster *coordinates* by geographic proximity.

    A coarse spatial hash first bins points into ~*distance_threshold*‑sized
    buckets.  We then use union‑find over neighbouring buckets to build
    clusters in *≈O(n)* expected time.

    ``returns (groups, n_users_in_current_user_group)``
    """

    if not coordinates:
        return {}, 0

    cell_km = max(distance_threshold, 50)  # at least 50 km cells for hashing
    cells: Dict[tuple[int, int], List[int]] = defaultdict(list)
    for idx, (lat, lon) in enumerate(coordinates):
        cells[_hash_cell(lat, lon, cell_km)].append(idx)

    parent = list(range(len(coordinates)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(i: int, j: int) -> None:
        pi, pj = find(i), find(j)
        if pi != pj:
            parent[pj] = pi

    neighbours = [(dx, dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1)]

    for (cx, cy), idxs in cells.items():
        candidate_idxs: List[int] = []
        for dx, dy in neighbours:
            candidate_idxs.extend(cells.get((cx + dx, cy + dy), []))

        for i in idxs:
            lat_i, lon_i = coordinates[i]
            for j in candidate_idxs:
                if j <= i:
                    continue  # skip duplicate checks
                lat_j, lon_j = coordinates[j]
                if (
                    abs(lat_i - lat_j) * _DISTANCE_DEGREE_KM > distance_threshold
                    or abs(lon_i - lon_j) * _DISTANCE_DEGREE_KM > distance_threshold
                ):
                    continue  # cheap reject
                if haversine_distance(lat_i, lon_i, lat_j, lon_j) <= distance_threshold:
                    union(i, j)

    groups: Dict[str, List[Tuple[float, float]]] = defaultdict(list)
    for idx, coord in enumerate(coordinates):
        gid = f"G-{find(idx)}"
        groups[gid].append(coord)

    users_in_same_group = 0
    if user_coords is not None:
        for members in groups.values():
            if user_coords in members:
                users_in_same_group = len(members)
                break

    return dict(groups), users_in_same_group


## Telegram helpers (used by the 'front-end' of tchaka bot)


async def dispatch_msg_in_group(
    ctx: ContextTypes.DEFAULT_TYPE,
    user_new_name: str,
    message: Message,
    user_list: Dict[str, Any],
    group_list: Dict[str, List[Tuple[float, float]]],
) -> None:
    """Relay *message* to everybody who shares the same geo‑cluster."""

    from tchaka.commands import append_chat_ids_messages

    try:
        _, current_location = user_list[user_new_name]
    except KeyError:
        # sender not yet registered – nothing to do...
        return

    # quick reverse lookup {coord: group_id}
    coord_to_group = {
        coord: gid for gid, coords in group_list.items() for coord in coords
    }
    group_id = coord_to_group.get(current_location)
    if group_id is None:
        return

    recipients = [
        (uname, info[0])
        for uname, info in user_list.items()
        if uname != user_new_name and info[1] in group_list[group_id]
    ]
    if not recipients:
        return

    # build outgoing text once
    truncated = safe_truncate(message.text, 200)
    base_text = f"__**{user_new_name}**__\n\n{truncated}"

    if (
        message.reply_to_message
        and message.reply_to_message.text
        and (lines := message.reply_to_message.text.splitlines())
    ):
        quote_author, quote_msg = lines[0], safe_truncate(lines[-1])
        base_text = (
            f"__**{user_new_name}**__\n```{quote_author}{quote_msg}```\n{truncated}"
        )

    async def _send(uname: str, cid: int) -> None:
        try:
            sent = await ctx.bot.send_message(
                chat_id=cid, text=base_text, parse_mode=ParseMode.MARKDOWN
            )
            await append_chat_ids_messages(cid, sent.message_id)
        except (Forbidden, BadRequest):
            _LOGGER.debug("Deliver failed for %s", uname)
        except Exception:
            _LOGGER.exception("Unexpected error delivering to %s", uname)

    await asyncio.gather(*(_send(u, c) for u, c in recipients))


async def notify_all_user_on_the_same_group_for_join(
    ctx: ContextTypes.DEFAULT_TYPE,
    current_chat_id: int,
    user_new_name: str,
    user_list: Dict[str, Any],
) -> None:
    """Broadcast a join notification to everyone except the new user."""

    text = html_format_text(f"{user_new_name} joined the area…")
    tasks = [
        ctx.bot.send_message(chat_id=chat_id, text=text, parse_mode=ParseMode.MARKDOWN)
        for chat_id, _ in user_list.values()
        if chat_id != current_chat_id
    ]

    for coro in asyncio.as_completed(tasks):
        try:
            await coro
        except (BadRequest, Forbidden):
            pass  # ignore users who blocked the bot
        except Exception:
            _LOGGER.exception("Failed to ping a user")


async def populate_new_user_to_appropriate_group(
    user_new_name: str,
    current_chat_id: int,
    latitude: float,
    longitude: float,
    user_list: Dict[str, Any],
    group_list: Dict[str, Any],
) -> Tuple[Dict[str, Any], Dict[str, Any], int]:
    """Register a new user and recompute geo‑clusters."""

    user_list[user_new_name] = [current_chat_id, (latitude, longitude)]
    group_list, user_same_group = await group_coordinates(
        [info[1] for info in user_list.values()],
        distance_threshold=100,
        user_coords=(latitude, longitude),
    )
    return user_list, group_list, user_same_group


async def clean_all_msg(
    message: Message,
    ctx: ContextTypes.DEFAULT_TYPE,
    list_of_msg_ids: List[int] | None = None,
) -> None:
    """Best‑effort purge of previous messages with exponential back‑off."""

    await asyncio.sleep(1)  # give Telegram a moment to settle

    def _range_from_ids(ids: List[int] | None) -> List[int]:
        if not ids:
            # heuristically delete up to 30 messages before the command
            return list(range(max(1, message.message_id - 30), message.message_id))
        # delete each id plus the two following ones (command + goodbye)
        targets = {mid + offset for mid in ids for offset in (0, 1, 2)}
        return sorted(targets)

    consecutive_bad = 0
    for mid in _range_from_ids(list_of_msg_ids):
        try:
            await ctx.bot.delete_message(chat_id=message.chat_id, message_id=mid)
            consecutive_bad = 0
        except BadRequest:
            consecutive_bad += 1
            if consecutive_bad >= MAX_BAD_REQUEST_ERROR:
                break
        except Exception:
            _LOGGER.exception("Deletion failed for %s", mid)
            break
        await asyncio.sleep(0.05)  # yield control
