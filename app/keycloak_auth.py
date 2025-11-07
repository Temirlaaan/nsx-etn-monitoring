# app/keycloak_auth.py
import os
from typing import Optional
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from keycloak import KeycloakOpenID
from jose import JWTError, jwt
from dotenv import load_dotenv
import logging
import urllib3

load_dotenv()

logger = logging.getLogger(__name__)

# Отключаем предупреждения SSL (если сертификат самоподписанный)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Конфигурация Keycloak
KEYCLOAK_SERVER_URL = os.getenv("KEYCLOAK_SERVER_URL")
KEYCLOAK_REALM = os.getenv("KEYCLOAK_REALM")
KEYCLOAK_CLIENT_ID = os.getenv("KEYCLOAK_CLIENT_ID")
KEYCLOAK_CLIENT_SECRET = os.getenv("KEYCLOAK_CLIENT_SECRET")
KEYCLOAK_ENABLED = os.getenv("KEYCLOAK_ENABLED", "false").lower() == "true"

# Проверяем наличие обязательных параметров
if KEYCLOAK_ENABLED:
    if not all([KEYCLOAK_SERVER_URL, KEYCLOAK_REALM, KEYCLOAK_CLIENT_ID]):
        logger.error("Missing required Keycloak configuration!")
        logger.error(f"KEYCLOAK_SERVER_URL: {KEYCLOAK_SERVER_URL}")
        logger.error(f"KEYCLOAK_REALM: {KEYCLOAK_REALM}")
        logger.error(f"KEYCLOAK_CLIENT_ID: {KEYCLOAK_CLIENT_ID}")
        KEYCLOAK_ENABLED = False

# Инициализация Keycloak OpenID
keycloak_openid = None
if KEYCLOAK_ENABLED:
    try:
        keycloak_openid = KeycloakOpenID(
            server_url=KEYCLOAK_SERVER_URL,
            client_id=KEYCLOAK_CLIENT_ID,
            realm_name=KEYCLOAK_REALM,
            client_secret_key=KEYCLOAK_CLIENT_SECRET,
            verify=False,
            timeout=10
        )
        logger.info(f"Keycloak client initialized: {KEYCLOAK_SERVER_URL}/realms/{KEYCLOAK_REALM}")
    except Exception as e:
        logger.error(f"Failed to initialize Keycloak client: {e}")
        keycloak_openid = None
        KEYCLOAK_ENABLED = False

security = HTTPBearer()


class KeycloakUser:
    """Модель пользователя из Keycloak"""
    def __init__(self, username: str, email: str, roles: list, user_id: str):
        self.username = username
        self.email = email
        self.roles = roles
        self.user_id = user_id
        self.is_active = True


def verify_token(token: str) -> dict:
    """Проверка токена через Keycloak"""
    if not keycloak_openid:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Keycloak service is not available"
        )
    
    try:
        # Получаем публичный ключ от Keycloak
        KEYCLOAK_PUBLIC_KEY = (
            "-----BEGIN PUBLIC KEY-----\n"
            + keycloak_openid.public_key()
            + "\n-----END PUBLIC KEY-----"
        )
        
        # Настройки для валидации токена
        options = {
            "verify_signature": True,
            "verify_aud": False,
            "verify_exp": True
        }
        
        # Декодируем и валидируем токен
        token_info = jwt.decode(
            token,
            KEYCLOAK_PUBLIC_KEY,
            algorithms=["RS256"],
            options=options
        )
        
        return token_info
        
    except JWTError as e:
        logger.error(f"Token validation error: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except Exception as e:
        logger.error(f"Unexpected error during token validation: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication failed",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> KeycloakUser:
    """Получение текущего пользователя из токена"""
    token = credentials.credentials
    
    try:
        # Верифицируем токен
        token_info = verify_token(token)
        
        # Извлекаем данные пользователя
        username = token_info.get("preferred_username", "unknown")
        email = token_info.get("email", "")
        user_id = token_info.get("sub", "")
        
        # Извлекаем роли из токена
        roles = []
        if "realm_access" in token_info:
            roles = token_info["realm_access"].get("roles", [])
        
        # Создаем объект пользователя
        user = KeycloakUser(
            username=username,
            email=email,
            roles=roles,
            user_id=user_id
        )
        
        logger.info(f"User authenticated: {username} (roles: {roles})")
        return user
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting current user: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def get_current_active_user(
    current_user: KeycloakUser = Depends(get_current_user)
) -> KeycloakUser:
    """Проверка активности пользователя"""
    if not current_user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")
    return current_user


def login_user(username: str, password: str) -> dict:
    """Логин пользователя через Keycloak"""
    if not keycloak_openid:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Keycloak service is not available"
        )
    
    try:
        logger.info(f"Attempting login for user: {username}")
        
        # Получаем токен от Keycloak
        token = keycloak_openid.token(username, password)
        
        logger.info(f"Login successful for user: {username}")
        
        return {
            "access_token": token["access_token"],
            "refresh_token": token.get("refresh_token"),
            "expires_in": token.get("expires_in"),
            "token_type": "bearer"
        }
        
    except Exception as e:
        logger.error(f"Login failed for user {username}: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )


def refresh_token(refresh_token: str) -> dict:
    """Обновление токена через refresh token"""
    if not keycloak_openid:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Keycloak service is not available"
        )
    
    try:
        token = keycloak_openid.refresh_token(refresh_token)
        
        return {
            "access_token": token["access_token"],
            "refresh_token": token.get("refresh_token"),
            "expires_in": token.get("expires_in"),
            "token_type": "bearer"
        }
        
    except Exception as e:
        logger.error(f"Token refresh failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not refresh token",
            headers={"WWW-Authenticate": "Bearer"},
        )


def logout_user(refresh_token: str):
    """Выход пользователя (инвалидация refresh token)"""
    if not keycloak_openid:
        logger.warning("Keycloak service not available for logout")
        return
    
    try:
        keycloak_openid.logout(refresh_token)
        logger.info("User logged out successfully")
    except Exception as e:
        logger.error(f"Logout failed: {e}")


def exchange_code_for_token(code: str) -> dict:
    """Обмен authorization code на токен"""
    if not keycloak_openid:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Keycloak service is not available"
        )
    
    try:
        # Получаем redirect_uri из env
        redirect_uri = os.getenv("FRONTEND_CALLBACK_URL", "https://web-etn-mon.t-cloud.kz/callback")
        
        token = keycloak_openid.token(
            grant_type='authorization_code',
            code=code,
            redirect_uri=redirect_uri
        )
        
        logger.info("Code exchanged for token successfully")
        
        return {
            "access_token": token["access_token"],
            "refresh_token": token.get("refresh_token"),
            "expires_in": token.get("expires_in"),
            "token_type": "bearer"
        }
    except Exception as e:
        logger.error(f"Code exchange failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not exchange code for token",
            headers={"WWW-Authenticate": "Bearer"},
        )