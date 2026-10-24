"""核心配置模块"""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    APP_NAME: str = "立即修平台"
    DATABASE_URL: str = "sqlite+aiosqlite:///./xiulijiu.db"
    UPLOAD_DIR: str = "uploads"
    DEBUG: bool = True
    ALLOW_DEMO_LOGIN: bool = False
    AUTH_SECRET: str = "change-me-in-production"
    SMS_PROVIDER: str = "debug"
    SMS_DEBUG_CODE: str = "246810"
    # 2026-10-05:调试短信通道必须显式打开。生产保持 false,
    # 否则 /api/v1/auth/sms/request 会回显固定验证码,任何人可登录任意手机号账号。
    ALLOW_SMS_DEBUG_ENDPOINT: bool = False
    WECHAT_MINIPROGRAM_ENV_VERSION: str = "trial"
    PUBLIC_BASE_URL: str = "https://x.iddg.cn"
    PAYMENT_ALLOW_MOCK: bool = False

    WECHAT_PAY_APPID: str = "wx2273201e59e280bc"
    WECHAT_PAY_MCH_ID: str = ""
    WECHAT_PAY_API_V3_KEY: str = ""
    WECHAT_PAY_CERT_PATH: str = "cert/apiclient_cert.pem"
    WECHAT_PAY_KEY_PATH: str = "cert/apiclient_key.pem"
    WECHAT_PAY_CERT_SERIAL_NO: str = ""
    WECHAT_PAY_NOTIFY_URL: str = ""
    WECHAT_REFUND_NOTIFY_URL: str = ""
    WECHAT_WITHDRAW_AUTO_TRANSFER: bool = False
    WECHAT_TRANSFER_SCENE_ID: str = ""
    WECHAT_TRANSFER_NOTIFY_URL: str = ""
    WECHAT_TRANSFER_REMARK: str = "withdrawal"
    WECHAT_TRANSFER_USER_RECV_PERCEPTION: str = "withdrawal"
    WECHAT_PAY_PLATFORM_CERT_PATH: str = ""
    WECHAT_APP_SECRET: str = ""
    WECHAT_REVIEW_ACCOUNT: str = ""
    WECHAT_REVIEW_PASSWORD: str = ""
    WECHAT_REVIEW_PHONE: str = "18800000999"
    WECHAT_REVIEW_MIN_BALANCE: float = 100.0

    # 2026-10-07:管理后台账号密码登录(替代手工粘贴 token)
    # 走 POST /api/v1/auth/admin-login,登录成功返回该手机号对应的管理员用户与 token。
    # 账号密码明文放 .env,与 WECHAT_REVIEW_PASSWORD 的做法一致。
    ADMIN_WEB_ACCOUNT: str = ""
    ADMIN_WEB_PASSWORD: str = ""
    ADMIN_WEB_PHONE: str = "18800000000"

    # 2026-08-09:启动时强制跑 strict env 校验。生产建议开,dev 留 false
    # 开了之后:任意 FILL_* / 弱 secret / 非 https 都会让进程 exit 1
    STRICT_ENV_ON_STARTUP: bool = False

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        # 让 docker compose / 第三方工具的额外 env(如 MYSQL_*)能进 .env
        # 而不污染 Settings 模型。unknown 变量静默忽略,已知 typo
        # 仍然会因为 Pydantic 的 type validation 暴露出来。
        "extra": "ignore",
    }


settings = Settings()
