import streamlit as st
import requests
import json
import pandas as pd
from datetime import datetime
import os
import time

API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")

st.set_page_config(page_title="DevAssist AI", page_icon="🤖", layout="wide")

# Custom CSS
st.markdown("""
<style>
    .stApp { background-color: #0E1117; color: #FAFAFA; }
    .stButton>button { background-color: #4CAF50; color: white; border-radius: 8px; font-weight: 600; }
    .stButton>button:hover { background-color: #45a049; }
    div[data-testid="stMetric"] { background-color: #1a1a2e; border-radius: 10px; padding: 12px; border: 1px solid #333; }
</style>
""", unsafe_allow_html=True)


def poll_task(task_id: str, max_wait: int = 900) -> dict:
    """
    Poll for async task result with live progress updates.
    
    max_wait raised to 900s (15 min) to accommodate local LLM reviews
    which can take 300-500s depending on file count and model speed.
    """
    start = time.time()
    status_placeholder = st.empty()
    
    while True:
        elapsed = int(time.time() - start)
        
        if elapsed >= max_wait:
            status_placeholder.empty()
            return {"status": "TIMEOUT", "error": f"Task did not complete after {max_wait}s."}
        
        try:
            resp = requests.get(f"{API_BASE_URL}/task/{task_id}", timeout=10)
            data = resp.json()
            task_status = data.get("status", "UNKNOWN")
            
            if task_status == "SUCCESS":
                status_placeholder.empty()
                return data
            elif task_status == "FAILURE":
                status_placeholder.empty()
                error_msg = data.get("error", data.get("result", "Task failed"))
                return {"status": "FAILURE", "error": str(error_msg)}
            else:
                # Show live progress — task is still running
                minutes, seconds = divmod(elapsed, 60)
                status_placeholder.caption(
                    f"⏳ Review in progress... ({minutes}m {seconds}s elapsed) — Status: `{task_status}`"
                )
        except Exception:
            pass  # Network blip — retry on next iteration
        
        time.sleep(5)


with st.sidebar:
    st.title("⚙️ DevAssist AI")
    st.caption("v2.0 — Multi-LLM Architecture")

    st.markdown("### API Status")
    try:
        response = requests.get(f"{API_BASE_URL}/status", timeout=5)
        if response.status_code == 200:
            data = response.json()
            st.markdown("🟢 **API is running**")
            st.caption(f"Provider: `{data.get('llm_provider', '?')}` · Model: `{data.get('llm_model', '?')}`")
        else:
            st.markdown("🔴 **API is down**")
    except requests.exceptions.RequestException:
        st.markdown("🔴 **API is unreachable**")

    st.markdown("---")

    # Health check
    if st.button("🩺 Health Check"):
        try:
            resp = requests.get(f"{API_BASE_URL}/health", timeout=10)
            health = resp.json()
            for component, status in health.get("components", {}).items():
                icon = "✅" if "ok" in str(status) else "⚠️"
                st.markdown(f"{icon} **{component}**: {status}")
        except Exception as e:
            st.error(f"Health check failed: {e}")

    st.markdown(f"[📖 API Documentation]({API_BASE_URL}/docs)")
    st.markdown("---")
    st.caption("Built with LLM Router + Multi-Provider | DevAssist AI v2.0")


tab1, tab2, tab3 = st.tabs(["🔍 PR Review", "📄 Documentation", "📜 History"])

with tab1:
    st.header("Automated PR Code Review")
    pr_number = st.number_input("Pull Request Number", min_value=1, step=1, key="pr_input")

    if st.button("🚀 Start Review", key="review_btn"):
        with st.spinner("Submitting review request..."):
            try:
                response = requests.post(
                    f"{API_BASE_URL}/review",
                    json={"pr_number": pr_number},
                    timeout=180
                )
                data = response.json()

                # If we got a task_id back, we're in async mode
                if "task_id" in data:
                    st.info(f"Task queued: `{data['task_id']}`. Polling for result...")
                    with st.spinner("Waiting for review to complete..."):
                        result = poll_task(data["task_id"])

                    if result.get("status") == "SUCCESS":
                        data = result.get("result", {})
                    else:
                        st.error(f"Task failed: {result.get('error', result.get('status'))}")
                        data = None

                if data and data.get("success"):
                    comments = data.get("comments", [])
                    st.success(f"Review complete! {len(comments)} comments posted.")

                    col1, col2, col3, col4 = st.columns(4)
                    with col1:
                        st.metric("Files Reviewed", len(data.get("files_reviewed", [])))
                    with col2:
                        st.metric("Comments", len(comments))
                    with col3:
                        st.metric("Provider", data.get("provider_used", "N/A"))
                    with col4:
                        st.metric("Model", data.get("model_used", "N/A"))

                    if comments:
                        def highlight_severity(val):
                            colors = {"error": "#F44336", "warning": "#FF9800", "suggestion": "#2196F3"}
                            return f'color: {colors.get(val, "#4CAF50")}'

                        df = pd.DataFrame(comments)
                        if "severity" in df.columns:
                            st.dataframe(df.style.map(highlight_severity, subset=["severity"]), use_container_width=True)
                        else:
                            st.dataframe(df, use_container_width=True)

                    with st.expander("🔍 Agent Audit Trail"):
                        for log in data.get("audit_log", []):
                            st.text(log)

                elif data:
                    st.error(f"Review failed: {data.get('error', 'Unknown error')}")
            except Exception as e:
                st.error(f"Failed to connect to API: {str(e)}")

with tab2:
    st.header("Automated Documentation Generator")
    file_path = st.text_input("File Path", placeholder="/path/to/your/module.py", key="doc_path")
    save_updated = st.checkbox("Save updated file with docstrings", value=False, key="save_check")

    if st.button("📝 Generate Documentation", key="doc_btn"):
        if not file_path:
            st.warning("Please enter a file path.")
        else:
            with st.spinner("Submitting documentation request..."):
                try:
                    response = requests.post(
                        f"{API_BASE_URL}/document",
                        json={"file_path": file_path, "save_updated": save_updated},
                        timeout=180
                    )
                    data = response.json()

                    # Async mode
                    if "task_id" in data:
                        st.info(f"Task queued: `{data['task_id']}`. Polling for result...")
                        with st.spinner("Waiting for documentation to complete..."):
                            result = poll_task(data["task_id"])

                        if result.get("status") == "SUCCESS":
                            data = result.get("result", {})
                        else:
                            st.error(f"Task failed: {result.get('error', result.get('status'))}")
                            data = None

                    if data and data.get("success"):
                        changes = data.get("changes_made", 0)
                        st.success(f"Done! Documented {changes} functions/classes.")

                        col_info1, col_info2 = st.columns(2)
                        with col_info1:
                            st.metric("Provider", data.get("provider_used", "N/A"))
                        with col_info2:
                            st.metric("Model", data.get("model_used", "N/A"))

                        items = data.get("items_documented", [])
                        if items:
                            st.info(f"Items documented: {', '.join(items)}")

                        col1, col2 = st.columns(2)
                        with col1:
                            st.subheader("Updated Code")
                            st.code(data.get("updated_code", ""), language="python")
                        with col2:
                            st.subheader("Generated Documentation")
                            st.markdown(data.get("markdown", ""))

                    elif data:
                        st.error(f"Documentation failed: {data.get('error', 'Unknown error')}")
                except Exception as e:
                    st.error(f"Failed to connect to API: {str(e)}")

with tab3:
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Recent Reviews")
        if st.button("🔄 Refresh Reviews", key="refresh_reviews"):
            try:
                response = requests.get(f"{API_BASE_URL}/history/reviews")
                if response.status_code == 200:
                    reviews = response.json()
                    if reviews:
                        history_data = [
                            {
                                "PR": r.get("pr_number"),
                                "Success": r.get("success"),
                                "Comments": len(r.get("comments", [])),
                                "Provider": r.get("provider_used", ""),
                                "Model": r.get("model_used", ""),
                            } for r in reviews
                        ]
                        st.dataframe(pd.DataFrame(history_data), use_container_width=True)
                    else:
                        st.info("No review history yet.")
            except Exception as e:
                st.error(f"Failed to fetch history: {str(e)}")

    with col2:
        st.subheader("Recent Docs")
        if st.button("🔄 Refresh Docs", key="refresh_docs"):
            try:
                response = requests.get(f"{API_BASE_URL}/history/docs")
                if response.status_code == 200:
                    docs = response.json()
                    if docs:
                        history_data = [
                            {
                                "File": r.get("file_path"),
                                "Success": r.get("success"),
                                "Changes": r.get("changes_made", 0),
                                "Provider": r.get("provider_used", ""),
                                "Model": r.get("model_used", ""),
                            } for r in docs
                        ]
                        st.dataframe(pd.DataFrame(history_data), use_container_width=True)
                    else:
                        st.info("No doc history yet.")
            except Exception as e:
                st.error(f"Failed to fetch history: {str(e)}")
