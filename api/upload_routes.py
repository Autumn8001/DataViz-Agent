import os
import uuid
import shutil
from fastapi import APIRouter, UploadFile, File, HTTPException

router = APIRouter()

# 明确规定咱们的文件存放重镇
UPLOAD_DIR = "data/uploads"

# 确保文件夹存在（防止手滑删了报错）
os.makedirs(UPLOAD_DIR, exist_ok=True)

#  架构师的安全红线：白名单机制
ALLOWED_EXTENSIONS = {".csv", ".xlsx", ".xls"}


@router.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    """接收前端上传的数据文件，并安全持久化到本地磁盘"""

    # 1. 提取文件后缀名，并转为小写
    file_ext = os.path.splitext(file.filename)[1].lower()

    # 2. 安全防线：文件类型白名单校验
    if file_ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"安全拦截：不支持的文件类型 '{file_ext}'。只允许上传 CSV 或 Excel！",
        )

    # 3. 解决高并发痛点：使用 UUID 生成绝对唯一的文件名
    # 如果两个人都上传了 data.csv，不改名字的话后一个会把前一个覆盖掉！
    unique_filename = f"{uuid.uuid4().hex}{file_ext}"
    file_path = os.path.join(UPLOAD_DIR, unique_filename)

    # 4. 把文件按块（Chunk）写入磁盘，防止大文件撑爆内存
    try:
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"文件保存失败: {str(e)}")
    finally:
        # 无论成功失败，一定要关闭上传流，释放资源
        await file.close()

    print(f"📦 [Upload] 接收文件成功！已保存至: {file_path}")

    # 5. 把保存好的物理路径返回给前端
    # 前端拿着这个路径，待会儿请求 /chat 接口的时候再传给咱们！
    return {
        "message": "上传成功",
        "original_name": file.filename,
        "file_path": file_path,  #  这个极其重要！这是文件的“取件码”
    }
