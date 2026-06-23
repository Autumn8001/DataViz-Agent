import os
import uuid
import shutil
from fastapi import APIRouter, UploadFile, File, HTTPException, Depends
from core.auth import get_current_user

router = APIRouter()

# 架构师的安全红线：白名单机制
ALLOWED_EXTENSIONS = {".csv", ".xlsx", ".xls"}


@router.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user)
):
    """接收前端上传的数据文件，并按用户 user_id 安全地在物理上进行隔离持久化"""

    user_id = current_user["user_id"]

    # 1. 提取文件后缀名，并转为小写
    file_ext = os.path.splitext(file.filename)[1].lower()

    # 2. 安全防线：文件类型白名单校验
    if file_ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"安全拦截：不支持的文件类型 '{file_ext}'。只允许上传 CSV 或 Excel！",
        )

    # 3. 动态物理隔离用户上传文件夹
    user_upload_dir = f"data/uploads/{user_id}"
    os.makedirs(user_upload_dir, exist_ok=True)

    # 4. 解决高并发与覆盖冲突痛点：使用 UUID 生成绝对唯一的文件名
    unique_filename = f"{uuid.uuid4().hex}{file_ext}"
    file_path = os.path.join(user_upload_dir, unique_filename)

    # 5. 把文件按块（Chunk）写入磁盘，防止大文件撑爆内存
    try:
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"文件保存失败: {str(e)}")
    finally:
        # 无论成功失败，一定要关闭上传流，释放资源
        await file.close()

    print(f"📦 [Upload] 用户 {user_id} 接收文件成功！已物理隔离保存至: {file_path}")

    # 6. 把保存好的物理路径返回给前端
    return {
        "message": "上传成功",
        "original_name": file.filename,
        "file_path": file_path,  # 这是文件的“取件码”
    }
