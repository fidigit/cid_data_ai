from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """所有敏感参数均由环境变量或密钥服务注入，禁止提交到仓库。"""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "development"
    database_url: str = "sqlite:///./data/app.db"
    redis_url: str = "redis://localhost:6379/0"
    admin_api_token: str = ""
    artifacts_dir: Path = Path("artifacts")
    max_export_rows: int = 200_000
    timezone: str = "Asia/Shanghai"

    auth_session_secret: str = ""
    auth_session_ttl_seconds: int = 28_800
    auth_cookie_name: str = "event_ops_session"
    superadmin_username: str = ""
    superadmin_password_hash: str = ""
    query_execution_mode: str = "thread"

    odps_access_id: str = ""
    odps_access_key_secret: str = ""
    odps_project: str = ""
    odps_endpoint: str = ""
    odps_tunnel_endpoint: str = ""

    data_source_table: str = ""
    data_partition_column: str = "ds"
    data_event_code_column: str = "cid"
    data_user_id_column: str = "device_id"
    partition_date_format: str = "%Y%m%d"

    # execute_sql_cost 返回扫描量等估算信息；金额按内部配置单价换算，仅供参考。
    cost_estimate_token_secret: str = ""
    cost_estimate_token_ttl_seconds: int = 600
    cost_estimate_price_per_gib_cny: float = 0.30

    spreadsheet_node_bin: str = "node"

    wecom_mode: str = "disabled"
    wecom_corp_id: str = ""
    wecom_agent_id: str = ""
    wecom_secret: str = ""
    wecom_callback_token: str = ""
    wecom_callback_aes_key: str = ""

    def validate_odps_ready(self) -> None:
        required = {
            "ODPS_ACCESS_ID": self.odps_access_id,
            "ODPS_ACCESS_KEY_SECRET": self.odps_access_key_secret,
            "ODPS_PROJECT": self.odps_project,
            "ODPS_ENDPOINT": self.odps_endpoint,
            "DATA_SOURCE_TABLE": self.data_source_table,
        }
        missing = [name for name, value in required.items() if not value]
        if missing:
            raise RuntimeError(f"ODPS 查询尚未配置：{', '.join(missing)}")


@lru_cache
def get_settings() -> Settings:
    return Settings()
