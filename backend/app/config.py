from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    app_name: str = "S-UI Manager"
    database_url: str = "sqlite:////data/sui_manager.db"
    secret_key: str = "CHANGE-ME"
    token_encryption_key: str = ""
    admin_username: str = "admin"
    admin_password: str = "ChangeMe123!"
    access_token_minutes: int = 720
    node_timeout_seconds: int = 8
    health_monitor_enabled: bool = True
    health_check_interval_seconds: int = 60
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = Settings()
