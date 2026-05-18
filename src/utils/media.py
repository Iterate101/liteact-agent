import base64
import mimetypes
import os

def image_to_base64(path):
    """
    将图片文件转换为 Base64 字符串。
    在大项目中，这类通用的多媒体处理函数应该放在 utils 包里。
    """
    try:
        with open(path, 'rb') as f:
            image_data = f.read()
            b64_string = base64.b64encode(image_data).decode('utf-8')
            mime_type, _ = mimetypes.guess_type(path)
            # 如果猜不到类型，我们默认给一个 image/jpeg
            return b64_string, mime_type or "image/jpeg"
    except Exception as e:
        raise RuntimeError(f"图片转换失败: {str(e)}")
