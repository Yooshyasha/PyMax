from __future__ import annotations

import random
from typing import Any, Literal

import ua_generator
from pydantic import AliasChoices, BaseModel, Field

from pymax.static.constant import (
    ANDROID_BUILD_TAGS,
    ANDROID_DEVICES,
    ANDROID_OS_VERSIONS,
    CHROME_MOBILE_VERSIONS,
    DEFAULT_APP_VERSION,
    DEFAULT_BUILD_NUMBER,
    DEFAULT_CLIENT_SESSION_ID,
    DEFAULT_DEVICE_LOCALE,
    DEFAULT_DEVICE_NAME,
    DEFAULT_DEVICE_TYPE,
    DEFAULT_LOCALE,
    DEFAULT_OS_VERSION,
    DEFAULT_SCREEN,
    DEFAULT_TIMEZONE,
    DEFAULT_USER_AGENT,
    DESKTOP_OS_POOL,
    DESKTOP_SCREENS,
    IOS_DEVICES,
    IOS_VERSIONS,
    TIMEZONES,
    WEB_BROWSERS,
)
from pymax.static.enum import AttachType, AuthType, Capability, ContactAction, ReadAction


def to_camel(string: str) -> str:
    parts = string.split("_")
    return parts[0] + "".join(word.capitalize() for word in parts[1:])


class CamelModel(BaseModel):
    model_config = {
        "alias_generator": to_camel,
        "populate_by_name": True,
        "arbitrary_types_allowed": True,
    }


class BaseWebSocketMessage(BaseModel):
    ver: Literal[10, 11] = 11
    cmd: int
    seq: int
    opcode: int
    payload: dict[str, Any]


class UserAgentPayload(CamelModel):
    device_type: str = Field(default=DEFAULT_DEVICE_TYPE)
    locale: str = Field(default=DEFAULT_LOCALE)
    device_locale: str = Field(default=DEFAULT_DEVICE_LOCALE)
    os_version: str = Field(default=DEFAULT_OS_VERSION)
    device_name: str = Field(default=DEFAULT_DEVICE_NAME)
    header_user_agent: str = Field(default=DEFAULT_USER_AGENT)
    app_version: str = Field(default=DEFAULT_APP_VERSION)
    screen: str = Field(default=DEFAULT_SCREEN)
    timezone: str = Field(default=DEFAULT_TIMEZONE)
    client_session_id: int = Field(default=DEFAULT_CLIENT_SESSION_ID)
    build_number: int = Field(default=DEFAULT_BUILD_NUMBER)
    push_device_type: str | None = Field(default=None)
    arch: str | None = Field(default=None)


def _generate_android_ua(
    app_version: str = DEFAULT_APP_VERSION,
    build_number: int = DEFAULT_BUILD_NUMBER,
) -> UserAgentPayload:
    device = random.choice(ANDROID_DEVICES)
    android_ver = random.choice(ANDROID_OS_VERSIONS)
    chrome_ver = random.choice(CHROME_MOBILE_VERSIONS)
    build_tag = random.choice(ANDROID_BUILD_TAGS)

    header_ua = (
        f"Mozilla/5.0 (Linux; Android {android_ver}; {device['model']}; "
        f"Build/{build_tag}) AppleWebKit/537.36 (KHTML, like Gecko) "
        f"Chrome/{chrome_ver} Mobile Safari/537.36"
    )

    return UserAgentPayload(
        device_type="ANDROID",
        os_version=f"Android {android_ver}",
        device_name=device["name"],
        header_user_agent=header_ua,
        screen=device["screen"],
        app_version=app_version,
        build_number=build_number,
        timezone=random.choice(TIMEZONES),
        client_session_id=random.randint(1, 15),
        push_device_type="GCM",
        arch="arm64-v8a",
    )


def _generate_ios_ua(
    app_version: str = DEFAULT_APP_VERSION,
    build_number: int = DEFAULT_BUILD_NUMBER,
) -> UserAgentPayload:
    device = random.choice(IOS_DEVICES)
    version = random.choice(IOS_VERSIONS)

    os_ver_underscored = version["os"].replace(".", "_")
    header_ua = (
        f"Mozilla/5.0 (iPhone; CPU iPhone OS {os_ver_underscored} like Mac OS X) "
        f"AppleWebKit/605.1.15 (KHTML, like Gecko) "
        f"Version/{version['safari']} Mobile/15E148 Safari/604.1"
    )

    return UserAgentPayload(
        device_type="IOS",
        os_version=f"iOS {version['os']}",
        device_name=device["name"],
        header_user_agent=header_ua,
        screen=device["screen"],
        app_version=app_version,
        build_number=build_number,
        timezone=random.choice(TIMEZONES),
        client_session_id=random.randint(1, 15),
        push_device_type="APNS",
        arch="arm64",
    )


def _generate_desktop_ua(
    app_version: str = DEFAULT_APP_VERSION,
    build_number: int = DEFAULT_BUILD_NUMBER,
) -> UserAgentPayload:
    os_info = random.choice(DESKTOP_OS_POOL)

    ua_platform_map = {
        "Windows": "windows",
        "macOS": "macos",
        "Linux": "linux",
    }
    ua_platform = ua_platform_map.get(os_info["device_name"], "windows")
    ua = ua_generator.generate(device="desktop", platform=ua_platform, browser="chrome")

    return UserAgentPayload(
        device_type="DESKTOP",
        os_version=os_info["os_version"],
        device_name=os_info["device_name"],
        header_user_agent=ua.text,
        screen=random.choice(DESKTOP_SCREENS),
        app_version=app_version,
        build_number=build_number,
        timezone=random.choice(TIMEZONES),
        client_session_id=random.randint(1, 15),
    )


def _generate_web_ua(
    app_version: str = DEFAULT_APP_VERSION,
    build_number: int = DEFAULT_BUILD_NUMBER,
) -> UserAgentPayload:
    browser_name = random.choice(WEB_BROWSERS)

    browser_map = {
        "Chrome": "chrome",
        "Chromium": "chrome",
        "Brave": "chrome",
        "Vivaldi": "chrome",
        "Opera": "chrome",
        "Edge": "edge",
        "Firefox": "firefox",
        "Safari": "safari",
    }
    ua_browser = browser_map.get(browser_name, "chrome")
    platform = ("windows", "macos", "linux")
    if ua_browser == "safari":
        platform = "macos"
    ua = ua_generator.generate(device="desktop", platform=platform, browser=ua_browser)

    os_label_map = {
        "windows": random.choice(["Windows 10", "Windows 11"]),
        "macos": random.choice(["macOS Sonoma", "macOS Ventura", "macOS Sequoia"]),
        "linux": random.choice(["Ubuntu 22.04", "Ubuntu 24.04", "Fedora 40"]),
    }
    os_version = os_label_map.get(ua.platform, "Windows 10")

    return UserAgentPayload(
        device_type="WEB",
        os_version=os_version,
        device_name=browser_name,
        header_user_agent=ua.text,
        screen=random.choice(DESKTOP_SCREENS),
        app_version=app_version,
        build_number=build_number,
        timezone=random.choice(TIMEZONES),
        client_session_id=random.randint(1, 15),
    )


_GENERATORS: dict[str, callable] = {
    "ANDROID": _generate_android_ua,
    "IOS": _generate_ios_ua,
    "DESKTOP": _generate_desktop_ua,
    "WEB": _generate_web_ua,
}


def generate_user_agent(
    device_type: Literal["WEB", "DESKTOP", "ANDROID", "IOS"] = "WEB",
    app_version: str = DEFAULT_APP_VERSION,
    build_number: int = DEFAULT_BUILD_NUMBER,
) -> UserAgentPayload:
    """Generate a realistic :class:`UserAgentPayload` for the given *device_type*.

    Supported device types: ``"WEB"``, ``"DESKTOP"``, ``"ANDROID"``, ``"IOS"``.

    :param device_type: Тип устройства.
    :param app_version: Версия приложения (например ``"26.3.0"``).
    :param build_number: Номер сборки (например ``6498``).
    """
    gen = _GENERATORS.get(device_type)
    if gen is None:
        raise ValueError(
            f"Unknown device_type={device_type!r}. "
            f"Expected one of {set(_GENERATORS)}"
        )
    return gen(app_version=app_version, build_number=build_number)


class RequestCodePayload(CamelModel):
    phone: str
    type: AuthType = AuthType.START_AUTH
    language: str = "ru"


class SendCodePayload(CamelModel):
    token: str
    verify_code: str
    auth_token_type: AuthType = AuthType.CHECK_CODE


class LoginPayload(CamelModel):
    token: str
    interactive: bool = True
    chats_sync: int = 0
    contacts_sync: int = 0
    presence_sync: int = 0
    calls_sync: int = 0
    last_login: int = 0
    drafts_sync: int = 0
    banners_sync: int = 0
    config_hash: str | None = None

    def to_payload(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "token": self.token,
            "interactive": self.interactive,
            "presenceSync": self.presence_sync,
        }
        if self.chats_sync > 0:
            d["chatsSync"] = self.chats_sync
        if self.contacts_sync > 0:
            d["contactsSync"] = self.contacts_sync
        if self.calls_sync > 0:
            d["callsSync"] = self.calls_sync
        if self.last_login > 0:
            d["lastLogin"] = self.last_login
        if self.drafts_sync > 0:
            d["draftsSync"] = self.drafts_sync
        if self.banners_sync > 0:
            d["bannersSync"] = self.banners_sync
        if self.config_hash:
            d["configHash"] = self.config_hash
        d["exp"] = {}
        return d


SyncPayload = LoginPayload


class ReplyLink(CamelModel):
    type: str = "REPLY"
    message_id: str


class UploadPayload(CamelModel):
    count: int = 1
    profile: bool = False


class AttachPhotoPayload(CamelModel):
    type: AttachType = Field(default=AttachType.PHOTO, alias="_type")
    photo_token: str


class VideoAttachPayload(CamelModel):
    type: AttachType = Field(default=AttachType.VIDEO, alias="_type")
    video_id: int
    token: str


class AttachFilePayload(CamelModel):
    type: AttachType = Field(default=AttachType.FILE, alias="_type")
    file_id: int


class MessageElement(CamelModel):
    type: str
    from_: int = Field(..., alias="from")
    length: int


class SendMessagePayloadMessage(CamelModel):
    text: str
    cid: int
    elements: list[MessageElement]
    attaches: list[AttachPhotoPayload | AttachFilePayload | VideoAttachPayload]
    link: ReplyLink | None = None


class SendMessagePayload(CamelModel):
    chat_id: int
    message: SendMessagePayloadMessage
    notify: bool = False


class EditMessagePayload(CamelModel):
    chat_id: int
    message_id: int
    text: str
    elements: list[MessageElement]
    attaches: list[AttachPhotoPayload | AttachFilePayload | VideoAttachPayload]


class DeleteMessagePayload(CamelModel):
    chat_id: int
    message_ids: list[int]
    for_me: bool = False


class FetchContactsPayload(CamelModel):
    contact_ids: list[int]


class FetchHistoryPayload(CamelModel):
    chat_id: int
    from_time: int = Field(
        validation_alias=AliasChoices("from_time", "from"),
        serialization_alias="from",
    )
    forward: int
    backward: int = 200
    get_messages: bool = True


class ChangeProfilePayload(CamelModel):
    first_name: str
    last_name: str | None = None
    description: str | None = None
    photo_token: str | None = None
    avatar_type: str = "USER_AVATAR"  # TODO: вынести гада в энам


class ResolveLinkPayload(CamelModel):
    link: str


class PinMessagePayload(CamelModel):
    chat_id: int
    notify_pin: bool
    pin_message_id: int


class CreateGroupAttach(CamelModel):
    type: Literal["CONTROL"] = Field("CONTROL", alias="_type")
    event: str = "new"
    chat_type: str = "CHAT"
    title: str
    user_ids: list[int]


class CreateGroupMessage(CamelModel):
    cid: int
    attaches: list[CreateGroupAttach]


class CreateGroupPayload(CamelModel):
    message: CreateGroupMessage
    notify: bool = True


class InviteUsersPayload(CamelModel):
    chat_id: int
    user_ids: list[int]
    show_history: bool
    operation: str = "add"


class RemoveUsersPayload(CamelModel):
    chat_id: int
    user_ids: list[int]
    operation: str = "remove"
    clean_msg_period: int


class ChangeGroupSettingsOptions(BaseModel):
    ONLY_OWNER_CAN_CHANGE_ICON_TITLE: bool | None
    ALL_CAN_PIN_MESSAGE: bool | None
    ONLY_ADMIN_CAN_ADD_MEMBER: bool | None
    ONLY_ADMIN_CAN_CALL: bool | None
    MEMBERS_CAN_SEE_PRIVATE_LINK: bool | None


class ChangeGroupSettingsPayload(CamelModel):
    chat_id: int
    options: ChangeGroupSettingsOptions


class ChangeGroupProfilePayload(CamelModel):
    chat_id: int
    theme: str | None
    description: str | None


class GetGroupMembersPayload(CamelModel):
    type: Literal["MEMBER"] = "MEMBER"
    marker: int | None = None
    chat_id: int
    count: int


class SearchGroupMembersPayload(CamelModel):
    type: Literal["MEMBER"] = "MEMBER"
    query: str
    chat_id: int


class NavigationEventParams(BaseModel):
    action_id: int
    screen_to: int
    screen_from: int | None = None
    source_id: int
    session_id: int


class NavigationEventPayload(CamelModel):
    event: str
    time: int
    type: str = "NAV"
    user_id: int
    params: NavigationEventParams


class NavigationPayload(CamelModel):
    events: list[NavigationEventPayload]


class GetVideoPayload(CamelModel):
    chat_id: int
    message_id: int | str
    video_id: int


class GetFilePayload(CamelModel):
    chat_id: int
    message_id: str | int
    file_id: int


class SearchByPhonePayload(CamelModel):
    phone: str


class JoinChatPayload(CamelModel):
    link: str


class ReactionInfoPayload(CamelModel):
    reaction_type: str = "EMOJI"
    id: str


class AddReactionPayload(CamelModel):
    chat_id: int
    message_id: str
    reaction: ReactionInfoPayload


class GetReactionsPayload(CamelModel):
    chat_id: int
    message_ids: list[str]


class RemoveReactionPayload(CamelModel):
    chat_id: int
    message_id: str


class ReworkInviteLinkPayload(CamelModel):
    revoke_private_link: bool = True
    chat_id: int


class ContactActionPayload(CamelModel):
    contact_id: int
    action: ContactAction


class RegisterPayload(CamelModel):
    last_name: str | None = None
    first_name: str
    token: str
    token_type: AuthType = AuthType.REGISTER


class CreateFolderPayload(CamelModel):
    id: str
    title: str
    include: list[int]
    filters: list[Any] = []


class GetChatInfoPayload(CamelModel):
    chat_ids: list[int]


class GetFolderPayload(CamelModel):
    folder_sync: int = 0


class UpdateFolderPayload(CamelModel):
    id: str
    title: str
    include: list[int]
    filters: list[Any] = []
    options: list[Any] = []


class DeleteFolderPayload(CamelModel):
    folder_ids: list[str]


class LeaveChatPayload(CamelModel):
    chat_id: int


class FetchChatsPayload(CamelModel):
    marker: int


class ReadMessagesPayload(CamelModel):
    type: ReadAction
    chat_id: int
    message_id: str
    mark: int


class CheckPasswordChallengePayload(CamelModel):
    track_id: str
    password: str


class CreateTrackPayload(CamelModel):
    type: int = 0


class SetPasswordPayload(CamelModel):
    track_id: str
    password: str


class SetHintPayload(CamelModel):
    track_id: str
    hint: str


class SetTwoFactorPayload(CamelModel):
    expected_capabilities: list[Capability]
    track_id: str
    password: str
    hint: str | None = None


class RequestEmailCodePayload(CamelModel):
    track_id: str
    email: str


class SendEmailCodePayload(CamelModel):
    track_id: str
    verify_code: str
