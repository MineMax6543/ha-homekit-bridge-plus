"""Accessory containers: a generic one and a camera (ffmpeg streaming)."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

from pyhap.accessory import Accessory
from pyhap.camera import (
    VIDEO_CODEC_PARAM_LEVEL_TYPES,
    VIDEO_CODEC_PARAM_PROFILE_ID_TYPES,
    Camera,
)
from pyhap.const import CATEGORY_CAMERA, CATEGORY_OTHER

from homeassistant.core import HomeAssistant

from .const import (
    CONF_MAX_FPS,
    CONF_MAX_HEIGHT,
    CONF_MAX_WIDTH,
    CONF_STREAM_SOURCE,
    CONF_SUPPORT_AUDIO,
    CONF_VIDEO_CODEC,
    DEFAULT_MAX_FPS,
    DEFAULT_MAX_HEIGHT,
    DEFAULT_MAX_WIDTH,
)
from .util import is_available

if TYPE_CHECKING:
    from .handlers import Handler

_LOGGER = logging.getLogger(__name__)


class _Container:
    """Shared behaviour: holds handlers, reports availability."""

    hass: HomeAssistant
    handlers: list[Handler]
    primary_entities: list[str]

    def _init_container(self, hass: HomeAssistant) -> None:
        self.hass = hass
        self.handlers = []
        # The entities whose availability decides if the accessory is reachable
        self.primary_entities = []

    @property
    def available(self) -> bool:
        """Reachable if any primary entity is available."""
        if not self.primary_entities:
            return True
        return any(
            is_available(self.hass.states.get(eid)) for eid in self.primary_entities
        )

    async def stop(self) -> None:
        """Stop handlers."""
        for handler in self.handlers:
            handler.stop()
        await super().stop()  # type: ignore[misc]


class HAAccessory(_Container, Accessory):
    """An accessory made of one or more entity handlers."""

    def __init__(self, hass: HomeAssistant, driver: Any, name: str, aid: int) -> None:
        Accessory.__init__(self, driver, name, aid=aid)
        self._init_container(hass)
        self.category = CATEGORY_OTHER


# ---------------------------------------------------------------------------
# Camera
# ---------------------------------------------------------------------------
_RESOLUTIONS = [
    [1920, 1080, 30],
    [1280, 960, 30],
    [1280, 720, 30],
    [1024, 768, 30],
    [640, 480, 30],
    [640, 360, 30],
    [480, 360, 30],
    [480, 270, 30],
    [320, 240, 30],
    [320, 240, 15],  # Apple Watch
    [320, 180, 30],
]
_PROFILE_NAMES = {0: "baseline", 1: "main", 2: "high"}
_SRTP_SUITE = "AES_CM_128_HMAC_SHA1_80"


def camera_options(cfg: dict[str, Any], address: str) -> dict[str, Any]:
    """HAP camera options derived from the per-entity config."""
    max_w = int(cfg.get(CONF_MAX_WIDTH) or DEFAULT_MAX_WIDTH)
    max_h = int(cfg.get(CONF_MAX_HEIGHT) or DEFAULT_MAX_HEIGHT)
    max_fps = int(cfg.get(CONF_MAX_FPS) or DEFAULT_MAX_FPS)
    resolutions = [
        [w, h, min(fps, max_fps)] for w, h, fps in _RESOLUTIONS if w <= max_w and h <= max_h
    ] or [[320, 240, min(15, max_fps)]]
    return {
        "video": {
            "codec": {
                "profiles": list(VIDEO_CODEC_PARAM_PROFILE_ID_TYPES.values()),
                "levels": list(VIDEO_CODEC_PARAM_LEVEL_TYPES.values()),
            },
            "resolutions": resolutions,
        },
        "audio": {
            "codecs": [
                {"type": "OPUS", "samplerate": 24},
                {"type": "OPUS", "samplerate": 16},
            ]
        },
        "srtp": True,
        "address": address,
    }


def build_ffmpeg_args(
    binary: str, source: str, cfg: dict[str, Any], stream_config: dict[str, Any]
) -> list[str]:
    """Build the ffmpeg argument list (no shell involved)."""
    codec = cfg.get(CONF_VIDEO_CODEC) or "libx264"
    address = stream_config["address"]
    args = [binary, "-hide_banner", "-nostats", "-loglevel", "warning"]
    if source.startswith("rtsp"):
        args += ["-rtsp_transport", "tcp"]
    args += ["-i", source]

    # video
    v_port = stream_config["v_port"]
    bitrate = int(stream_config["v_max_bitrate"])
    args += ["-map", "0:v:0", "-an", "-c:v", codec]
    if codec != "copy":
        profile = _PROFILE_NAMES.get(_profile_index(stream_config.get("v_profile_id")), "main")
        if codec == "libx264":
            args += ["-profile:v", profile, "-tune", "zerolatency"]
        args += [
            "-pix_fmt", "yuv420p",
            "-r", str(stream_config["fps"]),
            "-vf", f"scale=-2:{stream_config['height']}",
            "-b:v", f"{bitrate}k",
            "-bufsize", f"{bitrate * 4}k",
            "-maxrate", f"{bitrate}k",
        ]
    args += [
        "-payload_type", "99",
        "-ssrc", str(stream_config["v_ssrc"]),
        "-f", "rtp",
        "-srtp_out_suite", _SRTP_SUITE,
        "-srtp_out_params", stream_config["v_srtp_key"],
        f"srtp://{address}:{v_port}?rtcpport={v_port}&localrtcpport={v_port}&pkt_size=1316",
    ]

    # audio
    if cfg.get(CONF_SUPPORT_AUDIO) and stream_config.get("a_port"):
        a_port = stream_config["a_port"]
        a_bitrate = int(stream_config.get("a_max_bitrate") or 24)
        args += [
            "-map", "0:a:0?",
            "-vn",
            "-c:a", "libopus",
            "-application", "lowdelay",
            "-ac", "1",
            "-ar", f"{stream_config.get('a_sample_rate', 24)}k",
            "-b:a", f"{a_bitrate}k",
            "-bufsize", f"{a_bitrate * 4}k",
            "-payload_type", "110",
            "-ssrc", str(stream_config["a_ssrc"]),
            "-f", "rtp",
            "-srtp_out_suite", _SRTP_SUITE,
            "-srtp_out_params", stream_config["a_srtp_key"],
            f"srtp://{address}:{a_port}?rtcpport={a_port}&localrtcpport={a_port}&pkt_size=188",
        ]
    return args


def _profile_index(value: Any) -> int:
    if isinstance(value, (bytes, bytearray)) and value:
        return value[0]
    if isinstance(value, int):
        return value
    return 1


class HACameraAccessory(_Container, Camera):
    """A HomeKit camera backed by a Home Assistant camera entity."""

    def __init__(
        self,
        hass: HomeAssistant,
        driver: Any,
        name: str,
        aid: int,
        entity_id: str,
        cfg: dict[str, Any],
        address: str,
    ) -> None:
        Camera.__init__(self, camera_options(cfg, address), driver, name, aid=aid)
        self._init_container(hass)
        self.category = CATEGORY_CAMERA
        self.entity_id = entity_id
        self.cfg = cfg

    async def async_get_snapshot(self, image_size: dict[str, Any]) -> bytes:
        """Snapshot through Home Assistant's camera component."""
        from homeassistant.components.camera import async_get_image  # noqa: PLC0415

        image = await async_get_image(
            self.hass,
            self.entity_id,
            width=image_size.get("image-width"),
            height=image_size.get("image-height"),
        )
        return image.content

    async def _stream_source(self) -> str | None:
        if source := self.cfg.get(CONF_STREAM_SOURCE):
            return source
        from homeassistant.components.camera import (  # noqa: PLC0415
            async_get_stream_source,
        )

        try:
            return await async_get_stream_source(self.hass, self.entity_id)
        except Exception:  # noqa: BLE001
            _LOGGER.exception("Could not get stream source for %s", self.entity_id)
            return None

    async def start_stream(
        self, session_info: dict[str, Any], stream_config: dict[str, Any]
    ) -> bool:
        """Start ffmpeg, pushing SRTP to the iOS device."""
        try:
            self._validate_stream_config(stream_config)
        except ValueError as err:
            _LOGGER.error("%s: refusing stream config: %s", self.entity_id, err)
            return False
        source = await self._stream_source()
        if not source:
            _LOGGER.error(
                "%s has no stream source. Set one in the entity options of HomeKit "
                "Bridge Plus (e.g. an rtsp:// URL)",
                self.entity_id,
            )
            return False
        from homeassistant.components.ffmpeg import get_ffmpeg_manager  # noqa: PLC0415

        args = build_ffmpeg_args(
            get_ffmpeg_manager(self.hass).binary, source, self.cfg, stream_config
        )
        _LOGGER.debug("%s: starting ffmpeg %s", self.entity_id, args)
        try:
            process = await asyncio.create_subprocess_exec(
                *args,
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.PIPE,
            )
        except OSError as err:
            _LOGGER.error("%s: could not start ffmpeg: %s", self.entity_id, err)
            return False
        session_info["process"] = process
        session_info["log_task"] = self.hass.async_create_background_task(
            self._log_stderr(process), f"homekit_plus ffmpeg log {self.entity_id}"
        )
        return True

    async def _log_stderr(self, process: asyncio.subprocess.Process) -> None:
        assert process.stderr is not None
        while line := await process.stderr.readline():
            _LOGGER.debug("%s ffmpeg: %s", self.entity_id, line.decode(errors="replace").rstrip())
        code = await process.wait()
        if code not in (0, 255, -15):
            _LOGGER.warning("%s: ffmpeg exited with code %s", self.entity_id, code)

    async def stop_stream(self, session_info: dict[str, Any]) -> None:
        """Stop ffmpeg."""
        process: asyncio.subprocess.Process | None = session_info.get("process")
        if process is None or process.returncode is not None:
            return
        process.terminate()
        try:
            async with asyncio.timeout(3):
                await process.wait()
        except TimeoutError:
            process.kill()
            await process.wait()

    async def reconfigure_stream(
        self, session_info: dict[str, Any], stream_config: dict[str, Any]
    ) -> bool:
        """iOS asks for a new bitrate/resolution; keep the current stream."""
        return True
