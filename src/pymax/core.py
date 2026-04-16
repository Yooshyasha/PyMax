from __future__ import annotations

import asyncio
import contextlib
import datetime
import logging
import random
import socket
import ssl
import time
from collections.abc import Awaitable
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, Optional
from uuid import UUID

from typing_extensions import override

from .crud import Database
from .exceptions import (
    InvalidPhoneError,
    SocketNotConnectedError,
    WebSocketNotConnectedError, NeedRegistration,
)
from .interfaces import BaseClient
from .mixins import ApiMixin, SocketMixin, WebSocketMixin
from .payloads import UserAgentPayload, generate_user_agent
from .static.enum import Opcode
from .static.constant import (
    DEFAULT_PING_INTERVAL,
    HOST,
    PORT,
    REGISTER_ONLINE_DURATION,
    SESSION_STORAGE_DB,
    WEBSOCKET_URI,
    first_names,
    last_names,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    import websockets

    from pymax.filters import BaseFilter

    from .types import Channel, Chat, Dialog, Me, Message, ReactionInfo, User

logger = logging.getLogger(__name__)


class MaxClient(ApiMixin, WebSocketMixin, BaseClient):
    allowed_device_types: set[str] = {"WEB"}
    """
    Основной клиент для работы с WebSocket API сервиса Max.

    :param phone: Номер телефона для авторизации.
    :type phone: str
    :param uri: URI WebSocket сервера.
    :type uri: str, optional
    :param session_name: Название сессии для хранения базы данных.
    :type session_name: str, optional
    :param work_dir: Рабочая директория для хранения базы данных.
    :type work_dir: str, optional
    :param logger: Пользовательский логгер. Если не передан, используется логгер модуля с именем f"{__name__}.MaxClient".
    :type logger: logging.Logger | None
    :param headers: Заголовки для подключения к WebSocket.
    :type headers: UserAgentPayload
    :param token: Токен авторизации. Если не передан, будет выполнен процесс логина по номеру телефона.
    :type token: str | None, optional
    :param host: Хост API сервера.
    :type host: str, optional
    :param port: Порт API сервера.
    :type port: int, optional
    :param registration: Флаг регистрации нового пользователя.
    :type registration: bool, optional
    :param first_name: Имя пользователя для регистрации. Требуется, если registration=True.
    :type first_name: str, optional
    :param last_name: Фамилия пользователя для регистрации.
    :type last_name: str | None, optional
    :param send_fake_telemetry: Флаг отправки фейковой телеметрии.
    :type send_fake_telemetry: bool, optional
    :param proxy: Прокси для подключения к WebSocket (см. https://websockets.readthedocs.io/en/stable/topics/proxies.html).
    :type proxy: str | Literal[True] | None, optional
    :param reconnect: Флаг автоматического переподключения при потере соединения.
    :type reconnect: bool, optional

    :raises InvalidPhoneError: Если формат номера телефона неверный.
    """

    def __init__(
            self,
            phone: str,
            uri: str = WEBSOCKET_URI,
            session_name: str = SESSION_STORAGE_DB,
            headers: UserAgentPayload | None = None,
            token: str | None = None,
            send_fake_telemetry: bool = True,
            host: str = HOST,
            port: int = PORT,
            proxy: str | Literal[True] | None = None,
            work_dir: str = ".",
            registration: bool = False,
            first_name: str = "",
            last_name: str | None = None,
            device_id: UUID | None = None,
            logger: logging.Logger | None = None,
            reconnect: bool = True,
            reconnect_delay: float = 1.0,
    ) -> None:
        self.logger = logger or logging.getLogger(f"{__name__}")
        self.uri: str = uri
        self.phone: str = phone
        if not self._check_phone():
            raise InvalidPhoneError(self.phone)
        self.host: str = host
        self.port: int = port
        self.registration: bool = registration
        self.first_name: str = first_name
        self.last_name: str | None = last_name
        self.proxy: str | Literal[True] | None = proxy
        self.reconnect: bool = reconnect
        self.reconnect_delay: float = reconnect_delay

        self.is_connected: bool = False

        self.chats: list[Chat] = []
        self.dialogs: list[Dialog] = []
        self.channels: list[Channel] = []
        self.me: Me | None = None
        self.contacts: list[User] = []
        self._users: dict[int, User] = {}

        self._work_dir: str = work_dir
        self._database_path: Path = Path(work_dir) / session_name
        self._database_path.parent.mkdir(parents=True, exist_ok=True)
        self._database_path.touch(exist_ok=True)
        self._database = Database(self._work_dir)

        self._incoming: asyncio.Queue[dict[str, Any]] | None = None
        self._outgoing: asyncio.Queue[dict[str, Any]] | None = None
        self._recv_task: asyncio.Task[Any] | None = None
        self._outgoing_task: asyncio.Task[Any] | None = None
        self._pending: dict[int, asyncio.Future[dict[str, Any]]] = {}
        self._file_upload_waiters: dict[int, asyncio.Future[dict[str, Any]]] = {}
        self._background_tasks: set[asyncio.Task[Any]] = set()
        self._stop_event = asyncio.Event()

        self._seq: int = 0
        self._error_count: int = 0
        self._circuit_breaker: bool = False
        self._last_error_time: float = 0.0

        self._device_id = device_id if device_id is not None else self._database.get_device_id()
        self._file_upload_waiters: dict[int, asyncio.Future[dict[str, Any]]] = {}

        self._token = self._database.get_auth_token() or token
        if headers is None:
            headers = self._default_headers()
        self.user_agent = headers
        self._validate_device_type()
        self._send_fake_telemetry: bool = send_fake_telemetry
        self._session_id: int = int(time.time() * 1000)
        self._action_id: int = 1
        self._current_screen: str = "chats_list_tab"

        self._on_message_handlers: list[
            tuple[Callable[[Message], Any], BaseFilter[Message] | None]
        ] = []
        self._on_message_edit_handlers: list[
            tuple[Callable[[Message], Any], BaseFilter[Message] | None]
        ] = []
        self._on_message_delete_handlers: list[
            tuple[Callable[[Message], Any], BaseFilter[Message] | None]
        ] = []
        self._on_start_handler: Callable[[], Any | Awaitable[Any]] | None = None
        self._on_stop_handler: Callable[[], Any | Awaitable[Any]] | None = None
        self._on_reaction_change_handlers: list[Callable[[str, int, ReactionInfo], Any]] = []
        self._on_chat_update_handlers: list[Callable[[Chat], Any | Awaitable[Any]]] = []
        self._on_raw_receive_handlers: list[Callable[[dict[str, Any]], Any | Awaitable[Any]]] = []
        self._scheduled_tasks: list[tuple[Callable[[], Any | Awaitable[Any]], float]] = []

        self._ssl_context = ssl.create_default_context()
        self._ssl_context.set_ciphers("DEFAULT")
        self._ssl_context.check_hostname = True
        self._ssl_context.verify_mode = ssl.CERT_REQUIRED
        self._ssl_context.minimum_version = ssl.TLSVersion.TLSv1_2
        self._ssl_context.load_default_certs()
        self._socket: socket.socket | None = None
        self._ws: websockets.ClientConnection | None = None

        self._setup_logger()
        self.logger.debug(
            "Initialized MaxClient uri=%s work_dir=%s",
            self.uri,
            self._work_dir,
        )

    @staticmethod
    def _default_headers() -> UserAgentPayload:
        return generate_user_agent("WEB")

    def _validate_device_type(self) -> None:
        if self.user_agent.device_type not in self.allowed_device_types:
            raise ValueError(
                f"{self.__class__.__name__} does not support "
                f"device_type={self.user_agent.device_type}"
            )

    async def _wait_forever(self) -> None:
        try:
            await self.ws.wait_closed()
        except asyncio.CancelledError:
            self.logger.debug("wait_closed cancelled")
        except WebSocketNotConnectedError:
            self.logger.info("WebSocket not connected, exiting wait_forever")

    async def close(self) -> None:
        """
        Закрывает клиент и освобождает ресурсы.

        :return: None
        """
        try:
            self.logger.info("Closing client")
            self._stop_event.set()
        except Exception:
            self.logger.exception("Error closing client")

    async def _post_login_tasks(self, sync: bool = True) -> None:
        if sync:
            await self._sync()

        self.logger.debug("is_connected=%s before starting ping", self.is_connected)
        ping_task = asyncio.create_task(self._send_interactive_ping())
        ping_task.add_done_callback(self._log_task_exception)
        self._background_tasks.add(ping_task)

        start_scheduled_task = asyncio.create_task(self._start_scheduled_tasks())
        start_scheduled_task.add_done_callback(self._log_task_exception)

        if self._send_fake_telemetry:
            telemetry_task = asyncio.create_task(self._start())
            telemetry_task.add_done_callback(self._log_task_exception)
            self._background_tasks.add(telemetry_task)

        if self._on_start_handler:
            self.logger.debug("Calling on_start handler")
            result = self._on_start_handler()
            if asyncio.iscoroutine(result):
                await self._safe_execute(result, context="on_start handler")

    async def _keep_online_after_register(
            self, duration: float = REGISTER_ONLINE_DURATION,
    ) -> None:
        try:
            await self._sync(self.user_agent)
        except Exception:
            self.logger.warning("Post-registration sync failed", exc_info=True)
            return

        self.logger.info(
            "Post-registration online session started (%.0f min)",
            duration / 60,
        )
        deadline = asyncio.get_event_loop().time() + duration
        while self.is_connected and asyncio.get_event_loop().time() < deadline:
            try:
                await self._send_and_wait(
                    opcode=Opcode.PING,
                    payload={"interactive": True},
                    cmd=0,
                )
                self.logger.debug("Post-registration ping sent")
            except Exception:
                self.logger.warning("Post-registration ping failed, stopping")
                break
            await asyncio.sleep(DEFAULT_PING_INTERVAL)

        self.logger.info("Post-registration online session ended")

    # noinspection DuplicatedCode
    async def register_with_code(
            self,
            temp_token: str,
            code: str,
            start: bool = False,
            first_name: Optional[str] = None,
            last_name: Optional[str] = None,
    ) -> None:
        # простите за тех.долг, я копипастил
        response = await self._send_code(code, temp_token)

        token = response.get("tokenAttrs", {}).get("REGISTER", {}).get("token", "")
        if not token:
            self.logger.critical("Failed to register, token not received")
            raise ValueError("Failed to register, token not received")

        await self.continue_register(token, first_name, last_name)

        if start:
            # чувак, если ты будешь это читать, то нельзя делать одну функцию и логином и рантаймом;
            # честно, воняет, но я все понимаю и не виню
            while True:
                # noinspection PyBroadException
                try:
                    await self._post_login_tasks()
                    await self._wait_forever()
                except Exception:
                    self.logger.exception("Error during post-login tasks")
                finally:
                    await self._cleanup_client()

                self.logger.info("Reconnecting after post-login tasks failure")
                await asyncio.sleep(self.reconnect_delay)
        else:
            self.logger.info("Login successful, token saved to database, exiting...")

    async def continue_register(
            self,
            token: str,
            first_name: Optional[str] = None,
            last_name: Optional[str] = None,
    ):
        if first_name is None:
            first_name = random.choice(first_names)
        if last_name is None:
            last_name = random.choice(last_names)

        data = await self._submit_reg_info(first_name, last_name, token)
        self._token = data.get("token")
        if not self._token:
            self.logger.critical("Failed to register, token not received")
            raise ValueError("Failed to register, token not received")

        self._database.update_auth_token(self._device_id, self._token)

        online_task = asyncio.create_task(
            self._keep_online_after_register(),
            name="post-register-online",
        )
        online_task.add_done_callback(self._log_task_exception)
        self._background_tasks.add(online_task)
        online_task.add_done_callback(self._background_tasks.discard)

    async def login_with_code(self, temp_token: str, code: str, start: bool = False) -> None:
        """
        Завершает кастомный login flow: отправляет код, сохраняет токен и запускает пост-логин задачи.

        :param temp_token: Временный токен, полученный из request_code.
        :type temp_token: str
        :param code: Код верификации (6 цифр).
        :type code: str
        :param start: Флаг запуска пост-логин задач и ожидания навсегда. Если False, только сохраняет токен.
        :type start: bool, optional
        :return: None
        :rtype: None
        """
        if self.registration:
            raise ValueError("Session should register")

        resp = await self._send_code(code, temp_token)

        login_attrs = resp.get("tokenAttrs", {}).get("LOGIN", {})
        password_challenge = resp.get("passwordChallenge")

        if password_challenge and not login_attrs:
            token = await self._two_factor_auth(password_challenge)
        else:
            token = login_attrs.get("token")

        if not token:
            if not resp.get("tokenAttrs", {}).get("REGISTER"):
                raise ValueError("Login response did not contain tokenAttrs.LOGIN.token")
            else:
                self.registration = True
                token = resp.get("tokenAttrs", {}).get("REGISTER", {}).get("token", "")
                raise NeedRegistration(token)
        self._token = token
        self._database.update_auth_token(self._device_id, token)
        if start:
            while True:
                try:
                    await self._post_login_tasks()
                    await self._wait_forever()
                except Exception:
                    self.logger.exception("Error during post-login tasks")
                finally:
                    await self._cleanup_client()

                self.logger.info("Reconnecting after post-login tasks failure")
                await asyncio.sleep(self.reconnect_delay)
        else:
            self.logger.info("Login successful, token saved to database, exiting...")

    async def start(self) -> None:
        """
        Запускает клиент, подключается к WebSocket, авторизует
        пользователя (если нужно) и запускает фоновый цикл.
        Теперь включает безопасный reconnect-loop, если self.reconnect=True.

        :return: None
        :rtype: None
        """
        self.logger.info("Client starting")
        while not self._stop_event.is_set():
            try:
                await self.connect(self.user_agent)

                if self.registration:
                    if not self.first_name:
                        raise ValueError("First name is required for registration")
                    await self._register(self.first_name, self.last_name)

                if self._token and self._database.get_auth_token() is None:
                    self._database.update_auth_token(self._device_id, self._token)

                if self._token is None:
                    await self._login()

                await self._sync(self.user_agent)
                await self._post_login_tasks(sync=False)

                wait_task = asyncio.create_task(self._wait_forever())
                stop_task = asyncio.create_task(self._stop_event.wait())

                done, pending = await asyncio.wait(
                    [wait_task, stop_task], return_when=asyncio.FIRST_COMPLETED
                )

                for task in pending:
                    task.cancel()
                    with contextlib.suppress(asyncio.CancelledError):
                        await task

            except asyncio.CancelledError:
                self.logger.info("Client task cancelled, stopping")
                break
            except Exception as e:
                self.logger.exception("Client start iteration failed")
            finally:
                await self._cleanup_client()

            if not self.reconnect or self._stop_event.is_set():
                self.logger.info("Reconnect disabled or stop requested — exiting start()")
                break

            self.logger.info("Reconnect enabled — restarting client")
            await asyncio.sleep(self.reconnect_delay)

        self.logger.info("Client exited cleanly")


class SocketMaxClient(SocketMixin, MaxClient):
    allowed_device_types = {"ANDROID", "IOS", "DESKTOP"}

    @staticmethod
    def _default_headers() -> UserAgentPayload:
        return generate_user_agent("DESKTOP")

    @override
    async def _wait_forever(self):
        if self._recv_task:
            try:
                await self._recv_task
            except asyncio.CancelledError:
                self.logger.debug("Socket recv_task cancelled")
            except Exception as e:
                self.logger.exception("Socket recv_task failed: %s", e)

    @override
    async def _cleanup_client(self):
        for task in list(self._background_tasks):
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            except Exception:
                self.logger.debug(
                    "Background task raised during cancellation (socket)",
                    exc_info=True,
                )
            self._background_tasks.discard(task)

        if self._recv_task:
            self._recv_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._recv_task
            self._recv_task = None

        if self._outgoing_task:
            self._outgoing_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._outgoing_task
            self._outgoing_task = None

        for fut in self._pending.values():
            if not fut.done():
                fut.set_exception(SocketNotConnectedError())
        self._pending.clear()

        if self._socket:
            try:
                self._socket.close()
            except Exception:
                self.logger.debug("Error closing socket during cleanup", exc_info=True)
            self._socket = None

        self.is_connected = False
        self.logger.info("Client start() cleaned up (socket)")


async def web_max_client_from_socket(
        socket_client: SocketMaxClient,
        *,
        password: str | None = None,
        web_work_dir: str | None = None,
        **max_client_kwargs: Any,
) -> MaxClient:
    if not socket_client.is_connected:
        raise ValueError("SocketMaxClient must be connected")
    if not socket_client._token:
        raise ValueError("SocketMaxClient must be authenticated")

    work_dir = (
        web_work_dir
        if web_work_dir is not None
        else str(Path(socket_client._work_dir) / "web_session")
    )

    web = MaxClient(
        phone=socket_client.phone,
        work_dir=work_dir,
        token=None,
        **max_client_kwargs,
    )

    if not web._validate_version(web.user_agent.app_version, "25.12.13"):
        raise ValueError("Your app version is too old for WEB QR login")

    await web.connect(web.user_agent)
    try:
        qr_data = await web._request_qr_login()
        poll_interval = qr_data.get("pollingInterval")
        link = qr_data.get("qrLink")
        track_id = qr_data.get("trackId")
        expires_at = qr_data.get("expiresAt")

        if not poll_interval or not link or not track_id or not expires_at:
            raise ValueError("Invalid QR login data from GET_QR")

        await socket_client.authorize_qr_link(link)

        now_ms = datetime.datetime.now().timestamp() * 1000
        expires_ms = float(expires_at)
        if now_ms >= expires_ms:
            raise RuntimeError("QR code expired before polling")

        poll_timeout_sec = (expires_ms - now_ms) / 1000.0
        try:
            confirmed = await asyncio.wait_for(
                web._poll_qr_login(track_id, int(poll_interval)),
                timeout=poll_timeout_sec,
            )
        except asyncio.TimeoutError:
            raise RuntimeError("QR code expired before confirmation") from None
        if not confirmed:
            raise RuntimeError("QR login failed or expired")

        login_resp = await web._get_qr_login_data(track_id)

        password_challenge = login_resp.get("passwordChallenge")
        login_attrs = (login_resp.get("tokenAttrs") or {}).get("LOGIN", {})

        if password_challenge and not login_attrs:
            if not password:
                raise ValueError(
                    "Account requires 2FA password. "
                    "Pass the 'password' argument to web_max_client_from_socket()."
                )

            challenge_track_id = password_challenge.get("trackId")
            if not challenge_track_id:
                raise ValueError("Password challenge missing trackId")

            token_attrs = await web._check_password(password, challenge_track_id)
            if not token_attrs:
                raise ValueError("Incorrect 2FA password")

            login_attrs = token_attrs.get("LOGIN", {})

        token = login_attrs.get("token")
        if not token:
            raise ValueError("WEB session token not received after LOGIN_BY_QR")

        web._token = token
        web._database.update_auth_token(web._device_id, token)
    finally:
        await web._cleanup_client()

    return web
