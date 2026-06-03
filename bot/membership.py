from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import List, Set

from telethon import TelegramClient
from telethon.errors import UserAdminInvalidError, ParticipantIdInvalidError
from telethon.tl.functions.channels import EditBannedRequest, GetParticipantRequest
from telethon.tl.functions.messages import DeleteChatUserRequest, GetFullChatRequest
from telethon.tl.types import (
    Channel,
    ChannelParticipantAdmin,
    ChannelParticipantCreator,
    ChannelParticipantsAdmins,
    Chat,
    ChatBannedRights,
    ChatParticipantAdmin,
    ChatParticipantCreator,
)

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class GroupUser:
    user_id: int
    username: str
    full_name: str


class MembershipManager:
    def __init__(self, client: TelegramClient, group_id: int):
        self.client = client
        self.group_id = group_id
        self._self_user_id: int | None = None
        self._entity = None
        self._resolved = False

    async def _ensure_ready(self) -> None:
        if self._resolved:
            return

        me = await self.client.get_me()
        self._self_user_id = me.id
        self._entity = await self.client.get_entity(self.group_id)

        logger.info(
            "MembershipManager ready: configured_group_id=%s resolved_entity_id=%s title=%s entity_type=%s telethon_self_id=%s",
            self.group_id,
            getattr(self._entity, "id", "unknown"),
            getattr(self._entity, "title", "unknown"),
            type(self._entity).__name__,
            self._self_user_id,
        )
        self._resolved = True

    def _is_channel_like(self) -> bool:
        return isinstance(self._entity, Channel)

    def _is_basic_chat(self) -> bool:
        return isinstance(self._entity, Chat)

    def _user_to_group_user(self, user) -> GroupUser | None:
        if user is None or getattr(user, "bot", False):
            return None
        user_id = getattr(user, "id", None)
        if user_id is None:
            return None
        full_name = " ".join(
            filter(None, [getattr(user, "first_name", None), getattr(user, "last_name", None)])
        ).strip() or str(user_id)
        return GroupUser(user_id=user_id, username=getattr(user, "username", None) or "", full_name=full_name)

    async def _get_basic_chat_full(self):
        await self._ensure_ready()
        return await self.client(GetFullChatRequest(self._entity.id))

    async def _list_basic_chat_users(self) -> List[GroupUser]:
        await self._ensure_ready()
        if not self._is_basic_chat():
            return []

        try:
            full = await self._get_basic_chat_full()
        except Exception:
            logger.exception("Failed to load full basic chat info for chat_id=%s", getattr(self._entity, "id", self.group_id))
            return []

        participants_obj = getattr(getattr(full, "full_chat", None), "participants", None)
        raw_participants = list(getattr(participants_obj, "participants", []) or [])
        logger.info(
            "Basic chat raw participants collected: %s; full.users count: %s",
            len(raw_participants),
            len(getattr(full, "users", []) or []),
        )

        users_by_id = {
            getattr(user, "id"): user
            for user in (getattr(full, "users", []) or [])
            if getattr(user, "id", None) is not None
        }

        members: List[GroupUser] = []
        seen: Set[int] = set()

        for participant in raw_participants:
            user_id = getattr(participant, "user_id", None)
            if user_id is None or user_id in seen:
                continue

            user = users_by_id.get(user_id)
            if user is None:
                try:
                    user = await self.client.get_entity(user_id)
                except Exception:
                    logger.exception("Failed to resolve basic chat participant user_id=%s", user_id)
                    continue

            item = self._user_to_group_user(user)
            if item is None:
                continue

            seen.add(item.user_id)
            members.append(item)

        logger.info("Basic chat human users resolved: %s; ids=%s", len(members), ",".join(str(m.user_id) for m in members))
        return members

    async def _get_basic_chat_admin_ids(self) -> Set[int]:
        await self._ensure_ready()
        admin_ids: Set[int] = set()

        if not self._is_basic_chat():
            return admin_ids

        try:
            full = await self._get_basic_chat_full()
            participants_obj = getattr(getattr(full, "full_chat", None), "participants", None)
            raw_participants = list(getattr(participants_obj, "participants", []) or [])
            for participant in raw_participants:
                if isinstance(participant, (ChatParticipantAdmin, ChatParticipantCreator)):
                    user_id = getattr(participant, "user_id", None)
                    if user_id is not None:
                        admin_ids.add(user_id)
        except Exception:
            logger.exception("Failed to collect basic chat admins for chat_id=%s", getattr(self._entity, "id", self.group_id))

        if self._self_user_id is not None:
            admin_ids.add(self._self_user_id)

        logger.info("Basic chat admins collected: %s; ids=%s", len(admin_ids), ",".join(str(x) for x in admin_ids))
        return admin_ids

    async def _get_group_admin_ids(self) -> Set[int]:
        await self._ensure_ready()
        admin_ids: Set[int] = set()

        if self._is_channel_like():
            async for user in self.client.iter_participants(self._entity, filter=ChannelParticipantsAdmins):
                admin_ids.add(user.id)
        elif self._is_basic_chat():
            admin_ids = await self._get_basic_chat_admin_ids()

        if self._self_user_id is not None:
            admin_ids.add(self._self_user_id)

        return admin_ids

    async def _is_protected_user(self, user_id: int) -> bool:
        await self._ensure_ready()

        if self._self_user_id is not None and user_id == self._self_user_id:
            return True

        if self._is_basic_chat():
            admin_ids = await self._get_basic_chat_admin_ids()
            return user_id in admin_ids

        if self._is_channel_like():
            try:
                result = await self.client(GetParticipantRequest(self._entity, user_id))
                participant = result.participant
                if isinstance(participant, (ChannelParticipantAdmin, ChannelParticipantCreator)):
                    return True
            except Exception:
                logger.exception("Failed to inspect participant %s", user_id)

        return False

    async def list_all_human_members(self) -> List[GroupUser]:
        await self._ensure_ready()

        if self._is_basic_chat():
            members = await self._list_basic_chat_users()
            logger.info("Live group human members collected via basic chat participants API: %s", len(members))
            return members

        members: List[GroupUser] = []
        seen: Set[int] = set()

        async for user in self.client.iter_participants(self._entity):
            item = self._user_to_group_user(user)
            if item is None or item.user_id in seen:
                continue
            seen.add(item.user_id)
            members.append(item)

        logger.info("Live group human members collected via channel API: %s; ids=%s", len(members), ",".join(str(m.user_id) for m in members))
        return members

    async def list_removable_human_members(self) -> List[GroupUser]:
        await self._ensure_ready()
        protected_ids = await self._get_group_admin_ids()
        all_members = await self.list_all_human_members()
        members = [user for user in all_members if user.user_id not in protected_ids]
        logger.info(
            "Removable candidate members collected: %s (all_humans=%s protected=%s); ids=%s",
            len(members),
            len(all_members),
            len(protected_ids),
            ",".join(str(m.user_id) for m in members),
        )
        return members

    async def remove_user(self, user_id: int) -> bool:
        await self._ensure_ready()

        if await self._is_protected_user(user_id):
            logger.warning("Refused to remove protected user %s", user_id)
            return False

        try:
            if self._is_channel_like():
                rights = ChatBannedRights(
                    until_date=None,
                    view_messages=True,
                    send_messages=True,
                    send_media=True,
                    send_stickers=True,
                    send_gifs=True,
                    send_games=True,
                    send_inline=True,
                    embed_links=True,
                )
                await self.client(EditBannedRequest(self._entity, user_id, rights))
            else:
                await self.client(DeleteChatUserRequest(chat_id=self._entity.id, user_id=user_id))

            logger.info("Removed user %s from group/chat %s", user_id, self.group_id)
            return True

        except UserAdminInvalidError:
            logger.exception("Telethon account has no rights to remove members.")
            return False
        except Exception:
            logger.exception("Failed to remove user %s from group/chat %s", user_id, self.group_id)
            return False

    async def restrict_user_sending(self, user_id: int) -> bool:
        await self._ensure_ready()

        if await self._is_protected_user(user_id):
            logger.warning("Refused to restrict protected user %s", user_id)
            return False

        if not self._is_channel_like():
            logger.warning("Cannot restrict sending in basic chat. Convert chat to supergroup.")
            return False

        rights = ChatBannedRights(
            until_date=None,
            view_messages=False,
            send_messages=True,
            send_media=True,
            send_stickers=True,
            send_gifs=True,
            send_games=True,
            send_inline=True,
            embed_links=True,
        )

        try:
            await self.client(EditBannedRequest(self._entity, user_id, rights))
            logger.info("Restricted sending for user %s in group %s", user_id, self.group_id)
            return True
        except Exception:
            logger.exception("Failed to restrict sending for user %s in group %s", user_id, self.group_id)
            return False

    async def unrestrict_user_sending(self, user_id: int) -> bool:
        await self._ensure_ready()

        if not self._is_channel_like():
            logger.warning("Cannot unrestrict sending in basic chat. Convert chat to supergroup.")
            return False

        rights = ChatBannedRights(
            until_date=None,
            view_messages=False,
            send_messages=False,
            send_media=False,
            send_stickers=False,
            send_gifs=False,
            send_games=False,
            send_inline=False,
            embed_links=False,
        )

        try:
            await self.client(EditBannedRequest(self._entity, user_id, rights))
            logger.info("Unrestricted sending for user %s in group %s", user_id, self.group_id)
            return True
        except ParticipantIdInvalidError:
            logger.info("Cannot unrestrict user %s — not a group participant yet", user_id)
            return False
        except Exception:
            logger.exception("Failed to unrestrict sending for user %s in group %s", user_id, self.group_id)
            return False
