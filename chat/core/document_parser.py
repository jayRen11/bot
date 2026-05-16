import os
import sys
import re
import pdfplumber
import docx
from pdf2image import convert_from_bytes
from PIL import Image
import pytesseract

# 🪟 Windows 本地运行路径自动适配 (云端 Linux 会自动忽略)
if sys.platform == "win32":
    # Tesseract 常见安装路径
    tesseract_paths = [
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe"
    ]
    for p in tesseract_paths:
        if os.path.exists(p):
            pytesseract.pytesseract.tesseract_cmd = p
            break

    # Poppler 常见路径 (用于 pdf2image)
    POPPLER_PATH = os.getenv("POPPLER_PATH", r"C:\poppler-26.02.0\Library\bin")
    if not os.path.exists(POPPLER_PATH):
        POPPLER_PATH = None
else:
    POPPLER_PATH = None


def extract_text(uploaded_file):
    file_name = uploaded_file.name.lower()
    text = ""
    try:
        if file_name.endswith('.txt'):
            text = uploaded_file.read().decode('utf-8')
        elif file_name.endswith('.docx'):
            doc = docx.Document(uploaded_file)
            text = "\n".join([para.text for para in doc.paragraphs])
        elif file_name.endswith('.pdf'):
            file_bytes = uploaded_file.read()
            uploaded_file.seek(0)
            with pdfplumber.open(uploaded_file) as pdf:
                for page in pdf.pages:
                    extracted = page.extract_text()
                    if extracted:
                        text += extracted + "\n"

            # 扫描版 PDF 回退机制
            if len(text.strip()) < 50:
                print("🔍 检测到扫描版 PDF，启动 Tesseract OCR...")
                text = ""
                kwargs = {"first_page": 1, "last_page": len(pdf.pages)}
                if POPPLER_PATH:
                    kwargs["poppler_path"] = POPPLER_PATH
                images = convert_from_bytes(file_bytes, **kwargs)
                for img in images:
                    text += pytesseract.image_to_string(img, lang='chi_sim') + "\n"
        elif file_name.endswith(('.png', '.jpg', '.jpeg')):
            img_pil = Image.open(uploaded_file).convert('RGB')
            text = pytesseract.image_to_string(img_pil, lang='chi_sim')

        # 清理空白字符
        text = re.sub(r'\n+', '\n', text)
        text = re.sub(r'[ \t]+', ' ', text)
        return text.strip()
    except Exception as e:
        return f"Error: 提取失败 - {e}"


def chunk_text(text, chunk_size=300, overlap=50):
    """语义感知分块：优先按句子/段落切分，避免硬截断"""
    if not text:
        return []
    # 按中文句号、感叹号、问号、换行符切分
    sentences = re.split(r'([。！？\n]+)', text)
    # 重新组合标点
    segments = []
    for i in range(0, len(sentences) - 1, 2):
        segments.append(sentences[i] + (sentences[i + 1] if i + 1 < len(sentences) else ""))
    if len(sentences) % 2 != 0:
        segments.append(sentences[-1])

    chunks, current_chunk = [], ""
    for seg in segments:
        if len(current_chunk) + len(seg) <= chunk_size:
            current_chunk += seg
        else:
            if current_chunk:
                chunks.append(current_chunk.strip())
            # 处理重叠
            overlap_text = current_chunk[-overlap:] if len(current_chunk) > overlap else ""
            current_chunk = overlap_text + seg
    if current_chunk.strip():
        chunks.append(current_chunk.strip())
    return chunks
