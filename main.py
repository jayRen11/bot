import os
import sys

# 🛡️ SQLite 兼容性补丁 (仅在 Linux/云端生效)
try:
    __import__('pysqlite3')
    sys.modules['sqlite3'] = sys.modules.pop('pysqlite3')
except ImportError:
    pass

import streamlit as st

# 🥇 必须是整个脚本的第一个 Streamlit 命令
st.set_page_config(page_title="淮师大智能助手", page_icon="🏫", layout="wide")

# 🚀 【核心修复】：智能判断运行环境
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"

# 如果是在本地 Windows 运行，则使用国内镜像加速
if sys.platform == "win32":
    os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"
# 如果是在 Streamlit Cloud (Linux) 运行，什么都不设置，让它直连官方原站！
else:
    # 确保清除可能存在的残留环境变量
    os.environ.pop("HF_ENDPOINT", None)
from datetime import datetime
from streamlit_mic_recorder import speech_to_text
from gtts import gTTS
from io import BytesIO

from core.db_manager import DBManager
from core.llm_engine import LLMEngine
from core.document_parser import extract_text, chunk_text



# ================= 配置区 =================
API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
if not API_KEY:
    try:
        API_KEY = st.secrets["DEEPSEEK_API_KEY"]
    except Exception:
        pass

# 🛡️ 强校验：本地未配置时显示输入框 (此时 set_page_config 已执行，安全)
if not API_KEY:
    st.warning("⚠️ 未检测到 DeepSeek API Key，请在下方输入以继续：")
    API_KEY = st.text_input("请输入 DeepSeek API Key (sk-...)", type="password", key="manual_api_key")
    if not API_KEY:
        st.stop()  # 暂停渲染，避免下方引擎初始化报错


# ================= 1. 初始化核心引擎 =================
@st.cache_resource
def load_engines(api_key):
    db = DBManager()
    llm = LLMEngine(api_key=api_key)
    return db, llm

db_manager, llm_engine = load_engines(API_KEY)

# ================= 2. 辅助功能函数 =================
def text_to_audio_bytes(text):
    try:
        tts = gTTS(text=text, lang='zh-cn')
        fp = BytesIO()
        tts.write_to_fp(fp)
        return fp.getvalue()
    except Exception as e:
        st.warning(f"语音生成失败: {e}")
        return None

def generate_notes(messages):
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    md = f"# 📚 淮师大智能助手 - 专属复习笔记\n> 生成时间：{current_time}\n\n---\n\n"
    for msg in messages:
        if msg["role"] == "assistant":
            if "你好同学" in msg["content"] or "专属学霸导师" in msg["content"]:
                continue
            md += f"### 🤖 导师解答\n{msg['content']}\n\n---\n\n"
        elif msg["role"] == "user":
            md += f"### 👤 我的问题\n{msg['content']}\n\n"
    return md

# ================= 3. Web 界面构建 =================
st.title("🏫 校园全能智能助手 Pro+")
tab_chat, tab_vision, tab_admin = st.tabs(["💬 智能对话", "👁️ 视觉顾问", "🛠️ 知识库管理"])

# 检查 API Key
if not API_KEY:
    st.error("⚠️ 未检测到 DeepSeek API Key。请在环境变量设置 `DEEPSEEK_API_KEY`，或在项目根目录创建 `.streamlit/secrets.toml`。")
    st.stop()


# ================= 模块 A：聊天助手 =================
with tab_chat:
    with st.sidebar:
        st.header("⚙️ 模式与控制中心")
        current_mode = st.radio("🧠 选择助手大脑：", ["生活助手", "专业课导师"])

        enable_socratic = False
        if current_mode == "专业课导师":
            enable_socratic = st.toggle("💡 启发式教学 (不直接给答案)", value=False)

        st.divider()
        st.markdown("### 🎙️ 语音输入")
        voice_input = speech_to_text(language='zh-CN', use_container_width=True, just_once=True, key='STT')
        enable_tts = st.toggle("🔊 开启语音播报", value=True)

        st.divider()
        st.markdown("### 💾 记忆管理")
        col_c1, col_c2 = st.columns(2)
        with col_c1:
            if st.button("🗑️ 清空当前对话", use_container_width=True):
                st.session_state.messages = []
                st.rerun()

        if "messages" in st.session_state and len(st.session_state.messages) > 1:
            notes_md = generate_notes(st.session_state.messages)
            st.download_button(
                label="📥 导出复习笔记 (.md)",
                data=notes_md,
                file_name=f"复习笔记_{datetime.now().strftime('%m%d_%H%M')}.md",
                mime="text/markdown",
                use_container_width=True
            )

    if "messages" not in st.session_state:
        welcome = "你好同学！生活上遇到什么问题可以直接问我哦！" if current_mode == "生活助手" else "你好！我是你的专属学霸导师，复习到哪一章卡壳了？随时问我！"
        st.session_state.messages = [{"role": "assistant", "content": welcome}]

    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    text_input = st.chat_input(f"当前模式：{current_mode}...")
    final_input = text_input or voice_input

    if final_input:
        st.session_state.messages.append({"role": "user", "content": final_input})
        with st.chat_message("user"):
            st.markdown(final_input)

        with st.chat_message("assistant"):
            with st.spinner("正在查阅资料与思考中..."):
                retrieved_context = db_manager.search(final_input, current_mode)
                reply = llm_engine.generate_reply(final_input, st.session_state.messages, retrieved_context,
                                                  current_mode, enable_socratic)
                st.markdown(reply)

                if retrieved_context:
                    with st.expander("👁️ 查看底层检索资料 (防自编验证)"):
                        st.info(retrieved_context)

                if enable_tts:
                    with st.spinner("正在生成语音播报..."):
                        audio_bytes = text_to_audio_bytes(reply)
                        if audio_bytes:
                            st.audio(audio_bytes, format="audio/mp3", autoplay=True)

        st.session_state.messages.append({"role": "assistant", "content": reply})

# ================= 模块 B：视觉顾问 =================
with tab_vision:
    st.header("👁️ 智能视觉顾问 (即时分析：课表/题目截图)")
    st.markdown("此处的图片内容抠字后，将**直接**交由 DeepSeek 大模型进行推理分析，**不存入**长期数据库。")

    image_analysis_type = st.radio("请选择图片分析意图：", ["解题思路引导 (不给最终答案)", "课程/时间安排规划"], horizontal=True)
    uploaded_image = st.file_uploader("上传截图或照片 (支持 .png, .jpg, .jpeg)", type=['png', 'jpg', 'jpeg'], key='img_uploader')

    if uploaded_image is not None:
        st.image(uploaded_image, caption="待分析图片", use_container_width=True)

        if st.button("🚀 开始即时视觉分析", type="primary", key="start_visual"):
            with st.spinner("正在启动 Tesseract 视觉引擎抠字..."):
                ocr_text = extract_text(uploaded_image)

            if ocr_text and len(ocr_text.strip()) > 10:
                with st.spinner("正在请求 DeepSeek 导师大脑进行智能分析..."):
                    analysis_result = llm_engine.generate_analysis_reply(ocr_text, image_analysis_type)
                    st.session_state.current_analysis = analysis_result
                    st.session_state.current_img_name = uploaded_image.name
                    st.session_state.current_img_type = image_analysis_type
            else:
                st.error("❌ 无法从图片中抠出有效文字，请确保图片清晰且包含印刷体文本。")

        if st.session_state.get("current_analysis"):
            st.success("✅ 图片分析完成！结果如下：")
            st.markdown(st.session_state.current_analysis)

            if st.button("➕ 将分析报告添加到聊天助手对话历史", type="secondary"):
                st.session_state.messages.append({
                    "role": "user",
                    "content": f"[视觉分析上传]: {st.session_state.current_img_name} ({st.session_state.current_img_type})"
                })
                st.session_state.messages.append({
                    "role": "assistant",
                    "content": st.session_state.current_analysis
                })
                st.session_state.current_analysis = None
                st.toast("🎉 已成功添加到聊天界面！请切换到【💬 智能对话】查看。", icon="✅")
                st.rerun()
        elif not uploaded_image:
            st.info("👆 请上传图片后点击分析按钮。")

# ================= 模块 C：知识库管理 =================
with tab_admin:
    st.header("📚 长期知识库中央控制台")
    st.markdown("此处数据将持久化至向量数据库 ChromaDB 中，供聊天助手调用。")

    st.markdown("### 📊 数据库长期记忆状态")
    col_d1, col_d2 = st.columns(2)
    with col_d1:
        st.info(f"**🏫 生活助手长期大脑**\n\n数据量：`{db_manager.count('生活助手')}` 条切片")
        if st.button("🔥 清空生活长期数据库", type="secondary", key="clear_life"):
            db_manager.clear("生活助手")
            st.toast("生活数据库已清空！", icon="✅")
            st.rerun()
    with col_d2:
        st.success(f"**🎓 专业课导师长期大脑**\n\n数据量：`{db_manager.count('专业课导师')}` 条切片")
        if st.button("🔥 清空学习长期数据库", type="secondary", key="clear_study"):
            db_manager.clear("专业课导师")
            st.toast("学习数据库已清空！", icon="✅")
            st.rerun()

    st.divider()
    st.markdown("### 📤 上传新长期知识文档")
    target_brain = st.radio("请选择存入的数据库：", ["生活助手", "专业课导师"], horizontal=True)
    uploaded_file = st.file_uploader("拖拽或点击上传文档 (.txt, .docx, .pdf)", type=['txt', 'docx', 'pdf'], key='doc_uploader')

    if uploaded_file is not None:
        if st.button("🚀 开始解析并存入长期数据库", type="primary", key="start_learn"):
            with st.spinner("正在读取文件并榨取纯文本..."):
                extracted_text = extract_text(uploaded_file)
                if extracted_text and not extracted_text.startswith("Error"):
                    with st.spinner("正在进行语义切片并存入数据库..."):
                        chunks = chunk_text(extracted_text)
                        chunk_count = db_manager.ingest(chunks, target_brain, uploaded_file.name)
                    st.balloons()
                    st.success(f"🎉 学习完成！文件已存入【{target_brain}】的大脑中，新增 {chunk_count} 个记忆切片。")
                    st.rerun()
                else:
                    st.error(f"解析失败！{extracted_text}")
