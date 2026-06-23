import os
from fastapi import Header, HTTPException, status
from jose import JWTError, jwt
from dotenv import load_dotenv

load_dotenv()

# JWT 配置信息（与 RAG 后端共享以支持 SSO）
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "enterprise-rag-super-secret-key-change-it-in-production")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")

async def get_current_user(
    authorization: str | None = Header(None, description="Bearer Token 认证")
) -> dict:
    """
    通过共享密钥解密 JWT Bearer 令牌，获取当前已登录用户的身份，并提取 user_id & tenant_id。
    """
    token = None
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="请求未携带有效的 Bearer 令牌，鉴权失败。",
            headers={"WWW-Authenticate": "Bearer"},
        )

    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="凭证校验失败，令牌可能已失效或被篡改。",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        username: str = payload.get("sub")
        tenant_id: str = payload.get("tenant_id")
        if username is None or tenant_id is None:
            raise credentials_exception
        
        return {
            "user_id": username,
            "tenant_id": tenant_id
        }
    except JWTError:
        raise credentials_exception
