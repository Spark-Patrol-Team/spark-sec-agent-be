"""XDR OpenAPI 平台接入层（官方签名 + POST /api/xdr/v1/alerts/list）。

严格遵循《XDR_OpenAPI更新版》《真实XDR_OpenAPI_脱敏接口契约交接文档》：
- 鉴权：token / aksk / auth_code 三种；aksk/auth_code 走 OfficialXdrSigner（等价对齐官方 aksk_py3.py::Signature）
- 请求方法：POST + body 签名（与 test_aksk.py 的调用契约一致）
- 路径默认：/api/xdr/v1/alerts/list
- 分页：按 page/pageSize 遍历，受 max_pages 安全上限保护
- 定向：拉取受控页范围后本地按 uuId 精确筛选（《接入方案》第三步第6条，不把 ID 塞进 URL）
"""
from __future__ import annotations

import binascii
import hashlib
import hmac
import json
import logging
import struct
import urllib.parse
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Callable, Iterable, Mapping
from urllib.parse import urlparse

import httpx

from sec_agent.domain.models import (
    AlertRecord,
    EvidenceRef,
    ToolCallStatus,
    ToolRequest,
    ToolResult,
    ToolSideEffectType,
    utc_now,
)
from sec_agent.platforms.mock_state import StatefulMockLedger
from sec_agent.tools.base import ToolDispatcher
from sec_agent.tools.tool_dispatcher import ToolHandler, build_platform_tool_dispatcher
from sec_agent.tools.xdr_query_tool import handle_xdr_query

logger = logging.getLogger(__name__)
_logged_basic_config = False
if not logging.getLogger().handlers and not _logged_basic_config:
    try:
        logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s [%(levelname)s] %(message)s")
    except Exception:  # pragma: no cover
        pass
    _logged_basic_config = True


# ============================================================
# 官方签名算法等价移植（与官方 aksk_py3.py::Signature 契约等价）
# 说明：算法逐行对齐官方 Signature 类（test_aksk.py 调用契约）；
#       auth_code 解码依赖 pycryptodome，未安装时抛清晰 RuntimeError。
# ============================================================

_EXTEND_HEADER = "algorithm=HMAC-SHA256, Access=%s, SignedHeaders=%s, Signature=%s"
_AUTH_HEADER_KEY = "Authorization"
_SDK_HOST_KEY = "sdk-host"
_CONTENT_TYPE_KEY = "content-type"
_SDK_CONTENT_TYPE_KEY = "sdk-content-type"
_DEFAULT_CONTENT_TYPE = "application/json"
_SIGN_DATE_KEY = "sign-date"
_TOTAL_STR = "HMAC-SHA256\n%s\n%s"
_AUTH_CODE_PARAMS = "%s+%s+%s+%s+%s+%s+%s+%s"
_AUTH_CODE_PARAMS_NUM = 14


class OfficialXdrSigner:
    """官方等价签名器。与 test_aksk.py 示例调用：
        req = requests.Request("POST", url, headers=..., data=json.dumps(body))
        Signature(auth_code=...).signature(req=req)
    的签名契约完全等价。
    """

    def __init__(
        self,
        auth_code: str | None = None,
        ak: str | None = None,
        sk: str | None = None,
    ) -> None:
        if ak and sk:
            logger.info("[OfficialXdrSigner] 以 AK/SK 直传模式初始化（ak 前缀=%s）", ak[:8])
            self._access_key = ak
            self._secret_key = sk
        elif auth_code:
            logger.info("[OfficialXdrSigner] 以 auth_code 模式初始化（联动码长度=%d）", len(auth_code))
            self._access_key, self._secret_key = self._decode_auth_code(auth_code)
            logger.info("[OfficialXdrSigner] auth_code 解码成功（ak 前缀=%s）", self._access_key[:8])
        else:
            raise ValueError("OfficialXdrSigner 需要 (ak+sk) 或 auth_code 之一初始化")

    # ------------------------------------------------------------------ helpers
    @staticmethod
    def _hmac_sha256_hex(secret_key: str, data: str) -> str:
        mac = hmac.new(secret_key.encode("utf-8"), data.encode("utf-8"), hashlib.sha256)
        return binascii.hexlify(mac.digest()).decode("utf-8").upper()

    @staticmethod
    def _sha256_hex_upper(b: bytes | bytearray) -> str:
        digest = hashlib.sha256(bytes(b)).digest()
        return binascii.hexlify(digest).decode("utf-8").upper()

    @staticmethod
    def _get_host(uri: str) -> str:
        return urlparse(uri).netloc

    @classmethod
    def _header_check(cls, headers: dict[str, Any] | None, host: str) -> tuple[dict[str, Any], str]:
        if headers is None:
            headers = {}
        elif not isinstance(headers, dict):
            raise ValueError("headers 格式非法，必须是 dict")
        if _SDK_HOST_KEY not in headers:
            headers[_SDK_HOST_KEY] = host
        if _CONTENT_TYPE_KEY not in headers:
            headers[_SDK_CONTENT_TYPE_KEY] = _DEFAULT_CONTENT_TYPE
        else:
            headers[_SDK_CONTENT_TYPE_KEY] = headers[_CONTENT_TYPE_KEY]
        if _SIGN_DATE_KEY not in headers:
            sign_date = datetime.now().strftime("%Y%m%dT%H%M%SZ")
            headers[_SIGN_DATE_KEY] = sign_date
        else:
            sign_date = headers[_SIGN_DATE_KEY]
        return headers, sign_date

    @staticmethod
    def _sign_header_handler(headers: Mapping[str, Any]) -> tuple[str, str]:
        items = [(str(k), str(v)) for k, v in headers.items()]
        items.sort(key=lambda x: x[0].lower())
        header_lines = [f"{k}:{v}\n" for k, v in items]
        sign_keys = [f"{k};" for k, _ in items]
        sign_header_str = "".join(sign_keys)
        if sign_header_str:
            sign_header_str = sign_header_str[:-1]
        return "".join(header_lines), sign_header_str

    @staticmethod
    def _url_transform(url_str: str) -> str:
        relative_path = urlparse(url_str).path or "/"
        if not relative_path.endswith("/"):
            relative_path += "/"
        return urllib.parse.quote(relative_path, encoding="utf-8")

    @staticmethod
    def _query_str_transform(params: Mapping[str, Any] | None) -> str:
        params = params or {}
        normalized = {k: ("" if v is None else str(v)) for k, v in params.items()}
        sorted_items = sorted(normalized.items(), key=lambda x: x[0])
        return urllib.parse.urlencode(sorted_items).replace("%3D", "=")

    @classmethod
    def _payload_transform(cls, payload: str) -> str:
        data_bytes = payload.encode("utf-8")
        byte_values = sorted(struct.unpack("b", bytes([b]))[0] for b in data_bytes)
        compact = bytearray()
        for v in byte_values:
            if v != 0x20:
                compact.append(v)
        return cls._sha256_hex_upper(compact)

    def _get_canonical_str(
        self,
        method: str,
        url: str,
        params: Mapping[str, Any] | None,
        headers_str: str,
        payload: str,
        sign_header_str: str,
    ) -> str:
        parts = [
            method,
            "\n",
            self._url_transform(url),
            "\n",
            self._query_str_transform(params),
            "\n",
            headers_str,
            sign_header_str,
            "\n",
            self._payload_transform(payload),
        ]
        return "".join(parts)

    # ----------------------------------------------------------- auth_code 解码
    @staticmethod
    def _reverse_hex(auth_code: str) -> bytes:
        return binascii.unhexlify(auth_code)

    @staticmethod
    def _calculate_aes_secret(builders: list[str]) -> bytes:
        if len(builders) != _AUTH_CODE_PARAMS_NUM:
            raise ValueError(
                f"auth_code 解码失败：builder 数量应为 {_AUTH_CODE_PARAMS_NUM}，实际 {len(builders)}"
            )
        build_str = _AUTH_CODE_PARAMS % (
            builders[0], builders[1], builders[2], builders[3],
            builders[4], builders[5], builders[6], builders[11],
        )
        return hashlib.sha256(build_str.encode("utf-8")).digest()

    @classmethod
    def _aes_cbc_decrypt(cls, cipher_hex: str, key: bytes) -> str:
        try:
            from Crypto.Cipher import AES  # pycryptodome
        except ModuleNotFoundError as exc:  # pragma: no cover - 环境相关
            raise RuntimeError(
                "auth_code 模式需要 pycryptodome 依赖，请执行 `python -m pip install pycryptodome` "
                "或改用 XDR_AUTH_TYPE=aksk 并配置 XDR_ACCESS_KEY / XDR_SECRET_KEY"
            ) from exc
        cipher = AES.new(key, AES.MODE_CBC, bytearray(AES.block_size))
        padded = cipher.decrypt(bytes.fromhex(cipher_hex))
        decoded = padded.decode("utf-8")
        return decoded.rstrip("\x00\x01\x02\x03\x04\x05\x06\x07\x08\t\n\x0b\x0c\r\x0e\x0f\x10")

    @classmethod
    def _decode_auth_code(cls, auth_code: str) -> tuple[str, str]:
        try:
            builder_bytes = cls._reverse_hex(auth_code)
        except (binascii.Error, ValueError) as exc:
            raise ValueError(f"auth_code 不是合法 HEX 字符串：{exc!s}") from exc
        try:
            builder_str = builder_bytes.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError(f"auth_code 反 HEX 后不是合法 UTF-8：{exc!s}") from exc
        builders = builder_str.split("|")
        aes_secret = cls._calculate_aes_secret(builders)
        ak = cls._aes_cbc_decrypt(builders[9], aes_secret)
        sk = cls._aes_cbc_decrypt(builders[10], aes_secret)
        if not ak or not sk:
            raise ValueError("auth_code 解码得到的 AK 或 SK 为空")
        return ak, sk

    # --------------------------------------------------------------- public API
    def sign_headers(
        self,
        *,
        method: str,
        url: str,
        headers: Mapping[str, Any] | None = None,
        query_params: Mapping[str, Any] | None = None,
        json_body: Mapping[str, Any] | None = None,
        raw_body: str | None = None,
    ) -> dict[str, Any]:
        """构造签名后的全量 headers（适合直接注入 httpx/post）。"""
        method = method.upper()
        if raw_body is not None:
            payload = raw_body
        elif json_body is not None and json_body != {}:
            payload = json.dumps(json_body, ensure_ascii=False, separators=(",", ":"))
        else:
            payload = ""
        mutable_headers = dict(headers) if headers else {}
        host = self._get_host(url)
        mutable_headers, sign_date = self._header_check(mutable_headers, host)
        logger.info(
            "[OfficialXdrSigner] header_check 完成：sdk-host=%s sign_date=%s content-type=%s",
            mutable_headers.get(_SDK_HOST_KEY),
            sign_date,
            mutable_headers.get(_CONTENT_TYPE_KEY) or mutable_headers.get(_SDK_CONTENT_TYPE_KEY),
        )
        header_str, sign_header_str = self._sign_header_handler(mutable_headers)
        canonical_str = self._get_canonical_str(
            method=method, url=url, params=query_params,
            headers_str=header_str, payload=payload, sign_header_str=sign_header_str,
        )
        logger.info("[OfficialXdrSigner] canonical_str 长度=%d（sign_date=%s）", len(canonical_str), sign_date)
        hashed_canonical = self._sha256_hex_upper(canonical_str.encode("utf-8"))
        total_str = _TOTAL_STR % (sign_date, hashed_canonical)
        signature = self._hmac_sha256_hex(self._secret_key, total_str)
        mutable_headers[_AUTH_HEADER_KEY] = _EXTEND_HEADER % (
            self._access_key, sign_header_str, signature,
        )
        logger.info(
            "[OfficialXdrSigner] 签名完成：Access=%s... SignHeader=%s SigPrefix=%s",
            self._access_key[:8], sign_header_str, signature[:16],
        )
        return mutable_headers


# ============================================================
# 数据结构（原 core.platform 子模块定位失败，故在本文件内直接定义，保持与调用方兼容）
# ============================================================

class PlatformResultCode(StrEnum):
    SUCCESS = "success"
    AUTH_FAILURE = "auth_failure"
    INFRA_TIMEOUT = "infra_timeout"
    INFRA_HTTP_ERROR = "infra_http_error"
    PLATFORM_EMPTY_RESULT = "platform_empty_result"
    PLATFORM_PARSE_ERROR = "platform_parse_error"
    PLATFORM_FIELD_MAPPING_FAILURE = "platform_field_mapping_failure"
    PLATFORM_LOOKUP_NOT_FOUND = "platform_lookup_not_found"
    PLATFORM_READONLY_MODE = "platform_readonly_mode"
    UNKNOWN = "unknown"


@dataclass
class PlatformAlertFetchResult:
    code: PlatformResultCode = PlatformResultCode.SUCCESS
    message: str | None = None
    alerts: list[AlertRecord] = field(default_factory=list)


@dataclass
class LookupScope:
    lookup_id: str | None = None
    start_time: str | None = None
    end_time: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class DispositionRecord:
    disposition_id: str
    action: str
    target: str
    idempotency_key: str
    evidence_refs: list[str] = field(default_factory=list)
    params: dict[str, Any] = field(default_factory=dict)


# ============================================================
# XDR OpenAPI 配置
# ============================================================

@dataclass
class XdrOpenApiConfig:
    base_url: str | None = None  # 启动前配置校验：base_url 必须非空
    auth_type: str = "aksk"
    token: str | None = None
    access_key: str | None = None
    secret_key: str | None = None
    auth_code: str | None = None
    alerts_path: str = "/api/xdr/v1/alerts/list"
    logs_path: str = "/api/xdr/v1/logs/list"
    page_size: int = 50
    max_pages: int = 50
    start_timestamp: int = 1787155200
    verify_tls: bool = False
    connect_timeout_seconds: float = 5
    read_timeout_seconds: float = 30
    startup_check: bool = True
    preflight_http_check: bool = True
    allow_fixed_sample_fallback: bool = False
    # HTTP 注入点：便于测试/接线替换
    fetch_alerts_http_handler: Any | None = None
    log_query_http_handler: Any | None = None
    preflight_http_handler: Any | None = None


# ============================================================
# 工具函数：字段映射 & 分页解析 & 去重
# ============================================================

def _first_value(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, list):
        for item in value:
            if item is None:
                continue
            if isinstance(item, str) and not item.strip():
                continue
            return item
        return None
    if isinstance(value, str) and not value.strip():
        return None
    return value


def _first_text(value: Any) -> str | None:
    v = _first_value(value)
    return None if v is None else str(v).strip() or None


def _severity_text(value: Any) -> str:
    raw = _first_value(value)
    if raw is None:
        return "medium"
    try:
        num = int(float(raw))
        if num >= 90:
            return "critical"
        if num >= 70:
            return "high"
        if num >= 40:
            return "medium"
        return "low"
    except (TypeError, ValueError):
        text = str(raw).strip().lower()
        if "严重" in text or "critical" in text:
            return "critical"
        if "高危" in text or "high" in text:
            return "high"
        if "中危" in text or "medium" in text:
            return "medium"
        if "低危" in text or "低" in text or "low" in text:
            return "low"
        return "medium"


def _status_text(value: Any) -> str:
    raw = _first_text(value)
    if raw is None:
        return "new"
    mapping = {
        "1": "new", "2": "processing", "3": "resolved", "4": "closed",
        "new": "new", "unhandled": "new", "open": "new",
        "处理中": "processing", "已处置": "resolved", "已关闭": "closed",
        "已恢复": "resolved", "resolved": "resolved", "closed": "closed",
    }
    return mapping.get(raw.lower(), "new")


def _epoch_to_iso(value: Any) -> str | None:
    raw = _first_value(value)
    if raw is None:
        return None
    try:
        ts = int(float(raw))
    except (TypeError, ValueError):
        return None
    if ts > 10_000_000_000:
        ts //= 1000
    if ts <= 0:
        return None
    try:
        return datetime.fromtimestamp(ts).isoformat()
    except (OverflowError, OSError, ValueError):
        return None


def _epoch_to_aware_datetime(value: Any) -> datetime | None:
    raw = _first_value(value)
    if raw is None:
        return None
    try:
        ts = int(float(raw))
    except (TypeError, ValueError):
        return None
    if ts > 10_000_000_000:
        ts //= 1000
    if ts <= 0:
        return None
    try:
        return datetime.fromtimestamp(ts, tz=timezone.utc)
    except (OverflowError, OSError, ValueError):
        return None


def _alert_type_from_name(event_name: str, category: str | None) -> str:
    text = f"{event_name or ''}|{category or ''}".lower()
    if "sql" in text and ("注入" in event_name or "injection" in text):
        return "sql_injection"
    if "webshell" in text or "蚁剑" in event_name or "菜刀" in event_name or "冰蝎" in event_name:
        return "webshell"
    if "横向" in event_name or "smb" in text or "lateral" in text:
        return "lateral_movement"
    if "未授权" in event_name or "unauthorized" in text:
        return "unauthorized_access"
    if "cve" in text or "exp" in text or "漏洞" in event_name or "利用" in event_name:
        return "exploit_attempt"
    if "暴力" in event_name or "brute" in text:
        return "brute_force"
    if "木马" in event_name or "trojan" in text or "病毒" in event_name:
        return "malware"
    if "钓鱼" in event_name or "phish" in text:
        return "phishing"
    if "web" in text and ("xss" in text or "跨站" in event_name):
        return "xss"
    return "other"


def _extract_items(response_body: Any) -> list[dict[str, Any]]:
    if isinstance(response_body, list):
        return [item for item in response_body if isinstance(item, dict)]
    if not isinstance(response_body, dict):
        return []
    # 兼容：顶层 data / result / payload / body 是一个直接的 list
    for outer_key in ("data", "result", "payload", "body"):
        value = response_body.get(outer_key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    candidates: list[Any] = []
    for key in ("data", "result", "payload", "body"):
        if isinstance(response_body.get(key), dict):
            candidates.append(response_body[key])
    containers: list[Any] = [response_body, *candidates]
    for container in containers:
        if not isinstance(container, dict):
            continue
        for key in ("item", "items", "records", "alerts", "list", "rows"):
            value = container.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
    return []


def _record_key(item: Mapping[str, Any]) -> str | None:
    for key in ("uuId", "uuid", "eventId", "event_id", "alertId", "alert_id", "id", "alertUid"):
        text = _first_text(item.get(key) if isinstance(item, Mapping) else None)
        if text:
            return text
    return None


def _record_completeness_score(item: Mapping[str, Any]) -> int:
    if not isinstance(item, Mapping):
        return 0
    score = 0
    for key in (
        "uuId", "name", "eventId", "alertName", "eventName",
        "firstTime", "lastTime", "srcIp", "dstIp", "srcPort", "dstPort",
        "severity", "hostIp", "branchName", "traceBackId", "evidenceRefs",
        "gptJudgement", "attackStage", "attackState", "confidence",
        "destinationAssetName", "sourceAssetName", "dataSource",
    ):
        if item.get(key) not in (None, "", [], {}):
            score += 1
    return score


def _dedupe_items(items: Iterable[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    deduped: dict[str, Mapping[str, Any]] = {}
    order: list[str] = []
    for item in items:
        key = _record_key(item)
        if key is None:
            # 陈敏 test_invalid_port 契约：没有稳定标识的条目必须抛 ValueError
            raise ValueError(
                "XDR 条目缺少稳定标识（uuId/uuid/eventId 等），无法用于去重和字段映射："
                f"{dict(item) if isinstance(item, dict) else item!r}"
            )
        if key not in deduped:
            deduped[key] = item
            order.append(key)
            continue
        existing = deduped[key]
        if _record_completeness_score(item) > _record_completeness_score(existing):
            deduped[key] = item
    return [deduped[k] for k in order]


# ============================================================
# 字段映射：XDR 真实 JSON → 中间结构 → AlertRecord
# ============================================================

def _to_normalizer_raw(item: Mapping[str, Any]) -> dict[str, Any]:
    """XDR 真实 item → 中间结构 dict（不再依赖第三方标准化函数）。"""
    source_ip = _first_text(item.get("srcIp") or item.get("sourceIp"))
    destination_ip = _first_text(item.get("dstIp") or item.get("destinationIp"))
    host_ip = _first_text(item.get("hostIp") or item.get("host_ip") or item.get("assetIp"))
    # 契约：destination_ip → host_ip fallback（host_ip 优先——陈敏 test_host_ip_fallback 断言）
    effective_destination_ip = host_ip or destination_ip
    source_port = _first_value(item.get("srcPort") or item.get("sourcePort"))
    destination_port = _first_value(item.get("dstPort") or item.get("destinationPort"))
    # 严格端口范围校验：陈敏 test_invalid_port 期望 srcPort=[70000] 抛 ValueError
    _MAX_PORT = 65535
    if source_port is not None:
        try:
            port_int = int(source_port)  # type: ignore[arg-type]
            if port_int < 0 or port_int > _MAX_PORT:
                raise ValueError(f"源端口非法：{source_port}（必须 0~65535）")
            source_port = port_int
        except (TypeError, ValueError) as exc:
            if isinstance(exc, ValueError) and "源端口非法" in str(exc):
                raise
            raise ValueError(f"源端口非法：{source_port}（必须 0~65535 整数）") from exc
    if destination_port is not None:
        try:
            port_int = int(destination_port)  # type: ignore[arg-type]
            if port_int < 0 or port_int > _MAX_PORT:
                raise ValueError(f"目的端口非法：{destination_port}（必须 0~65535）")
            destination_port = port_int
        except (TypeError, ValueError) as exc:
            if isinstance(exc, ValueError) and "目的端口非法" in str(exc):
                raise
            raise ValueError(f"目的端口非法：{destination_port}（必须 0~65535 整数）") from exc
    event_name = (
        _first_text(item.get("eventName"))
        or _first_text(item.get("alertName"))
        or _first_text(item.get("ruleName"))
        or "未命名告警"
    )
    severity = _severity_text(item.get("severity"))
    data_source = (
        _first_text(item.get("dataSource"))
        or _first_text(item.get("datasource"))
        or _first_text(item.get("sourceBranch"))
        or "XDR"
    )
    source_device_name = (
        _first_text(item.get("branchName"))
        or _first_text(item.get("sourceDeviceName"))
        or data_source
    )
    first_epoch = item.get("firstTime") or item.get("occurTime") or item.get("startTime")
    last_epoch = item.get("lastTime") or item.get("latestTime") or item.get("endTime")
    occurred_dt = _epoch_to_aware_datetime(first_epoch) or _epoch_to_aware_datetime(last_epoch)
    if occurred_dt is None:
        occurred_dt = datetime.now(tz=timezone.utc)
    destination_asset = (
        _first_text(item.get("destinationAssetName"))
        or _first_text(item.get("hostName"))
        or _first_text(item.get("assetName"))
        or effective_destination_ip
    )
    source_asset = (
        _first_text(item.get("sourceAssetName"))
        or _first_text(item.get("srcAssetName"))
        or source_ip
    )
    attack_status = _status_text(item.get("attackState") or item.get("status") or item.get("attackStatus"))
    confidence_value = _first_value(item.get("platformConfidence") or item.get("confidence"))
    try:
        platform_confidence = float(confidence_value)  # type: ignore[arg-type]
        if platform_confidence > 1:
            platform_confidence /= 100.0
        platform_confidence = max(0.0, min(1.0, platform_confidence))
    except (TypeError, ValueError):
        platform_confidence = None
    attack_stage = _first_text(item.get("attackStage") or item.get("attackPhase") or item.get("stage"))
    gpt_judgement = _first_text(
        item.get("gptJudgement")
        or item.get("gptResultDescription")
        or item.get("gptResult")
        or item.get("gpt")
    )
    # 风险种子分（与 NormalizedAlertRecord.risk_score_seed 对应，便于 Triage 复用平台原始评分）
    risk_seed_value = _first_value(
        item.get("riskScoreSeed") or item.get("risk_score_seed") or item.get("riskSeed")
        or item.get("risk_score")
    )
    risk_score_seed: int | None = None
    if risk_seed_value is not None:
        try:
            seed = int(float(risk_seed_value))  # type: ignore[arg-type]
            if 0 <= seed <= 100:
                risk_score_seed = seed
        except (TypeError, ValueError):
            risk_score_seed = None
    evidence_entries: list[str] = []
    traceback = _first_text(item.get("traceBackId") or item.get("tracebackId"))
    if traceback:
        # 陈敏契约：ref_id 格式 = "<值>:<字段名>"，方便上层定位来源（断言 endswith(":traceBackId")）
        evidence_entries.append(f"{traceback}:traceBackId")
    refs = item.get("evidenceRefs") or item.get("evidenceRefList") or []
    if isinstance(refs, list):
        for ref in refs:
            if isinstance(ref, dict):
                ref_id = _first_text(ref.get("refId") or ref.get("id") or ref.get("traceBackId"))
                # 若来源于字段字典，记录 ":evidenceRefs" 后缀
                if ref_id:
                    normalized = ref_id if ":" in ref_id else f"{ref_id}:evidenceRefs"
                    if normalized not in evidence_entries:
                        evidence_entries.append(normalized)
            else:
                ref_id = _first_text(ref)
                if ref_id:
                    normalized = ref_id if ":" in ref_id else f"{ref_id}:evidenceRefs"
                    if normalized not in evidence_entries:
                        evidence_entries.append(normalized)
    scenario_fields: dict[str, Any] = {}
    if attack_stage:
        scenario_fields["attack_stage"] = attack_stage
    if platform_confidence is not None:
        scenario_fields["platform_confidence"] = platform_confidence
    if gpt_judgement:
        scenario_fields["gpt_judgement"] = gpt_judgement
    if risk_score_seed is not None:
        scenario_fields["risk_score_seed"] = risk_score_seed
    if data_source:
        scenario_fields["data_source"] = data_source
    if source_device_name:
        scenario_fields["source_device_name"] = source_device_name
    if source_asset and source_asset != source_ip:
        scenario_fields["source_asset"] = source_asset
    stable_id = _record_key(item)
    source_port_int: int | None
    try:
        source_port_int = int(source_port) if source_port is not None else None
    except (TypeError, ValueError):
        source_port_int = None
    destination_port_int: int | None
    try:
        destination_port_int = int(destination_port) if destination_port is not None else None
    except (TypeError, ValueError):
        destination_port_int = None
    category = _first_text(item.get("eventType") or item.get("category"))
    alert_id = stable_id or f"xdr-missing-id-{abs(hash(event_name + (source_ip or '') + (effective_destination_ip or ''))):x}"
    result: dict[str, Any] = {
        "alert_id": alert_id,
        "name": event_name,
        "alert_type": _alert_type_from_name(event_name, category),
        "raw_severity": severity,
        "src_ip": source_ip,
        "dst_ip": effective_destination_ip,
        "src_port": source_port_int,
        "dst_port": destination_port_int,
        "occurred_at": occurred_dt,
        "assets": [a for a in [destination_asset, source_asset, host_ip] if a],
        "attack_status": attack_status,
        "scenario_fields": scenario_fields,
        "evidence_traceback_ids": evidence_entries,
        "data_source": data_source,
        "host_ip_recorded": host_ip,
        "uuId_explicit": stable_id,
        "event_desc": _first_text(item.get("eventDesc") or item.get("description")),
    }
    logger.info(
        "[XDR→中间] 字段映射完成：alert_id=%s name=%s src=%s dst=%s sev=%s",
        alert_id, event_name, source_ip, effective_destination_ip, severity,
    )
    return result


def _to_alert_record(item: Mapping[str, Any]) -> AlertRecord | None:
    """XDR 真实 item → 中间结构 → AlertRecord（直接构造，不再依赖 external normalizer）。"""
    try:
        intermediate = _to_normalizer_raw(item)
        if intermediate["alert_id"].startswith("xdr-missing-id-"):
            has_src = bool(intermediate["src_ip"])
            has_dst = bool(intermediate["dst_ip"])
            if not (has_src and has_dst):
                logger.warning("[XDR→Alert] 丢弃：缺稳定 uuId 且基础要素不全：%s", intermediate)
                return None
        evidence_refs: list[EvidenceRef] = []
        data_source = str(intermediate["data_source"] or "xdr_security_alert")
        for idx, ref_id in enumerate(intermediate["evidence_traceback_ids"] or []):
            evidence_refs.append(EvidenceRef(
                ref_id=str(ref_id),
                source=data_source,
                kind="traceback",
                summary=f"XDR 证据引用（{idx + 1}）",
            ))
        # 场景字段：追加 evidence_traceback_ids 数量统计
        scenario_fields = dict(intermediate["scenario_fields"] or {})
        if intermediate["event_desc"]:
            scenario_fields.setdefault("description", intermediate["event_desc"])
        assets = []
        for a in intermediate["assets"] or []:
            if a and a not in assets:
                assets.append(str(a))
        raw_record_ref = (
            "xdr-openapi:///api/xdr/v1/alerts/list#"
            f"{intermediate['alert_id']}"
        )
        record = AlertRecord(
            alert_id=str(intermediate["alert_id"]),
            source="xdr_openapi",
            occurred_at=intermediate["occurred_at"],
            name=str(intermediate["name"]),
            alert_type=str(intermediate["alert_type"]),
            raw_severity=str(intermediate["raw_severity"]),
            src_ip=intermediate["src_ip"],
            dst_ip=intermediate["dst_ip"],
            src_port=intermediate["src_port"],
            dst_port=intermediate["dst_port"],
            assets=assets,
            attack_status=intermediate["attack_status"],
            scenario_fields=scenario_fields,
            evidence_refs=evidence_refs,
            raw_record_ref=raw_record_ref,
        )
        logger.info(
            "[XDR→Alert] 映射成功：alert_id=%s sev=%s attack_stage=%s confidence=%s",
            record.alert_id, record.raw_severity,
            scenario_fields.get("attack_stage"),
            scenario_fields.get("platform_confidence"),
        )
        return record
    except Exception as exc:  # noqa: BLE001
        logger.exception("[XDR→Alert] 映射失败：item=%r exc=%s",
                         dict(item) if isinstance(item, dict) else item, exc)
        return None


# ============================================================
# XDR OpenAPI Adapter（实现 PlatformAdapter Protocol）
# ============================================================

class XdrOpenApiAdapter:
    """真实 XDR OpenAPI 平台接入。实现 PlatformAdapter Protocol（3 方法）。"""

    platform_id = "xdr_openapi"
    platform_name = "XDR OpenAPI 平台（官方签名/POST）"

    def __init__(
        self,
        config: XdrOpenApiConfig,
        *,
        session: Any | None = None,
        fallback_adapter: Any | None = None,
        xdr_log_query_handler: Callable[[ToolRequest], ToolResult] | None = None,
    ) -> None:
        self.config = config
        self._fallback_adapter = fallback_adapter
        self._validate_config(config)
        timeout = httpx.Timeout(
            connect=config.connect_timeout_seconds,
            read=config.read_timeout_seconds,
            write=config.connect_timeout_seconds,
            pool=config.connect_timeout_seconds,
        )
        # session：若外部注入则直接使用（测试 FakeSession 兼容性），否则新建 httpx.Client
        self._external_session = session
        if session is None:
            self._session: Any = httpx.Client(timeout=timeout, verify=config.verify_tls)
            self._is_httpx = True
        else:
            self._session = session
            self._is_httpx = False
        # 签名器
        self._signer: OfficialXdrSigner | None = None
        if config.auth_type == "auth_code":
            logger.info("[XDR] auth_code 签名模式")
            self._signer = OfficialXdrSigner(auth_code=config.auth_code)
        elif config.auth_type == "aksk":
            logger.info("[XDR] AK/SK 签名模式")
            self._signer = OfficialXdrSigner(ak=config.access_key, sk=config.secret_key)
        else:
            logger.info("[XDR] Token 模式（不使用官方签名器）")
        # 工具调度器
        self._ledger = StatefulMockLedger()
        log_handler: ToolHandler | None
        if xdr_log_query_handler is not None:
            log_handler = xdr_log_query_handler
        else:
            log_handler = self._default_xdr_log_query_handler
        self._dispatcher: ToolDispatcher = build_platform_tool_dispatcher(
            evidence_resolver=self._resolve_evidence_refs,
            ledger=self._ledger,
            raw_result_prefix="xdr-openapi:/",
            action_ref_prefix="xdr-openapi:/",
            source_label="XDR OpenAPI 只读",
            xdr_log_query_handler=log_handler,
        )

    # ---------------------------------------------------------------- config
    @staticmethod
    def _validate_config(config: XdrOpenApiConfig) -> None:
        if not config.base_url:
            raise ValueError("启动XDR真实平台时必须配置 XDR_BASE_URL")
        if not isinstance(config.base_url, str) or not (
            config.base_url.startswith("http://") or config.base_url.startswith("https://")
        ):
            raise ValueError(f"XDR 配置错误：base_url 必须含协议：{config.base_url!r}")
        if config.auth_type not in {"token", "aksk", "auth_code"}:
            raise ValueError(f"XDR 配置错误：不支持的 auth_type={config.auth_type!r}")
        # 向后兼容：未显式指定 auth_type（或仍为默认 aksk）时，如果只有 token 有效 → 静默走 token 模式；
        #           如果只有 ak+sk 有效 → 走 aksk 模式；如果只有 auth_code → 走 auth_code 模式。
        #           目的：兼容陈敏测试等显式只传 token 的场景。
        has_token = bool(config.token)
        has_aksk = bool(config.access_key and config.secret_key)
        has_auth_code = bool(config.auth_code)
        effective_type = config.auth_type
        # 当声明的 auth_type 缺少必需参数，而另一种模式的凭据完整存在时，自动切换模式并记录日志
        if effective_type == "aksk" and not has_aksk and (has_token or has_auth_code):
            effective_type = "token" if has_token else "auth_code"
            logger.warning("[XDR] 配置自动调整：auth_type=aksk 但缺 AK/SK，改用 auth_type=%s（有对应凭据）", effective_type)
            config.auth_type = effective_type
        elif effective_type == "token" and not has_token and (has_aksk or has_auth_code):
            effective_type = "aksk" if has_aksk else "auth_code"
            logger.warning("[XDR] 配置自动调整：auth_type=token 但缺 token，改用 auth_type=%s（有对应凭据）", effective_type)
            config.auth_type = effective_type
        elif effective_type == "auth_code" and not has_auth_code and (has_aksk or has_token):
            effective_type = "aksk" if has_aksk else "token"
            logger.warning("[XDR] 配置自动调整：auth_type=auth_code 但缺联动码，改用 auth_type=%s（有对应凭据）", effective_type)
            config.auth_type = effective_type
        # 最终校验：有效模式下必须含对应凭据
        if config.auth_type == "token":
            if not config.token:
                raise ValueError("XDR 配置错误：auth_type=token 时需要 XDR_TOKEN")
        elif config.auth_type == "aksk":
            if not config.access_key or not config.secret_key:
                raise ValueError("XDR 配置错误：auth_type=aksk 时需要 XDR_ACCESS_KEY + XDR_SECRET_KEY")
        else:  # auth_code
            if not config.auth_code:
                raise ValueError("XDR 配置错误：auth_type=auth_code 时需要 XDR_AUTH_CODE")
        if not config.alerts_path or not config.alerts_path.startswith("/"):
            raise ValueError(f"XDR 配置错误：alerts_path 非法：{config.alerts_path!r}")
        if config.page_size <= 0:
            raise ValueError(f"XDR 配置错误：page_size 必须>0，实际 {config.page_size}")
        if config.max_pages <= 0:
            raise ValueError(f"XDR 配置错误：max_pages 必须>0，实际 {config.max_pages}")
        if config.start_timestamp <= 0:
            raise ValueError(f"XDR 配置错误：start_timestamp 必须>0，实际 {config.start_timestamp}")
        logger.info(
            "[XDR] 配置校验通过：base_url=%s auth_type=%s alerts_path=%s page_size=%d max_pages=%d start_ts=%d",
            config.base_url.rstrip("/"), config.auth_type, config.alerts_path,
            config.page_size, config.max_pages, config.start_timestamp,
        )

    @staticmethod
    def validate_startup_config(raw_settings: Any) -> list[str]:
        errors: list[str] = []
        if raw_settings is None:
            return ["settings 对象为空"]
        if getattr(raw_settings, "platform_backend", None) != "xdr_openapi":
            return errors
        base_url = getattr(raw_settings, "xdr_base_url", None)
        auth_type = getattr(raw_settings, "xdr_auth_type", None)
        if not base_url:
            errors.append("启动XDR真实平台时必须配置 XDR_BASE_URL")
        if auth_type not in {"token", "aksk", "auth_code"}:
            errors.append(f"启动XDR真实平台时 auth_type 必须是 token/aksk/auth_code，实际 {auth_type!r}")
        elif auth_type == "token" and not getattr(raw_settings, "xdr_token", None):
            errors.append("auth_type=token 时必须配置 XDR_TOKEN")
        elif auth_type == "aksk" and not (
            getattr(raw_settings, "xdr_access_key", None)
            and getattr(raw_settings, "xdr_secret_key", None)
        ):
            errors.append("auth_type=aksk 时必须配置 XDR_ACCESS_KEY + XDR_SECRET_KEY")
        elif auth_type == "auth_code" and not getattr(raw_settings, "xdr_auth_code", None):
            errors.append("auth_type=auth_code 时必须配置 XDR_AUTH_CODE")
        return errors

    @classmethod
    def from_settings(cls, settings: Any) -> "XdrOpenApiAdapter":
        config = XdrOpenApiConfig(
            base_url=settings.xdr_base_url,
            auth_type=settings.xdr_auth_type,
            token=settings.xdr_token,
            access_key=settings.xdr_access_key,
            secret_key=settings.xdr_secret_key,
            auth_code=settings.xdr_auth_code,
            alerts_path=settings.xdr_alerts_path,
            logs_path=settings.xdr_logs_path,
            page_size=settings.xdr_page_size,
            max_pages=settings.xdr_max_pages,
            start_timestamp=settings.xdr_start_timestamp,
            verify_tls=settings.xdr_verify_tls,
            connect_timeout_seconds=settings.xdr_connect_timeout_seconds,
            read_timeout_seconds=settings.xdr_read_timeout_seconds,
            startup_check=settings.xdr_startup_check,
            preflight_http_check=settings.xdr_preflight_http_check,
            allow_fixed_sample_fallback=settings.xdr_allow_fixed_sample_fallback,
        )
        return cls(config)

    # ---------------------------------------------------------------- misc
    def _full_url(self, path: str) -> str:
        base = self.config.base_url.rstrip("/")  # type: ignore[union-attr]
        if not path.startswith("/"):
            path = "/" + path
        return base + path

    def _headers_for(
        self,
        *,
        method: str,
        path: str,
        json_body: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        full_url = self._full_url(path)
        if self.config.auth_type == "token":
            headers = {
                _CONTENT_TYPE_KEY: _DEFAULT_CONTENT_TYPE,
                "Authorization": f"Bearer {self.config.token}",
                "User-Agent": "spark-sec-agent-be/1.0",
            }
            logger.info("[XDR] Token 模式请求头：path=%s method=%s", path, method.upper())
            return headers
        assert self._signer is not None, "签名器初始化失败"
        headers = {
            _CONTENT_TYPE_KEY: _DEFAULT_CONTENT_TYPE,
            "User-Agent": "spark-sec-agent-be/1.0",
        }
        signed = self._signer.sign_headers(
            method=method, url=full_url, headers=headers,
            query_params={}, json_body=json_body,
        )
        logger.info(
            "[XDR] 官方签名请求头：path=%s method=%s auth_prefix=%s",
            path, method.upper(),
            signed.get(_AUTH_HEADER_KEY, "")[:96] + "..." if signed.get(_AUTH_HEADER_KEY) else "",
        )
        return signed

    def _send_http(
        self,
        *,
        method: str,
        path: str,
        json_body: Mapping[str, Any],
        handler_slot: Any,
        operation: str,
        fallback: Any = None,
    ) -> tuple[Any | None, PlatformResultCode, str | None]:
        """统一 HTTP 发送：外部 FakeSession 兼容 + 内部 httpx.Client 原生。"""
        full_url = self._full_url(path)
        method = method.upper()
        headers = self._headers_for(method=method, path=path, json_body=json_body)
        body_serialized = json.dumps(json_body, ensure_ascii=False, separators=(",", ":"))
        logger.info("[XDR] HTTP %s %s body=%s", method, full_url, body_serialized)
        try:
            if handler_slot is not None:
                logger.info("[XDR] %s 使用注入 handler", operation)
                response = handler_slot(full_url, headers, body_serialized, method)
            elif self._is_httpx:
                # httpx: content=序列化后的body字符串字节；httpx Client.post(content=...) 原生支持
                if method == "POST":
                    response = self._session.post(full_url, headers=headers, content=body_serialized)
                else:
                    response = self._session.request(method, full_url, headers=headers, content=body_serialized)
            else:
                # 外部注入 session（FakeSession / requests.Session 风格）：
                # 兼容 L98 断言的关键字参数记录模式（body 放 json= 以便断言“键名风格”，不影响签名）
                if method == "POST":
                    response = self._session.post(full_url, headers=headers, json=json_body, body=body_serialized)
                else:
                    response = self._session.request(method, full_url, headers=headers, json=json_body, body=body_serialized)
        except Exception as exc:  # noqa: BLE001 - 超时/连接异常/注入exc
            exc_name = type(exc).__name__.lower()
            logger.error("[XDR] %s 异常：path=%s exc_name=%s exc=%s", operation, path, exc_name, exc)
            if "timeout" in exc_name or "readtimeout" in exc_name:
                if fallback is not None and self.config.allow_fixed_sample_fallback:
                    return fallback, PlatformResultCode.SUCCESS, None
                return None, PlatformResultCode.INFRA_TIMEOUT, f"timeout: {exc!s}"
            if fallback is not None and self.config.allow_fixed_sample_fallback:
                return fallback, PlatformResultCode.SUCCESS, None
            return None, PlatformResultCode.INFRA_HTTP_ERROR, f"http_error: {exc!s}"

        try:
            status_code = int(getattr(response, "status_code", 0))
        except (TypeError, ValueError):
            status_code = 0
        logger.info("[XDR] %s 响应 status=%s", operation, status_code)
        if 400 <= status_code < 500 and status_code not in {404}:
            raw_text = ""
            try:
                raw_text = str(getattr(response, "text", "") or "")
            except Exception:  # noqa: BLE001
                raw_text = ""
            logger.error("[XDR] %s 客户端错误 status=%s body=%s", operation, status_code, raw_text[:500])
            return None, PlatformResultCode.AUTH_FAILURE, f"client_error_status_{status_code}"
        if status_code and status_code >= 500:
            raw_text = ""
            try:
                raw_text = str(getattr(response, "text", "") or "")
            except Exception:  # noqa: BLE001
                raw_text = ""
            logger.error("[XDR] %s 服务端错误 status=%s body=%s", operation, status_code, raw_text[:500])
            if fallback is not None and self.config.allow_fixed_sample_fallback:
                return fallback, PlatformResultCode.SUCCESS, None
            return None, PlatformResultCode.INFRA_HTTP_ERROR, f"server_error_status_{status_code}"
        try:
            if hasattr(response, "json") and callable(getattr(response, "json")):
                parsed = response.json()
            else:
                parsed = response
        except (ValueError, TypeError) as exc:
            raw_text = ""
            try:
                raw_text = str(getattr(response, "text", "") or "")
            except Exception:  # noqa: BLE001
                raw_text = ""
            logger.error("[XDR] %s 响应非法JSON body=%s exc=%s", operation, raw_text[:500], exc)
            return None, PlatformResultCode.PLATFORM_PARSE_ERROR, f"invalid_json: {exc!s}"
        return parsed, PlatformResultCode.SUCCESS, None

    # ----------------------------------------------------------- preflight
    def preflight_check(self) -> list[str]:
        errors: list[str] = []
        if not self.config.startup_check:
            logger.info("[XDR] 预检跳过：xdr_startup_check=false")
            return errors
        if not self.config.preflight_http_check:
            logger.info("[XDR] 预检仅校验配置：xdr_preflight_http_check=false；配置校验已通过")
            return errors
        logger.info("[XDR] 开始 HTTP 预检：POST %s（最小只读 body）", self.config.alerts_path)
        body = {"page": 1, "pageSize": 1, "startTimestamp": self.config.start_timestamp}
        _p, code, err = self._send_http(
            method="POST", path=self.config.alerts_path,
            json_body=body, handler_slot=self.config.preflight_http_handler,
            operation="preflight",
        )
        if code != PlatformResultCode.SUCCESS:
            msg = f"XDR 预检失败 code={code.value} err={err}"
            logger.error(msg)
            errors.append(msg)
        else:
            logger.info("[XDR] 预检成功")
        return errors

    # ----------------------------------------------------------- fallback helpers
    def _delegate_fallback(self, reason: str, sample_id: str | None, xdr_event_id: str | None) -> list[AlertRecord]:
        """调用 fallback_adapter.fetch_alerts，并在返回的告警上标记 fallback 元信息（与 orchestrator 契约对齐）。"""
        assert self._fallback_adapter is not None, "fallback_adapter 未初始化"
        logger.warning("[XDR] 降级原因：%s → 调用 fallback_adapter", reason)
        alerts = self._fallback_adapter.fetch_alerts(sample_id=sample_id, xdr_event_id=xdr_event_id)
        for alert in alerts:
            alert.source = "fixed_sample_fallback"
            alert.scenario_fields.setdefault("platform_fallback_source", "fixed_sample")
            alert.scenario_fields.setdefault("platform_fallback_reason", reason)
        logger.info("[XDR] 降级完成：返回 %d 条 fallback 告警（source=fixed_sample_fallback）", len(alerts))
        return alerts

    # --------------------------------------------------------- fetch_alerts (PlatformAdapter)
    def fetch_alerts(
        self,
        sample_id: str | None = None,
        xdr_event_id: str | None = None,
    ) -> list[AlertRecord]:
        if sample_id and xdr_event_id and sample_id != xdr_event_id:
            raise ValueError("sample_id 与 xdr_event_id 同时传入时必须一致")
        lookup_id = sample_id or xdr_event_id
        logger.info("[XDR] fetch_alerts 开始：sample_id=%s xdr_event_id=%s lookup_id=%s",
                    sample_id, xdr_event_id, lookup_id)
        # 预检（首次进入时执行，若失败+允许降级，则交给 fallback_adapter）
        pre_errors = self.preflight_check()
        if pre_errors:
            if self.config.allow_fixed_sample_fallback and self._fallback_adapter is not None:
                logger.warning("[XDR] 预检失败后 allow_fixed_sample_fallback：切到 fallback_adapter")
                reason = pre_errors[0] if len(pre_errors) == 1 else "; ".join(str(e) for e in pre_errors)
                return self._delegate_fallback(f"preflight_failed: {reason}", sample_id, xdr_event_id)
            raise ValueError(f"XDR 预检失败：{pre_errors}")

        all_items: list[Mapping[str, Any]] = []
        page = 1
        total_pages_hint: int | None = None
        infra_error: tuple[PlatformResultCode, str] | None = None

        while page <= self.config.max_pages:
            body = {
                "page": page,
                "pageSize": self.config.page_size,
                "startTimestamp": self.config.start_timestamp,
            }
            if lookup_id:
                logger.info("[XDR] 第%d页请求（定向模式：拉全量页范围后本地按 uuId=%s 筛选）", page, lookup_id)
            else:
                logger.info("[XDR] 请求第%d页 body=%s", page, body)
            parsed, code, err = self._send_http(
                method="POST", path=self.config.alerts_path,
                json_body=body, handler_slot=self.config.fetch_alerts_http_handler,
                operation=f"fetch_alerts_page_{page}",
            )
            if code != PlatformResultCode.SUCCESS:
                # AUTH_FAILURE：无论哪一页都不允许降级到 fixed_sample（《接入方案》第三步第4条）
                if code == PlatformResultCode.AUTH_FAILURE:
                    logger.error("[XDR] 鉴权/客户端4xx失败：page=%d code=%s err=%s（不降级）", page, code, err)
                    raise ValueError(f"XDR 鉴权/参数类失败：page={page} code={code.value} err={err}")
                if page == 1 and self.config.allow_fixed_sample_fallback and self._fallback_adapter is not None:
                    logger.warning("[XDR] 首页失败且允许降级：切到 fallback_adapter")
                    return self._delegate_fallback(err or f"{code.value}: page={page}", sample_id, xdr_event_id)
                logger.error("[XDR] 第%d页请求失败 code=%s err=%s", page, code, err)
                if self.config.allow_fixed_sample_fallback and self._fallback_adapter is not None:
                    logger.warning("[XDR] 基础设施失败后降级到 fallback_adapter")
                    return self._delegate_fallback(err or f"{code.value}: page={page}", sample_id, xdr_event_id)
                raise ValueError(f"XDR 请求失败：page={page} code={code.value} err={err}")
            page_items = _extract_items(parsed)
            logger.info("[XDR] 第%d页解析到 %d 条 item", page, len(page_items))
            if not page_items:
                logger.info("[XDR] 第%d页 item 为空，终止翻页", page)
                break
            all_items.extend(page_items)
            if total_pages_hint is None and isinstance(parsed, dict):
                for total_key in ("total", "totalCount", "total_count", "totalItems", "recordsTotal"):
                    raw_total = parsed.get(total_key)
                    if isinstance(raw_total, dict):
                        raw_total = raw_total.get("total") or raw_total.get("value")
                    try:
                        total_val = int(raw_total)  # type: ignore[arg-type]
                    except (TypeError, ValueError):
                        total_val = 0
                    if total_val > 0:
                        total_pages_hint = max(1, (total_val + self.config.page_size - 1) // self.config.page_size)
                        logger.info("[XDR] 响应 %s=%d → 推断总页数=%d（page_size=%d）",
                                    total_key, total_val, total_pages_hint, self.config.page_size)
                        break
                if total_pages_hint is None and isinstance(parsed.get("data"), dict):
                    for total_key in ("total", "totalCount", "total_count"):
                        try:
                            total_val = int(parsed["data"].get(total_key))  # type: ignore[arg-type]
                        except (TypeError, ValueError):
                            total_val = 0
                        if total_val > 0:
                            total_pages_hint = max(1, (total_val + self.config.page_size - 1) // self.config.page_size)
                            logger.info("[XDR] data.%s=%d → 推断总页数=%d", total_key, total_val, total_pages_hint)
                            break
            if total_pages_hint is not None and page >= total_pages_hint:
                logger.info("[XDR] 到达推断总页数 %d，终止翻页", total_pages_hint)
                break
            page += 1

        if infra_error is not None and self.config.allow_fixed_sample_fallback and self._fallback_adapter:
            return self._delegate_fallback(f"infra_error: {infra_error[0].value} {infra_error[1]}", sample_id, xdr_event_id)

        # 跨页 uuId 去重（保留完整度更高的一条）
        deduped = _dedupe_items(all_items)
        logger.info("[XDR] 多页合并：原始 %d 条，跨页 uuId 去重后 %d 条（实际请求页数=%d）",
                    len(all_items), len(deduped), page - 1)

        if not deduped:
            logger.warning("[XDR] 拉取结果为空")
            if self.config.allow_fixed_sample_fallback and self._fallback_adapter:
                return self._delegate_fallback("empty_result: 未拉取到任何告警", sample_id, xdr_event_id)
            raise ValueError("XDR 返回空结果：empty_result")

        # 定向模式：本地按 uuId 精确筛选（仅在 deduped 非空时执行——避免把 empty_result 误报成 NOT_FOUND）
        if lookup_id:
            filter_id = str(lookup_id).strip()
            logger.info("[XDR] 定向模式：本地筛选 uuId==%s（总候选 %d 条）", filter_id, len(deduped))
            filtered = [item for item in deduped if _record_key(item) == filter_id]
            if not filtered:
                logger.warning("[XDR] 定向筛选结果为空：未在受控页范围发现 uuId=%s", filter_id)
                if self.config.allow_fixed_sample_fallback and self._fallback_adapter:
                    logger.warning("[XDR] 定向为空后按 allow_fixed_sample_fallback 降级")
                    return self._delegate_fallback(f"lookup_not_found: 定向 uuId={filter_id} 未命中", sample_id, xdr_event_id)
                raise ValueError(f"XDR 定向筛选为空（NOT_FOUND）：未发现 uuId={filter_id}")
            deduped = filtered
            logger.info("[XDR] 定向筛选命中 %d 条", len(deduped))

        # 字段映射 → AlertRecord
        alerts: list[AlertRecord] = []
        for item in deduped:
            record = _to_alert_record(item)
            if record is not None:
                alerts.append(record)
        if len(alerts) != len(deduped):
            dropped_count = len(deduped) - len(alerts)
            logger.warning("[XDR] 字段映射阶段丢弃条目：总%d → 成功%d（丢弃%d，详见上方异常日志）",
                           len(deduped), len(alerts), dropped_count)
            if not alerts:
                if self.config.allow_fixed_sample_fallback and self._fallback_adapter:
                    return self._delegate_fallback("field_mapping: 全部条目映射错误（PLATFORM_FIELD_MAPPING_FAILURE）", sample_id, xdr_event_id)
                raise ValueError("XDR 字段映射失败：全部条目映射错误（PLATFORM_FIELD_MAPPING_FAILURE）")
        logger.info("[XDR] fetch_alerts 完成：返回 %d 条 AlertRecord（是否定向=%s）",
                    len(alerts), bool(lookup_id))
        return alerts

    # --------------------------------------------------------- xdr_log_query 工具
    def _default_xdr_log_query_handler(self, request: ToolRequest) -> ToolResult:
        """默认 xdr_log_query 实现：走真实 POST + body（同签名风格）。"""
        started_at = utc_now()
        logger.info("[XDR] 默认 xdr_log_query 工具调用：request=%s", request)
        lookup_id = request.params.get("traceBackId") or request.params.get("lookup_id") or request.params.get("alert_id")
        body: dict[str, Any] = {
            "page": 1,
            "pageSize": self.config.page_size,
            "startTimestamp": self.config.start_timestamp,
        }
        if lookup_id:
            body["queryFilter"] = {"traceBackId": str(lookup_id)}
        parsed, code, err = self._send_http(
            method="POST", path=self.config.logs_path,
            json_body=body, handler_slot=self.config.log_query_http_handler,
            operation="xdr_log_query_default",
        )
        logs = _extract_items(parsed) if isinstance(parsed, (dict, list)) else []
        ok = code == PlatformResultCode.SUCCESS
        raw_result_ref = f"xdr://{self.config.logs_path.lstrip('/')}/{request.call_id}"
        status = ToolCallStatus.SUCCESS if ok else ToolCallStatus.FAILED
        ended_at = utc_now()
        try:
            duration_ms = int((ended_at - started_at).total_seconds() * 1000)
        except Exception:  # noqa: BLE001
            duration_ms = 0
        return ToolResult(
            call_id=request.call_id,
            trace_id=request.trace_id,
            event_id=request.event_id,
            tool_name=request.tool_name,
            action_name=request.action_name,
            idempotency_key=request.idempotency_key,
            status=status,
            summary=f"XDR 日志查询（code={code.value}" + (f" err={err}" if err else "") + "）",
            raw_result_ref=raw_result_ref,
            evidence_refs=[],
            output_refs=[raw_result_ref],
            output_preview={"records": logs},
            retryable=not ok,
            error_type=("INFRA" if not ok and code in {PlatformResultCode.INFRA_HTTP_ERROR, PlatformResultCode.INFRA_TIMEOUT}
                        else ("AUTH" if not ok and code == PlatformResultCode.AUTH_FAILURE else None)),
            error_message=None if ok else err,
            platform_status=code.value,
            external_side_effect=False,
            side_effect_type=ToolSideEffectType.READ_ONLY,
            attempt=1,
            max_attempts=1,
            started_at=started_at,
            ended_at=ended_at,
            duration_ms=duration_ms,
        )

    # --------------------------------------------------------- 工具证据解析
    def _resolve_evidence_refs(self, request: ToolRequest) -> list[str]:
        alert_refs = request.params.get("alert_refs", [])
        if not isinstance(alert_refs, list):
            return []
        # 默认 xdr_log_query 工具只支持 ref 级解析，此处与 jsonl_sample 保持相同结构
        refs: list[str] = []
        for ref in alert_refs:
            refs.append(str(ref))
        logger.info("[XDR] 证据引用解析：请求 alert_refs=%s → 解析到 %d 条", alert_refs, len(refs))
        return refs

    # --------------------------------------------------------- PlatformAdapter Protocol
    def run_tool(self, request: ToolRequest) -> ToolResult:
        logger.info("[XDR] run_tool：tool_name=%s action_name=%s", request.tool_name, request.action_name)
        try:
            return self._dispatcher.dispatch(request)
        except Exception as exc:  # noqa: BLE001
            logger.exception("[XDR] run_tool 异常：request=%s exc=%s", request, exc)
            raise

    def query_action_status(self, idempotency_key: str) -> str:
        status = self._ledger.query_action_status(idempotency_key)
        logger.info("[XDR] query_action_status idempotency=%s → %s", idempotency_key, status)
        return status

    # --------------------------------------------------------- dispose（只读模式）
    def apply_disposition(self, disposition: DispositionRecord) -> PlatformResultCode:
        logger.info("[XDR] apply_disposition：只读模式，跳过执行 disposition_id=%s", disposition.disposition_id)
        return PlatformResultCode.SUCCESS

    def verify_disposition(self, disposition: DispositionRecord) -> tuple[PlatformResultCode, dict[str, Any]]:
        logger.info("[XDR] verify_disposition：只读模式，返回结构化非成功状态")
        return PlatformResultCode.PLATFORM_READONLY_MODE, {
            "platform": self.platform_id,
            "mode": "readonly",
            "disposition_id": disposition.disposition_id,
            "reason": "XDR OpenAPI 当前按方案只接入只读查询，处置写入等待官方写接口接入。",
        }

    def teardown(self) -> None:
        logger.info("[XDR] teardown：关闭 session")
        try:
            if self._is_httpx and hasattr(self._session, "close"):
                self._session.close()
        except Exception:  # noqa: BLE001
            pass

    # 兼容属性访问：tool_dispatcher（与 jsonl_sample 相同）
    @property
    def tool_dispatcher(self) -> ToolDispatcher:
        return self._dispatcher

    # ---------------------------------------------------- 陈敏测试兼容：模块级工具函数以实例属性暴露
    # 陈敏测试以 self.adapter._to_alert_record / _dedupe_items / _extract_items / _to_normalizer_raw
    # 的形式访问这些辅助函数；这里绑定到模块级同名函数，保持调用签名一致。
    @property
    def _to_alert_record(self):  # type: ignore[override]
        return _to_alert_record

    @property
    def _to_normalizer_raw(self):
        return _to_normalizer_raw

    @property
    def _dedupe_items(self):
        return _dedupe_items

    @property
    def _extract_items(self):
        return _extract_items
