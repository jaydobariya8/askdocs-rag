"""
Single-file entry point for Streamlit Cloud deployment.
Runs FastAPI backend in a background thread, then runs Streamlit UI.
"""
from __future__ import annotations

import threading
import time
import socket
import traceback
import uvicorn

BACKEND_URL = "http://localhost:8000"
_backend_error: str = ""


def _port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("localhost", port)) == 0


def _run_backend():
    global _backend_error
    try:
        from backend.main import app as fastapi_app
        uvicorn.run(fastapi_app, host="0.0.0.0", port=8000, log_level="info")
    except Exception:
        _backend_error = traceback.format_exc()


# Only start backend thread if port not already bound
if not _port_in_use(8000):
    _thread = threading.Thread(target=_run_backend, daemon=True)
    _thread.start()
    # Wait until port is ready (max 15s)
    for _ in range(30):
        if _port_in_use(8000):
            break
        time.sleep(0.5)

# ── Everything below is the Streamlit UI ─────────────────────────────────────
import streamlit as st
import requests


def api_upload(file_bytes: bytes, filename: str) -> dict | None:
    try:
        resp = requests.post(
            f"{BACKEND_URL}/upload-document",
            files={"file": (filename, file_bytes)},
            timeout=60,
        )
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.ConnectionError:
        st.error("Backend not ready yet. Please wait a moment and try again.")
    except requests.exceptions.HTTPError as e:
        st.error(f"Upload failed: {e.response.json().get('detail', str(e))}")
    return None


def api_query(question: str) -> dict | None:
    try:
        resp = requests.post(
            f"{BACKEND_URL}/query",
            json={"question": question},
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.ConnectionError:
        st.error("Backend not ready yet. Please wait a moment and try again.")
    except requests.exceptions.HTTPError as e:
        st.error(f"Query failed: {e.response.json().get('detail', str(e))}")
    return None


def api_list_docs() -> list[dict]:
    try:
        resp = requests.get(f"{BACKEND_URL}/documents", timeout=10)
        resp.raise_for_status()
        return resp.json()
    except Exception:
        return []


def api_delete_doc(doc_id: str) -> bool:
    try:
        resp = requests.delete(f"{BACKEND_URL}/documents/{doc_id}", timeout=10)
        resp.raise_for_status()
        return True
    except Exception:
        return False


def refresh_docs():
    st.session_state.documents = api_list_docs()


st.set_page_config(
    page_title="Document Chatbot",
    page_icon="📄",
    layout="wide",
)

if _backend_error:
    st.error("Backend failed to start. Error details:")
    st.code(_backend_error)
    st.stop()

if "messages" not in st.session_state:
    st.session_state.messages = []
if "documents" not in st.session_state:
    st.session_state.documents = api_list_docs()


# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.title("📂 Documents")
    st.divider()

    st.caption("⚠️ Free tier: keep files under 5 MB for best results.")

    uploaded_file = st.file_uploader(
        "Upload PDF or TXT",
        type=["pdf", "txt"],
        label_visibility="collapsed",
    )

    # Warn if file exceeds 5 MB
    MAX_FILE_SIZE = 5 * 1024 * 1024  # 5 MB
    file_too_large = uploaded_file is not None and uploaded_file.size > MAX_FILE_SIZE

    if file_too_large:
        st.warning(f"File is {uploaded_file.size / 1024 / 1024:.1f} MB. Please upload a file under 5 MB.")

    if st.button("⬆ Upload", use_container_width=True, disabled=uploaded_file is None or file_too_large):
        with st.spinner("Uploading and indexing…"):
            result = api_upload(uploaded_file.read(), uploaded_file.name)
        if result:
            st.success(f"Indexed **{result['filename']}** ({result['num_chunks']} chunks)")
            refresh_docs()

    st.divider()

    doc_count = len(st.session_state.documents)
    st.caption(f"**{doc_count} document{'s' if doc_count != 1 else ''} uploaded**")

    if st.session_state.documents:
        for doc in st.session_state.documents:
            col1, col2 = st.columns([3, 1])
            with col1:
                st.markdown(
                    f"**{doc['filename']}**  \n"
                    f"<small>{doc['num_chunks']} chunks</small>",
                    unsafe_allow_html=True,
                )
            with col2:
                if st.button("🗑", key=f"del_{doc['doc_id']}", help="Delete document"):
                    if api_delete_doc(doc["doc_id"]):
                        st.success("Deleted.")
                        refresh_docs()
                        st.rerun()
                    else:
                        st.error("Delete failed.")
    else:
        st.info("No documents yet. Upload a PDF or TXT to get started.")


# ── Main chat ─────────────────────────────────────────────────────────────────
st.title("📄 Document Chatbot")
st.caption("Ask questions about your uploaded documents. Answers are grounded strictly in document content.")

if not st.session_state.documents:
    st.info("👈 Upload a document in the sidebar to start chatting.")

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if msg["role"] == "assistant" and msg.get("sources"):
            with st.expander("📎 Sources"):
                for src in msg["sources"]:
                    st.markdown(f"- {src}")

if prompt := st.chat_input("Ask something about your documents…"):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.spinner("Thinking…"):
            result = api_query(prompt)

        if result:
            st.markdown(result["answer"])
            sources = result.get("sources", [])
            if sources:
                with st.expander("📎 Sources"):
                    for src in sources:
                        st.markdown(f"- {src}")
            st.session_state.messages.append(
                {"role": "assistant", "content": result["answer"], "sources": sources}
            )
        else:
            fallback = "Something went wrong. Please check backend status."
            st.error(fallback)
            st.session_state.messages.append(
                {"role": "assistant", "content": fallback, "sources": []}
            )
