import logging
import sys
from pathlib import Path
from datetime import datetime
from typing import Any
from logging.handlers import RotatingFileHandler, TimedRotatingFileHandler
import json

from app.core.config import get_settings


class JSONFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            "timestamp": datetime.utcnow().isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        if hasattr(record, "user_id"):
            log_data["user_id"] = record.user_id

        if hasattr(record, "request_id"):
            log_data["request_id"] = record.request_id

        if hasattr(record, "extra_data"):
            log_data["extra"] = record.extra_data

        return json.dumps(log_data)


class CloudWatchHandler(logging.Handler):
    def __init__(self, log_group: str, log_stream: str):
        super().__init__()
        self.log_group = log_group
        self.log_stream = log_stream
        self.client = None
        self._init_client()

    def _init_client(self):
        try:
            import boto3
            self.client = boto3.client("logs")
            self._ensure_log_stream()
        except Exception as e:
            print(f"Failed to initialize CloudWatch: {e}")

    def _ensure_log_stream(self):
        if not self.client:
            return

        try:
            self.client.create_log_group(logGroupName=self.log_group)
        except self.client.exceptions.ResourceAlreadyExistsException:
            pass

        try:
            self.client.create_log_stream(
                logGroupName=self.log_group,
                logStreamName=self.log_stream
            )
        except self.client.exceptions.ResourceAlreadyExistsException:
            pass

    def emit(self, record: logging.LogRecord):
        if not self.client:
            return

        try:
            log_event = {
                "logGroupName": self.log_group,
                "logStreamName": self.log_stream,
                "logEvents": [
                    {
                        "timestamp": int(datetime.utcnow().timestamp() * 1000),
                        "message": self.format(record),
                    }
                ],
            }
            self.client.put_log_events(**log_event)
        except Exception:
            self.handleError(record)


class DatadogHandler(logging.Handler):
    def __init__(self, api_key: str, service_name: str):
        super().__init__()
        self.api_key = api_key
        self.service_name = service_name
        self.endpoint = "https://http-intake.logs.datadoghq.com/v1/input"

    def emit(self, record: logging.LogRecord):
        try:
            import httpx

            log_data = {
                "ddsource": "python",
                "ddtags": f"service:{self.service_name},env:production",
                "hostname": "backend",
                "message": self.format(record),
                "level": record.levelname,
            }

            httpx.post(
                self.endpoint,
                headers={
                    "DD-API-KEY": self.api_key,
                    "Content-Type": "application/json",
                },
                json=log_data,
                timeout=5.0,
            )
        except Exception:
            self.handleError(record)


class SentryHandler(logging.Handler):
    def __init__(self, dsn: str, environment: str):
        super().__init__()
        self.dsn = dsn
        self.environment = environment
        self._init_sentry()

    def _init_sentry(self):
        try:
            import sentry_sdk
            sentry_sdk.init(
                dsn=self.dsn,
                environment=self.environment,
                traces_sample_rate=1.0,
            )
        except Exception as e:
            print(f"Failed to initialize Sentry: {e}")

    def emit(self, record: logging.LogRecord):
        try:
            import sentry_sdk

            if record.exc_info:
                sentry_sdk.capture_exception(record.exc_info[1])
            else:
                sentry_sdk.capture_message(record.getMessage(), level=record.levelname.lower())
        except Exception:
            self.handleError(record)


class LoggerManager:
    _instance = None
    _initialized = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(LoggerManager, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        if not self._initialized:
            self.settings = get_settings()
            self.loggers = {}
            self._setup_root_logger()
            LoggerManager._initialized = True

    def _setup_root_logger(self):
        log_level_str = getattr(self.settings, "log_level", "INFO")
        log_level = getattr(logging, log_level_str.upper(), logging.INFO)

        root_logger = logging.getLogger()
        root_logger.setLevel(log_level)
        root_logger.handlers.clear()

        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(log_level)
        console_formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
        console_handler.setFormatter(console_formatter)
        root_logger.addHandler(console_handler)

        log_file = getattr(self.settings, "log_file", None)
        if log_file:
            log_path = Path(log_file)
            log_path.parent.mkdir(parents=True, exist_ok=True)

            file_handler = RotatingFileHandler(
                log_path,
                maxBytes=10 * 1024 * 1024,
                backupCount=5,
                encoding="utf-8"
            )
            file_handler.setLevel(log_level)

            log_format = getattr(self.settings, "log_format", "text")
            if log_format == "json":
                file_handler.setFormatter(JSONFormatter())
            else:
                file_handler.setFormatter(console_formatter)

            root_logger.addHandler(file_handler)

        cloudwatch_enabled = getattr(self.settings, "cloudwatch_logging_enabled", False)
        if cloudwatch_enabled:
            log_group = getattr(self.settings, "cloudwatch_log_group", "/chatbot/backend")
            log_stream = getattr(
                self.settings,
                "cloudwatch_log_stream",
                f"backend-{datetime.utcnow().strftime('%Y-%m-%d')}"
            )
            try:
                cloudwatch_handler = CloudWatchHandler(log_group, log_stream)
                cloudwatch_handler.setLevel(logging.INFO)
                cloudwatch_handler.setFormatter(JSONFormatter())
                root_logger.addHandler(cloudwatch_handler)
            except Exception as e:
                root_logger.warning(f"Failed to setup CloudWatch handler: {e}")

        datadog_api_key = getattr(self.settings, "datadog_api_key", None)
        if datadog_api_key:
            try:
                datadog_handler = DatadogHandler(
                    datadog_api_key,
                    getattr(self.settings, "service_name", "chatbot-backend")
                )
                datadog_handler.setLevel(logging.INFO)
                datadog_handler.setFormatter(JSONFormatter())
                root_logger.addHandler(datadog_handler)
            except Exception as e:
                root_logger.warning(f"Failed to setup Datadog handler: {e}")

        sentry_dsn = getattr(self.settings, "sentry_dsn", None)
        if sentry_dsn:
            try:
                sentry_handler = SentryHandler(
                    sentry_dsn,
                    self.settings.environment
                )
                sentry_handler.setLevel(logging.ERROR)
                root_logger.addHandler(sentry_handler)
            except Exception as e:
                root_logger.warning(f"Failed to setup Sentry handler: {e}")

    def get_logger(self, name: str) -> logging.Logger:
        if name not in self.loggers:
            self.loggers[name] = logging.getLogger(name)
        return self.loggers[name]


logger_manager = LoggerManager()


def get_logger(name: str = "app") -> logging.Logger:
    return logger_manager.get_logger(name)


class LoggerAdapter(logging.LoggerAdapter):
    def __init__(self, logger: logging.Logger, extra: dict[str, Any] | None = None):
        super().__init__(logger, extra or {})

    def process(self, msg: str, kwargs: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        if self.extra:
            if "extra" not in kwargs:
                kwargs["extra"] = {}
            kwargs["extra"].update(self.extra)
        return msg, kwargs

    def with_context(self, **context: Any) -> "LoggerAdapter":
        extra = self.extra.copy() if self.extra else {}
        extra.update(context)
        return LoggerAdapter(self.logger, extra)


def get_logger_with_context(**context: Any) -> LoggerAdapter:
    base_logger = get_logger()
    return LoggerAdapter(base_logger, context)
